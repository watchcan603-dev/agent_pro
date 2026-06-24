"""Register diagnostic tools — read, dump, query, indirect access."""
import json


def register(mcp, pool, reg_db=None, **kw):
    @mcp.tool()
    def reg_db_list_blocks() -> str:
        """列出已加载的寄存器模块 (block) 及其描述。"""
        if not reg_db or not reg_db.is_loaded:
            return json.dumps({"success": False, "error": "No register database loaded."}, ensure_ascii=False, indent=2)
        blocks = []
        for name in reg_db.list_blocks():
            b = reg_db.get_block(name)
            blocks.append({"name": name, "description": b.description, "base_address": b.base_address, "register_count": len(b.registers)})
        return json.dumps({"success": True, "chip": reg_db.chip_name, "block_count": len(blocks), "blocks": blocks}, ensure_ascii=False, indent=2)

    @mcp.tool()
    def reg_db_query(block_name: str, register_name: str = "") -> str:
        """查询寄存器数据库中的寄存器定义和字段含义。"""
        if not reg_db or not reg_db.is_loaded:
            return json.dumps({"success": False, "error": "No register database loaded."}, ensure_ascii=False, indent=2)
        block = reg_db.get_block(block_name)
        if not block:
            return json.dumps({"success": False, "error": f"Block '{block_name}' not found. Available: {reg_db.list_blocks()}"}, ensure_ascii=False, indent=2)
        if register_name:
            reg = block.get_register(register_name)
            if not reg:
                return json.dumps({"success": False, "error": f"Register '{register_name}' not found in '{block.name}'",
                                    "available_registers": [r.name for r in block.registers]}, ensure_ascii=False, indent=2)
            regs = [reg]
        else:
            regs = block.registers
        result = {"success": True, "block_name": block.name, "block_description": block.description, "base_address": block.base_address, "registers": []}
        for r in regs:
            result["registers"].append({
                "name": r.name, "offset": r.offset, "address": r.address,
                "width": r.width, "access": r.access, "description": r.description,
                "notes": r.notes,
                "fields": [{"name": f.name, "bits": f.bits, "description": f.description} for f in r.fields],
                "error_patterns": r.error_values,
            })
        return json.dumps(result, ensure_ascii=False, indent=2)

    @mcp.tool()
    def reg_read(session_id: str, address: str, width: int = 32) -> str:
        """读取远程设备单个寄存器 (busybox devmem) + 数据库自动解读。"""
        try:
            addr = address.lower().replace("0x", "")
            addr_int = int(addr, 16)
            cmd = f"busybox devmem 0x{addr} {width}"
            result = pool.exec_on_session(session_id, cmd, timeout=5)
            if result.exit_code != 0:
                return json.dumps({"success": False, "error": f"devmem failed: {result.stderr.strip()}"}, ensure_ascii=False, indent=2)
            raw = result.stdout.strip()
            value = int(raw, 16) if raw.startswith("0x") else int(raw, 0)
            interpretation = reg_db.interpret_register(addr_int, value) if reg_db else {}
            return json.dumps({
                "success": True, "address": f"0x{addr_int:08x}", "width": width,
                "raw_value": f"0x{value:0{width//4}x}", "raw_decimal": value,
                "database": interpretation,
            }, ensure_ascii=False, indent=2)
        except ValueError as e:
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)

    @mcp.tool()
    def reg_read_range(session_id: str, start_address: str, count: int, width: int = 32) -> str:
        """批量读取连续地址范围的寄存器值 (最多 64 个)。"""
        if count > 64: count = 64
        try:
            addr = start_address.lower().replace("0x", "")
            base = int(addr, 16)
            step = width // 8
            addrs = [f"0x{base + i * step:x}" for i in range(count)]
            cmd = " && ".join([f"echo '=== {a} ===' && busybox devmem {a} {width}" for a in addrs])
            result = pool.exec_on_session(session_id, cmd, timeout=15)
            results = []
            current_addr = None
            for line in result.stdout.split("\n"):
                line = line.strip()
                if line.startswith("=== ") and line.endswith(" ==="):
                    current_addr = line.replace("===", "").strip()
                elif line.startswith("0x") and current_addr:
                    value = int(line, 16)
                    addr_int = int(current_addr, 16)
                    interp = reg_db.interpret_register(addr_int, value) if reg_db else {}
                    results.append({"address": current_addr, "value": f"0x{value:0{width//4}x}", "decimal": value, "database": interp})
                    current_addr = None
            return json.dumps({"success": True, "start_address": f"0x{base:08x}", "count": count, "width": width, "registers": results}, ensure_ascii=False, indent=2)
        except ValueError as e:
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)

    @mcp.tool()
    def reg_indirect_read(session_id: str, index_reg: str, data_reg: str, index: int, width: int = 32) -> str:
        """间接寄存器读取 — 先写索引寄存器，再读数据寄存器 (用于转发芯片统计表等)。"""
        try:
            idx_addr = index_reg.lower().replace("0x", "")
            dat_addr = data_reg.lower().replace("0x", "")
            cmd = f"busybox devmem 0x{idx_addr} {width} {index} && busybox devmem 0x{dat_addr} {width}"
            result = pool.exec_on_session(session_id, cmd, timeout=5)
            if result.exit_code != 0:
                return json.dumps({"success": False, "error": f"Command failed: {result.stderr.strip()}"}, ensure_ascii=False, indent=2)
            lines = [l.strip() for l in result.stdout.strip().split("\n") if l.strip() and l.startswith("0x")]
            if len(lines) >= 2:
                data_value = int(lines[-1], 16)
                dat_addr_int = int(dat_addr, 16)
                interp = reg_db.interpret_register(dat_addr_int, data_value) if reg_db else {}
                return json.dumps({
                    "success": True, "index_register": index_reg, "data_register": data_reg,
                    "index_written": index, "data_value": f"0x{data_value:0{width//4}x}",
                    "data_decimal": data_value, "database": interp,
                }, ensure_ascii=False, indent=2)
            return json.dumps({"success": False, "error": f"Unexpected output: {result.stdout.strip()}"}, ensure_ascii=False, indent=2)
        except ValueError as e:
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)

    @mcp.tool()
    def reg_dump_block(session_id: str, block_name: str, include_fields: bool = True) -> str:
        """导出指定寄存器模块的所有寄存器值，并标注字段含义和异常诊断。"""
        if not reg_db or not reg_db.is_loaded:
            return json.dumps({"success": False, "error": "No register database loaded."}, ensure_ascii=False, indent=2)
        block = reg_db.get_block(block_name)
        if not block:
            return json.dumps({"success": False, "error": f"Block '{block_name}' not found. Available: {reg_db.list_blocks()}"}, ensure_ascii=False, indent=2)
        if not block.registers:
            return json.dumps({"success": False, "error": f"Block '{block_name}' has no register definitions."}, ensure_ascii=False, indent=2)
        try:
            if block.base_address == "MDIO":
                return _dump_phy(session_id, block, include_fields, pool)
            return _dump_mmio(session_id, block, include_fields, pool, reg_db)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)


def _dump_mmio(session_id, block, include_fields, pool, reg_db):
    results, diagnoses = [], []
    for reg in block.registers:
        addr = reg.address_int
        if addr < 0: continue
        try:
            result = pool.exec_on_session(session_id, f"busybox devmem 0x{addr:x} 32", timeout=5)
            if result.exit_code != 0:
                results.append({"name": reg.name, "address": reg.address, "error": result.stderr.strip()})
                continue
            raw = result.stdout.strip()
            value = int(raw, 16) if raw.startswith("0x") else int(raw, 0)
            entry = {"name": reg.name, "address": reg.address, "offset": reg.offset,
                     "description": reg.description, "raw_value": f"0x{value:08x}", "decimal": value, "access": reg.access}
            if include_fields and reg.fields:
                entry["fields"] = {}
                for f in reg.fields:
                    fv = f.extract(value)
                    entry["fields"][f.name] = {"value": f"0x{fv:x}", "decimal": fv, "bits": f.bits, "description": f.description}
                for pattern, meaning in reg.error_values.items():
                    if "=" in pattern:
                        fname, fval_str = pattern.split("=")
                        fname = fname.strip(); fval_str = fval_str.strip()
                        for f in reg.fields:
                            if f.name.lower() != fname.lower(): continue
                            try:
                                if fval_str.startswith("0x"): fval = int(fval_str, 16)
                                elif fval_str.startswith(">") and fval_str[1:].isdigit():
                                    if f.extract(value) > int(fval_str[1:]): diagnoses.append({"register": reg.name, "address": reg.address, "finding": meaning})
                                    continue
                                elif fval_str.startswith("<") and fval_str[1:].isdigit():
                                    if f.extract(value) < int(fval_str[1:]): diagnoses.append({"register": reg.name, "address": reg.address, "finding": meaning})
                                    continue
                                else: fval = int(fval_str)
                                if f.extract(value) == fval: diagnoses.append({"register": reg.name, "address": reg.address, "finding": meaning})
                            except (ValueError, IndexError): pass
            results.append(entry)
        except Exception as e:
            results.append({"name": reg.name, "address": reg.address, "error": str(e)})
    return json.dumps({"success": True, "block_name": block.name, "block_description": block.description,
                        "base_address": block.base_address, "registers_read": len(results),
                        "registers": results, "diagnoses": diagnoses, "diagnosis_count": len(diagnoses)}, ensure_ascii=False, indent=2)


def _dump_phy(session_id, block, include_fields, pool):
    results = []
    for reg in block.registers:
        results.append({"name": reg.name, "offset": reg.offset, "description": reg.description, "note": "PHY register via MDIO"})
    try:
        ethtool_r = pool.exec_on_session(session_id, "ethtool eth0 2>&1", timeout=5)
        eth_status = ethtool_r.stdout
    except Exception:
        eth_status = "ethtool not available"
    return json.dumps({"success": True, "block_name": block.name, "block_description": block.description,
                        "access_method": "MDIO (via ethtool)", "ethtool_status": eth_status,
                        "registers": results, "diagnoses": []}, ensure_ascii=False, indent=2)
