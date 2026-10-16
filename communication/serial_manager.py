"""
Serial communication layer for STM32L475VG UART communication.
Handles port enumeration, non-blocking background reading, thread-safe queuing,
reconnection logic, buffer management, error tracking, and graceful shutdown.
"""

import logging
import queue
import threading
import time
from datetime import datetime
from typing import List, Optional, Tuple, Dict, Any

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    serial = None  # Handled gracefully if mock or testing

from smart_lab_guardian_dashboard.communication.message_models import (
    ProtocolMessage,
    MalformedMessage,
)
from smart_lab_guardian_dashboard.communication.protocol_parser import ProtocolParser

logger = logging.getLogger("SmartLabGuardian.Serial")


class SerialConnectionState:
    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    ERROR = "ERROR"


class SerialManager:
    """
    Manages serial communication with the STM32 microcontroller.
    Runs a background daemon thread that reads lines from the UART interface,
    parses them through ProtocolParser, and places them into a thread-safe Queue.
    """

    def __init__(self, baudrate: int = 115200, timeout: float = 0.5):
        self.default_baudrate = baudrate
        self.timeout = timeout
        self.parser = ProtocolParser(source_label="HARDWARE")

        self.port: Optional[str] = None
        self.baudrate: int = baudrate
        self.state: str = SerialConnectionState.DISCONNECTED
        self.error_message: Optional[str] = None

        self._serial_handle: Optional[Any] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

        # Thread-safe message queue (bounded to prevent memory exhaustion)
        self.message_queue: queue.Queue[ProtocolMessage] = queue.Queue(maxsize=5000)

        # Communication statistics
        self.messages_received: int = 0
        self.malformed_messages: int = 0
        self.connection_errors: int = 0
        self.last_message_time: Optional[datetime] = None

    @staticmethod
    def list_available_ports() -> List[Dict[str, str]]:
        """
        Dynamically enumerates available COM ports on the system.
        Returns a list of dicts with 'port', 'description', and 'hwid'.
        """
        if serial is None:
            return []

        port_list = []
        try:
            ports = serial.tools.list_ports.comports()
            for p in ports:
                port_list.append({
                    "port": p.device,
                    "description": p.description or p.device,
                    "hwid": p.hwid or "",
                })
        except Exception as e:
            logger.warning(f"Error enumerating serial ports: {e}")

        return port_list

    def is_connected(self) -> bool:
        """Returns True if the serial port is actively open and connected."""
        with self._lock:
            return (
                self.state == SerialConnectionState.CONNECTED
                and self._serial_handle is not None
                and getattr(self._serial_handle, "is_open", False)
            )

    def connect(self, port: str, baudrate: Optional[int] = None) -> Tuple[bool, str]:
        """
        Opens connection to the specified port and launches background reader thread.
        Thread-safe and idempotent (will not launch duplicate threads).
        """
        if serial is None:
            self.state = SerialConnectionState.ERROR
            self.error_message = "PySerial library is not available"
            return False, self.error_message

        with self._lock:
            if self.state == SerialConnectionState.CONNECTED:
                if self.port == port:
                    return True, f"Already connected to {port}"
                self._disconnect_internal()

            self.port = port
            self.baudrate = baudrate or self.default_baudrate
            self.state = SerialConnectionState.CONNECTING
            self.error_message = None

            try:
                # Open serial port with 8-N-1, no flow control
                self._serial_handle = serial.Serial(
                    port=self.port,
                    baudrate=self.baudrate,
                    bytesize=serial.EIGHTBITS,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                    timeout=self.timeout,
                    xonxoff=False,
                    rtscts=False,
                    dsrdtr=False,
                )

                self._stop_event.clear()
                self._thread = threading.Thread(
                    target=self._reader_loop,
                    name=f"SerialReader-{self.port}",
                    daemon=True,
                )
                self._thread.start()

                self.state = SerialConnectionState.CONNECTED
                logger.info(f"Successfully connected to {self.port} at {self.baudrate} baud")
                return True, f"Connected to {self.port}"

            except serial.SerialException as se:
                self.connection_errors += 1
                self.error_message = f"Serial error opening {port}: {str(se)}"
                logger.error(self.error_message)
                self._disconnect_internal(target_state=SerialConnectionState.ERROR)
                return False, self.error_message

            except Exception as e:
                self.connection_errors += 1
                self.error_message = f"Unexpected error opening {port}: {str(e)}"
                logger.error(self.error_message)
                self._disconnect_internal(target_state=SerialConnectionState.ERROR)
                return False, self.error_message

    def disconnect(self) -> None:
        """Explicitly disconnects from the serial port and shuts down reader thread."""
        with self._lock:
            self._disconnect_internal()

    def _disconnect_internal(self, target_state: str = SerialConnectionState.DISCONNECTED) -> None:
        """Internal disconnect logic (assumes caller holds _lock)."""
        self._stop_event.set()

        if self._serial_handle is not None:
            try:
                if getattr(self._serial_handle, "is_open", False):
                    self._serial_handle.close()
            except Exception as e:
                logger.warning(f"Error closing serial port: {e}")
            finally:
                self._serial_handle = None

        if self._thread is not None and self._thread.is_alive():
            # Wait briefly for thread to exit
            self._thread.join(timeout=1.0)
            self._thread = None

        self.state = target_state
        logger.info(f"Disconnected from {self.port or 'serial port'} (state: {self.state})")

    def _reader_loop(self) -> None:
        """
        Dedicated background loop for non-blocking serial reading.
        Accumulates bytes into lines, parses them, and places them into the queue.
        """
        line_buffer = ""
        while not self._stop_event.is_set():
            try:
                if self._serial_handle is None or not self._serial_handle.is_open:
                    break

                # Read available bytes or up to newline
                raw_bytes = self._serial_handle.readline()
                if not raw_bytes:
                    # Timeout with no data, loop again to check stop_event
                    time.sleep(0.01)
                    continue

                try:
                    text_chunk = raw_bytes.decode("utf-8", errors="replace")
                except Exception:
                    text_chunk = raw_bytes.decode("latin1", errors="replace")

                line_buffer += text_chunk

                # Process all complete lines terminated by newline
                while "\n" in line_buffer:
                    line, line_buffer = line_buffer.split("\n", 1)
                    line = line.strip("\r")
                    if not line.strip():
                        continue

                    # Parse message
                    parsed = self.parser.parse_line(line)
                    if parsed is not None:
                        self.messages_received += 1
                        self.last_message_time = datetime.now()

                        if isinstance(parsed, MalformedMessage):
                            self.malformed_messages += 1

                        # Enqueue message (drop oldest if queue is full)
                        try:
                            self.message_queue.put_nowait(parsed)
                        except queue.Full:
                            try:
                                self.message_queue.get_nowait()
                                self.message_queue.put_nowait(parsed)
                            except Exception:
                                pass

            except serial.SerialException as se:
                logger.error(f"Serial read exception: {se}")
                self.connection_errors += 1
                self.state = SerialConnectionState.ERROR
                self.error_message = f"Hardware disconnected or read error: {str(se)}"
                break

            except Exception as e:
                logger.error(f"Unexpected reader loop error: {e}")
                self.connection_errors += 1
                self.state = SerialConnectionState.ERROR
                self.error_message = str(e)
                break

        # Cleanup if reader exited due to error
        with self._lock:
            if self._serial_handle is not None and getattr(self._serial_handle, "is_open", False):
                try:
                    self._serial_handle.close()
                except Exception:
                    pass
                self._serial_handle = None
            if self.state != SerialConnectionState.ERROR:
                self.state = SerialConnectionState.DISCONNECTED

    def get_messages(self, max_messages: int = 100) -> List[ProtocolMessage]:
        """
        Drains up to max_messages from the incoming thread-safe queue.
        Non-blocking.
        """
        messages = []
        count = 0
        while count < max_messages:
            try:
                msg = self.message_queue.get_nowait()
                messages.append(msg)
                count += 1
            except queue.Empty:
                break
        return messages

    def get_stats(self) -> Dict[str, Any]:
        """Returns snapshot of connection statistics."""
        return {
            "state": self.state,
            "port": self.port,
            "baudrate": self.baudrate,
            "error_message": self.error_message,
            "messages_received": self.messages_received,
            "malformed_messages": self.malformed_messages,
            "connection_errors": self.connection_errors,
            "last_message_time": self.last_message_time,
            "queue_size": self.message_queue.qsize(),
        }
