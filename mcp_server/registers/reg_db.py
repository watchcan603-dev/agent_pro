"""Register database — structured register definitions for diagnostic analysis.

The register database is a JSON file containing chip-level register definitions
organized as blocks (functional units), each containing multiple registers with
bit-field descriptions and diagnostic interpretation rules.

Format:
{
  "chip": "Chip Name",
  "version": "1.0",
  "base_address_width": 32,
  "blocks": [
    {
      "name": "block_name",
      "description": "Functional block description",
      "base_address": "0x...",
      "registers": [
        {
          "name": "REG_NAME",
          "offset": "0x...",
          "address": "0x...",
          "width": 32,
          "access": "RO/RW/W1C/...",
          "description": "What this register does",
          "fields": [
            {"bits": "15:0", "name": "FIELD_NAME", "description": "..."}
          ],
          "notes": "Extra info for diagnosis"
        }
      ]
    }
  ]
}
"""

import json
import os
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field


@dataclass
class RegisterField:
    name: str
    bits: str  # e.g. "0", "15:8", "31"
    description: str

    @property
    def bit_mask(self) -> int:
        """Convert bit string to mask."""
        if ":" in self.bits:
            high, low = self.bits.split(":")
            width = int(high) - int(low) + 1
            return ((1 << width) - 1) << int(low)
        else:
            return 1 << int(self.bits)

    @property
    def bit_shift(self) -> int:
        """Get the shift amount for extracting field value."""
        if ":" in self.bits:
            return int(self.bits.split(":")[1])
        else:
            return int(self.bits)

    def extract(self, value: int) -> int:
        """Extract this field's value from a register value."""
        return (value & self.bit_mask) >> self.bit_shift


@dataclass
class RegisterDef:
    name: str
    offset: str
    address: str
    width: int = 32
    access: str = "RW"
    description: str = ""
    fields: List[RegisterField] = field(default_factory=list)
    notes: str = ""
    error_values: Dict[str, str] = field(default_factory=dict)
    # {value_pattern: meaning} for diagnostic interpretation

    @property
    def address_int(self) -> int:
        """Return address as integer. For PHY MDIO registers, return offset.
        Returns -1 if address is not parseable (e.g., symbolic name)."""
        try:
            return int(self.address, 16)
        except ValueError:
            # Symbolic address like "PHY_REG_0x00" — return offset
            try:
                return int(self.offset, 16)
            except ValueError:
                return -1

    @property
    def offset_int(self) -> int:
        try:
            return int(self.offset, 16)
        except ValueError:
            return -1

    def interpret(self, value: int) -> dict:
        """Interpret a register value, returning field values and any diagnostic notes."""
        result = {
            "raw_value": f"0x{value:0{self.width // 4}x}",
            "raw_decimal": value,
            "fields": {},
            "diagnosis": [],
        }

        for f in self.fields:
            fv = f.extract(value)
            result["fields"][f.name] = {
                "value": f"0x{fv:x}",
                "decimal": fv,
                "description": f.description,
            }

        # Check error patterns
        for pattern, meaning in self.error_values.items():
            if pattern.startswith("0x"):
                expected = int(pattern, 16)
                if value == expected:
                    result["diagnosis"].append(meaning)
            elif "=" in pattern:
                field_name, field_val = pattern.split("=")
                field_val = int(field_val, 16) if field_val.startswith("0x") else int(field_val)
                for f in self.fields:
                    if f.name.lower() == field_name.strip().lower():
                        if f.extract(value) == field_val:
                            result["diagnosis"].append(meaning)

        return result


@dataclass
class RegisterBlock:
    name: str
    description: str
    base_address: str
    registers: List[RegisterDef] = field(default_factory=list)

    @property
    def base_addr_int(self) -> int:
        return int(self.base_address, 16)

    def get_register(self, name: str) -> Optional[RegisterDef]:
        """Find a register by name (case-insensitive partial match)."""
        name_lower = name.lower()
        for r in self.registers:
            if r.name.lower() == name_lower:
                return r
        # Partial match
        for r in self.registers:
            if name_lower in r.name.lower():
                return r
        return None

    def get_register_by_address(self, address: str) -> Optional[RegisterDef]:
        """Find a register by address."""
        addr_int = int(address, 16) if isinstance(address, str) else address
        for r in self.registers:
            if r.address_int == addr_int:
                return r
        return None


class RegisterDatabase:
    """Load and query register definitions from JSON files."""

    def __init__(self, db_dir: Optional[str] = None):
        if db_dir is None:
            db_dir = os.path.join(os.path.dirname(__file__))
        self._db_dir = db_dir
        self._blocks: Dict[str, RegisterBlock] = {}
        self._all_registers: Dict[str, RegisterDef] = {}  # address -> reg
        self._chip_name = "Unknown"
        self._loaded = False

    def load(self, filename: str) -> None:
        """Load a register definition file."""
        filepath = os.path.join(self._db_dir, filename)
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Register database not found: {filepath}")

        with open(filepath, "r") as f:
            data = json.load(f)

        self._chip_name = data.get("chip", "Unknown")
        self._loaded = True

        for block_data in data.get("blocks", []):
            registers = []
            for reg_data in block_data.get("registers", []):
                fields = [
                    RegisterField(
                        name=f["name"],
                        bits=f["bits"],
                        description=f.get("description", ""),
                    )
                    for f in reg_data.get("fields", [])
                ]
                reg = RegisterDef(
                    name=reg_data["name"],
                    offset=reg_data["offset"],
                    address=reg_data["address"],
                    width=reg_data.get("width", 32),
                    access=reg_data.get("access", "RW"),
                    description=reg_data.get("description", ""),
                    fields=fields,
                    notes=reg_data.get("notes", ""),
                    error_values=reg_data.get("error_values", {}),
                )
                registers.append(reg)
                # Only add to address map if address is a real hex address
                if reg.address_int >= 0:
                    self._all_registers[reg.address_int] = reg

            block = RegisterBlock(
                name=block_data["name"],
                description=block_data.get("description", ""),
                base_address=block_data["base_address"],
                registers=registers,
            )
            self._blocks[block.name] = block

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def chip_name(self) -> str:
        return self._chip_name

    def list_blocks(self) -> List[str]:
        """List all loaded register blocks."""
        return list(self._blocks.keys())

    def get_block(self, name: str) -> Optional[RegisterBlock]:
        """Get a register block by name (case-insensitive partial match)."""
        name_lower = name.lower()
        # Exact match
        if name_lower in self._blocks:
            return self._blocks[name_lower]
        # Partial match
        for k, v in self._blocks.items():
            if name_lower in k.lower():
                return v
        return None

    def find_register(self, address: int) -> Optional[RegisterDef]:
        """Find a register definition by address."""
        return self._all_registers.get(address)

    def interpret_register(self, address: int, value: int) -> dict:
        """Interpret a register value against its definition."""
        reg = self.find_register(address)
        if reg is None:
            return {
                "address": f"0x{address:08x}",
                "value": f"0x{value:x}",
                "known": False,
                "note": "Register not in database",
            }
        result = reg.interpret(value)
        result["address"] = reg.address
        result["name"] = reg.name
        result["description"] = reg.description
        result["known"] = True
        return result

    def get_all_registers_in_block(self, block_name: str) -> List[RegisterDef]:
        """Get all register definitions in a block."""
        block = self.get_block(block_name)
        if block:
            return block.registers
        return []


# Global instance
_reg_db: Optional[RegisterDatabase] = None


def get_reg_db(db_dir: Optional[str] = None) -> RegisterDatabase:
    """Get or create the global register database instance."""
    global _reg_db
    if _reg_db is None:
        _reg_db = RegisterDatabase(db_dir)
    return _reg_db
