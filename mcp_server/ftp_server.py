"""Minimal FTP server for busybox ftpget/ftpput file transfer.

Pure Python stdlib — no external dependencies.
Supports: USER, PASS, PASV, STOR, RETR, QUIT.
"""

import os
import socket
import threading
from typing import Optional


class _FTPDataChannel:
    """Manages passive-mode data connections."""

    def __init__(self):
        self._sock = None
        self._conn = None

    def setup_passive(self) -> tuple:
        """Create a passive data socket. Returns (host, port)."""
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("0.0.0.0", 0))
        self._sock.listen(1)
        host = self._sock.getsockname()
        return host

    def accept(self, timeout: float = 10):
        """Accept the data connection."""
        self._sock.settimeout(timeout)
        self._conn, addr = self._sock.accept()
        return self._conn

    def send_data(self, data: bytes):
        """Send data through the data connection."""
        if self._conn:
            self._conn.sendall(data)

    def recv_data(self, bufsize: int = 8192) -> bytes:
        """Receive data from the data connection."""
        data = b""
        if self._conn:
            self._conn.settimeout(5)
            while True:
                try:
                    chunk = self._conn.recv(bufsize)
                    if not chunk:
                        break
                    data += chunk
                except socket.timeout:
                    break
        return data

    def close(self):
        """Close the data connection."""
        for s in (self._conn, self._sock):
            if s:
                try:
                    s.close()
                except Exception:
                    pass
        self._conn = None
        self._sock = None


class MiniFTPServer:
    """Minimal FTP server supporting passive-mode file transfer.

    Protocol support:
        USER <name>       — set username
        PASS <password>   — authenticate
        PASV              — enter passive mode
        STOR <filename>   — receive file from client (device ftpput)
        RETR <filename>   — send file to client (device ftpget)
        QUIT              — disconnect
    """

    def __init__(self, host: str = "0.0.0.0", port: int = 2121,
                 username: str = "embed", password: str = "tool",
                 root_dir: str = "/tmp/embed_ftp"):

        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.root_dir = os.path.abspath(root_dir)

        self._socket: Optional[socket.socket] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None

        # Per-session state
        self._authenticated = False
        self._data = _FTPDataChannel()

    def start(self):
        """Start the FTP server in a background thread."""
        if self._running:
            return

        os.makedirs(self.root_dir, exist_ok=True)

        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._socket.bind((self.host, self.port))
        self._socket.listen(5)
        self._socket.settimeout(1.0)
        self._running = True

        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop the FTP server."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None
        if self._socket:
            try:
                self._socket.close()
            except Exception:
                pass
            self._socket = None
        self._data.close()

    @property
    def is_running(self) -> bool:
        return self._running

    # ── Server loop ──────────────────────────────────────────────────────

    def _serve(self):
        while self._running:
            try:
                conn, addr = self._socket.accept()
                t = threading.Thread(target=self._handle_client, args=(conn, addr), daemon=True)
                t.start()
            except socket.timeout:
                continue
            except Exception:
                if self._running:
                    break

    def _handle_client(self, conn: socket.socket, addr: tuple):
        conn.settimeout(60)
        self._control_conn = conn  # Save for data channel methods
        self._authenticated = False

        try:
            conn.sendall(b"220 Embed FTP ready.\r\n")

            while self._running:
                data = conn.recv(4096)
                if not data:
                    break
                line = data.decode("utf-8", errors="replace").strip()
                if not line:
                    continue

                response = self._handle_command(line)
                conn.sendall((response + "\r\n").encode("utf-8"))

                if response.startswith("221"):
                    break
        except Exception:
            pass
        finally:
            self._data.close()
            self._control_conn = None
            try:
                conn.close()
            except Exception:
                pass

    def _handle_command(self, line: str) -> str:
        """Parse and execute an FTP command."""
        parts = line.split(maxsplit=1)
        cmd = parts[0].upper()
        arg = parts[1] if len(parts) > 1 else ""

        if cmd == "USER":
            return "331 Password required."
        elif cmd == "PASS":
            self._authenticated = True
            return "230 Login successful."
        elif cmd == "PASV":
            if not self._authenticated:
                return "530 Not logged in."
            host_port = self._data.setup_passive()
            ip_parts = host_port[0].split(".")
            p1, p2 = host_port[1] // 256, host_port[1] % 256
            return f"227 Entering Passive Mode ({','.join(ip_parts)},{p1},{p2})"
        elif cmd == "STOR":
            if not self._authenticated:
                return "530 Not logged in."
            return self._do_stor(arg, line)
        elif cmd == "RETR":
            if not self._authenticated:
                return "530 Not logged in."
            return self._do_retr(arg, line)
        elif cmd == "QUIT":
            return "221 Bye."
        elif cmd == "TYPE":
            return "200 Type set to I."
        elif cmd == "SYST":
            return "215 UNIX Type: L8"
        elif cmd == "FEAT":
            return "211-Features:\r\n PASV\r\n211 End"
        elif cmd == "PWD":
            return f'257 "{self.root_dir}"'
        elif cmd == "CWD":
            return "250 OK"
        elif cmd == "OPTS":
            return "200 OK"
        elif cmd == "SIZE":
            # Return file size for the given path
            fpath = os.path.join(self.root_dir, os.path.basename(arg))
            if os.path.isfile(fpath):
                return f"213 {os.path.getsize(fpath)}"
            return "550 File not found"
        elif cmd == "LIST" or cmd == "NLST":
            return self._do_list()
        else:
            return f"502 Command not implemented: {cmd}"

    def _do_stor(self, filename: str, raw_line: str) -> str:
        """Handle STOR — receive file from client (device uploads to host)."""
        fname = os.path.basename(filename)
        fpath = os.path.join(self.root_dir, fname)

        try:
            self._data.accept(timeout=10)
            self._control_conn.sendall(b"150 Opening data connection.\r\n")
            file_data = self._data.recv_data()

            with open(fpath, "wb") as f:
                f.write(file_data)

            return "226 Transfer complete."
        except Exception as e:
            return f"550 Error: {str(e)}"
        finally:
            self._data.close()

    def _do_retr(self, filename: str, raw_line: str) -> str:
        """Handle RETR — send file to client (device downloads from host)."""
        fname = os.path.basename(filename)
        fpath = os.path.join(self.root_dir, fname)

        if not os.path.isfile(fpath):
            return "550 File not found."

        try:
            self._data.accept(timeout=10)
            self._control_conn.sendall(b"150 Opening data connection.\r\n")

            with open(fpath, "rb") as f:
                self._data.send_data(f.read())

            return "226 Transfer complete."
        except Exception as e:
            return f"550 Error: {str(e)}"
        finally:
            self._data.close()

    def _do_list(self) -> str:
        """Handle LIST — return directory listing."""
        try:
            self._data.accept(timeout=10)
            self._control_conn.sendall(b"150 Opening data connection.\r\n")

            listing = ""
            for name in sorted(os.listdir(self.root_dir)):
                fpath = os.path.join(self.root_dir, name)
                if os.path.isfile(fpath):
                    size = os.path.getsize(fpath)
                    listing += f"-rw-r--r-- 1 embed tool {size:>8} Jan 01 00:00 {name}\r\n"

            self._data.send_data(listing.encode("utf-8"))
            return "226 Transfer complete."
        except Exception:
            return "550 Error."
        finally:
            self._data.close()


# ── Manager (same API as before) ──────────────────────────────────────────────

class FTPServerManager:
    """Manages the minimal FTP server lifecycle."""

    DEFAULT_PORT = 2121
    DEFAULT_USER = "embed"
    DEFAULT_PASS = "tool"
    DEFAULT_DIR = "/tmp/embed_ftp"

    def __init__(self):
        self._server: Optional[MiniFTPServer] = None
        self._port = self.DEFAULT_PORT
        self._username = self.DEFAULT_USER
        self._password = self.DEFAULT_PASS
        self._directory = self.DEFAULT_DIR

    def start(self, directory: str = None, port: int = None,
              username: str = None, password: str = None) -> dict:
        if self._server and self._server.is_running:
            raise RuntimeError("FTP server already running")

        if directory:  self._directory = directory
        if port:       self._port = port
        if username:   self._username = username
        if password:   self._password = password

        os.makedirs(self._directory, exist_ok=True)

        self._server = MiniFTPServer(
            host="0.0.0.0", port=self._port,
            username=self._username, password=self._password,
            root_dir=self._directory,
        )
        self._server.start()
        return self.info

    def stop(self):
        if self._server:
            self._server.stop()
            self._server = None

    @property
    def is_running(self) -> bool:
        return self._server is not None and self._server.is_running

    @property
    def info(self) -> Optional[dict]:
        if not self._server:
            return None
        return {
            "host": self._get_host_ip(),
            "port": self._port,
            "username": self._username,
            "password": self._password,
            "directory": self._directory,
        }

    @staticmethod
    def _get_host_ip() -> str:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return socket.gethostbyname(socket.gethostname())
