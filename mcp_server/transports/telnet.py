"""Telnet transport — for serial servers, switch consoles, and debug ports."""

import re
import socket
import time
from typing import Optional

from .base import BaseTransport, TransportConfig, ExecResult


class TelnetTransport(BaseTransport):
    """Telnet transport for connecting to serial servers or debug consoles.

    Supports login (username/password) and shell-based command execution
    using echo markers to delimit command output.

    Connection flow:
        1. TCP connect
        2. Wait for login prompt → send username
        3. Wait for password prompt → send password
        4. Wait for shell prompt → ready for commands
    """

    # Default prompt patterns for common embedded Linux systems
    DEFAULT_LOGIN_PROMPTS = [rb"login:", rb"Login:", rb"user:", rb"Username:"]
    DEFAULT_PASSWORD_PROMPTS = [rb"Password:", rb"password:", rb"Passwd:"]
    DEFAULT_SHELL_PROMPTS = [
        rb"# ", rb"$ ", rb"#\r", rb"$\r",
        rb"~ # ", rb"~ $ ",
        rb"root@", rb"admin@",
    ]

    ECHO_START = b"__EMBED_CMD_BEGIN__"
    ECHO_END = b"__EMBED_CMD_END__"

    def __init__(self, config: TransportConfig):
        super().__init__(config)
        self._socket: Optional[socket.socket] = None
        self._buffer = b""
        self._logged_in = False

    def connect(self) -> None:
        """Establish telnet connection and login."""
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.settimeout(10)

        try:
            self._socket.connect((self.config.host, self.config.port))
        except (socket.timeout, ConnectionRefusedError, OSError) as e:
            self._socket.close()
            self._socket = None
            raise ConnectionError(f"Telnet connection failed: {e}") from e

        # Try login if username is configured
        if self.config.username:
            self._login()
        else:
            # No login needed (e.g., already at a shell after reboot)
            self._logged_in = True

        self._connected = True

    def _login(self) -> None:
        """Perform telnet login sequence."""
        # Wait for login prompt
        self._expect_any(self.DEFAULT_LOGIN_PROMPTS, timeout=15,
                         error_msg="No login prompt received")

        # Send username
        self._send_line(self.config.username)
        time.sleep(0.3)

        # Wait for password prompt (optional — some systems skip if no password set)
        if self.config.password:
            try:
                self._expect_any(self.DEFAULT_PASSWORD_PROMPTS, timeout=5,
                                 error_msg="No password prompt")
            except ConnectionError:
                # Some systems don't show password prompt if password is empty
                pass
            else:
                self._send_line(self.config.password)
                time.sleep(0.5)

        # Wait for shell prompt
        self._expect_any(self.DEFAULT_SHELL_PROMPTS, timeout=10,
                         error_msg="No shell prompt after login")
        self._logged_in = True

    def exec_command(self, command: str, timeout: int = 30) -> ExecResult:
        """Execute a command using echo markers for output delimiting.

        Pattern:
            echo __EMBED_CMD_BEGIN__
            <actual command>
            echo __EMBED_CMD_END__:$?
        """
        if not self._socket or not self._connected:
            raise RuntimeError("Telnet transport not connected")

        # Clear stale buffer before sending command
        self._drain_buffer()

        # Build delimited command
        full_cmd = (
            f"echo {self.ECHO_START.decode()} && "
            f"({command}) 2>&1; "
            f"_ec=$?; echo {self.ECHO_END.decode()}:$_ec"
        )
        self._send_line(full_cmd)

        # Read until we see the end marker
        try:
            raw = self._read_until(
                self.ECHO_END, timeout=timeout,
                error_msg=f"Command timed out after {timeout}s",
            )
        except ConnectionError as e:
            return ExecResult(stdout="", stderr=str(e), exit_code=-1)

        # Parse: everything between BEGIN and END is command output
        raw_str = raw.decode("utf-8", errors="replace")

        # Extract exit code from END marker
        exit_code = 0
        end_pattern = re.compile(rf"{self.ECHO_END.decode()}[:-]?(\d+)")
        end_match = end_pattern.search(raw_str)
        if end_match:
            try:
                exit_code = int(end_match.group(1))
            except ValueError:
                pass

        # Extract output between BEGIN and END
        begin_marker = self.ECHO_START.decode()
        end_marker = self.ECHO_END.decode()

        output = ""
        begin_idx = raw_str.find(begin_marker)
        end_idx = raw_str.find(end_marker)

        if begin_idx >= 0 and end_idx >= 0:
            # Get content after BEGIN marker (skip the echo line itself)
            after_begin = raw_str[begin_idx + len(begin_marker):]
            # Find end marker in remaining
            end_in_remainder = after_begin.find(end_marker)
            if end_in_remainder >= 0:
                output = after_begin[:end_in_remainder]

        # Clean up: remove the command echo line if present
        lines = output.split("\n")
        # First line is often the echoed command itself, remove it
        cleaned_lines = []
        skip_next = False
        for line in lines:
            stripped = line.strip()
            if self.ECHO_START.decode() in stripped:
                continue
            if command.strip() in stripped and not skip_next:
                skip_next = True
                continue
            cleaned_lines.append(line)
        output = "\n".join(cleaned_lines).strip()

        return ExecResult(stdout=output, stderr="", exit_code=exit_code)

    def close(self) -> None:
        """Close the telnet connection."""
        if self._socket:
            try:
                self._socket.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                self._socket.close()
            except Exception:
                pass
            self._socket = None
        self._connected = False
        self._logged_in = False

    def get_transport_type(self) -> str:
        return "telnet"

    # ── Interactive session ───────────────────────────────────────────────────

    def open_interactive(self, command: str) -> None:
        """Launch an interactive program over the telnet session."""
        if self._interactive_mode:
            raise RuntimeError("Interactive session already active")
        self._drain_buffer()
        self._send_line(command)
        self._interactive_mode = True

    def send_interactive(self, data: str) -> None:
        """Send raw data to the interactive session."""
        if not self._connected:
            raise RuntimeError("Not connected")
        self._socket.sendall(data.encode("utf-8"))

    def recv_interactive(self, marker: str, timeout: int = 30) -> str:
        """Read until marker is found."""
        return self._read_until(marker.encode("utf-8"), timeout).decode("utf-8", errors="replace")

    def close_interactive(self) -> None:
        """Close interactive session."""
        self._interactive_mode = False

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _drain_buffer(self) -> None:
        """Clear any stale data in the receive buffer."""
        self._buffer = b""
        try:
            self._socket.settimeout(0.1)
            while True:
                data = self._socket.recv(4096)
                if not data:
                    break
        except socket.timeout:
            pass

    def _send_line(self, text: str) -> None:
        """Send text + CRLF."""
        data = text.encode("utf-8") + b"\r\n"
        self._socket.sendall(data)

    def _recv(self, timeout: float = 1.0) -> bytes:
        """Receive available data with timeout."""
        self._socket.settimeout(timeout)
        try:
            data = self._socket.recv(4096)
            if not data:
                raise ConnectionError("Connection closed by remote")
            self._buffer += data
            return data
        except socket.timeout:
            return b""

    def _expect_any(self, patterns: list[bytes], timeout: float = 10,
                    error_msg: str = "Timed out waiting for prompt") -> bytes:
        """Read until one of the patterns matches in buffer. Returns matched data."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            remaining = deadline - time.time()
            self._recv(timeout=min(remaining, 0.5))
            for pat in patterns:
                if pat in self._buffer:
                    # Don't consume the match — caller may need it
                    return self._buffer
        raise ConnectionError(error_msg)

    def _read_until(self, marker: bytes, timeout: float = 30,
                    error_msg: str = "Timed out") -> bytes:
        """Read until marker is found in buffer."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            remaining = deadline - time.time()
            self._recv(timeout=min(remaining, 0.5))
            if marker in self._buffer:
                return self._buffer
        raise ConnectionError(error_msg)
