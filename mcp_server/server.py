"""Embed Tool MCP Server — embedded ARM Linux device remote debug assistant.

Thin entry point: creates FastMCP, loads register DB, registers all tools.

Architecture:
    Skills (knowledge) → Tools (domain logic) → Sessions → Transports (protocols)

Usage:
    python -m mcp_server.server          # stdio mode (Claude Code)
    python -m mcp_server.server --help
"""

import json
import logging
import os
import sys

# Quiet down paramiko transport logs
logging.getLogger("paramiko.transport").setLevel(logging.WARNING)

from mcp.server.fastmcp import FastMCP

from .device_registry import DeviceRegistry
from .sessions.pool import ConnectionPool
from .tools import register_all

# ── Global state ──────────────────────────────────────────────────────────────

CONFIG_PATH = os.environ.get(
    "EMBED_TOOL_DEVICES",
    os.path.join(os.path.dirname(__file__), "devices.json"),
)

registry = DeviceRegistry(CONFIG_PATH)
pool = ConnectionPool()

# ── FastMCP app ───────────────────────────────────────────────────────────────

mcp = FastMCP(
    "embed-tool",
    instructions="""嵌入式 ARM Linux 设备远程调试助手。通过 SSH/Telnet/Serial 连接设备。

## 核心工具
- device_list / device_connect / device_disconnect — 连接管理
- device_register / device_deregister / device_update — 设备注册与配置
- device_exec — 执行任意 Shell 命令 (最常用)
- device_info — 查看系统信息
- file_upload / file_download — SCP 文件传输

## 诊断工具
- dmesg_get / dmesg_follow / log_file_tail / journalctl_get — 日志采集
- reg_read / reg_read_range / reg_dump_block — 寄存器读写
- reg_db_query / reg_db_list_blocks — 查询寄存器定义
- reg_indirect_read — 间接读表 (写索引→读结果)
- gdb_launch / gdb_exec / gdb_close — GDB 交互调试

## 典型工作流
1. device_connect → 获得 session_id
2. device_info → 确认设备状态
3. device_exec → 编译/加载/测试
4. dmesg_get → 查看内核日志
5. gdb_launch → 启动调试 (如需要)
6. device_disconnect → 释放连接

## 注意事项
- GDB 会话期间 device_exec 被阻塞，用 gdb_close 退出恢复
- 寄存器读取前先用 reg_db_query 查看字段含义
- 烧写固件前务必备份 (参考 skills/firmware-flash.md)
""",
)

# Register all domain tools
register_all(mcp, pool, registry=registry)

# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    """Run the MCP server in stdio mode."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
