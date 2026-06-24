"""Serial transport — direct COM port connection via pyserial.

For connecting to embedded device UART consoles through USB-to-serial
adapters (/dev/ttyUSB0, /dev/ttyACM0, etc.) or built-in COM ports.

Uses echo-marker pattern for command execution, same as Telnet transport.
"""

import re
import time
from typing import Optional

import serial
import serial.tools.list_ports

from .base import BaseTransport, TransportConfig, ExecResult


class SerialTransport(BaseTransport):
    """Serial/UART transport for direct COM port connections.

    Opens a local serial port (e.g., /dev/ttyUSB0, COM3) and provides
    shell-based command execution via echo markers.

    Typical use case: USB-to-TTL adapter connected to the device's debug UART,
    giving access to the Linux console or U-Boot prompt.
    """

    ECHO_START = b"__EMBED_CMD_BEGIN__"
    ECHO_END = b"__EMBED_CMD_END__"

    def __init__(self, config: TransportConfig):
        super().__init__(config)
        self._serial: Optional[serial.Serial] = None

    # Default prompt patterns for serial console login
    DEFAULT_LOGIN_PROMPTS = [rb"login:", rb"Login:", rb"user:", rb"Username:"]
    DEFAULT_PASSWORD_PROMPTS = [rb"Password:", rb"password:"]
    DEFAULT_SHELL_PROMPTS = [rb"# ", rb"$ ", rb"~ # ", rb"~ $ "]

    def connect(self) -> None:
        """Open the serial port and optionally perform login."""
        try:
            self._serial = serial.Serial(
                port=self.config.host,  # host field holds the device path
                baudrate=self.config.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=0.5,
                write_timeout=5,
            )
        except serial.SerialException as e:
            raise ConnectionError(f"Serial open failed ({self.config.host}): {e}") from e

        # Flush any stale data
        self._serial.reset_input_buffer()
        self._serial.reset_output_buffer()

        # Perform login if username is configured
        if self.config.username:
            self._login()

        self._connected = True

    def _login(self) -> None:
        """Perform serial console login sequence.

        Strategy:
          1. Check if we're already at a shell prompt (device was already logged in)
          2. Read any banner/login prompt the device may have already sent
          3. If we see a login prompt, proceed with login
          4. If nothing, send newline to wake up the console
        """
        # First, check for existing data (banner, prompt, or already-logged-in shell)
        time.sleep(0.3)
        initial = self._recv(timeout=0.5)

        # Already at shell?
        for pat in self.DEFAULT_SHELL_PROMPTS:
            if pat in initial:
                return

        # Already showing login prompt?
        saw_login = False
        for pat in self.DEFAULT_LOGIN_PROMPTS:
            if pat in initial:
                saw_login = True
                break

        if not saw_login:
            # Send newline to wake up console
            self._send_line("")
            time.sleep(0.5)

        # Wait for login prompt
        try:
            self._expect_any(self.DEFAULT_LOGIN_PROMPTS, timeout=8,
                             error_msg="No login prompt on serial console")
        except ConnectionError:
            # Maybe already at shell?
            try:
                self._expect_any(self.DEFAULT_SHELL_PROMPTS, timeout=2)
                return
            except ConnectionError:
                pass
            raise ConnectionError(
                "No login or shell prompt on serial console. "
                "Check baudrate, wiring, and that the device is powered on."
            )

        # Send username
        self._send_line(self.config.username)
        time.sleep(0.5)

        # Wait for password prompt
        if self.config.password:
            try:
                self._expect_any(self.DEFAULT_PASSWORD_PROMPTS, timeout=8,
                                 error_msg="No password prompt")
            except ConnectionError:
                # Some systems skip password prompt
                pass
            else:
                self._send_line(self.config.password)
                time.sleep(0.5)

        # Wait for shell prompt
        self._expect_any(self.DEFAULT_SHELL_PROMPTS, timeout=10,
                         error_msg="No shell prompt after login. Check credentials.")

    def exec_command(self, command: str, timeout: int = 30) -> ExecResult:
        """Execute a command via the serial console.

        Uses echo markers to precisely delimit command output:
            echo __EMBED_CMD_BEGIN__
            <actual command>
            echo __EMBED_CMD_END__:$?

        This works with both Linux shell and U-Boot console.
        """
        if not self._serial or not self._connected:
            raise RuntimeError("Serial transport not connected")

        # Build delimited command — works for both Linux shell and U-Boot
        full_cmd = (
            f"echo {self.ECHO_START.decode()} && "
            f"({command}) 2>&1; "
            f"_ec=$?; echo {self.ECHO_END.decode()}:$_ec"
        )

        self._send_line(full_cmd)

        try:
            raw = self._read_until(self.ECHO_END, timeout=timeout)
        except ConnectionError as e:
            return ExecResult(stdout="", stderr=str(e), exit_code=-1)

        raw_str = raw.decode("utf-8", errors="replace")

        # Extract exit code
        exit_code = 0
        end_pattern = re.compile(rf"{self.ECHO_END.decode()}[:-]?(\d+)")
        end_match = end_pattern.search(raw_str)
        if end_match:
            try:
                exit_code = int(end_match.group(1))
            except ValueError:
                pass

        # Extract output between BEGIN and END markers
        output = self._extract_between_markers(
            raw_str,
            self.ECHO_START.decode(),
            self.ECHO_END.decode(),
            command,
        )

        return ExecResult(stdout=output, stderr="", exit_code=exit_code)

    def close(self) -> None:
        """Close the serial port."""
        if self._serial:
            try:
                self._serial.close()
            except Exception:
                pass
            self._serial = None
        self._connected = False

    def get_transport_type(self) -> str:
        return "serial"

    @staticmethod
    def list_ports() -> list[dict]:
        """List available serial ports on the host."""
        ports = []
        for p in serial.tools.list_ports.comports():
            ports.append({
                "device": p.device,
                "description": p.description,
                "hwid": p.hwid,
                "manufacturer": p.manufacturer,
                "product": p.product,
            })
        return ports

    # ── Interactive session ───────────────────────────────────────────────────

    def open_interactive(self, command: str) -> None:
        """Launch an interactive program over the serial connection."""
        if self._interactive_mode:
            raise RuntimeError("Interactive session already active")
        self._send_line(command)
        time.sleep(0.3)
        self._interactive_mode = True

    def send_interactive(self, data: str) -> None:
        """Send raw data to the interactive session."""
        if not self._serial or not self._connected:
            raise RuntimeError("Serial transport not connected")
        self._serial.write(data.encode("utf-8"))
        self._serial.flush()
        time.sleep(0.05)

    def recv_interactive(self, marker: str, timeout: int = 30) -> str:
        """Read until marker is found."""
        raw = self._read_until(marker.encode("utf-8"), timeout)
        return raw.decode("utf-8", errors="replace")

    def close_interactive(self) -> None:
        """Close interactive session."""
        self._interactive_mode = False

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _send_line(self, text: str) -> None:
        """Send text + CR+LF (works for both Linux and bootloader consoles)."""
        data = text.encode("utf-8") + b"\r\n"
        self._serial.write(data)
        self._serial.flush()

    def _recv(self, timeout: float = 0.5) -> bytes:
        """Receive available data with timeout."""
        self._serial.timeout = timeout
        try:
            chunk = self._serial.read(4096)
            return chunk
        except serial.SerialException:
            return b""

    def _expect_any(self, patterns: list[bytes], timeout: float = 10,
                    error_msg: str = "Timed out waiting for pattern") -> bytes:
        """Read until one of the patterns matches. Returns accumulated data."""
        deadline = time.time() + timeout
        buffer = b""
        while time.time() < deadline:
            remaining = deadline - time.time()
            chunk = self._recv(timeout=min(remaining, 0.3))
            if chunk:
                buffer += chunk
                for pat in patterns:
                    if pat in buffer:
                        return buffer
            else:
                time.sleep(0.05)
        raise ConnectionError(error_msg)

    def _read_until(self, marker: bytes, timeout: float = 30) -> bytes:
        """Read from serial until marker is found or timeout."""
        deadline = time.time() + timeout
        buffer = b""

        while time.time() < deadline:
            remaining = deadline - time.time()
            self._serial.timeout = min(remaining, 0.3)

            try:
                chunk = self._serial.read(4096)
            except serial.SerialException:
                chunk = b""

            if chunk:
                buffer += chunk
                if marker in buffer:
                    return buffer

            if not chunk:
                time.sleep(0.05)

        raise ConnectionError(f"Serial read timed out after {timeout}s (marker not found)")

    def _extract_between_markers(self, raw: str, begin: str, end: str,
                                  command: str) -> str:
        """Extract command output from between the echo markers."""
        begin_idx = raw.find(begin)
        end_idx = raw.find(end)

        if begin_idx < 0 or end_idx < 0:
            return raw.strip()

        # Get everything between the two markers
        between = raw[begin_idx + len(begin):end_idx]

        # Clean up: remove the echoed command line
        lines = between.split("\n")
        cleaned = []
        cmd_stripped = command.strip()
        for line in lines:
            # Skip lines that are the echoed command itself
            if cmd_stripped and cmd_stripped in line:
                continue
            if begin in line:
                continue
            cleaned.append(line)

        return "\n".join(cleaned).strip()
