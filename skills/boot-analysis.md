# 启动流程分析专家

ARM Linux 设备启动全流程分析。覆盖 BootROM → U-Boot → Kernel → Userspace。

## 依赖的 MCP 工具

| 工具 | 用途 |
|------|------|
| `device_exec` | 执行命令 |
| `dmesg_get` | 内核启动日志 |
| `journalctl_get` | systemd 启动日志 |
| `log_file_tail` | /var/log/boot.log, syslog |
| `file_upload` / `file_download` | 设备树/内核镜像传输 |

## ARM Linux 启动流程

```
BootROM (芯片内部)
  → 加载 U-Boot SPL/TPL
  → U-Boot SPL 初始化 DDR
  → 加载 U-Boot (完整版)
  → U-Boot 加载内核 + DTB
  → Kernel 初始化
  → init (systemd/busybox)
  → 用户空间服务
```

## 诊断命令速查

### 查看启动阶段耗时

```bash
# 内核启动时间
dmesg_get(session_id)
# 关注行首时间戳: [   0.123456] → 内核启动后秒数

# 用户空间启动时间
systemd-analyze                # 总启动时间
systemd-analyze blame          # 各服务耗时排行
systemd-analyze critical-chain # 关键路径

# 内核各阶段耗时 (如果启用了 initcall_debug)
dmesg_get(session_id, lines=500)
# 搜索: "initcall" → 每个驱动初始化耗时
```

### 查看设备和驱动加载

```bash
# 已加载的驱动模块
lsmod

# 驱动绑定关系
ls -la /sys/bus/*/drivers/

# 设备树节点
ls /proc/device-tree/
cat /proc/device-tree/model

# 内核命令行
cat /proc/cmdline
```

## 常见启动故障

### 故障 1: 内核 panic 无法启动

```bash
dmesg_get(session_id, level="err")
# 关键特征:
# "Kernel panic - not syncing: VFS: Unable to mount root fs"
#   → 根文件系统未找到, 检查 root= 参数 / initrd
# "Kernel panic - not syncing: No working init found"
#   → /sbin/init 不存在, 检查根文件系统完整性
# "Unable to handle kernel paging request"
#   → 驱动空指针, 用 GDB 定位
```

### 故障 2: 某驱动加载失败

```bash
# 查看具体驱动日志
dmesg_get(session_id, lines=500)
# 过滤: filter_pattern="driver_name|probe"

# 检查驱动是否在内核中
ls /sys/bus/*/drivers/driver_name/ 2>/dev/null
# 或
modprobe --dry-run driver_name 2>&1

# 手动加载驱动 (带调试)
insmod /path/to/driver.ko
# 或带参数
modprobe driver_name debug=1
```

### 故障 3: systemd 服务启动失败

```bash
# 失败的 service
systemctl --failed

# 特定服务日志
journalctl_get(session_id, unit="failed-service.service", priority="err")

# 查看依赖
systemctl list-dependencies failed-service.service
```

### 故障 4: 设备树不匹配

```bash
# 确认实际加载的 DTB
cat /proc/device-tree/compatible
dmesg_get(session_id, lines=100)
# 搜索: "Machine model:" → 显示匹配的设备树

# 如果 DTB 与硬件不匹配:
# - 外设不会被探测
# - 驱动不会加载
# - 症状: 某个设备完全不工作
```

## 启动优化检查清单

```
□ dmesg 中是否有长时间停顿 (>100ms 无日志)?
  → initcall_debug 定位慢的驱动

□ systemd-analyze blame 前 5 名是什么?
  → 禁用不需要的服务

□ 内核命令行是否包含 "quiet"?
  → 去掉 quiet 获取更多启动日志

□ rootfs 是否用了 initramfs?
  → initramfs 可能很慢, 考虑直接 rootfs

□ 是否有不必要的固件加载?
  → dmesg | grep "failed to load firmware"
```

## U-Boot 阶段诊断

```bash
# 如果通过串口/telnet 连接到 U-Boot:
# 查看环境变量
printenv

# 启动参数
printenv bootargs

# 内核加载地址
printenv kernel_addr_r
printenv fdt_addr_r

# 手动加载内核
tftp ${kernel_addr_r} zImage
tftp ${fdt_addr_r} board.dtb
bootz ${kernel_addr_r} - ${fdt_addr_r}
```
