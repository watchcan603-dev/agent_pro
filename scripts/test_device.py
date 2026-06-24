#!/usr/bin/env python3
"""Quick test: connect to a device and show system info."""

import sys
import os

# Add parent to path so we can import mcp_server
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp_server.device_registry import DeviceRegistry
from mcp_server.connection_pool import ConnectionPool


def main():
    r = DeviceRegistry()
    devices = r.list_all()

    if not devices:
        print("No devices configured. Edit mcp_server/devices.json first.")
        sys.exit(1)

    print("Available devices:")
    for i, d in enumerate(devices):
        print(f"  [{i}] {d.id}: {d.name} @ {d.host}:{d.port}")

    # Use first device or specified device
    if len(sys.argv) > 1:
        device_id = sys.argv[1]
    else:
        device_id = devices[0].id

    device = r.get(device_id)
    if not device:
        print(f"Device not found: {device_id}")
        sys.exit(1)

    print(f"\nConnecting to {device.name} ({device.host})...")
    pool = ConnectionPool()

    try:
        session = pool.create_session(device)
        sid = session.session_id
        print(f"Session: {sid}")

        # System info
        print("\n--- System Info ---")
        for cmd, label in [
            ("uname -a", "Kernel"),
            ("cat /proc/cpuinfo | grep -E 'model name|Processor|Hardware|CPU architecture' | head -3", "CPU"),
            ("free -h | head -2", "Memory"),
            ("df -h / | tail -1", "Disk"),
        ]:
            result = pool.exec_on_session(sid, cmd, timeout=5)
            print(f"[{label}]")
            print(result.stdout.strip())
            print()

        pool.remove_session(sid)
        print("Test complete!")

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
