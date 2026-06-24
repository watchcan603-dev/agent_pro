"""Firmware flash manager — CPU-specific partition layouts and flash logic."""

import json
import os
from typing import Dict, List, Optional


class Partition:
    """A flashable partition on an embedded device."""

    def __init__(self, data: dict):
        self.name: str = data["name"]
        self.mtd: str = data["mtd"]
        self.description: str = data.get("description", "")
        self.max_size_mb: float = data.get("max_size_mb", 0)
        self.file_hint: str = data.get("file_hint", "")
        self.danger: bool = data.get("danger", False)
        self.notes: str = data.get("notes", "")

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "mtd": self.mtd,
            "description": self.description,
            "max_size_mb": self.max_size_mb,
            "file_hint": self.file_hint,
            "danger": self.danger,
            "notes": self.notes,
        }


class CpuFlashConfig:
    """Flash configuration for a specific CPU/SoC."""

    def __init__(self, data: dict):
        self.cpu: str = data["cpu"]
        self.family: str = data.get("family", self.cpu)
        self.arch: str = data.get("arch", "unknown")
        self.vendor: str = data.get("vendor", "")
        self.flash_type: str = data.get("flash_type", "mtd")
        self.partitions: List[Partition] = [
            Partition(p) for p in data.get("partitions", [])
        ]

    def get_partition(self, name: str) -> Optional[Partition]:
        for p in self.partitions:
            if p.name == name:
                return p
        return None

    def to_dict(self) -> dict:
        return {
            "cpu": self.cpu,
            "family": self.family,
            "arch": self.arch,
            "vendor": self.vendor,
            "flash_type": self.flash_type,
            "partitions": [p.to_dict() for p in self.partitions],
        }


class FlashManager:
    """Manages CPU-specific flash configurations and executes flash operations."""

    def __init__(self):
        config_dir = os.path.join(os.path.dirname(__file__), "configs")
        self._configs: Dict[str, CpuFlashConfig] = {}
        self._load_all(config_dir)

    def _load_all(self, config_dir: str) -> None:
        if not os.path.isdir(config_dir):
            return
        for fname in sorted(os.listdir(config_dir)):
            if fname.endswith(".json"):
                path = os.path.join(config_dir, fname)
                with open(path, "r") as f:
                    data = json.load(f)
                cfg = CpuFlashConfig(data)
                self._configs[cfg.cpu] = cfg

    def list_cpus(self) -> List[str]:
        return sorted(self._configs.keys())

    def get_config(self, cpu: str) -> Optional[CpuFlashConfig]:
        return self._configs.get(cpu)

    def flash_partition(self, pool, session_id: str, cpu: str,
                        partition_name: str, file_path: str) -> dict:
        """Flash a single partition: erase + write + sync + verify.

        Returns a dict with success/error and step details.
        """
        cfg = self.get_config(cpu)
        if not cfg:
            return {"success": False, "error": f"Unknown CPU: '{cpu}'. Available: {self.list_cpus()}"}

        part = cfg.get_partition(partition_name)
        if not part:
            return {"success": False, "error": f"Unknown partition '{partition_name}' for {cpu}. Available: {[p.name for p in cfg.partitions]}"}

        steps = []

        # Step 1: Check file exists on remote
        r = pool.exec_on_session(session_id, f"test -f {file_path} && echo OK || echo MISSING", timeout=5)
        if "MISSING" in r.stdout:
            return {"success": False, "error": f"File not found on device: {file_path}", "steps": steps}
        steps.append({"step": "check_file", "status": "ok", "detail": file_path})

        # Step 2: Check file size vs partition max_size
        r = pool.exec_on_session(session_id, f"stat -c%s {file_path}", timeout=5)
        try:
            file_bytes = int(r.stdout.strip())
            file_mb = file_bytes / (1024 * 1024)
        except (ValueError, AttributeError):
            file_bytes = 0
            file_mb = 0

        if part.max_size_mb > 0 and file_mb > part.max_size_mb:
            return {
                "success": False,
                "error": f"File too large: {file_mb:.1f}MB > partition max {part.max_size_mb}MB",
                "steps": steps,
            }
        steps.append({"step": "check_size", "status": "ok", "detail": f"{file_mb:.1f}MB"})

        # Step 3: Safety — refuse to flash rootfs if it's currently mounted
        if partition_name == "rootfs":
            r = pool.exec_on_session(session_id, f"mount | grep 'on / ' | grep {part.mtd}", timeout=5)
            if part.mtd in r.stdout:
                return {
                    "success": False,
                    "error": f"SAFETY: {part.mtd} is the current root filesystem. Boot from alternate media first.",
                    "steps": steps,
                }

        # Step 4: Backup before erase
        backup_path = f"/tmp/backup_{part.name}_{part.mtd.replace('/dev/', '')}.bin"
        r = pool.exec_on_session(session_id, f"dd if={part.mtd} of={backup_path} bs=4M status=none 2>&1; echo EXIT:$?", timeout=30)
        if "EXIT:0" not in r.stdout:
            steps.append({"step": "backup", "status": "warn", "detail": f"Backup may have failed: {r.stdout.strip()[:200]}"})
        else:
            steps.append({"step": "backup", "status": "ok", "detail": backup_path})

        # Step 5: Erase
        r = pool.exec_on_session(session_id, f"flash_erase {part.mtd} 0 0 2>&1; echo EXIT:$?", timeout=60)
        if "EXIT:0" not in r.stdout:
            return {"success": False, "error": f"flash_erase failed: {r.stdout.strip()[:300]}", "steps": steps}
        steps.append({"step": "erase", "status": "ok", "detail": part.mtd})

        # Step 6: Write
        r = pool.exec_on_session(session_id, f"cat {file_path} > {part.mtd} 2>&1; echo EXIT:$?", timeout=60)
        if "EXIT:0" not in r.stdout:
            return {"success": False, "error": f"Write failed: {r.stdout.strip()[:300]}", "steps": steps}
        steps.append({"step": "write", "status": "ok"})

        # Step 7: Sync
        r = pool.exec_on_session(session_id, "sync; echo EXIT:$?", timeout=10)
        steps.append({"step": "sync", "status": "ok"})

        # Step 8: Verify (compare first 4KB)
        r = pool.exec_on_session(
            session_id,
            f"cmp -n 4096 {file_path} {part.mtd} >/dev/null 2>&1 && echo MATCH || echo MISMATCH",
            timeout=10,
        )
        if "MISMATCH" in r.stdout:
            return {
                "success": False,
                "error": "Verification failed: first 4KB of written data does not match source file.",
                "steps": steps,
            }
        steps.append({"step": "verify", "status": "ok", "detail": "first 4KB match"})

        return {
            "success": True,
            "message": f"Flashed {part.name} ({part.mtd}) from {file_path}",
            "partition": part.name,
            "mtd": part.mtd,
            "file_size_mb": round(file_mb, 2),
            "backup": backup_path,
            "steps": steps,
        }
