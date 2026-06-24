"""SSH transport implementation using paramiko."""

import os
import logging
import time
from typing import Optional

import paramiko
from paramiko import SSHClient, AutoAddPolicy
from scp import SCPClient

# Suppress paramiko transport logs
logging.getLogger("paramiko.transport").setLevel(logging.WARNING)

from .base import BaseTransport, TransportConfig, ExecResult


class SSHTransport(BaseTransport):
    """SSH transport for connecting to Linux-based embedded devices."""

    def __init__(self, config: TransportConfig):
        super().__init__(config)
        self._client: Optional[SSHClient] = None
        self._scp: Optional[SCPClient] = None
        self._interactive_channel = None

    def connect(self) -> None:
        """Establish SSH connection using password or key authentication."""
        self._client = SSHClient()
        self._client.set_missing_host_key_policy(AutoAddPolicy())

        connect_kwargs = {
            "hostname": self.config.host,
            "port": self.config.port,
            "username": self.config.username,
            "timeout": 10,
            "banner_timeout": 10,
            "auth_timeout": 10,
        }

        if self.config.key_path:
            expanded_path = os.path.expanduser(self.config.key_path)
            if os.path.exists(expanded_path):
                connect_kwargs["key_filename"] = expanded_path
            else:
                raise FileNotFoundError(f"SSH key not found: {expanded_path}")

        if self.config.password:
            connect_kwargs["password"] = self.config.password

        self._client.connect(**connect_kwargs)

        # Set up SCP client for file transfers
        self._scp = SCPClient(self._client.get_transport())

        self._connected = True

    def exec_command(self, command: str, timeout: int = 30) -> ExecResult:
        """Execute a command on the remote device via SSH."""
        if not self._client or not self._connected:
            raise RuntimeError("SSH transport not connected")

        stdin, stdout, stderr = self._client.exec_command(command, timeout=timeout)

        # Set channel timeout for long-running reads
        stdout.channel.settimeout(timeout)

        # Read output before checking exit status
        stdout_str = stdout.read().decode("utf-8", errors="replace")
        stderr_str = stderr.read().decode("utf-8", errors="replace")
        exit_code = stdout.channel.recv_exit_status()

        return ExecResult(stdout=stdout_str, stderr=stderr_str, exit_code=exit_code)

    def upload_file(self, local_path: str, remote_path: str) -> None:
        """Upload a file to the remote device via SCP."""
        if not self._scp or not self._connected:
            raise RuntimeError("SSH transport not connected")
        self._scp.put(local_path, remote_path)

    def download_file(self, remote_path: str, local_path: str) -> None:
        """Download a file from the remote device via SCP."""
        if not self._scp or not self._connected:
            raise RuntimeError("SSH transport not connected")
        self._scp.get(remote_path, local_path)

    def close(self) -> None:
        """Close the SSH connection."""
        if self._scp:
            try:
                self._scp.close()
            except Exception:
                pass
            self._scp = None

        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None

        self._connected = False

    def get_transport_type(self) -> str:
        return "ssh"

    # ── Interactive session (GDB over SSH) ────────────────────────────────────

    def open_interactive(self, command: str) -> None:
        """Launch an interactive command via a persistent SSH exec channel.

        Opens a dedicated SSH channel that stays alive for the duration
        of the interactive session. The channel's stdin/stdout are connected
        directly to the remote process (no shell wrapper).

        Args:
            command: e.g. 'gdb -q /path/to/binary'
        """
        if not self._client or not self._connected:
            raise RuntimeError("SSH transport not connected")
        if self._interactive_channel:
            raise RuntimeError("Interactive session already active")

        transport = self._client.get_transport()
        channel = transport.open_session()
        channel.get_pty()  # Needed for GDB's interactive output
        channel.exec_command(command)
        channel.settimeout(1.0)

        self._interactive_channel = channel
        self._interactive_mode = True

    def send_interactive(self, data: str) -> None:
        """Send raw data to the interactive session's stdin."""
        if not self._interactive_channel:
            raise RuntimeError("No interactive session active")
        self._interactive_channel.send(data.encode("utf-8"))
        # Small delay to let the remote process receive and echo
        import time
        time.sleep(0.05)

    def recv_interactive(self, marker: str, timeout: int = 30) -> str:
        """Read from interactive session until marker string is found.

        Args:
            marker: String to wait for (e.g., '(gdb)' for GDB prompt).
            timeout: Maximum seconds to wait.

        Returns:
            All data received up to and including the marker.

        Raises:
            TimeoutError: If marker is not seen within timeout.
        """
        if not self._interactive_channel:
            raise RuntimeError("No interactive session active")

        import time
        deadline = time.time() + timeout
        buffer = b""
        marker_bytes = marker.encode("utf-8")

        self._interactive_channel.settimeout(0.3)

        while time.time() < deadline:
            try:
                chunk = self._interactive_channel.recv(4096)
                if chunk:
                    buffer += chunk
                    if marker_bytes in buffer:
                        return buffer.decode("utf-8", errors="replace")
                else:
                    time.sleep(0.05)
            except Exception:
                # Timeout on recv, just retry
                time.sleep(0.05)

            if time.time() >= deadline:
                break

        raise TimeoutError(
            f"Interactive recv timed out after {timeout}s waiting for {marker!r}. "
            f"Received so far: {buffer[-200:].decode('utf-8', errors='replace')}"
        )

    def close_interactive(self) -> None:
        """Close the interactive channel and restore normal mode."""
        if self._interactive_channel:
            try:
                self._interactive_channel.close()
            except Exception:
                pass
            self._interactive_channel = None
        self._interactive_mode = False

    def heartbeat(self) -> bool:
        """Check SSH connection is alive."""
        if self._interactive_mode:
            return self._client is not None and self._connected
        return super().heartbeat()
