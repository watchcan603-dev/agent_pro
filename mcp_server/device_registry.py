"""Device registry — reads and queries the device configuration file."""

import json
import os
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field


@dataclass
class DeviceInfo:
    """Information about a registered device."""
    id: str
    name: str
    host: str
    type: str
    port: int
    username: str = "root"
    password: Optional[str] = None
    key_path: Optional[str] = None
    baudrate: int = 115200
    tags: List[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "id": self.id,
            "name": self.name,
            "host": self.host,
            "type": self.type,
            "port": self.port,
            "username": self.username,
            "tags": self.tags,
            "notes": self.notes,
        }
        if self.password:
            d["auth"] = {"method": "password", "password": "***"}
        if self.key_path:
            d["auth"] = {"method": "key", "key_path": self.key_path}
        if self.type in ("serial-tcp",):
            d["baudrate"] = self.baudrate
        return d

    def to_list_item(self) -> Dict[str, Any]:
        """Return a compact representation for device listing."""
        return {
            "id": self.id,
            "name": self.name,
            "host": self.host,
            "type": self.type,
            "port": self.port,
            "tags": self.tags,
            "notes": self.notes,
        }


class DeviceRegistry:
    """Manages the device configuration file and provides lookup methods."""

    def __init__(self, config_path: Optional[str] = None):
        if config_path is None:
            config_path = os.path.join(os.path.dirname(__file__), "devices.json")
        self._config_path = config_path
        self._devices: Dict[str, DeviceInfo] = {}
        self._load()

    def _load(self) -> None:
        """Load devices from the JSON configuration file."""
        if not os.path.exists(self._config_path):
            raise FileNotFoundError(f"Device config not found: {self._config_path}")

        with open(self._config_path, "r") as f:
            data = json.load(f)

        self._devices = {}
        for item in data.get("devices", []):
            auth = item.get("auth", {})
            device = DeviceInfo(
                id=item["id"],
                name=item.get("name", item["id"]),
                host=item["host"],
                type=item.get("type", "ssh"),
                port=item.get("port", 22),
                username=item.get("username", "root"),
                password=auth.get("password") if auth.get("method") == "password" else None,
                key_path=auth.get("key_path") if auth.get("method") == "key" else None,
                baudrate=item.get("baudrate", 115200),
                tags=item.get("tags", []),
                notes=item.get("notes", ""),
            )
            self._devices[device.id] = device

    def list_all(self) -> List[DeviceInfo]:
        """Return all registered devices."""
        return list(self._devices.values())

    def get(self, device_id: str) -> Optional[DeviceInfo]:
        """Get a device by ID. Supports partial match (prefix)."""
        # Exact match first
        if device_id in self._devices:
            return self._devices[device_id]
        # Prefix match
        for did, dev in self._devices.items():
            if did.startswith(device_id):
                return dev
        return None

    def find_by_tag(self, tag: str) -> List[DeviceInfo]:
        """Find devices matching a tag."""
        return [d for d in self._devices.values() if tag in d.tags]

    def find_by_host(self, host: str) -> Optional[DeviceInfo]:
        """Find a device by host address."""
        for dev in self._devices.values():
            if dev.host == host:
                return dev
        return None

    @property
    def device_count(self) -> int:
        return len(self._devices)
