#!/usr/bin/env bash
# ============================================================================
# embed-tool — 嵌入式助手一键安装脚本
#
# 用法:
#   bash install.sh                          # 交互式安装
#   bash install.sh --agent claude           # 指定 agent
#   bash install.sh --agent opencode         #
#   bash install.sh --agent generic --no-interact  # 非交互
#   bash install.sh --mirror https://pypi.tuna.tsinghua.edu.cn/simple
# ============================================================================
set -euo pipefail

# ── 参数解析 ──────────────────────────────────────────────────────────────────

AGENT=""
MIRROR="https://mirrors.aliyun.com/pypi/simple/"
NON_INTERACTIVE=false
SKIP_DEPS=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --agent)      AGENT="$2"; shift 2 ;;
        --mirror)     MIRROR="$2"; shift 2 ;;
        --no-interact) NON_INTERACTIVE=true; shift ;;
        --skip-deps)  SKIP_DEPS=true; shift ;;
        --help|-h)
            echo "用法: bash install.sh [选项]"
            echo ""
            echo "选项:"
            echo "  --agent claude|opencode|generic  指定 AI agent (默认: 交互选择)"
            echo "  --mirror URL                     pip 镜像地址"
            echo "  --no-interact                    非交互模式"
            echo "  --skip-deps                      跳过 Python 依赖安装"
            exit 0
            ;;
        *) echo "未知选项: $1"; exit 1 ;;
    esac
done

# ── 颜色 ──────────────────────────────────────────────────────────────────────

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'
info()  { echo -e "${GREEN}[✓]${NC} $1"; }
warn()  { echo -e "${YELLOW}[!]${NC} $1"; }
err()   { echo -e "${RED}[✗]${NC} $1"; }
step()  { echo -e "\n${BOLD}${CYAN}═══ $1 ═══${NC}"; }
abort() { err "$1"; exit 1; }

# ── 环境检测 ──────────────────────────────────────────────────────────────────

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

step "1/5 环境检测"

# Python
PYTHON=""
for py in python3 python; do
    if command -v $py &>/dev/null; then
        PYTHON=$py
        break
    fi
done
[[ -z "$PYTHON" ]] && abort "未找到 Python3。请先安装: apt install python3 或 brew install python3"
PYVER=$($PYTHON --version 2>&1)
info "Python: $PYVER"

# pip
if ! $PYTHON -m pip --version &>/dev/null; then
    warn "pip 未安装，尝试安装..."
    $PYTHON -m ensurepip --upgrade 2>/dev/null || \
        abort "pip 安装失败。手动安装: $PYTHON -m ensurepip --upgrade"
fi
info "pip: $($PYTHON -m pip --version 2>&1 | head -1)"

# Agent 检测
if [[ -z "$AGENT" ]] && [[ "$NON_INTERACTIVE" == false ]]; then
    echo ""
    echo "  检测到以下 AI Agent (自动检测):"
    which claude      &>/dev/null && echo "    - Claude Code (claude)"
    which opencode    &>/dev/null && echo "    - OpenCode (opencode)"
    echo ""
    echo "  请选择你要使用的 AI Agent:"
    echo "    [1] Claude Code"
    echo "    [2] OpenCode"
    echo "    [3] 通用 MCP Agent (手动配置)"
    echo "    [0] 仅安装依赖，不配置 Agent"
    read -rp "  输入数字 (1/2/3/0): " choice
    case "$choice" in
        1) AGENT="claude" ;;
        2) AGENT="opencode" ;;
        3) AGENT="generic" ;;
        0) AGENT="none" ;;
        *) AGENT="claude"; info "默认选择 Claude Code" ;;
    esac
elif [[ -z "$AGENT" ]]; then
    AGENT="generic"
    info "非交互模式，使用通用 MCP 配置"
fi

info "目标 Agent: ${AGENT}"

# ── Python 依赖 ───────────────────────────────────────────────────────────────

step "2/5 Python 依赖"

PIP_PACKAGES="paramiko scp pexpect pyserial mcp"
PIP_EXTRA=""

# Debian 12+ / Ubuntu 23.04+ 需要 --break-system-packages
$PYTHON -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)" 2>/dev/null && \
    PIP_EXTRA="--break-system-packages"

if [[ "$SKIP_DEPS" == true ]]; then
    warn "跳过依赖安装 (--skip-deps)"
else
    echo "  安装: $PIP_PACKAGES"
    echo "  镜像: $MIRROR"

    for pkg in paramiko scp pexpect pyserial mcp; do
        printf "  %-20s" "$pkg"
        if $PYTHON -c "import ${pkg//-/_}" 2>/dev/null; then
            echo -e "${GREEN}已安装${NC}"
        else
            if $PYTHON -m pip install $PIP_EXTRA -q -i "$MIRROR" "$pkg" 2>/tmp/pip_err.log; then
                echo -e "${GREEN}OK${NC}"
            else
                echo -e "${RED}失败${NC}"
                warn "错误日志: $(head -3 /tmp/pip_err.log)"
                echo ""
                echo "  手动重试:"
                echo "    pip3 install $PIP_EXTRA -i https://pypi.org/simple/ $pkg"
                echo "    或使用系统包: apt install python3-${pkg}"
            fi
        fi
    done

    # Verify critical packages
    for mod in paramiko mcp; do
        $PYTHON -c "import ${mod//-/_}" 2>/dev/null || \
            abort "关键模块 $mod 导入失败。检查安装: pip3 install $PIP_EXTRA $mod"
    done
fi

info "所有 Python 依赖就绪"

# ── MCP Server 验证 ───────────────────────────────────────────────────────────

step "3/5 MCP Server 验证"

cd "$PROJECT_DIR"
TOOL_COUNT=$($PYTHON -c "
import sys; sys.path.insert(0, '.')
from mcp_server.server import mcp
print(len(mcp._tool_manager._tools))
" 2>/dev/null) || TOOL_COUNT=0

if [[ "$TOOL_COUNT" -gt 0 ]]; then
    info "MCP Server 正常: $TOOL_COUNT 个工具已注册"
else
    abort "MCP Server 启动失败。检查: cd $PROJECT_DIR && python3 -m mcp_server.server"
fi

# ── 设备配置 ──────────────────────────────────────────────────────────────────

step "4/5 设备配置"

DEVICES_FILE="$PROJECT_DIR/mcp_server/devices.json"

if [[ ! -f "$DEVICES_FILE" ]]; then
    # Create from template
    cat > "$DEVICES_FILE" << 'DEVEOF'
{
  "devices": [
    {
      "id": "my-board",
      "name": "我的 ARM 开发板",
      "host": "192.168.1.100",
      "type": "ssh",
      "port": 22,
      "username": "root",
      "auth": { "method": "password", "password": "your_password" },
      "tags": ["arm"],
      "notes": "修改 host 和 password 为你设备的实际值"
    }
  ]
}
DEVEOF
    warn "已创建模板配置: $DEVICES_FILE"
    warn "请编辑此文件，填入你设备的实际 IP 和密码"
else
    info "设备配置文件已存在: $DEVICES_FILE"
    DEV_COUNT=$($PYTHON -c "
import sys; sys.path.insert(0, '.')
from mcp_server.device_registry import DeviceRegistry
print(DeviceRegistry().device_count)
" 2>/dev/null) || DEV_COUNT=0
    info "已配置 $DEV_COUNT 个设备"
fi

# ── Agent MCP 配置 ────────────────────────────────────────────────────────────

step "5/5 Agent 配置"

case "$AGENT" in
    claude)
        # Claude Code: .mcp.json already in project root
        if [[ -f "$PROJECT_DIR/.mcp.json" ]]; then
            info "Claude Code: .mcp.json 已就绪 (自动加载)"
        else
            cat > "$PROJECT_DIR/.mcp.json" << 'MCPEOF'
{
  "mcpServers": {
    "embed-tool": {
      "command": "python3",
      "args": ["-m", "mcp_server.server"]
    }
  }
}
MCPEOF
            info "Claude Code: 已创建 .mcp.json"
        fi
        echo ""
        echo "  Claude Code 会在项目目录启动时自动加载 MCP server。"
        echo "  也可以手动启用: claude mcp add embed-tool -- python3 -m mcp_server.server"
        ;;

    opencode)
        # OpenCode: opencode.json already in project root
        if [[ -f "$PROJECT_DIR/opencode.json" ]]; then
            info "OpenCode: opencode.json 已就绪 (自动加载 MCP server + skills)"
            echo ""
            echo "  项目根目录 opencode.json 已配置:"
            echo "    - MCP server: 24 个调试工具自动注册"
            echo "    - Instructions: AGENTS.md + prompts/ 知识库加载"
            echo "    - Skills: .opencode/skills/ 下 8 个领域专家自动发现"
            echo ""
            echo "  使用方法:"
            echo "    cd $PROJECT_DIR && opencode"
            echo ""
            echo "  如需全局配置 (所有项目可用):"
            echo "    将 configs/opencode.json 的 MCP 配置合并到 ~/.config/opencode/opencode.json"
        else
            # Fallback: create opencode.json in project root
            cat > "$PROJECT_DIR/opencode.json" << 'OCEOF'
{
  "$schema": "https://opencode.ai/config.json",
  "instructions": ["AGENTS.md", "prompts/*.txt"],
  "mcp": {
    "embed-tool": {
      "type": "local",
      "command": ["python3", "-m", "mcp_server.server"],
      "cwd": "."
    }
  }
}
OCEOF
            info "OpenCode: 已创建 opencode.json (MCP server + skills 配置)"
            echo ""
            echo "  使用方法:"
            echo "    cd $PROJECT_DIR && opencode"
        fi
        ;;

    generic)
        GENCONF="$PROJECT_DIR/configs/mcp-generic.json"
        $PYTHON -c "
import json
with open('$GENCONF') as f: cfg = json.load(f)
cfg['mcpServers']['embed-tool']['cwd'] = '$PROJECT_DIR'
with open('$GENCONF', 'w') as f: json.dump(cfg, f, indent=2)
" 2>/dev/null
        info "通用 MCP 配置: $GENCONF"
        echo ""
        echo "  MCP Server 启动命令:"
        echo "    cd $PROJECT_DIR && python3 -m mcp_server.server"
        echo ""
        echo "  将此命令配置到你的 agent 的 MCP server 列表中。"
        echo "  标准 MCP 配置格式见: $GENCONF"
        ;;

    none)
        info "跳过 Agent 配置"
        echo ""
        echo "  手动启动 MCP Server:"
        echo "    cd $PROJECT_DIR && python3 -m mcp_server.server"
        ;;
esac

# ── 完成 ──────────────────────────────────────────────────────────────────────

echo ""
echo -e "${BOLD}${CYAN}════════════════════════════════════════════${NC}"
echo -e "${BOLD}${CYAN}  安装完成!${NC}"
echo -e "${BOLD}${CYAN}════════════════════════════════════════════${NC}"
echo ""
echo -e "  ${BOLD}项目目录:${NC} $PROJECT_DIR"
echo -e "  ${BOLD}MCP Tools:${NC} $TOOL_COUNT 个"
echo -e "  ${BOLD}Domain Guides:${NC} $(ls skills/*.md 2>/dev/null | wc -l) skills + $(ls prompts/*.txt 2>/dev/null | wc -l) prompts"
echo ""
echo -e "${BOLD}下一步:${NC}"
echo "  1. 编辑设备配置: mcp_server/devices.json"
echo "  2. 测试连接:     python3 scripts/test_device.py [device_id]"
echo "  3. 启动 Agent:   claude    # 或 opencode, 或你的 MCP agent"
echo ""
echo -e "${BOLD}快速测试:${NC}"
echo "  cd $PROJECT_DIR"
echo "  python3 scripts/test_device.py"
echo ""
echo -e "${BOLD}文档:${NC}"
echo "  AGENTS.md    — 多 Agent 支持说明"
echo "  SUMMARY.md   — 项目总结"
echo "  CLAUDE.md    — Claude Code 项目说明"
