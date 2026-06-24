"""Tool modules — each file registers a domain of MCP tools.

Usage from server.py:
    from .tools import register_all
    mcp = FastMCP("embed-tool")
    register_all(mcp, pool, registry, reg_db)
"""


def register_all(mcp, pool, registry):
    """Register all domain tools on the FastMCP instance."""
    from . import connection, execution, file_transfer, logging as logtools
    from . import registers as regtools, gdb, serial_ports, ftp, flash

    modules = [connection, execution, file_transfer, logtools, regtools, gdb, serial_ports, ftp, flash]
    for mod in modules:
        mod.register(mcp, pool, registry=registry)
