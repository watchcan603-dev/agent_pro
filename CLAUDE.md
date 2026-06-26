# 嵌入式助手 (Embed Tool)

AI 驱动的嵌入式 ARM Linux 设备远程调试助手。

### 架构

```
Skills (领域专家)  ← 新增业务只需加 Skill 文件
  ↓ 调用
MCP Tools (基础设施) ← 24 个基础工具, 按功能域拆分
  ↓ 调用
Session Pool (会话管理) ← 连接池 + GDB 模式切换
  ↓ 调用
Transports (协议适配) ← SSH / Telnet / Serial / (未来: SSL)
```

## 快速开始

### 1. 安装 wheel
```bash
python3 -m pip install --upgrade build
python3 -m build --wheel
python3 -m pip install dist/embed_tool-*.whl
```

### 2. 配置设备
编辑 `~/.config/embed-tool/devices.json`，填入设备 IP 和登录信息。也可以设置 `EMBED_TOOL_DEVICES` 指向自定义配置文件。

### 3. MCP Server 自动加载
项目根目录 `.mcp.json` 已配好，Claude Code 启动时自动加载。

## MCP Tools (24 个)

### 连接管理
`device_list` `device_connect` `device_disconnect` `device_info` `device_list_sessions`

### 命令执行 & 文件传输
`device_exec` `file_upload` `file_download`

### 日志采集
`dmesg_get` `dmesg_follow` `log_file_tail` `journalctl_get`

### 寄存器诊断
`reg_db_list_blocks` `reg_db_query` `reg_read` `reg_read_range` `reg_indirect_read` `reg_dump_block`

### GDB 调试
`gdb_launch` `gdb_exec` `gdb_close` `gdbserver_start` `gdbserver_stop`

### 串口
`serial_list_ports`

## 领域专家 Skills (7 个)

| Skill | 领域 | 用途 |
|-------|------|------|
| `network-diag.md` | 网口调试专家 | 以太网 MAC/PHY/DMA 寄存器诊断 |
| `i2c-debug.md` | I2C 调试专家 | I2C 总线扫描、设备读写、控制器寄存器 |
| `spi-debug.md` | SPI 调试专家 | SPI/QSPI Flash、信号完整性排查 |
| `boot-analysis.md` | 启动分析专家 | BootROM→U-Boot→Kernel→Userspace 全流程 |
| `firmware-flash.md` | 固件烧写专家 | dd/fastboot/flashcp 烧写与校验 |
| `log-analysis.md` | 日志分析专家 | 内核 panic/OOM/驱动故障模式匹配 |
| `gdb-debug.md` | GDB 调试专家 | gdbserver + GDB 交互模式工作流 |

### 如何新增领域专家

1. 在 `skills/` 下新建 `my-domain.md`
2. 文件头部声明依赖的 MCP 工具
3. 写入该领域的诊断流程、常见故障速查表

无需修改任何 Python 代码。Claude Code 会自动加载 skills/ 目录下的所有 `.md` 文件。

## 项目结构

```
embed_tool/
├── .mcp.json                     # MCP 配置
├── CLAUDE.md
├── pyproject.toml                  # wheel 构建配置
├── requirements.txt
├── mcp_server/
│   ├── server.py                 # embed-tool-mcp 入口
│   ├── devices.json              # wheel 内置设备模板
│   ├── device_registry.py
│   ├── transports/               # 协议适配层
│   │   ├── base.py               #   BaseTransport 接口
│   │   ├── ssh.py                #   SSH (paramiko + SCP) ✅
│   │   ├── telnet.py             #   Telnet (socket) 🧪
│   │   └── serial.py             #   Serial/COM (pyserial) 🧪
│   ├── sessions/                 # 会话管理层
│   │   ├── session.py            #   Session 数据类
│   │   ├── pool.py               #   ConnectionPool + GDB 追踪
│   │   └── gdb_session.py        #   GDB 交互模式管理器
│   ├── tools/                    # 领域工具层 (按功能域拆分)
│   │   ├── connection.py         #   device_list / connect / disconnect / info
│   │   ├── execution.py          #   device_exec
│   │   ├── file_transfer.py      #   file_upload / download
│   │   ├── logging.py            #   dmesg_get / follow / log_file_tail / journalctl
│   │   ├── registers.py          #   reg_read / range / indirect / dump / query
│   │   ├── gdb.py                #   gdb_launch / exec / close
│   │   └── serial_ports.py       #   serial_list_ports
│   └── registers/                # 寄存器数据库
│       ├── reg_db.py             #   数据库引擎
│       └── *.json                #   芯片寄存器定义
└── skills/                       # 领域专家 (Markdown, 无代码)
    ├── network-diag.md           #   网口调试
    ├── i2c-debug.md              #   I2C 调试
    ├── spi-debug.md              #   SPI 调试
    ├── boot-analysis.md          #   启动分析
    ├── firmware-flash.md         #   固件烧写
    ├── log-analysis.md           #   日志分析
    └── gdb-debug.md              #   GDB 调试
```

## 状态

- SSH: ✅ 稳定 (25 tests)
- 日志: ✅ 稳定 (14 tests)
- 寄存器诊断: ✅ 稳定
- GDB 交互: ✅ 稳定
- Telnet/Serial: 🧪 实验性
