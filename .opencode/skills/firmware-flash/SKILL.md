---
name: firmware-flash
description: ARM Cortex-A Linux device firmware flashing guide covering dd, fastboot, flashcp, partition layouts, backup, and verification for embedded devices.
---

# 固件烧写助手

ARM Cortex-A Linux 设备固件烧写知识库。

## 核心流程

### 1. 先了解设备分区布局

```bash
# 查看块设备
lsblk

# 查看分区详情
blkid

# MTD 设备（NAND/NOR Flash）
cat /proc/mtd

# 查看 eMMC 分区
fdisk -l /dev/mmcblk0
```

### 2. 备份现有固件（烧写前必须做！）

```bash
# 备份整个 eMMC
dd if=/dev/mmcblk0 of=/tmp/backup_emmc.img bs=4M status=progress

# 备份单个分区
dd if=/dev/mmcblk0p1 of=/tmp/backup_boot.img bs=4M status=progress

# 校验备份
md5sum /tmp/backup_emmc.img
```

### 3. 烧写方式

#### 方式 A：dd 写入（最通用，适用于运行中的 Linux）

```bash
# 写入 bootloader（通常在 mmcblk0boot0 或前几个扇区）
dd if=u-boot.imx of=/dev/mmcblk0 bs=1K seek=1 conv=fsync

# 写入分区镜像
dd if=boot.img of=/dev/mmcblk0p1 bs=4M conv=fsync

# 写入整个磁盘镜像
dd if=system.img of=/dev/mmcblk0 bs=4M conv=fsync
```

#### 方式 B：flashcp（MTD 设备）

```bash
flashcp -v rootfs.ubi /dev/mtd3
```

#### 方式 C：fastboot（需要设备处于 bootloader 模式）

```bash
# 设备端：进入 U-Boot 后执行 fastboot
# U-Boot> fastboot usb

# PC 端：
fastboot flash boot boot.img
fastboot flash rootfs rootfs.ext4
fastboot reboot
```

### 4. 烧写后验证

```bash
# 校验写入的数据
dd if=/dev/mmcblk0p1 bs=4M | md5sum
# 与本地 boot.img 的 md5 对比

# 同步并重启
sync
reboot
```

## 常见问题

| 症状 | 可能原因 | 排查命令 |
|------|---------|---------|
| dd 写入后启动不了 | 写入了错误的分区/偏移 | `fdisk -l`, 确认分区表 |
| flashcp 报 I/O error | MTD 分区有坏块 | `dmesg \| grep -i bad`, `nanddump` |
| reboot 后还是旧固件 | 没 sync，或写到了错误的 mmcblk | `mount \| grep mmcblk` 确认挂载 |
| 启动到 kernel panic | 内核和 dtb 不匹配 | 检查 dtb 路径，`ls /boot/` |

## 芯片厂商特殊说明

| 厂商 | 烧写工具 | 备注 |
|------|---------|------|
| NXP i.MX | uuu (mfgtool) 或 dd | U-Boot 放在 1KB 偏移处 |
| TI Sitara | dfu-util 或 dd | 第一分区通常是 FAT boot |
| Rockchip | rkdeveloptool | 需要进入 maskrom 模式 |
| Allwinner | sunxi-fel | 通过 USB OTG 烧写 |
| 树莓派 | 直接写 SD 卡 | `dd if=xxx.img of=/dev/sdX` |

## 安全规则

- **永远不要** 对正在挂载的 `/` 分区执行 `dd` 写入
- **始终** 在烧写前备份当前固件
- **始终** 烧写后做 `sync` 再 `reboot`
- 烧写 bootloader 时，确认写入的偏移地址与芯片手册一致
