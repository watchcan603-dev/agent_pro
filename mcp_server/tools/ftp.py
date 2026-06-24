"""FTP file transfer tools — for devices without SCP (Telnet/Serial connections).

Workflow:
    1. ftp_server_start → host starts temporary FTP server
    2. ftp_upload / ftp_download → device uses busybox ftpget/ftpput
    3. ftp_server_stop → host stops FTP server
"""
import json
import os

# Module-level FTP server instance (shared across tool calls)
_ftp_server = None


def _get_ftp():
    global _ftp_server
    if _ftp_server is None:
        from ..ftp_server import FTPServerManager
        _ftp_server = FTPServerManager()
    return _ftp_server


def register(mcp, pool, **kw):
    @mcp.tool()
    def ftp_server_start(session_id: str = "", port: int = 2121,
                          directory: str = "/tmp/embed_ftp") -> str:
        """在宿主机上启动临时 FTP 服务器，供设备通过 ftpget/ftpput 传输文件。

        设备需要能通过网络访问宿主机 IP。启动后返回连接参数。

        Args:
            session_id: 会话 ID (可选，用于验证设备是否能 ping 通宿主机)。
            port: FTP 端口，默认 2121。
            directory: FTP 根目录，默认 /tmp/embed_ftp。

        Returns:
            JSON with {host, port, username, password, directory}.
        """
        try:
            ftp = _get_ftp()
            if ftp.is_running:
                return json.dumps({
                    "success": True,
                    "message": "FTP server already running",
                    **ftp.info,
                }, ensure_ascii=False, indent=2)

            info = ftp.start(port=port, directory=directory)

            # If session provided, verify device can reach host
            reachable = None
            if session_id:
                try:
                    r = pool.exec_on_session(
                        session_id,
                        f"ping -c 1 -W 3 {info['host']} 2>&1 || echo UNREACHABLE",
                        timeout=5,
                    )
                    reachable = "UNREACHABLE" not in r.stdout
                except Exception:
                    reachable = False

            return json.dumps({
                "success": True,
                "message": "FTP server started",
                **info,
                "device_reachable": reachable,
                "usage": (
                    f"设备上传到宿主机: ftpput -u {info['username']} -p {info['password']} "
                    f"{info['host']} <远程路径> <本地路径>"
                ),
                "usage_download": (
                    f"宿主机下载到设备: ftpget -u {info['username']} -p {info['password']} "
                    f"{info['host']} <本地路径> <远程路径>"
                ),
            }, ensure_ascii=False, indent=2)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)

    @mcp.tool()
    def ftp_server_stop() -> str:
        """停止宿主机的 FTP 服务器。"""
        try:
            ftp = _get_ftp()
            if not ftp.is_running:
                return json.dumps({
                    "success": True,
                    "message": "FTP server was not running",
                }, ensure_ascii=False, indent=2)
            ftp.stop()
            return json.dumps({
                "success": True,
                "message": "FTP server stopped",
            }, ensure_ascii=False, indent=2)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)

    @mcp.tool()
    def ftp_upload(session_id: str, local_path: str, remote_path: str) -> str:
        """通过 FTP 上传文件到设备 (设备执行 ftpget 从宿主机拉取)。

        需要先调用 ftp_server_start 启动 FTP 服务器。
        文件先复制到 FTP 目录，然后设备通过 ftpget 拉取。

        Args:
            session_id: 会话 ID。
            local_path: 宿主机上的文件路径。
            remote_path: 设备上的目标路径。
        """
        try:
            ftp = _get_ftp()
            if not ftp.is_running:
                return json.dumps({
                    "success": False,
                    "error": "FTP server not running. Call ftp_server_start first.",
                }, ensure_ascii=False, indent=2)

            if not os.path.exists(local_path):
                return json.dumps({
                    "success": False,
                    "error": f"Local file not found: {local_path}",
                }, ensure_ascii=False, indent=2)

            # Copy file to FTP directory
            basename = os.path.basename(local_path)
            ftp_file = os.path.join(ftp.info["directory"], basename)

            import shutil
            # Remove old file if exists
            if os.path.exists(ftp_file):
                os.remove(ftp_file)
            shutil.copy2(local_path, ftp_file)
            os.chmod(ftp_file, 0o644)

            # Device uses ftpget to download from host
            info = ftp.info
            cmd = (
                f"ftpget -u {info['username']} -p {info['password']} "
                f"{info['host']} '{remote_path}' '{basename}'"
            )

            # Actually, ftpget syntax is: ftpget [options] HOST LOCAL_FILE REMOTE_FILE
            # So LOCAL_FILE is on the device, REMOTE_FILE is on the FTP server
            # Correct command:
            cmd = (
                f"ftpget -u {info['username']} -p {info['password']} "
                f"{info['host']} '{remote_path}' '{basename}'"
            )

            result = pool.exec_on_session(session_id, cmd, timeout=30)

            # Clean up FTP directory
            try:
                os.remove(ftp_file)
            except Exception:
                pass

            return json.dumps({
                "success": result.exit_code == 0,
                "exit_code": result.exit_code,
                "local_path": local_path,
                "remote_path": remote_path,
                "method": "ftpget (device pulls from host)",
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
            }, ensure_ascii=False, indent=2)
        except ValueError as e:
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)

    @mcp.tool()
    def ftp_download(session_id: str, remote_path: str, local_path: str) -> str:
        """通过 FTP 从设备下载文件 (设备执行 ftpput 推送到宿主机)。

        需要先调用 ftp_server_start 启动 FTP 服务器。

        Args:
            session_id: 会话 ID。
            remote_path: 设备上的文件路径。
            local_path: 宿主机保存路径。
        """
        try:
            ftp = _get_ftp()
            if not ftp.is_running:
                return json.dumps({
                    "success": False,
                    "error": "FTP server not running. Call ftp_server_start first.",
                }, ensure_ascii=False, indent=2)

            # Device uses ftpput to upload to host
            info = ftp.info
            basename = os.path.basename(remote_path)
            cmd = (
                f"ftpput -u {info['username']} -p {info['password']} "
                f"{info['host']} '{basename}' '{remote_path}'"
            )

            result = pool.exec_on_session(session_id, cmd, timeout=30)

            # Move file from FTP directory to target location
            ftp_file = os.path.join(info["directory"], basename)
            if os.path.exists(ftp_file):
                local_dir = os.path.dirname(local_path)
                if local_dir and not os.path.exists(local_dir):
                    os.makedirs(local_dir, exist_ok=True)
                import shutil
                shutil.move(ftp_file, local_path)

            return json.dumps({
                "success": result.exit_code == 0 and os.path.exists(local_path),
                "exit_code": result.exit_code,
                "remote_path": remote_path,
                "local_path": local_path,
                "method": "ftpput (device pushes to host)",
                "local_size": os.path.getsize(local_path) if os.path.exists(local_path) else 0,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
            }, ensure_ascii=False, indent=2)
        except ValueError as e:
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)
