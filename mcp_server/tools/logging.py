"""Log collection tools — dmesg, journalctl, log files."""
import json


def register(mcp, pool, **kw):
    @mcp.tool()
    def dmesg_get(session_id: str, level: str = "", lines: int = 200) -> str:
        """获取远程设备内核日志 (dmesg)。level 可选: emerg, alert, crit, err, warn, notice, info, debug。"""
        try:
            cmd = f"dmesg --level={level} 2>/dev/null | tail -{lines}" if level else f"dmesg | tail -{lines}"
            result = pool.exec_on_session(session_id, cmd, timeout=10)
            line_count = len([l for l in result.stdout.split("\n") if l.strip()])
            return json.dumps({
                "success": True, "level": level or "all",
                "lines_requested": lines, "lines_returned": line_count,
                "output": result.stdout,
            }, ensure_ascii=False, indent=2)
        except ValueError as e:
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)
        except Exception as e:
            return json.dumps({"success": False, "error": f"dmesg failed: {str(e)}"}, ensure_ascii=False, indent=2)

    @mcp.tool()
    def dmesg_follow(session_id: str, duration: int = 10, filter_pattern: str = "") -> str:
        """持续采集内核日志 N 秒。duration 最大 60。"""
        duration = max(1, min(duration, 60))
        try:
            if filter_pattern:
                cmd = f"timeout {duration} dmesg -w 2>/dev/null | grep -iE '{filter_pattern}' || echo '(no match)'"
            else:
                cmd = f"timeout {duration} dmesg -w 2>/dev/null || echo '(dmesg -w not supported)'"
            result = pool.exec_on_session(session_id, cmd, timeout=duration + 5)
            lines = [l for l in result.stdout.split("\n") if l.strip()]
            return json.dumps({
                "success": True, "duration_seconds": duration,
                "filter": filter_pattern or "none", "lines_captured": len(lines),
                "output": result.stdout,
            }, ensure_ascii=False, indent=2)
        except ValueError as e:
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)

    @mcp.tool()
    def log_file_tail(session_id: str, file_path: str, lines: int = 500,
                       filter_pattern: str = "") -> str:
        """获取远程设备日志文件尾部。支持 /var/log/syslog, /var/log/kern.log 等。"""
        try:
            check = pool.exec_on_session(session_id, f"test -r '{file_path}' && wc -l '{file_path}' || echo NOT_FOUND", timeout=5)
            if "NOT_FOUND" in check.stdout:
                return json.dumps({"success": False, "error": f"File not found: {file_path}"}, ensure_ascii=False, indent=2)
            cmd = f"tail -n {lines} '{file_path}'"
            if filter_pattern:
                cmd += f" | grep -iE '{filter_pattern}'"
            result = pool.exec_on_session(session_id, cmd, timeout=10)
            line_count = len([l for l in result.stdout.split("\n") if l.strip()])
            return json.dumps({
                "success": True, "file_path": file_path, "lines_requested": lines,
                "lines_returned": line_count, "filter": filter_pattern or "none",
                "output": result.stdout,
            }, ensure_ascii=False, indent=2)
        except ValueError as e:
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)

    @mcp.tool()
    def journalctl_get(session_id: str, lines: int = 200, priority: str = "",
                        unit: str = "", since: str = "") -> str:
        """获取 systemd journal 日志。priority: emerg..debug, unit: ssh.service, since: '10 min ago'。"""
        try:
            check = pool.exec_on_session(session_id, "which journalctl", timeout=5)
            if check.exit_code != 0:
                return json.dumps({"success": False, "error": "journalctl not available"}, ensure_ascii=False, indent=2)
            parts = [f"journalctl -n {lines} --no-pager"]
            if priority: parts.append(f"-p {priority}")
            if unit: parts.append(f"-u {unit}")
            if since: parts.append(f'--since "{since}"')
            result = pool.exec_on_session(session_id, " ".join(parts), timeout=15)
            line_count = len([l for l in result.stdout.split("\n") if l.strip()])
            return json.dumps({
                "success": True, "lines_requested": lines, "lines_returned": line_count,
                "priority": priority or "all", "unit": unit or "all",
                "since": since or "N/A", "output": result.stdout,
            }, ensure_ascii=False, indent=2)
        except ValueError as e:
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)
