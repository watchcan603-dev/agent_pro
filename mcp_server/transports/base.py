"""Base transport interface for device connections."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ExecResult:
    """Result of a command execution on a remote device."""
    stdout: str
    stderr: str
    exit_code: int


@dataclass
class TransportConfig:
    """Configuration for establishing a transport connection."""
    host: str
    port: int = 22
    username: str = "root"
    password: Optional[str] = None
    key_path: Optional[str] = None
    # For serial/telnet
    baudrate: int = 115200


@dataclass
class SessionInfo:
    """Information about an active session."""
    session_id: str
    device_id: str
    transport_type: str
    connected_at: float = 0.0
    last_used: float = 0.0


class BaseTransport(ABC):
    """Abstract transport for remote device communication.

    Each concrete transport (SSH, Telnet, Serial-TCP) implements
    the connect / exec / close lifecycle.
    """

    def __init__(self, config: TransportConfig):
        self.config = config
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    @abstractmethod
    def connect(self) -> None:
        """Establish connection to the remote device."""
        ...

    @abstractmethod
    def exec_command(self, command: str, timeout: int = 30) -> ExecResult:
        """Execute a shell command and return its output."""
        ...

    @abstractmethod
    def close(self) -> None:
        """Close the connection."""
        ...

    @abstractmethod
    def get_transport_type(self) -> str:
        """Return transport type identifier (ssh, telnet, serial-tcp)."""
        ...

    def upload_file(self, local_path: str, remote_path: str) -> None:
        """Upload a file to the remote device. Override in subclasses."""
        raise NotImplementedError("File upload not supported for this transport")

    def download_file(self, remote_path: str, local_path: str) -> None:
        """Download a file from the remote device. Override in subclasses."""
        raise NotImplementedError("File download not supported for this transport")

    # ── Interactive session support (GDB, etc.) ───────────────────────────────

    _interactive_mode: bool = False

    @property
    def interactive_active(self) -> bool:
        """Whether an interactive session (e.g., GDB) is currently running."""
        return self._interactive_mode

    def open_interactive(self, command: str) -> None:
        """Launch an interactive program that takes over the transport.

        After calling this, the transport is dedicated to the interactive
        process. Use send_interactive / recv_interactive to communicate.
        exec_command is blocked until close_interactive() is called.

        Args:
            command: The command to launch (e.g., 'gdb -q /path/to/binary').
        """
        raise NotImplementedError(
            f"Interactive mode not supported for {self.get_transport_type()} transport"
        )

    def send_interactive(self, data: str) -> None:
        """Send raw data to the interactive session."""
        raise NotImplementedError(
            f"Interactive mode not supported for {self.get_transport_type()} transport"
        )

    def recv_interactive(self, marker: str, timeout: int = 30) -> str:
        """Read from interactive session until marker string is found.

        Returns all data received up to and including the marker.
        """
        raise NotImplementedError(
            f"Interactive mode not supported for {self.get_transport_type()} transport"
        )

    def close_interactive(self) -> None:
        """Terminate the interactive program and restore normal transport mode."""
        raise NotImplementedError(
            f"Interactive mode not supported for {self.get_transport_type()} transport"
        )

    def heartbeat(self) -> bool:
        """Check if the connection is still alive. Default: run 'echo ok'."""
        try:
            result = self.exec_command("echo ok", timeout=5)
            return result.stdout.strip() == "ok" and result.exit_code == 0
        except Exception:
            return False
