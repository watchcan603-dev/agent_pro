# 嵌入式助手 (Embed Tool)

AI-driven remote debug assistant for ARM Linux embedded devices.

Supports: **OpenCode**, **Claude Code**, and any **MCP-compatible agent**.

## Architecture

```
Agent (OpenCode / Claude Code / Cursor / ...)
  │
  ├── MCP Protocol ──→ mcp_server/  (24 tools)
  │                    ├── transports/   SSH / Telnet / Serial
  │                    ├── sessions/     Connection pool + GDB mode
  │                    └── tools/        Execution / Logging / Registers / GDB
  │
  └── Knowledge ──→ .opencode/skills/  (OpenCode native skills)
                    skills/             (Claude Code compatible)
                    prompts/            (agent-agnostic domain guides)
```

## Quick Start

### 1. Install dependencies
```bash
python3 -m build --wheel && python3 -m pip install dist/embed_tool-*.whl
```

### 2. Configure your device
Edit `~/.config/embed-tool/devices.json`:
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

**OpenCode** (recommended):
- `opencode.json` in project root auto-configures MCP server and loads skills
- Domain guides auto-loaded via `prompts/*.txt` in instructions config
- Skills available at `.opencode/skills/` — use `/` commands or agent auto-selects

**Claude Code**: Auto-detects `.mcp.json`.  Also reads `skills/` and `CLAUDE.md`.

**Other MCP agents**: Use the standard MCP config format in `configs/mcp-generic.json`.

### OpenCode Quick Setup

```bash
# 1. Install deps
python3 -m build --wheel && python3 -m pip install dist/embed_tool-*.whl

# 2. Edit device config
vim ~/.config/embed-tool/devices.json

# 3. Start opencode in project dir
cd /path/to/agent_pro
opencode
```

The `opencode.json` in project root automatically:
- Registers the MCP server with 24 tools
- Loads AGENTS.md and prompts/ as instructions
- Makes 8 domain skills available via the `skill` tool

## OpenCode Skills (8)

Available via the `skill` tool — opencode auto-discovers these from `.opencode/skills/`:

| Skill | Domain | Use when... |
|-------|--------|-------------|
| `network-diag` | Network/Ethernet | eth0 NO-CARRIER, packet loss, CRC errors |
| `i2c-debug` | I2C bus | I2C device not responding, scan failures |
| `spi-debug` | SPI/QSPI | SPI flash issues, signal integrity |
| `boot-analysis` | Boot flow | Kernel panic, driver load failures |
| `firmware-flash` | Flashing | Firmware updates, dd/fastboot |
| `log-analysis` | Log analysis | OOM, kernel panics, driver faults |
| `gdb-debug` | GDB debugging | Remote debug with gdbserver |
| `register-debug` | Registers | GMAC/PHY/DMA register bit-field decode |

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

| Domain | OpenCode Skill | Claude Skill | Plain Text Prompt |
|--------|---------------|-------------|-------------------|
| Network/Ethernet | `.opencode/skills/network-diag/` | `skills/network-diag.md` | `prompts/network-diag.txt` |
| I2C bus debugging | `.opencode/skills/i2c-debug/` | `skills/i2c-debug.md` | `prompts/i2c-debug.txt` |
| SPI bus debugging | `.opencode/skills/spi-debug/` | `skills/spi-debug.md` | `prompts/spi-debug.txt` |
| Boot flow analysis | `.opencode/skills/boot-analysis/` | `skills/boot-analysis.md` | `prompts/boot-analysis.txt` |
| Firmware flashing | `.opencode/skills/firmware-flash/` | `skills/firmware-flash.md` | `prompts/firmware-flash.txt` |
| Log analysis | `.opencode/skills/log-analysis/` | `skills/log-analysis.md` | `prompts/log-analysis.txt` |
| GDB debugging | `.opencode/skills/gdb-debug/` | `skills/gdb-debug.md` | `prompts/gdb-debug.txt` |
| Register debugging | `.opencode/skills/register-debug/` | `skills/register-debug.md` | `prompts/register-debug.txt` |
