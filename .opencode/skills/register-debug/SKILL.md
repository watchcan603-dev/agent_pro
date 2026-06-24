---
name: register-debug
description: Hardware register read/write and bit-field interpretation for ARM embedded devices. Covers DesignWare GMAC Ethernet, DMA, MMC statistics, and IEEE 802.3 PHY registers.
---

# 寄存器调试专家

寄存器原始值读取与比特位解读。**MCP 不做解读, LLM 根据本 Skill 解读 hex 值。**

## 依赖的 MCP 工具

| 工具 | 用途 |
|------|------|
| `device_exec` | 单寄存器读: `busybox devmem 0xADDR 32` |
| `reg_read_range` | 批量读连续地址 |
| `reg_indirect_read` | 间接读表 (写索引→读数据) |

## 寄存器读取方法

### 单寄存器读

```
device_exec(session_id, "busybox devmem 0xFE010000 32")
→ 0x08068203
```

### 批量读

```
reg_read_range(session_id, "0xFE010000", 8)
→ 返回 8 个连续 32-bit 寄存器的 hex 值
```

### 间接读表 (转发芯片统计表等)

```
reg_indirect_read(session_id,
    index_reg="0xSTAT_TABLE_INDEX",
    data_reg="0xSTAT_TABLE_DATA",
    index=0x10)
→ 先写 STAT_TABLE_INDEX=0x10, 再读 STAT_TABLE_DATA
```

## 解读方法

拿到 hex 值后, 用下面几步:

1. 转为二进制: `0x08068203` → `0000_1000_0000_0110_1000_0010_0000_0011`
2. 对照寄存器定义, 逐 bit/field 提取值
3. 根据 field 含义判断状态

## DesignWare GMAC 以太网寄存器 (RK3568)

基地址: GMAC0 = 0xFE010000

### GMAC_MAC_CONFIG @ 0xFE010000

主配置寄存器。值 = 全部 bits。

| Bit(s) | Name | 含义 | 诊断 |
|--------|------|------|------|
| 0 | RE | 0=RX关闭 1=RX使能 | RE=0 → 收不到任何帧 |
| 1 | TE | 0=TX关闭 1=TX使能 | TE=0 → 发不出帧 |
| 4:2 | PRELEN | Preamble Length, 0=7bytes | |
| 5 | DC | Deferral Check (half-duplex) | |
| 7:6 | BL | Back-off Limit | |
| 8 | DR | Disable Retry | |
| 9 | DCRS | Disable Carrier Sense | |
| 10 | DO | Disable Receive Own | |
| 11 | ECRSFD | Carrier Sense in Full Duplex | |
| 12 | LM | Loopback Mode, 1=内部环回 | **LM=1 → 环回模式, 正常通信时必须为0** |
| 13 | DM | Duplex Mode, 0=半双工 1=全双工 | **DM=0 → 半双工, 应为全双工** |
| 14 | FES | Fast Ethernet Speed, 0=10M 1=100M | 千兆时此位无意义 |
| 15 | PS | Port Select, 0=MII 1=RMII | |
| 16 | JE | Jumbo Frame Enable | |
| 17 | JF | Jabber Disable | |
| 19 | WD | Watchdog Disable | |
| 20 | ACS | Automatic Pad/CRC Stripping | |
| 21 | CST | CRC Stripping for Type frames | |
| 23:22 | SARC | Source Address Replacement | |
| 27:24 | IPG | Inter-Packet Gap | |
| 27 | IPC | Checksum Offload, 1=使能 | |
| 31 | S2KP | IEEE 802.3as Support | |

解读示例: `0x08068203`
```
bit0  = 1 → RE=1  RX使能 ✅
bit1  = 1 → TE=1  TX使能 ✅
bit12 = 0 → LM=0  非环回 ✅
bit13 = 0 → DM=0  ⚠️ 半双工!
bit14 = 0 → FES=0 10M
bit15 = 1 → PS=1  RMII
bit16 = 0 → JE=0  非巨型帧
bit17 = 1 → JF=1  Jabber禁用
bit27 = 1 → IPC=1  校验和卸载使能
```

### GMAC_MAC_FRAME_FILTER @ 0xFE010004

帧过滤器。

| Bit | Name | 含义 |
|-----|------|------|
| 0 | PR | Promiscuous Mode, 1=接收所有帧 |
| 1 | HUC | Hash Unicast |
| 2 | HMC | Hash Multicast |
| 3 | DAIF | DA Inverse Filtering |
| 4 | PM | Pass All Multicast |
| 5 | DBF | Disable Broadcast Frames, 1=丢弃广播 | **DBF=1 → ARP/DHCP会失败** |
| 6 | PBF | Pass Bad Frames, 1=接收错误帧(用于debug) | **PBF=1 → 正在收坏帧, 查CRC** |
| 7 | SAIF | SA Inverse Filtering |
| 8 | SAF | Source Address Filtering |
| 9 | HPF | Hash or Perfect Filter |
| 31 | RA | Receive All |

### GMAC_GMII_ADDR @ 0xFE010010

MDIO 控制寄存器 (访问外部 PHY)。

| Bit(s) | Name | 含义 |
|--------|------|------|
| 0 | GB | MII Busy, 1=MDIO 事务进行中 | **GB=1 → MDIO 操作未完成, PHY 无响应** |
| 1 | GW | MII Write, 1=Write 0=Read |
| 4:2 | CR | Clock Rate |
| 9:5 | GR | PHY Register Address (0-31) |
| 14:10 | PA | PHY Address (0-31) |

### GMAC_GMII_DATA @ 0xFE010014

MDIO 数据寄存器。配合 GMAC_GMII_ADDR 使用。

| Bit(s) | Name | 含义 |
|--------|------|------|
| 15:0 | GD | PHY Register Data (16-bit) |

### GMAC_FLOW_CTRL @ 0xFE010018

流控寄存器。

| Bit(s) | Name | 含义 |
|--------|------|------|
| 0 | FCB | Flow Control Busy (backpressure) |
| 1 | TFE | Transmit Flow Control Enable | **TFE=0 → 不发送 Pause 帧** |
| 2 | RFE | Receive Flow Control Enable | **RFE=0 → 接收流控关闭, 可能丢包** |
| 3 | UP | Unicast Pause Frame Detect |
| 6:4 | PLT | Pause Low Threshold |
| 7 | DZPQ | Disable Zero-Quanta Pause |
| 31:16 | PT | Pause Time value |

### GMAC_INT_STATUS @ 0xFE010038

中断状态。

| Bit | Name | 含义 |
|-----|------|------|
| 0 | RGMII | RGMII/SGMII PHY 状态变化 |
| 1 | PCSL | PCS Link Status Changed |
| 3 | PMT | Wake-on-LAN |
| 9 | PHY | PHY 中断 |
| 16 | NIS | Normal Interrupt Summary |
| 17 | AIS | Abnormal Interrupt Summary | **AIS=1 → 有异常, 需进一步检查** |

---

## DMA 寄存器 (基地址 0xFE011000)

### GMAC_DMA_BUS_MODE @ 0xFE011000

| Bit(s) | Name | 含义 |
|--------|------|------|
| 0 | SWR | Software Reset, 1=reset DMA, 自动清 |
| 1 | DA | DMA Arbitration |
| 4:2 | DSL | Descriptor Skip Length |
| 13:8 | PBL | Programmable Burst Length |
| 15:14 | PR | Priority Ratio RX/TX |
| 16 | FB | Fixed Burst |

### GMAC_DMA_STATUS @ 0xFE011014

DMA 状态和错误标志。

| Bit | Name | 含义 | 诊断 |
|-----|------|------|------|
| 0 | TI | Transmit Interrupt | |
| 1 | TPS | TX Process Stopped | **TPS=1 → TX 引擎停止, 检查 TX 描述符** |
| 2 | TU | TX Underflow | **TU=1 → TX FIFO 空了, DMA 带宽不足** |
| 3 | TJT | TX Jabber Timeout | |
| 4 | OVF | RX Overflow | **OVF=1 → RX FIFO 溢出, 丢包** |
| 5 | UNF | TX Underflow | 同 TU |
| 6 | RI | Receive Interrupt | |
| 7 | RU | RX Buffer Unavailable | **RU=1 → 驱动没分配 RX buffer** |
| 8 | RPS | RX Process Stopped | **RPS=1 → RX 引擎停止, 检查 RX 描述符** |
| 9 | RWT | RX Watchdog Timeout | |
| 13 | FBI | Fatal Bus Error | **FBI=1 → AXI 总线致命错误** |
| 16 | NIS | Normal Interrupt Summary | |
| 17 | AIS | Abnormal Interrupt Summary | |

### GMAC_MISSED_FRAME_CNT @ 0xFE01104C

| Bit(s) | Name | 含义 |
|--------|------|------|
| 15:0 | MISFRMCNT | Missed Frame Count | **>0 → 驱动来不及取帧** |
| 27:16 | OVFFRMCNT | Overflow Frame Count | **>0 → FIFO 溢出丢帧** |
| 28 | OVFCNTOVF | Missed counter overflow | |

---

## MMC 统计计数器 (基地址 0xFE010100)

### 关键计数器 (offset from MMC base)

| Offset | Name | 诊断意义 |
|--------|------|---------|
| 0x194 | RX CRC Error Counter | **>0 → 物理链路错误, 检查线缆/端接/EMC** |
| 0x198 | RX Alignment Error Counter | **>0 → 对齐错误, 通常伴随 CRC 错误** |
| 0x1C4 | RX FIFO Overflow Counter | **>0 → 系统来不及处理, 检查DMA和中断** |

---

## IEEE 802.3 PHY 寄存器 (通过 MDIO 访问)

PHY 寄存器通过 MDIO 总线访问。用 `ethtool eth0` 或读 GMAC_GMII_ADDR/DATA 来访问。

### PHY_BMCR (Basic Mode Control, offset 0x00)

| Bit | Name | 诊断 |
|-----|------|------|
| 15 | RESET | 1=PHY 复位中 |
| 14 | LOOPBACK | 1=环回 |
| 12 | AN_ENABLE | 0=自协商关闭 |
| 11 | POWER_DOWN | **1=PHY掉电, 链路必DOWN** |
| 10 | ISOLATE | **1=PHY电气隔离** |
| 8 | DUPLEX | 0=半双工 1=全双工 |

### PHY_BMSR (Basic Mode Status, offset 0x01)

| Bit | Name | 诊断 |
|-----|------|------|
| 5 | AN_COMPLETE | 0=自协商未完成 |
| 4 | REMOTE_FAULT | **1=对端报告故障** |
| 2 | LINK_STATUS | **0=物理链路DOWN** |

### PHY_1000_STATUS (1000BASE-T Status, offset 0x0A)

| Bit | Name | 诊断 |
|-----|------|------|
| 15 | MS_FAULT | **1=主从冲突, 两端都master** |
| 13 | LOCAL_RX_OK | **0=本端接收异常** |
| 12 | REMOTE_RX_OK | **0=对端接收异常** |

---

## 诊断流程

### 链路不通

```
1. device_exec(sid, "ip link show eth0")  → <NO-CARRIER>?
2. device_exec(sid, "ethtool eth0")       → Link detected: no?
3. device_exec(sid, "busybox devmem 0xFE010000 32")  → 读 MAC_CONFIG
   检查: RE=1? TE=1? LM=0? DM=1?
4. 如果 MAC_CONFIG 正常 → 问题在 PHY
   (PHY 寄存器通过 ethtool 访问)
```

### 丢包

```
1. device_exec(sid, "ethtool -S eth0")  → 查看统计
2. reg_read_range(sid, "0xFE011000", 8)  → DMA 寄存器
   检查: TPS? RPS? OVF? UNF? RU?
3. reg_read_range(sid, "0xFE010100", 0x20)  → MMC 计数器
   检查: CRC错误? Alignment错误? FIFO溢出?
```

### 吞吐低

```
1. 读 MAC_CONFIG → DM=1? (全双工)
2. 读 FLOW_CTRL → TFE=1? RFE=1? (流控使能)
3. 读 DMA_BUS_MODE → PBL 值 (Burst 长度)
4. device_exec(sid, "cat /proc/interrupts | grep eth")  → 中断分布
```

## 扩展

新增芯片的寄存器定义直接在此 Skill 文件中追加对应的表格即可。

格式: 块名 + 基地址 + 每个寄存器的字段表 + 诊断意义。
