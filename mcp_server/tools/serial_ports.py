"""Serial port listing tool."""
import json


def register(mcp, pool, **kw):
    @mcp.tool()
    def serial_list_ports() -> str:
        """列出宿主机上所有可用的串口设备。"""
        try:
            from ..transports.serial import SerialTransport
            ports = SerialTransport.list_ports()
        except Exception:
            import glob
            ports = []
            for pattern in ["/dev/ttyUSB*", "/dev/ttyACM*", "/dev/ttyS*", "/dev/ttyAMA*"]:
                for p in glob.glob(pattern):
                    ports.append({"device": p, "description": "serial port", "hwid": ""})
        return json.dumps({"success": True, "port_count": len(ports), "ports": ports}, ensure_ascii=False, indent=2)
