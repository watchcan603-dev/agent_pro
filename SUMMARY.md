# 嵌入式助手 (Embed Tool) — 项目总结与展望

## 一、项目概述

一个基于 Claude Code MCP Server 的嵌入式 ARM Linux 设备远程调试助手。通过网络协议（SSH/Telnet/Serial）连接设备，提供命令执行、文件传输、日志采集分析、寄存器诊断、GDB 交互调试等能力，结合 Skill 知识库辅助嵌入式底层驱动软件开发、调试和问题定位。

### 核心指标

| 指标 | 值 |
|------|-----|
| MCP Tools | 24 个 |
| 知识库 Skills | 4 个 |
| 传输协议 | SSH（稳定）/ Telnet（实验）/ Serial（实验） |
| 测试设备 | LubanCat-1 (RK3566, aarch64, Linux 4.19) |
| 测试通过 | SSH 25项 / 日志 14项 / GDB 全流程 / 寄存器诊断 |
| 代码规模 | ~2500 行 Python, ~600 行 Markdown |
| 打包体积 | 96KB (31 files) |

## 二、架构设计

### 整体分层

```
┌──────────────────────────────────────────────────┐
│                  Claude Code                      │
│                                                    │
│  ┌──────────────┐  ┌────────────────────────────┐ │
│  │ Skills (知识层)│  │ MCP Server (连接代理层)      │ │
│  │              │  │                            │ │
│  │ firmware-flash│  │  device_connect / exec     │ │
│  │ log-analysis │  │  file_upload / download    │ │
│  │ gdb-debug    │  │  dmesg / journalctl        │ │
│  │ network-diag │  │  reg_read / dump / query   │ │
│  │              │  │  gdb_launch / exec / close │ │
│  └──────────────┘  └──────────┬─────────────────┘ │
└────────────────────────────────┼──────────────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              ▼                  ▼                  ▼
         ┌─────────┐      ┌──────────┐      ┌──────────┐
         │   SSH   │      │  Telnet  │      │  Serial  │
         │paramiko │      │ socket   │      │ pyserial │
         └────┬────┘      └────┬─────┘      └────┬─────┘
              │                │                  │
    ┌─────────┴────────────────┴──────────────────┴──────┐
    │              嵌入式 ARM Linux 设备                    │
    │  Shell / GDB / devmem / dmesg / journalctl / ...    │
    └─────────────────────────────────────────────────────┘
```

### 关键设计决策

#### 1. MCP Server 做连接代理层

**为什么不直接用 Bash Tool？**  
Bash Tool 是"一次性执行等结果"模式。嵌入式调试需要持久连接、交互式会话、状态保持。MCP Server 维持连接池，每次 tool 调用复用同一个 SSH/telnet session。

#### 2. GDB 交互模式接管

**核心创新**：不依赖 gdbserver + 交叉 GDB 的传统方案，而是直接在设备上启动 GDB，通过同一个传输通道与之交互。

```
Shell 模式                        GDB 交互模式
┌──────────────────┐          ┌──────────────────┐
│ exec_command()   │          │ send_interactive()│
│ echo __BEGIN__   │  ──▶    │ break main\n      │
│ command          │          │ run\n             │
│ echo __END__:$?  │  ◀──    │ backtrace\n       │
│ marker 分隔      │          │ quit\n            │
└──────────────────┘          └──────────────────┘
         │                            │
         └── 同一个 TCP socket ───────┘
         切换的是解析模式，不是连接
```

#### 3. 寄存器数据库 + 自动诊断

用户提供芯片手册 → 填入 JSON → LLM 可以：
- 查询寄存器定义和字段含义
- 读取设备上的寄存器值
- 自动对比 error_values 输出诊断结论

这是"知识库 + 工具"的结合，LLM 负责理解手册内容辅助分析，工具负责精确读值。

## 三、功能矩阵

### MCP Tools (24个)

| 类别 | 工具 | 状态 |
|------|------|------|
| **连接管理** | device_list, device_connect, device_disconnect, device_info, device_exec, device_list_sessions | ✅ |
| **文件传输** | file_upload, file_download | ✅ |
| **日志采集** | dmesg_get, dmesg_follow, log_file_tail, journalctl_get | ✅ |
| **寄存器诊断** | reg_db_list_blocks, reg_db_query, reg_read, reg_read_range, reg_indirect_read, reg_dump_block | ✅ |
| **串口** | serial_list_ports | ✅ |
| **GDB调试** | gdb_launch, gdb_exec, gdb_close, gdbserver_start, gdbserver_stop | ✅ |

### Skills (4个)

| Skill | 内容 |
|-------|------|
| `firmware-flash.md` | 烧写方式对比 (dd/flashcp/fastboot), 分区布局, 安全检查清单, 芯片差异 |
| `log-analysis.md` | 内核 panic/oops 解读, OOM 排查, 驱动故障模式库, dmesg 分析流程 |
| `gdb-debug.md` | gdbserver 工作流, ARM 寄存器速查, backtrace 分析, GDB/MI 命令参考 |
| `network-diag.md` | 网络分层诊断流程, MAC/PHY/DMA 寄存器解读, 丢包/链路DOWN 速查表 |

## 四、实测验证

### 测试设备

| 项目 | 值 |
|------|-----|
| 型号 | EmbedFire LubanCat-1 |
| SoC | Rockchip RK3566 |
| 架构 | aarch64 (ARM Cortex-A55 ×4) |
| 内核 | Linux 4.19.232 |
| 系统 | Debian Buster |
| 内存 | 2GB |
| GDB | 8.2.1 (arm64 native) |

### SSH Transport 测试 (25项全部通过)

```
基础执行:   echo, 多行输出, cmd未找到, stderr, 200KB大输出
超时控制:   sleep正常返回, 强制超时, 长命令
文件传输:   上传, 下载, 1MB大文件
设备查询:   uname, CPU, 内存, 磁盘, 进程, 网络
会话管理:   列表, 无效ID异常, 关闭
特殊场景:   管道, 环境变量, &&链, ||或, $(cmd)替换
```

### GDB 交互模式测试 (全流程通过)

```
gdb_launch(sid, "/tmp/test_gdb")    ✅ Reading symbols...done.
gdb_exec(sid, "break add")           ✅ Breakpoint 1 at 0x770
gdb_exec(sid, "run")                 ✅ Stopped at add(a=10, b=20)
gdb_exec(sid, "backtrace")           ✅ #0 add, #1 main
gdb_exec(sid, "print a")             ✅ $1 = 10
gdb_exec(sid, "next")                ✅ main() at line 6
gdb_exec(sid, "continue")            ✅ Result: 30, exited normally
gdb_close(sid)                       ✅ Shell restored
device_exec(sid, "echo works")       ✅ Shell 恢复验证通过
device_exec during GDB               ✅ 正确阻塞
Re-launch GDB after close            ✅ 可重复启动
```

### 日志诊断实测

```
内核错误 (dmesg err): 50 行 — PCIe链路失败, DWC3时钟缺失
内核警告 (dmesg warn): 33 行 — GPU devfreq, HDMI
syslog 错误: 68 匹配行 — hostapd WiFi AP 启动失败
journal err: 21 行
诊断结论: 🔴 PCIe链路异常 🟡 非关键警告 🟢 无OOM/Panic
```

### 寄存器诊断实测

```
reg_read(sid, "0xFE010000")  → 0x08068203
  RE=1 ✅  TE=1 ✅
  DM=0 ⚠️ 半双工模式！
  Flow Control=0 ⚠️ 全部关闭
  PS=1 RMII模式
```

## 五、扩展方向

### 短期 (1-2周)

**1. Telnet/Serial 真机验证**
- 需要一个真实的串口服务器或 telnet 可访问的嵌入式设备
- 验证 login 流程在各种嵌入式系统上的兼容性
- 验证 GDB 交互模式在 telnet/serial 通道上的稳定性

**2. gdbserver 远程调试模式**
- 设备端启动 gdbserver，宿主机连接交叉 GDB
- 适用于需要宿主机符号文件、源码级调试的场景
- 可以与现有的"设备端 GDB"模式互补

**3. 寄存器数据库扩展**
- 支持从 CSV/Excel 直接导入寄存器定义（很多芯片手册是 Excel 格式）
- 增加更多芯片/外设的预置寄存器库（I2C、SPI、GPIO、Clock）
- 支持间接寄存器描述的链式依赖（eg. 读 A 寄存器 → 根据 bit3 值 → 读不同的 B 寄存器）

### 中期 (1-2月)

**4. 固件烧写工具**
- `flash_write` tool: 整合 dd / fastboot / 厂商工具
- 烧写前自动备份当前固件
- 烧写后自动校验 md5/sha256
- 支持分区表自动识别 (GPT/MBR)

**5. 多设备并行操作**
- 批量固件烧写
- 多设备同步执行命令
- 设备分组管理（产线/实验室/现场）

**6. 日志模板匹配引擎**
- 预定义常见故障的日志特征模板
- 采集日志后自动匹配并给出诊断建议
- 积累历史故障模式库

### 长期 (3-6月)

**7. 设备自动发现**
- mDNS/Avahi 扫描局域网内的 ARM Linux 设备
- 自动识别设备类型、芯片型号
- 支持动态添加/移除设备

**8. Web Dashboard**
- 设备状态面板：CPU/内存/温度/网络
- 日志实时流式展示
- 寄存器值可视化（bit field 展开图）
- 历史诊断记录

**9. CI/CD 集成**
- 烧写 + 测试 + 日志采集的自动化流水线
- 与 Jenkins/GitLab CI 集成
- 回归测试自动执行

## 六、是否适合做成 Claude Code 插件

### 结论：非常适合，且推荐做成 Plugin

### 对比分析

| 维度 | 当前形式 (MCP Server) | 做成 Plugin |
|------|----------------------|------------|
| 分发方式 | 手动 tar.gz 解压 + pip install | `claude plugins install embed-tool@marketplace` |
| 依赖管理 | 用户手动 pip install | 插件清单声明，自动安装 |
| 版本更新 | 手动下载覆盖 | `claude plugins update` 一键升级 |
| Skills 加载 | 需放在 Claude Code 项目目录 | 插件自动注入到 Claude 上下文 |
| MCP Server 启动 | 需配置 .mcp.json | 插件自动注册，零配置 |
| 多项目复用 | 每个项目拷一份 | 全局安装，所有项目可用 |
| 权限管理 | 手动 | Plugin manifest 声明所需权限 |
| 发现性 | 靠口碑传播 | 在 marketplace 中可被搜索 |

### Plugin 化需要做的工作

```
embed-tool/
├── .claude-plugin/
│   └── manifest.json          # 插件元数据：名称、版本、依赖、权限声明
├── mcp_server/                # 现有代码基本不变
├── skills/                    # 插件会自动注入到 Claude 上下文
├── CLAUDE.md                  # 项目说明 → 插件描述
└── requirements.txt           # Python 依赖 → manifest.dependencies
```

**manifest.json 示例：**
```json
{
  "name": "embed-tool",
  "version": "1.0.0",
  "description": "嵌入式 ARM Linux 设备远程调试助手",
  "author": { "name": "Embedded Tools Team" },
  "mcpServers": {
    "embed-tool": {
      "command": "python3",
      "args": ["-m", "mcp_server.server"]
    }
  },
  "skills": ["skills/"],
  "permissions": ["Bash", "Read", "Write"],
  "requirements": {
    "python": ">=3.10",
    "pip": ["paramiko>=3.0", "scp>=0.14", "pexpect>=4.9", "pyserial>=3.5", "mcp>=1.0"]
  }
}
```

## 七、多 Agent 协作模式

### 当前架构：单 Agent

```
Claude Code (单 Agent)
  └── MCP Server
       ├── SSH Transport ─── 设备 A
       ├── Telnet Transport ─── 设备 B
       └── Serial Transport ─── 设备 C
```

单 Agent 同时操作多设备时存在上下文窗口竞争问题——所有设备的状态、日志、寄存器值都在一个会话里，token 消耗线性增长。

### 演进方向：分层多 Agent

```
                      ┌─────────────┐
                      │ Orchestrator│  ← 编排 Agent (理解用户意图，分配任务)
                      │   Agent     │
                      └──┬───┬───┬──┘
                         │   │   │
            ┌────────────┼───┼───┼────────────┐
            ▼            ▼   ▼   ▼            ▼
      ┌──────────┐ ┌──────────┐ ┌──────────┐
      │ 烧写 Agent│ │诊断 Agent│ │监控 Agent│  ← 专业 Agent (各自聚焦)
      │ (设备A)   │ │ (设备B)   │ │ (设备C)   │
      └──────────┘ └──────────┘ └──────────┘
           │              │            │
           └──────────────┼────────────┘
                          │
                    MCP Server
                    (共享连接池)
```

### 典型协作场景

#### 场景 1：批量烧写 + 验证

```
User: "给实验室 5 台板子全部烧写 v2.1.0 固件"

Orchestrator Agent:
  ├── 并行烧写 (5 个子 Agent, 各操作一台设备)
  │   Agent-1: flash(board-01) → verify → report ✅
  │   Agent-2: flash(board-02) → verify → report ✅
  │   Agent-3: flash(board-03) → verify → report ❌ CRC mismatch
  │   Agent-4: flash(board-04) → verify → report ✅
  │   Agent-5: flash(board-05) → verify → report ✅
  │
  └── 汇总: 4/5 成功, board-03 需要重试
      Agent-3: retry → flash → verify → report ✅
      Final: 5/5 全部成功
```

#### 场景 2：多维度并行诊断

```
User: "设备 eth0 丢包率高，帮我全面诊断"

Orchestrator Agent:
  ├── Agent-A (PHY 层): 
  │    读 PHY 寄存器, ethtool 统计, 检查链路质量
  │    → 物理链路正常, 无 CRC 错误
  │
  ├── Agent-B (MAC/DMA 层):
  │    读 MAC MMC 计数器, DMA 状态寄存器
  │    → DMA FIFO 溢出, RX Buffer Unavailable
  │
  ├── Agent-C (驱动/系统层):
  │    查 dmesg, /proc/interrupts, NAPI 配置
  │    → 中断集中在 CPU0, 其他核空闲
  │
  └── Agent-D (网络协议栈):
      查 tc qdisc, socket buffer, iptables
      → 无异常
      
汇总诊断:
  根因: DMA 接收缓冲区不足 + 中断亲和性未配置
  建议: 增大 RX ring buffer + 配置 irqbalance
```

#### 场景 3：持续监控 + 主动告警

```
Cron: 每 5 分钟检查一次产线设备

Monitor Agent:
  ├── board-01: CPU 45°C, MEM 60%, Link OK     ✅
  ├── board-02: CPU 82°C ⚠️                     ← 温度偏高
  ├── board-03: Link DOWN 🔴                     ← 链路断开

  对 board-02: 启动诊断 Agent 查温度原因
  对 board-03: 启动诊断 Agent 查链路故障
  → 生成诊断报告, 发送告警
```

### 多 Agent 对 MCP Server 的要求

当前 MCP Server 已经具备基础条件：

| 已有能力 | 多 Agent 需要 |
|---------|-------------|
| 连接池 (多 session 共存) | ✅ 已支持，不同 Agent 用不同 session_id |
| 会话隔离 (session_id) | ✅ 已支持 |
| 无状态工具设计 | ✅ 所有 tool 接受 session_id 参数 |
| 并发安全性 | ⚠️ 需验证连接池的线程安全，加锁保护 |
| Agent 间通信 | ❌ 需增加：共享诊断结果、同步设备状态 |

## 八、总结

### 项目价值

1. **降低嵌入式调试门槛** — 不需要记忆复杂的手册和命令，AI 帮你查手册、组命令、解读结果
2. **知识沉淀** — register database + error_values + skills 是可积累、可复用的知识资产
3. **协议无关架构** — SSH/Telnet/Serial 统一接口，新增协议只需实现 BaseTransport
4. **交互模式接管** — 在不增加额外连接的情况下实现了 GDB 持久会话，是轻量嵌入式场景的最优解

### 下一步行动建议

| 优先级 | 事项 | 工作量 |
|--------|------|--------|
| P0 | 插件化 (manifest.json + marketplace 发布) | 1天 |
| P1 | Telnet/Serial 真机验证 | 1天 |
| P2 | 寄存器 CSV/Excel 导入 | 2天 |
| P3 | 多 Agent 协作原型 (Orchestrator + 诊断 Agent) | 3天 |
| P4 | Web Dashboard | 5天 |
