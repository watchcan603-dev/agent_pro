"""Session dataclass — represents an active device connection."""
import time
from dataclasses import dataclass, field
from ..transports.base import BaseTransport


@dataclass
class Session:
    """An active connection session to a remote device."""
    session_id: str
    device_id: str
    transport: BaseTransport
    created_at: float = field(default_factory=time.time)
    last_used: float = field(default_factory=time.time)

    def touch(self) -> None:
        self.last_used = time.time()

    @property
    def idle_seconds(self) -> float:
        return time.time() - self.last_used
