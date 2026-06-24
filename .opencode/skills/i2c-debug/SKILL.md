---
name: i2c-debug
description: I2C/SPMI/SMBus bus diagnostics for ARM Linux embedded devices. Covers controller, bus scanning, device read/write, and common faults.
---

# I2C 调试专家

I2C/SPMI/SMBus 总线问题诊断。覆盖控制器→总线→外设完整链路。

## 依赖的 MCP 工具

| 工具 | 用途 |
|------|------|
| `device_exec` | 执行 i2c-tools 命令 |
| `reg_read` / `reg_dump_block` | 读 I2C 控制器寄存器 |
| `dmesg_get` | 查看内核 I2C 驱动日志 |
| `log_file_tail` | 查看系统日志中的 I2C 错误 |

## 诊断流程

### Step 1: 确认 I2C 总线是否可用

```bash
# 列出所有 I2C 总线
i2cdetect -l

# 扫描总线上的设备 (以 bus 0 为例)
i2cdetect -y 0

# 输出解读:
#   -- : 地址未应答 (正常, 该地址无设备)
#   UU : 地址被内核驱动占用
#   0xXX : 设备存在且应答
```

### Step 2: 设备有应答但驱动加载失败

```bash
# 检查内核日志
dmesg_get(session_id, level="err")
# 过滤 I2C 相关: filter_pattern="i2c|I2C"

# 常见错误模式:
# "i2c i2c-0: controller timed out" → 总线被拉死
# "i2c i2c-0: Failed to read" → 设备无响应
# "probe of XXXX failed with error -16" → 地址冲突
```

### Step 3: 直接读写设备寄存器

```bash
# 读设备寄存器 (设备地址 0x50, 寄存器 0x00, 读 1 字节)
i2cget -y 0 0x50 0x00

# 读 2 字节寄存器 (word)
i2cget -y 0 0x50 0x00 w

# 写寄存器
i2cset -y 0 0x50 0x00 0x42

# 批量 dump
i2cdump -y 0 0x50
```

### Step 4: I2C 控制器寄存器诊断

如有寄存器数据库:
```bash
# 查看 I2C 控制器状态
reg_dump_block(session_id, "i2c0")
# 关注:
#   I2C_CON.START/STOP   — 起始/停止条件
#   I2C_STATUS.TFNF      — TX FIFO 非满, 可以继续写
#   I2C_STATUS.RFNE      — RX FIFO 非空, 有数据可读
#   I2C_INTR.TX_ABRT     — 传输中止, 检查 ABRT_SOURCE
```

## 常见故障速查

| 现象 | 可能原因 | 诊断命令 |
|------|---------|---------|
| `i2cdetect` 全部 `--` | SCL/SDA 被拉低, 总线死锁 | 示波器量 SCL/SDA, 检查上拉电阻 |
| 单个地址 `--` | 设备未上电 / 地址错误 / 线序反 | 万用表量设备供电, 确认地址 |
| `controller timed out` | 从设备拉低 SCL 不放 (clock stretch 过长) | 检查从设备是否正常工作 |
| `probe failed -16` | 设备树地址与驱动不匹配 | `cat /sys/bus/i2c/devices/` |
| 数据全 0xFF 或全 0x00 | 设备未供电 / 复位中 / 已损坏 | 量供电, 查 reset 引脚电平 |
| 间歇性通信失败 | 上拉电阻过大 / 总线电容过大 | I2C 总线电容 < 400pF, 上拉 2k~5kΩ |

## 扩展寄存器数据库

为 I2C 控制器添加寄存器定义:

```json
{
  "blocks": [{
    "name": "i2c0",
    "base_address": "0xFFB00000",
    "registers": [
      {"name": "I2C_CON", "offset": "0x000", "address": "0xFFB00000", "width": 32,
       "fields": [
         {"name": "MASTER_MODE", "bits": "0", "description": "主模式使能"},
         {"name": "SPEED", "bits": "2:1", "description": "0=100K, 1=400K, 2=1M, 3=3.4M"},
         {"name": "RESTART_EN", "bits": "5", "description": "支持 Repeated START"}
       ]},
      {"name": "I2C_STATUS", "offset": "0x070", "address": "0xFFB00070",
       "fields": [
         {"name": "TFNF", "bits": "1", "description": "TX FIFO not full"},
         {"name": "RFNE", "bits": "3", "description": "RX FIFO not empty"},
         {"name": "MASTER_ACT", "bits": "5", "description": "Master FSM active"}
       ]}
    ]
  }]
}
```
