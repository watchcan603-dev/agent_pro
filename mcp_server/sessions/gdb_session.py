"""GDB interactive session manager.

Manages a persistent GDB process over any transport that supports
interactive mode (SSH, Telnet, Serial). The transport connection is
temporarily dedicated to GDB while the session is active.

Architecture:
    Transport shell mode:  exec_command() works normally
           │
           ▼  gdb_launch()
    Transport interactive mode:  exec_command() BLOCKED
           │                    send/recv_interactive() active
           │
           ▼  gdb_close()
    Transport shell mode:  exec_command() works again
"""

import re
import time
from typing import Optional, List, Dict
from dataclasses import dataclass, field


# GDB prompt that signals command completion
GDB_PROMPT = "(gdb)"


@dataclass
class GdbBreakpoint:
    """Track a breakpoint set during the session."""
    number: int
    location: str
    enabled: bool = True
    hit_count: int = 0


class GdbSession:
    """Manages a persistent GDB process over a transport's interactive channel.

    Usage:
        gdb = GdbSession(transport)
        gdb.launch("/usr/bin/myapp")
        output = gdb.exec_cmd("break main")
        output = gdb.exec_cmd("continue")
        output = gdb.exec_cmd("backtrace")
        gdb.close()
    """

    def __init__(self):
        self._transport = None
        self._active = False
        self._binary_path = ""
        self._breakpoints: Dict[int, GdbBreakpoint] = {}
        self._command_history: List[str] = []

    # ── Public API ────────────────────────────────────────────────────────────

    def launch(self, transport, binary_path: str, args: str = "") -> str:
        """Start GDB on the transport and attach to / launch the target binary.

        Args:
            transport: A connected BaseTransport with interactive support.
            binary_path: Absolute path to the binary on the remote device.
            args: Optional command-line arguments for the binary.

        Returns:
            GDB startup output.
        """
        if self._active:
            raise RuntimeError("GDB session already active")

        self._transport = transport
        self._binary_path = binary_path

        # Build GDB launch command
        cmd = f"gdb -q {binary_path}"
        if args:
            # GDB's --args passes arguments to the inferior
            cmd = f"gdb -q --args {binary_path} {args}"

        # Switch transport to interactive mode and launch GDB
        transport.open_interactive(cmd)

        # Wait for GDB prompt
        try:
            output = transport.recv_interactive(GDB_PROMPT, timeout=15)
        except TimeoutError as e:
            # GDB might not be installed
            transport.close_interactive()
            raise RuntimeError(
                f"GDB failed to start. Is 'gdb' installed on the device? "
                f"Error: {e}"
            ) from e

        self._active = True
        return self._clean_output(output)

    def exec_cmd(self, command: str, timeout: int = 30) -> str:
        """Execute a GDB command and return the output.

        Args:
            command: GDB command (e.g., 'break main', 'continue', 'backtrace').
            timeout: Max seconds to wait for the (gdb) prompt.

        Returns:
            GDB output with the prompt stripped.
        """
        if not self._active:
            raise RuntimeError("GDB session not active. Call launch() first.")

        self._transport.send_interactive(command + "\n")
        self._command_history.append(command)

        try:
            raw = self._transport.recv_interactive(GDB_PROMPT, timeout=timeout)
        except TimeoutError:
            # GDB might be running (continue never hit breakpoint)
            # Send Ctrl+C to interrupt
            self._transport.send_interactive("\x03")
            try:
                raw = self._transport.recv_interactive(GDB_PROMPT, timeout=5)
            except TimeoutError:
                return f"(timeout after {timeout}s — program may be running)"

        output = self._clean_output(raw)

        # Track breakpoints
        self._track_breakpoint(command, output)

        return output

    def close(self) -> str:
        """Quit GDB and restore the transport to normal shell mode.

        Returns:
            Any final GDB output.
        """
        if not self._active:
            return ""

        try:
            self._transport.send_interactive("quit\n")
            # GDB asks "Quit anyway? (y or n)" if the program is running
            try:
                confirm = self._transport.recv_interactive("(y or n)", timeout=2)
                self._transport.send_interactive("y\n")
            except TimeoutError:
                pass

            # Read remaining output until channel closes
            try:
                leftover = self._transport.recv_interactive("\n", timeout=3)
            except TimeoutError:
                leftover = ""
        except Exception:
            leftover = ""
        finally:
            self._transport.close_interactive()

        self._active = False
        self._breakpoints.clear()
        self._command_history.clear()
        self._transport = None

        return leftover

    @property
    def is_active(self) -> bool:
        return self._active

    @property
    def binary_path(self) -> str:
        return self._binary_path

    @property
    def breakpoints(self) -> list:
        return [
            {"number": b.number, "location": b.location, "enabled": b.enabled}
            for b in self._breakpoints.values()
        ]

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _clean_output(self, raw: str) -> str:
        """Clean GDB output: remove echoed command and extra prompt lines."""
        lines = raw.split("\n")
        cleaned = []

        for line in lines:
            # Remove ANSI escape sequences
            line = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', line)
            # Skip empty prompt-only lines
            if line.strip() in ("(gdb)", "(gdb) "):
                continue
            cleaned.append(line)

        return "\n".join(cleaned).strip()

    def _track_breakpoint(self, command: str, output: str) -> None:
        """Extract breakpoint info from GDB command output."""
        # "break <location>" or "b <location>"
        if command.strip().startswith(("break ", "b ")):
            # GDB output: "Breakpoint 1 at 0x400123: file main.c, line 42."
            # or: "Breakpoint 1 at 0x400123"
            m = re.match(r"Breakpoint (\d+) at (0x[0-9a-fA-F]+)", output)
            if m:
                bp_num = int(m.group(1))
                location = command.strip().split(None, 1)[1] if len(command.strip().split(None, 1)) > 1 else "unknown"
                self._breakpoints[bp_num] = GdbBreakpoint(
                    number=bp_num,
                    location=location,
                    enabled=True,
                )
        # "delete <N>"
        elif command.strip().startswith(("delete ", "d ")):
            try:
                bp_num = int(command.strip().split()[1])
                self._breakpoints.pop(bp_num, None)
            except (IndexError, ValueError):
                pass
        # "disable <N>"
        elif command.strip().startswith("disable "):
            try:
                bp_num = int(command.strip().split()[1])
                if bp_num in self._breakpoints:
                    self._breakpoints[bp_num].enabled = False
            except (IndexError, ValueError):
                pass
        # "enable <N>"
        elif command.strip().startswith("enable "):
            try:
                bp_num = int(command.strip().split()[1])
                if bp_num in self._breakpoints:
                    self._breakpoints[bp_num].enabled = True
            except (IndexError, ValueError):
                pass
