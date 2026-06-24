"""Command execution tool — the primary interaction primitive."""
import json


def register(mcp, pool, **kw):
    @mcp.tool()
    def device_exec(session_id: str, command: str, timeout: int = 30) -> str:
        """在远程设备上执行 Shell 命令。核心工具。"""
        try:
            result = pool.exec_on_session(session_id, command, timeout=timeout)
            return json.dumps({
                "success": result.exit_code == 0,
                "exit_code": result.exit_code,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }, ensure_ascii=False, indent=2)
        except ValueError as e:
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)
        except RuntimeError as e:
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)
        except Exception as e:
            return json.dumps({"success": False, "error": f"Exec failed: {str(e)}"}, ensure_ascii=False, indent=2)
