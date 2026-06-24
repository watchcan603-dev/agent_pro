"""Connection pool — manages active device transport sessions."""

import uuid
from typing import Dict, Optional

from ..transports.base import TransportConfig, ExecResult
from ..transports.ssh import SSHTransport
from ..transports.telnet import TelnetTransport
from ..transports.serial import SerialTransport
from ..device_registry import DeviceInfo
from .session import Session
from .gdb_session import GdbSession


class ConnectionPool:
    """Manages device transport sessions, GDB mode, and file transfers."""

    IDLE_TIMEOUT = 300

    def __init__(self):
        self._sessions: Dict[str, Session] = {}
        self._gdb_sessions: Dict[str, GdbSession] = {}

    @staticmethod
    def _create_transport(device: DeviceInfo):
        """Factory: create the right transport for a device type."""
        config = TransportConfig(
            host=device.host, port=device.port,
            username=device.username, password=device.password,
            key_path=device.key_path, baudrate=device.baudrate,
        )
        t = device.type.lower()
        if t == "ssh":    return SSHTransport(config)
        if t == "telnet": return TelnetTransport(config)
        if t in ("serial", "serial-tcp", "serial_tcp"): return SerialTransport(config)
        raise ValueError(f"Unsupported transport type: {device.type}")

    # ── Session lifecycle ────────────────────────────────────────

    def create_session(self, device: DeviceInfo) -> Session:
        transport = self._create_transport(device)
        transport.connect()
        s = Session(session_id=str(uuid.uuid4())[:8], device_id=device.id, transport=transport)
        self._sessions[s.session_id] = s
        return s

    def get_session(self, session_id: str) -> Optional[Session]:
        return self._sessions.get(session_id)

    def remove_session(self, session_id: str) -> bool:
        self.stop_gdb(session_id)
        s = self._sessions.pop(session_id, None)
        if s:
            try: s.transport.close()
            except Exception: pass
            return True
        return False

    # ── Execution ───────────────────────────────────────────────

    def exec_on_session(self, session_id: str, command: str, timeout: int = 30) -> ExecResult:
        s = self.get_session(session_id)
        if not s: raise ValueError(f"Session not found: {session_id}")
        if self.is_gdb_active(session_id):
            raise RuntimeError(f"GDB active on {session_id}. Use gdb_close first.")
        s.touch()
        return s.transport.exec_command(command, timeout=timeout)

    def upload_via_session(self, session_id: str, local_path: str, remote_path: str):
        s = self.get_session(session_id)
        if not s: raise ValueError(f"Session not found: {session_id}")
        s.touch()
        s.transport.upload_file(local_path, remote_path)

    def download_via_session(self, session_id: str, remote_path: str, local_path: str):
        s = self.get_session(session_id)
        if not s: raise ValueError(f"Session not found: {session_id}")
        s.touch()
        s.transport.download_file(remote_path, local_path)

    # ── GDB ──────────────────────────────────────────────────────

    def start_gdb(self, session_id: str, binary_path: str, args: str = "") -> str:
        s = self.get_session(session_id)
        if not s: raise ValueError(f"Session not found: {session_id}")
        if session_id in self._gdb_sessions:
            raise RuntimeError(f"GDB already active on {session_id}")
        try:
            gdb = GdbSession()
            out = gdb.launch(s.transport, binary_path, args)
            self._gdb_sessions[session_id] = gdb
            s.touch()
            return out
        except Exception:
            self._gdb_sessions.pop(session_id, None)
            raise

    def gdb_exec(self, session_id: str, command: str, timeout: int = 30) -> str:
        gdb = self._gdb_sessions.get(session_id)
        if not gdb: raise RuntimeError(f"No GDB on {session_id}. Use gdb_launch first.")
        s = self._sessions.get(session_id)
        if s: s.touch()
        return gdb.exec_cmd(command, timeout=timeout)

    def stop_gdb(self, session_id: str) -> str:
        gdb = self._gdb_sessions.pop(session_id, None)
        return gdb.close() if gdb else ""

    def is_gdb_active(self, session_id: str) -> bool:
        gdb = self._gdb_sessions.get(session_id)
        return gdb is not None and gdb.is_active

    def get_gdb_info(self, session_id: str) -> Optional[dict]:
        gdb = self._gdb_sessions.get(session_id)
        if not gdb or not gdb.is_active: return None
        return {"binary_path": gdb.binary_path, "breakpoints": gdb.breakpoints}

    # ── Housekeeping ───────────────────────────────────────────

    def list_sessions(self) -> list:
        return [{
            "session_id": s.session_id, "device_id": s.device_id,
            "transport_type": s.transport.get_transport_type(),
            "idle_seconds": round(s.idle_seconds, 1),
            "gdb_active": self.is_gdb_active(sid),
        } for sid, s in self._sessions.items()]

    def cleanup_idle(self) -> int:
        return sum(1 for sid in [k for k, s in self._sessions.items()
                   if s.idle_seconds > self.IDLE_TIMEOUT] if self.remove_session(sid))

    def disconnect_all(self):
        for sid in list(self._sessions.keys()): self.remove_session(sid)

    @property
    def active_count(self) -> int:
        return len(self._sessions)
