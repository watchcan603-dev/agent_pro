# 固件烧写助手

ARM Cortex-A Linux 设备固件烧写知识库。通过 MTD 分区进行 flash_erase + cat 烧写。

## 依赖的 MCP 工具

| 工具 | 用途 |
|------|------|
| `device_flash_list_cpus` | 列出所有支持的 CPU 和分区布局 |
| `device_flash` | 执行烧写: 检查→备份→擦除→写入→校验 |
| `device_flash_check` | 查看 MTD 分区信息 |
| `device_exec` | 查看分区布局、验证 |
| `file_upload` / `file_download` | 上传/下载固件文件 |

## CPU 分区速查表

### Rockchip RK3566 (aarch64)

| 分区 | MTD 设备 | 大小 | 说明 |
|------|---------|------|------|
| u-boot | /dev/mtd0 | 4MB | Bootloader (TPL/SPL + U-Boot) |
| u-boot-env | /dev/mtd1 | 512KB | U-Boot 环境变量 |
| kernel | /dev/mtd2 | 32MB | Linux 内核镜像 |
| dtb | /dev/mtd3 | 1MB | 设备树文件 |
| rootfs | /dev/mtd4 | 512MB | 根文件系统 |

### NXP i.MX6ULL (armv7l)

| 分区 | MTD 设备 | 大小 | 说明 |
|------|---------|------|------|
| u-boot | /dev/mtd0 | 2MB | Bootloader (.imx 格式) |
| kernel | /dev/mtd1 | 16MB | Linux 内核 (zImage) |
| dtb | /dev/mtd2 | 1MB | 设备树 |
| rootfs | /dev/mtd3 | 256MB | 根文件系统 (UBIFS) |

## 标准烧写流程

### 1. 查看设备分区

```bash
# 查看 MTD 分区
cat /proc/mtd

# 用 MCP 工具查看 CPU 分区布局
device_flash_list_cpus()

# 检查特定分区状态
device_flash_check(session_id, "/dev/mtd2")
```

### 2. 上传固件到设备

```bash
# 先用 file_upload 把固件传到设备
file_upload(session_id, "./Image", "/tmp/Image")
file_upload(session_id, "./rk3566-lubancat.dtb", "/tmp/rk3566.dtb")
```

### 3. 烧写固件

```bash
# device_flash 自动完成: 检查文件 → 备份 → flash_erase → cat → sync → 校验
device_flash(session_id, "rk3566", "kernel", "/tmp/Image")
device_flash(session_id, "rk3566", "dtb", "/tmp/rk3566.dtb")
```

等价的手动命令:
```bash
flash_erase /dev/mtd2 0 0 && cat /tmp/Image > /dev/mtd2 && sync
```

### 4. 烧写后验证

```bash
device_exec(session_id, "cmp /tmp/Image /dev/mtd2 && echo OK")
```

## 安全规则

- **自动备份**: device_flash 会在烧写前自动 `dd` 备份分区到 `/tmp/backup_*.bin`
- **大小校验**: 固件文件超过 `max_size_mb` 则拒绝烧写
- **rootfs 保护**: 当前挂载的 `/` 分区禁止擦除
- **u-boot 警告**: 标记为 `danger` 的分区会在 skill 层提示确认
- 烧写后务必 `sync`（device_flash 自动执行）

## 新增 CPU 支持

1. 在 `mcp_server/firmware/configs/` 下创建 `<cpu>.json`
2. 按模板填写分区信息，MCP server 启动时自动加载
3. 同时更新本 skill 的 CPU 分区速查表

配置模板:
```json
{
  "cpu": "芯片型号",
  "family": "芯片系列",
  "arch": "aarch64|armv7l|...",
  "vendor": "厂商",
  "flash_type": "mtd",
  "partitions": [
    {
      "name": "分区名",
      "mtd": "/dev/mtd0",
      "description": "用途说明",
      "max_size_mb": 4,
      "file_hint": "匹配的固件文件名模式",
      "danger": false,
      "notes": "额外注意事项"
    }
  ]
}
```

## 常见问题

| 症状 | 可能原因 | 排查 |
|------|---------|------|
| flash_erase 报 I/O error | MTD 有坏块 | `cat /proc/mtd` 确认分区存在 |
| 烧写后启动不了 | 内核和 dtb 不匹配 | 确认 dtb 文件与板卡型号一致 |
| reboot 还是旧固件 | 没 sync 或写错分区 | 检查 mtd 编号，确认 sync 执行 |
| 启动 kernel panic | 内核和 dtb 版本不一致 | 内核和设备树必须同版本编译 |
| u-boot 烧写后变砖 | 烧入了错误格式文件 | i.MX 需 .imx 格式，检查文件头 |
