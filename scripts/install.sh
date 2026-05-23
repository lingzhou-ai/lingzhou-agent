#!/usr/bin/env bash
# install.sh — lingzhou 一键安装脚本（Linux / macOS）
#
# 用法:
#   curl -fsSL https://raw.githubusercontent.com/suuugeee/lingzhou-agent/main/scripts/install.sh | bash
#
# 安装内容:
#   - 克隆或更新 lingzhou 到 ~/.lingzhou/src
#   - 复用仓库内的 setup-lingzhou.sh 完成 venv / 依赖 / CLI 链接
#   - 提示首次启动路径
#
# 幂等：重复运行不会损坏已有安装；只更新源码与依赖。

set -euo pipefail

LINGZHOU_HOME="${LINGZHOU_HOME:-$HOME/.lingzhou}"
LINGZHOU_REPO="https://github.com/suuugeee/lingzhou-agent.git"
LINGZHOU_SRC="$LINGZHOU_HOME/src"

_cyan()  { printf '\033[36m%s\033[0m\n' "$*"; }
_green() { printf '\033[32m%s\033[0m\n' "$*"; }
_red()   { printf '\033[31m%s\033[0m\n' "$*"; }
_bold()  { printf '\033[1m%s\033[0m\n'  "$*"; }
_dim()   { printf '\033[2m%s\033[0m\n'  "$*"; }

_bold "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
_bold "  lingzhou 安装程序"
_dim  "  自编程自进化认知 agent 种子"
_bold "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo

# ── 1. 检测 git ─────────────────────────────────────────────────────────────
if ! command -v git &>/dev/null; then
  _red "缺少 git，请先安装 git 后重试。"
  exit 1
fi

# ── 2. 克隆 / 更新仓库 ──────────────────────────────────────────────────────
mkdir -p "$LINGZHOU_HOME"

if [ -d "$LINGZHOU_SRC/.git" ]; then
  _cyan "» 更新 lingzhou 源码..."
  git -C "$LINGZHOU_SRC" pull --ff-only --quiet
else
  _cyan "» 克隆 lingzhou..."
  git clone --depth 1 "$LINGZHOU_REPO" "$LINGZHOU_SRC"
fi
_green "✓ 源码: $LINGZHOU_SRC"

# ── 3. 复用源码引导脚本 ────────────────────────────────────────────────────
cd "$LINGZHOU_SRC"
bash ./setup-lingzhou.sh

# ── 完成 ───────────────────────────────────────────────────────────────────
echo
_bold "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
_green "  安装完成！"
_bold "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo
echo "  下一步:"
echo "    1. 首次启动:        lingzhou"
echo "    2. 显式引导:        lingzhou onboard"
echo "    3. 微信接入:        lingzhou gateway setup --channel wechat"

echo
echo "  其他命令:"
echo "    lingzhou doctor     # 诊断运行环境"
echo "    lingzhou --version  # 查看版本"
echo "    lingzhou --help     # 帮助"
echo
