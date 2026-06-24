"""GDB interactive debugging tools — session takeover mode."""
import json


def register(mcp, pool, **kw):
    @mcp.tool()
    def gdb_launch(session_id: str, binary_path: str, args: str = "") -> str:
        """在远程设备上启动 GDB 并接管当前会话。调用后 device_exec 被阻塞，直到 gdb_close。"""
        try:
            output = pool.start_gdb(session_id, binary_path, args)
            return json.dumps({
                "success": True, "session_id": session_id, "binary_path": binary_path,
                "message": "GDB session started. Transport now in GDB interactive mode.",
                "output": output,
            }, ensure_ascii=False, indent=2)
        except (ValueError, RuntimeError) as e:
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)

    @mcp.tool()
    def gdb_exec(session_id: str, command: str, timeout: int = 30) -> str:
        """向当前 GDB 会话发送命令 (break, run, continue, step, next, backtrace, print, info registers...)。"""
        try:
            output = pool.gdb_exec(session_id, command, timeout=timeout)
            gdb_info = pool.get_gdb_info(session_id)
            return json.dumps({
                "success": True, "session_id": session_id, "command": command,
                "output": output,
                "breakpoints": gdb_info.get("breakpoints", []) if gdb_info else [],
            }, ensure_ascii=False, indent=2)
        except RuntimeError as e:
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)

    @mcp.tool()
    def gdb_close(session_id: str) -> str:
        """退出 GDB 并恢复传输层到正常 Shell 模式。"""
        try:
            output = pool.stop_gdb(session_id)
            return json.dumps({
                "success": True, "session_id": session_id,
                "message": "GDB closed. Shell mode restored.",
                "final_output": output,
            }, ensure_ascii=False, indent=2)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)

    @mcp.tool()
    def gdbserver_start(session_id: str, binary_path: str = "", pid: int = 0, port: int = 2345) -> str:
        """在远程设备上通过 gdbserver 启动调试。如不可用请直接使用 gdb_launch。"""
        return json.dumps({
            "success": False,
            "message": "gdbserver 模式当前不可用。请直接使用 gdb_launch(session_id, binary_path) 在设备上启动 GDB 交互会话。",
            "alternative": "gdb_launch",
        }, ensure_ascii=False, indent=2)

    @mcp.tool()
    def gdbserver_stop(session_id: str, gdbserver_pid: int) -> str:
        """停止 gdbserver。如果使用 gdb_launch 启动的 GDB，请用 gdb_close。"""
        if pool.is_gdb_active(session_id):
            return json.dumps({"success": False, "message": "GDB 交互会话活跃中，请使用 gdb_close(session_id) 关闭。"}, ensure_ascii=False, indent=2)
        return json.dumps({"success": False, "message": f"无活跃 GDB 会话。手动 kill: kill {gdbserver_pid}"}, ensure_ascii=False, indent=2)
