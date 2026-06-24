"""Register I/O tools — pure read operations, no knowledge encoded.

Knowledge (field meanings, error patterns, diagnostic rules) lives in
skills/register-debug.md. The LLM interprets hex values using that knowledge.
"""
import json


def register(mcp, pool, **kw):
    @mcp.tool()
    def reg_read_range(session_id: str, start_address: str, count: int,
                        width: int = 32) -> str:
        """批量读取连续地址范围的寄存器值 (最多 64 个)。

        Returns raw hex values. LLM interprets them using register-debug skill.

        Args:
            session_id: 会话 ID。
            start_address: 起始物理地址 (hex), 如 "0xFE010000"。
            count: 连续读取个数 (最大 64)。
            width: 位宽, 默认 32。
        """
        if count > 64:
            count = 64
        try:
            addr = start_address.lower().replace("0x", "")
            base = int(addr, 16)
            step = width // 8
            addrs = [f"0x{base + i * step:x}" for i in range(count)]
            cmd = " && ".join(
                [f"echo '=== {a} ===' && busybox devmem {a} {width}" for a in addrs]
            )
            result = pool.exec_on_session(session_id, cmd, timeout=15)
            results = []
            current_addr = None
            for line in result.stdout.split("\n"):
                line = line.strip()
                if line.startswith("=== ") and line.endswith(" ==="):
                    current_addr = line.replace("===", "").strip()
                elif line.startswith("0x") and current_addr:
                    value = int(line, 16)
                    results.append({
                        "address": current_addr,
                        "hex": f"0x{value:0{width // 4}x}",
                        "decimal": value,
                    })
                    current_addr = None
            return json.dumps({
                "success": True,
                "start_address": f"0x{base:08x}",
                "count": count,
                "width": width,
                "registers": results,
            }, ensure_ascii=False, indent=2)
        except ValueError as e:
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)

    @mcp.tool()
    def reg_indirect_read(session_id: str, index_reg: str, data_reg: str,
                           index: int, width: int = 32) -> str:
        """间接寄存器读取 — 先写索引寄存器，再读数据寄存器。

        用于转发芯片统计表、MAC地址表等需要写索引再读数据的场景。
        **注意**: 会对 index_reg 执行 WRITE 操作。

        Args:
            session_id: 会话 ID。
            index_reg: 索引寄存器物理地址 (hex)。
            data_reg: 数据寄存器物理地址 (hex)。
            index: 要读取的表项索引值。
            width: 位宽, 默认 32。
        """
        try:
            idx_addr = index_reg.lower().replace("0x", "")
            dat_addr = data_reg.lower().replace("0x", "")
            cmd = (
                f"busybox devmem 0x{idx_addr} {width} {index} && "
                f"busybox devmem 0x{dat_addr} {width}"
            )
            result = pool.exec_on_session(session_id, cmd, timeout=5)
            if result.exit_code != 0:
                return json.dumps({
                    "success": False,
                    "error": f"Command failed: {result.stderr.strip()}",
                }, ensure_ascii=False, indent=2)

            lines = [
                l.strip() for l in result.stdout.strip().split("\n")
                if l.strip() and l.startswith("0x")
            ]
            if len(lines) >= 2:
                data_value = int(lines[-1], 16)
                return json.dumps({
                    "success": True,
                    "index_register": index_reg,
                    "data_register": data_reg,
                    "index_written": index,
                    "hex": f"0x{data_value:0{width // 4}x}",
                    "decimal": data_value,
                }, ensure_ascii=False, indent=2)
            return json.dumps({
                "success": False,
                "error": f"Unexpected output: {result.stdout.strip()}",
            }, ensure_ascii=False, indent=2)
        except ValueError as e:
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)
