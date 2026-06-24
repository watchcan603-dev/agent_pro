#!/bin/bash
# 嵌入式助手 (Embed Tool) — 环境安装脚本
# 用法: bash scripts/setup.sh [--no-break-system-packages] [--mirror URL]
set -e

MIRROR="${MIRROR:-https://mirrors.aliyun.com/pypi/simple/}"
PIP_EXTRA=""

# 检查是否需要 --break-system-packages (Debian/Ubuntu 新版本)
if python3 -c "import sys; exit(0 if sys.version_info >= (3,11) else 1)" 2>/dev/null; then
    PIP_EXTRA="--break-system-packages"
fi

echo "========================================"
echo "  嵌入式助手 (Embed Tool) 环境安装"
echo "========================================"
echo ""

# 1. Python 依赖
echo "[1/2] 安装 Python 依赖..."
pip3 install $PIP_EXTRA -q -i "$MIRROR" \
    paramiko scp pexpect pyserial mcp 2>&1 | tail -1

echo "      完成: paramiko scp pexpect pyserial mcp"

# 2. 验证
echo "[2/2] 验证安装..."
python3 -c "
import sys; sys.path.insert(0, '.')
from mcp_server.server import mcp
print(f'      MCP Server: OK ({len(mcp._tool_manager._tools)} tools)')
from mcp_server.device_registry import DeviceRegistry
r = DeviceRegistry()
print(f'      Devices: {r.device_count} configured')
" 2>&1

echo ""
echo "========================================"
echo "  安装完成!"
echo "========================================"
echo ""
echo "下一步:"
echo "  1. 编辑 mcp_server/devices.json — 填入你的设备 IP 和登录信息"
echo "  2. Claude Code 启动时会自动加载 .mcp.json 中的 MCP server"
echo "  3. 测试: python3 scripts/test_device.py [device_id]"
echo ""
echo "如果 pip 安装失败:"
echo "  - 尝试其他镜像: MIRROR=https://pypi.org/simple/ bash scripts/setup.sh"
echo "  - 或手动安装: pip3 install paramiko scp pexpect pyserial mcp"
