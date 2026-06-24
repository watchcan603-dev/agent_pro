"""Connection management tools."""
import json


def register(mcp, pool, registry=None, **kw):
    @mcp.tool()
    def device_list() -> str:
        """列出所有已注册的嵌入式设备。"""
        devices = registry.list_all()
        return json.dumps({
            "count": len(devices),
            "devices": [d.to_list_item() for d in devices],
        }, ensure_ascii=False, indent=2)

    @mcp.tool()
    def device_connect(device_id: str) -> str:
        """连接到指定的嵌入式设备。返回 session_id 用于后续操作。"""
        device = registry.get(device_id)
        if not device:
            return json.dumps({
                "success": False, "error": f"Device not found: '{device_id}'",
                "available_devices": [d.id for d in registry.list_all()],
            }, ensure_ascii=False, indent=2)
        try:
            session = pool.create_session(device)
            return json.dumps({
                "success": True, "session_id": session.session_id,
                "device_id": device.id, "device_name": device.name,
                "host": device.host,
                "transport_type": session.transport.get_transport_type(),
            }, ensure_ascii=False, indent=2)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)

    @mcp.tool()
    def device_disconnect(session_id: str) -> str:
        """断开与嵌入式设备的连接。"""
        if pool.remove_session(session_id):
            return json.dumps({"success": True, "message": f"Session {session_id} disconnected."}, ensure_ascii=False, indent=2)
        return json.dumps({"success": False, "error": f"Session not found: {session_id}",
                            "active_sessions": pool.list_sessions()}, ensure_ascii=False, indent=2)

    @mcp.tool()
    def device_info(session_id: str) -> str:
        """获取已连接设备的基本系统信息 (uname, cpu, uptime, memory)。"""
        try:
            uname = pool.exec_on_session(session_id, "uname -a", timeout=5)
            cpu = pool.exec_on_session(session_id, "cat /proc/cpuinfo | grep -E 'model name|Processor|Hardware|CPU architecture' | head -10", timeout=5)
            uptime = pool.exec_on_session(session_id, "uptime", timeout=5)
            mem = pool.exec_on_session(session_id, "free -h", timeout=5)
            return json.dumps({
                "success": True,
                "system": uname.stdout.strip(),
                "cpu": cpu.stdout.strip() or "N/A",
                "uptime": uptime.stdout.strip(),
                "memory": mem.stdout.strip(),
            }, ensure_ascii=False, indent=2)
        except ValueError as e:
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)

    @mcp.tool()
    def device_list_sessions() -> str:
        """列出当前所有活跃的连接会话。"""
        sessions = pool.list_sessions()
        return json.dumps({"active_count": len(sessions), "sessions": sessions}, ensure_ascii=False, indent=2)
