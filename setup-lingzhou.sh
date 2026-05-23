#!/usr/bin/env bash
# setup-lingzhou.sh — 源码检出后的本地引导脚本

set -euo pipefail

SCRIPT_DIR="$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

export UV_NO_CONFIG=1

PYTHON_VERSION="3.12"
LINK_DIR="${LINGZHOU_LINK_DIR:-$HOME/.local/bin}"
LINK_PATH="$LINK_DIR/lingzhou"

_cyan()  { printf '\033[36m%s\033[0m\n' "$*"; }
_green() { printf '\033[32m%s\033[0m\n' "$*"; }
_red()   { printf '\033[31m%s\033[0m\n' "$*"; }
_bold()  { printf '\033[1m%s\033[0m\n' "$*"; }

find_uv() {
  if command -v uv >/dev/null 2>&1; then
    command -v uv
    return 0
  fi
  if [ -x "$HOME/.local/bin/uv" ]; then
    printf '%s\n' "$HOME/.local/bin/uv"
    return 0
  fi
  if [ -x "$HOME/.cargo/bin/uv" ]; then
    printf '%s\n' "$HOME/.cargo/bin/uv"
    return 0
  fi
  return 1
}

install_uv() {
  _cyan "> 安装 uv..."
  local installer
  installer="$(mktemp 2>/dev/null || printf '/tmp/lingzhou-uv-installer.%s.sh' "$$")"
  trap 'rm -f "$installer"' EXIT
  if ! curl -LsSf https://astral.sh/uv/install.sh -o "$installer"; then
    _red "下载 uv 安装脚本失败。请先手动安装 uv: https://docs.astral.sh/uv/"
    exit 1
  fi
  sh "$installer"
}

UV_BIN="$(find_uv || true)"
if [ -z "$UV_BIN" ]; then
  install_uv
  UV_BIN="$(find_uv || true)"
fi

if [ -z "$UV_BIN" ]; then
  _red "未找到 uv，可先手动安装后重试。"
  exit 1
fi

_bold "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
_bold "  lingzhou 源码引导"
_bold "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if "$UV_BIN" python find "$PYTHON_VERSION" >/dev/null 2>&1; then
  _green "✓ Python $PYTHON_VERSION 已可用"
else
  _cyan "> 安装 Python $PYTHON_VERSION..."
  "$UV_BIN" python install "$PYTHON_VERSION"
fi

_cyan "> 创建或更新虚拟环境..."
"$UV_BIN" venv .venv --python "$PYTHON_VERSION"

_cyan "> 安装 lingzhou（editable + test 依赖）..."
UV_PROJECT_ENVIRONMENT="$SCRIPT_DIR/.venv" "$UV_BIN" pip install -e ".[test]"

mkdir -p "$LINK_DIR"
ln -sfn "$SCRIPT_DIR/.venv/bin/lingzhou" "$LINK_PATH"

echo
_green "✓ 已完成源码安装"
printf '  源码目录: %s\n' "$SCRIPT_DIR"
printf '  命令链接: %s\n' "$LINK_PATH"
echo
echo "  下一步:"
echo "    1. 首次启动:        lingzhou"
echo "    2. 显式引导:        lingzhou onboard"
echo "    3. 运行测试:        .venv/bin/python -m pytest tests/ -q"
echo
if [[ ":$PATH:" != *":$LINK_DIR:"* ]]; then
  echo "  提示: 当前 PATH 不包含 $LINK_DIR"
  echo "        可添加: export PATH=\"$LINK_DIR:\$PATH\""
  echo
fi