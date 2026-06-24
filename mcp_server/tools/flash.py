"""Firmware flash tools — CPU-specific partition flashing via flash_erase + cat."""
import json

from ..firmware.flash_mgr import FlashManager


_flash_mgr = None


def _get_fmgr():
    global _flash_mgr
    if _flash_mgr is None:
        _flash_mgr = FlashManager()
    return _flash_mgr


def register(mcp, pool, registry=None, **kw):
    @mcp.tool()
    def device_flash_list_cpus() -> str:
        """列出所有支持的 CPU 类型及其分区布局。"""
        fmgr = _get_fmgr()
        result = []
        for cpu_id in fmgr.list_cpus():
            cfg = fmgr.get_config(cpu_id)
            result.append(cfg.to_dict())
        return json.dumps({"count": len(result), "cpus": result}, ensure_ascii=False, indent=2)

    @mcp.tool()
    def device_flash(session_id: str, cpu: str, partition: str, file_path: str) -> str:
        """擦除并烧写设备上指定 CPU 类型的某个分区。

        烧写流程: 检查文件 → 备份 → flash_erase → cat 写入 → sync → 校验
        cpu: CPU 类型 (如 rk3566, imx6ull)
        partition: 分区名 (如 u-boot, kernel, dtb, rootfs)
        file_path: 设备上固件文件的绝对路径 (先用 file_upload 上传)
        """
        fmgr = _get_fmgr()
        result = fmgr.flash_partition(pool, session_id, cpu, partition, file_path)
        return json.dumps(result, ensure_ascii=False, indent=2)

    @mcp.tool()
    def device_flash_check(session_id: str, mtd_device: str) -> str:
        """检查设备上 MTD 分区的信息 (大小、擦除块大小、是否挂载)。"""
        try:
            # MTD info
            r = pool.exec_on_session(session_id, f"cat /proc/mtd 2>/dev/null | grep -E '(^dev:|{mtd_device})' || echo NO_MTD", timeout=5)
            mtd_info = r.stdout.strip() if r.stdout.strip() != "NO_MTD" else "N/A"
            # Check if mounted
            r2 = pool.exec_on_session(session_id, f"mount 2>/dev/null | grep {mtd_device} || echo NOT_MOUNTED", timeout=5)
            mounted = r2.stdout.strip()
            # Check if mtd device exists
            r3 = pool.exec_on_session(session_id, f"test -e {mtd_device} && echo EXISTS || echo MISSING", timeout=5)
            exists = "EXISTS" in r3.stdout

            return json.dumps({
                "success": True,
                "mtd_device": mtd_device,
                "exists": exists,
                "mtd_info": mtd_info,
                "mounted_as": mounted if mounted != "NOT_MOUNTED" else None,
            }, ensure_ascii=False, indent=2)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)
