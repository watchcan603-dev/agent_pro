"""File transfer tools (SCP for SSH, base64 for telnet/serial)."""
import json, os


def register(mcp, pool, **kw):
    @mcp.tool()
    def file_upload(session_id: str, local_path: str, remote_path: str) -> str:
        """上传文件到远程设备 (SSH→SCP, 其他→base64)。"""
        if not os.path.exists(local_path):
            return json.dumps({"success": False, "error": f"Local file not found: {local_path}"}, ensure_ascii=False, indent=2)
        try:
            pool.upload_via_session(session_id, local_path, remote_path)
            check = pool.exec_on_session(session_id, f"ls -lh '{remote_path}' && echo OK", timeout=5)
            return json.dumps({
                "success": True, "local_path": local_path, "remote_path": remote_path,
                "verified": "OK" in check.stdout,
            }, ensure_ascii=False, indent=2)
        except ValueError as e:
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)
        except Exception as e:
            return json.dumps({"success": False, "error": f"Upload failed: {str(e)}"}, ensure_ascii=False, indent=2)

    @mcp.tool()
    def file_download(session_id: str, remote_path: str, local_path: str) -> str:
        """从远程设备下载文件 (SSH→SCP, 其他→base64)。"""
        try:
            local_dir = os.path.dirname(local_path)
            if local_dir and not os.path.exists(local_dir):
                os.makedirs(local_dir, exist_ok=True)
            pool.download_via_session(session_id, remote_path, local_path)
            if os.path.exists(local_path):
                return json.dumps({
                    "success": True, "remote_path": remote_path,
                    "local_path": local_path, "size_bytes": os.path.getsize(local_path),
                }, ensure_ascii=False, indent=2)
            return json.dumps({"success": False, "error": f"File not found at {local_path} after download"}, ensure_ascii=False, indent=2)
        except ValueError as e:
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)
        except Exception as e:
            return json.dumps({"success": False, "error": f"Download failed: {str(e)}"}, ensure_ascii=False, indent=2)
