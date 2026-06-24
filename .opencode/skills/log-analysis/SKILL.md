---
name: log-analysis
description: Remote ARM Linux device log collection, filtering, and diagnostics. Covers kernel panics, OOM, driver fault patterns, dmesg, journalctl, and syslog analysis.
---

# 日志采集与分析助手

远程 ARM Linux 设备日志的采集、过滤、诊断知识库。

## 日志采集命令

### dmesg — 内核日志

```bash
# 查看所有日志
dmesg

# 只看错误及以上级别
dmesg --level=err,warn

# 带时间戳
dmesg -T

# 持续监控（尾随）
dmesg -w

# 按关键字过滤
dmesg | grep -iE 'error|fail|panic|oom|bug|fault'
```

### journalctl — systemd 日志（如果设备使用 systemd）

```bash
journalctl -n 200                    # 最近 200 条
journalctl -p err                    # 错误级别
journalctl -u my-service -f          # 跟踪特定服务
journalctl --since "10 min ago"      # 时间范围
```

### 应用日志

```bash
tail -f /var/log/syslog
tail -f /var/log/messages
tail -f /var/log/myapp.log
```

## 故障诊断速查

### Kernel Panic / Oops

**特征：**
```
Unable to handle kernel paging request at virtual address XXXXXXXX
Unable to handle kernel NULL pointer dereference at ...
Kernel panic - not syncing: ...
```

**排查步骤：**
1. 记录 PC 寄存器和 LR 寄存器地址
2. `dmesg | grep -B5 "Call trace:"` 查看调用栈
3. 用交叉工具链反汇编定位问题函数：
   `arm-linux-gnueabihf-addr2line -e vmlinux -f <PC地址>`
4. 常见原因：空指针、越界访问、驱动未初始化就使用

### OOM Killer

**特征：**
```
Out of memory: Killed process XXXXX (myapp) ...
oom-kill:constraint=CONSTRAINT_NONE ...
```

**排查步骤：**
1. `free -h` — 查看当前内存
2. `dmesg | grep -A20 "Out of memory"` — 查看 OOM 详细报告
3. `top -o %MEM` — 找内存大户
4. `cat /proc/<pid>/status | grep VmRSS` — 特定进程内存
5. 常见原因：内存泄漏、CMA 耗尽、应用申请过大 buffer

### 驱动故障

| 日志特征 | 可能原因 |
|---------|---------|
| `DMA: Out of SW-IOMMU space` | DMA 缓冲区耗尽 |
| `irq XX: nobody cared` | 中断没有 handler 或被意外触发 |
| `clk: failed to set rate` | 时钟配置不正确 |
| `spi_master spi0: timeout` | SPI 通信超时，检查引脚 |
| `i2c i2c-0: controller timed out` | I2C 设备无响应 |
| `mmc0: error -110` | eMMC/SD 卡通信超时 |

### 网络问题

```bash
# 检查网络接口
ip addr show
ifconfig -a

# 检查路由
ip route show

# 检查网络连接
dmesg | grep -iE 'eth|wlan|net'
```

## 采集和分析工作流

1. **先采集** — 用 device_exec 执行 `dmesg` 获取完整日志
2. **再过滤** — 根据问题类型过滤关键字
3. **对比正常日志** — 对比正常设备和异常设备同时间段的日志
4. **时序分析** — 注意日志时间戳，找出故障发生的先后顺序
