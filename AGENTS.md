# 嵌入式助手 (Embed Tool)

AI-driven remote debug assistant for ARM Linux embedded devices.

Supports: **Claude Code**, **OpenCode**, and any **MCP-compatible agent**.

## Architecture

```
Agent (Claude Code / OpenCode / Cursor / ...)
  │
  ├── MCP Protocol ──→ mcp_server/  (24 tools)
  │                    ├── transports/   SSH / Telnet / Serial
  │                    ├── sessions/     Connection pool + GDB mode
  │                    └── tools/        Execution / Logging / Registers / GDB
  │
  └── Knowledge ──→ prompts/   (agent-agnostic domain guides)
                    skills/    (Claude Code skill format)
```

## Quick Start

### 1. Install dependencies
```bash
pip3 install --break-system-packages paramiko scp pexpect pyserial mcp
```

### 2. Configure your device
Edit `mcp_server/devices.json`:
```json
{
  "devices": [{
    "id": "my-board",
    "host": "192.168.1.100",
    "type": "ssh",
    "port": 22,
    "username": "root",
    "auth": { "method": "password", "password": "your_password" }
  }]
}
```

### 3. Configure your agent

**Claude Code**: Auto-detects `.mcp.json`.  Also reads `skills/` and `CLAUDE.md`.

**OpenCode**: Copy `configs/opencode.json` to your OpenCode config directory.

**Other MCP agents**: Use the standard MCP config format in `configs/mcp-generic.json`.

## Available Tools (24)

| Category | Tools |
|----------|-------|
| Connection | `device_list`, `device_connect`, `device_disconnect`, `device_info`, `device_list_sessions` |
| Execution | `device_exec` |
| File Transfer | `file_upload`, `file_download` |
| Logging | `dmesg_get`, `dmesg_follow`, `log_file_tail`, `journalctl_get` |
| Registers | `reg_read`, `reg_read_range`, `reg_indirect_read`, `reg_dump_block`, `reg_db_query`, `reg_db_list_blocks` |
| GDB | `gdb_launch`, `gdb_exec`, `gdb_close`, `gdbserver_start`, `gdbserver_stop` |
| Serial | `serial_list_ports` |

## Domain Guides

Generic prompts (any agent): `prompts/` directory  
Claude Code skills: `skills/` directory

| Domain | File |
|--------|------|
| Network/Ethernet debugging | `prompts/network-diag.txt` |
| I2C bus debugging | `prompts/i2c-debug.txt` |
| SPI bus debugging | `prompts/spi-debug.txt` |
| Boot flow analysis | `prompts/boot-analysis.txt` |
| Firmware flashing | `prompts/firmware-flash.txt` |
| Log analysis | `prompts/log-analysis.txt` |
| GDB debugging | `prompts/gdb-debug.txt` |
