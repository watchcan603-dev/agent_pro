# Embed Tool — 嵌入式 AI 调试助手

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://python.org)
[![MCP](https://img.shields.io/badge/MCP-1.0-green)](https://modelcontextprotocol.io)
[![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

AI 驱动的 ARM Linux 嵌入式设备远程调试助手。通过 SSH/Telnet/Serial 连接设备，提供命令执行、文件传输、日志分析、寄存器诊断、GDB 交互调试等能力。支持 **Claude Code**、**OpenCode** 及任何 **MCP 兼容 Agent**。

---

## 为什么需要 Embed Tool

嵌入式驱动开发的核心痛点不是缺少工具，而是**工具太分散**——查手册、看寄存器、抓日志、调 GDB 个个都要手动操作，出问题时需要反复切换工具和翻阅文档。

Embed Tool 把这些能力整合到 AI Agent 中，开发者用自然语言描述问题，Agent 自动调用对应的工具链，结合芯片手册知识给出诊断结论。

```
"eth0 一直 NO-CARRIER，帮我看看怎么回事"
                    │
                    ▼
Agent 自动: device_connect → reg_dump_block("gmac_mac") → reg_dump_block("phy")
         → dmesg_get(level="err") → log_file_tail("/var/log/syslog", "error|eth")
         → 对比寄存器数据库 → 输出诊断结论
```

## 架构

```
┌─────────────────────────────────────────────────────────┐
│  AI Agent (Claude Code / OpenCode / Cursor / ...)       │
│                                                         │
│  Skills (知识层)     ← 领域专家，新增业务只加此目录          │
│  ├── network-diag  网口调试专家                           │
│  ├── i2c-debug     I2C 调试专家                          │
│  ├── spi-debug     SPI 调试专家                          │
│  ├── boot-analysis 启动分析专家                          │
│  ├── firmware-flash 固件烧写专家                         │
│  ├── log-analysis  日志分析专家                          │
│  └── gdb-debug     GDB 调试专家                          │
│                                                         │
│  MCP Server (工具层)  ← 24 个基础工具，协议无关              │
│  ├── Connection    device_list / connect / disconnect    │
│  ├── Execution     device_exec                           │
│  ├── File Transfer file_upload / download                │
│  ├── Logging       dmesg / journalctl / log_file_tail    │
│  ├── Registers     reg_read / dump / indirect_read       │
│  ├── GDB           gdb_launch / exec / close             │
│  └── Serial        serial_list_ports                     │
│                                                         │
│  Session Pool (会话层) ← 连接池 + GDB 交互模式切换          │
│                                                         │
│  Transport (传输层)  ← 统一接口，可插拔协议                  │
│  ├── SSH     (paramiko)    ✅ 稳定                       │
│  ├── Telnet  (socket)      🧪 实验                       │
│  └── Serial  (pyserial)    🧪 实验                       │
└─────────────────────────────────────────────────────────┘
         │  SSH / Telnet / Serial
         ▼
┌─────────────────────────────────────────────────────────┐
│         ARM Linux 嵌入式设备                              │
│  Shell / GDB / devmem / dmesg / fastboot / i2c-tools    │
└─────────────────────────────────────────────────────────┘
```

## 快速开始

### 安装（推荐 wheel）

某些 Agent 只能加载已安装的 wheel 包。Embed Tool 现在提供标准 Python 打包配置，并安装 `embed-tool-mcp` 命令作为 MCP Server 入口。

```bash
git clone <repo-url> embed_tool && cd embed_tool
python3 -m pip install --upgrade build
python3 -m build --wheel
python3 -m pip install dist/embed_tool-*.whl
```

安装后可直接测试 MCP Server 入口：

```bash
embed-tool-mcp
```

开发环境也可以使用 editable 安装：

```bash
python3 -m pip install -e .
```

### 配置设备

编辑默认设备配置 `~/.config/embed-tool/devices.json`（也可以用环境变量 `EMBED_TOOL_DEVICES` 指定其他路径）：

```json
{
  "devices": [{
    "id": "my-board",
    "name": "我的 ARM 开发板",
    "host": "192.168.1.100",
    "type": "ssh",
    "port": 22,
    "username": "root",
    "auth": { "method": "password", "password": "your_password" },
    "tags": ["arm", "cortex-a"]
  }]
}
```

### 测试连接

```bash
python3 scripts/test_device.py my-board
```

## MCP Tools (24 个)

### 连接管理

| Tool | 用途 |
|------|------|
| `device_list` | 列出所有已注册设备 |
| `device_connect` | 连接设备，获取 session_id |
| `device_disconnect` | 断开连接 |
| `device_info` | 系统信息快照 (uname/cpu/mem/disk) |
| `device_list_sessions` | 查看活跃会话 |

### 命令执行 & 文件传输

| Tool | 用途 |
|------|------|
| `device_exec` | **核心工具** — 执行任意 Shell 命令 |
| `file_upload` | 上传文件 (SSH→SCP, 其他→base64) |
| `file_download` | 下载文件 |

### 日志采集

| Tool | 用途 |
|------|------|
| `dmesg_get` | 内核日志，支持级别过滤 |
| `dmesg_follow` | 持续采集 N 秒，支持 grep |
| `log_file_tail` | 读取任意日志文件尾部 |
| `journalctl_get` | systemd journal 查询 |

### 寄存器诊断

| Tool | 用途 |
|------|------|
| `reg_db_list_blocks` | 列出已加载的寄存器模块 |
| `reg_db_query` | 查询寄存器字段定义和 error_values |
| `reg_read` | 读单个寄存器 + 数据库自动解读 |
| `reg_read_range` | 批量读连续地址 |
| `reg_indirect_read` | 间接读表 (写索引→读数据) |
| `reg_dump_block` | 导出整个模块 + 异常诊断 |

### GDB 交互调试

| Tool | 用途 |
|------|------|
| `gdb_launch` | 启动 GDB，接管传输会话 |
| `gdb_exec` | 执行 GDB 命令 (break/run/bt/print...) |
| `gdb_close` | 退出 GDB，恢复 Shell 模式 |
| `gdbserver_start` | gdbserver 模式 (备选) |
| `gdbserver_stop` | 停止 gdbserver |

### 串口

| Tool | 用途 |
|------|------|
| `serial_list_ports` | 列出宿主机可用串口 |

## 领域专家 Skills

每个 skill 是一个独立的领域知识库，告诉 Agent 如何诊断特定类型的问题。**新增业务只需添加 skill 文件，无需改代码。**

| Skill | 领域 | 核心内容 |
|-------|------|---------|
| `network-diag.md` | 网口调试 | MAC/PHY/DMA 寄存器解读, CRC 错误定位, 丢包分析 |
| `i2c-debug.md` | I2C 调试 | 总线扫描, 设备读写, 控制器寄存器, 常见故障速查 |
| `spi-debug.md` | SPI 调试 | Flash 读写, 信号完整性, 模式验证, FIFO 诊断 |
| `boot-analysis.md` | 启动分析 | BootROM→U-Boot→Kernel→Userspace 全流程, systemd 分析 |
| `firmware-flash.md` | 固件烧写 | dd/fastboot/flashcp, 分区布局, 安全校验 |
| `log-analysis.md` | 日志分析 | Kernel panic/OOM, 驱动故障模式库, 日志特征匹配 |
| `gdb-debug.md` | GDB 调试 | gdbserver 工作流, ARM 寄存器速查, backtrace 分析 |

## 多 Agent 支持

| 能力 | Claude Code | OpenCode | 通用 MCP Agent |
|------|-------------|----------|---------------|
| MCP Tools (24) | ✅ `.mcp.json` | ✅ 标准 MCP 协议 | ✅ 标准 MCP 协议 |
| MCP instructions | ✅ 握手发送 | ✅ 握手发送 | ✅ 握手发送 |
| Skills (`.md`) | ✅ 自动注入 | ❌ 使用 `prompts/` | ❌ 使用 `prompts/` |
| Prompts (`.txt`) | ✅ 可手动加载 | ✅ 可手动加载 | ✅ 可手动加载 |
| AGENTS.md | ✅ 自动读取 | ✅ 自动读取 | ⚠️ Agent 决定 |

`prompts/` 目录提供与 `skills/` 内容相同的纯文本版本，任何 Agent 都可使用。

## 使用示例

### 场景 1：驱动开发调试

```
开发者: "刚编译的驱动模块在板子上加载失败，帮我看看"

Agent:
  1. device_connect("my-board") → session_id
  2. file_upload(session_id, "drv.ko", "/tmp/drv.ko")
  3. device_exec(session_id, "insmod /tmp/drv.ko 2>&1")
  4. dmesg_get(session_id, level="err", lines=50)
  5. → 发现 "Unknown symbol" 错误
  6. → 建议: 检查内核配置，该符号可能未导出或需先加载依赖模块
```

### 场景 2：网口不通

```
开发者: "eth0 一直 NO-CARRIER"

Agent:
  1. device_exec(session_id, "ip link show eth0")
  2. device_exec(session_id, "ethtool eth0")
  3. reg_dump_block(session_id, "gmac_mac")
     → DM=0 半双工!  RE=1 TE=1 OK
  4. reg_dump_block(session_id, "phy")
     → LINK_STATUS=0, AN_COMPLETE=0
  5. → 诊断: PHY 自协商失败，检查网线和 PHY 供电
```

### 场景 3：GDB 调试崩溃

```
开发者: "app 在板子上 segfault，帮我定位"

Agent:
  1. file_upload(session_id, "app_debug", "/tmp/app")
  2. gdb_launch(session_id, "/tmp/app")
  3. gdb_exec(session_id, "run")
     → SIGSEGV at 0x400600
  4. gdb_exec(session_id, "backtrace")
     → #0 process_data at main.c:42
  5. gdb_exec(session_id, "print ptr")
     → $1 = (void *) 0x0   ← 空指针!
  6. → 定位: main.c:42 处 ptr 未初始化
```

## 项目结构

```
embed_tool/
├── pyproject.toml                # wheel 构建与依赖声明
├── MANIFEST.in                   # sdist/wheel 数据文件清单
├── README.md                     # 本文件
├── AGENTS.md                     # 多 Agent 说明
├── CLAUDE.md                     # Claude Code 项目配置
├── .mcp.json                     # Claude Code MCP 配置
├── opencode.json                 # OpenCode MCP + instructions 配置
├── requirements.txt              # 兼容旧环境的依赖清单
│
├── mcp_server/                   # MCP Server Python 包
│   ├── server.py                 #   `embed-tool-mcp` 入口
│   ├── devices.json              #   wheel 内置设备模板
│   ├── device_registry.py        #   默认读取 ~/.config/embed-tool/devices.json
│   ├── transports/               #   SSH / Telnet / Serial 适配层
│   ├── sessions/                 #   连接池 + GDB 交互模式
│   ├── tools/                    #   MCP 工具注册与实现
│   └── registers/                #   寄存器数据库与 JSON 定义
│
├── .opencode/skills/             # OpenCode 原生 Skills
├── skills/                       # Claude Code 兼容领域专家
├── prompts/                      # Agent 无关纯文本领域指南
├── configs/                      # 通用 MCP 配置模板
└── scripts/test_device.py        # 设备连通性测试脚本
```

## 扩展指南

### 新增协议 (如 SSL/TLS)

1. 在 `transports/` 下创建 `ssl.py`
2. 继承 `BaseTransport`，实现 `connect/exec_command/close`
3. 在 `sessions/pool.py` 的 `_create_transport` 中注册

### 新增领域专家 (如 UART 调试)

1. 在 `skills/` 下创建 `uart-debug.md`
2. 声明依赖的 MCP 工具
3. 写入诊断流程和故障速查表
4. 同时在 `prompts/` 下创建同名 `.txt` 文件

无需修改任何 Python 代码。

### 新增芯片寄存器

1. 在 `mcp_server/registers/` 下创建 `my_chip_regs.json`
2. 按 `eth_mac_regs.json` 的格式填入寄存器定义
3. 确保该 JSON 文件被包含在包数据中（`pyproject.toml` 已包含 `mcp_server/registers/*.json`）

支持的 error_values 格式：
```json
"FIELD=0"     → 字段等于 0 时告警
"FIELD>100"   → 字段大于 100 时告警
"FIELD<5"     → 字段小于 5 时告警
```

## 已验证环境

| 项目 | 值 |
|------|-----|
| 测试设备 | EmbedFire LubanCat-1 |
| SoC | Rockchip RK3566 |
| 架构 | aarch64 (ARM Cortex-A55 ×4) |
| 内核 | Linux 4.19.232 |
| 系统 | Debian Buster |
| GDB | 8.2.1 (arm64 native) |
| SSH 测试 | 25 项全部通过 |
| 日志测试 | 14 项全部通过 |
| GDB 测试 | 全流程通过 (breakpoint→backtrace→print→continue) |

## 文档索引

| 文档 | 内容 |
|------|------|
| `README.md` | 本文件 — 项目概述和快速上手 |
| `AGENTS.md` | 多 Agent 支持说明 |
| `CLAUDE.md` | Claude Code 专用项目配置 |
| `pyproject.toml` | wheel 构建、依赖、`embed-tool-mcp` 命令入口 |

## License

MIT
