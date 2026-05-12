#!/usr/bin/env bash
# install.sh — lingzhou 一键安装脚本（Linux / macOS）
#
# 用法:
#   curl -fsSL https://raw.githubusercontent.com/your-org/lingzhou/main/scripts/install.sh | bash
#
# 安装内容:
#   - 检测/安装 uv（Astral 的高速 Python 包管理器）
#   - 克隆 lingzhou 到 ~/.lingzhou/src（如尚未存在）
#   - 用 uv 创建 .venv（Python 3.12），安装依赖
#   - 将 lingzhou 可执行文件链接到 ~/.local/bin/lingzhou
#   - 提示下一步操作
#
# 幂等：重复运行不会损坏已有安装；只更新依赖。

set -euo pipefail

LINGZHOU_HOME="${LINGZHOU_HOME:-$HOME/.lingzhou}"
LINGZHOU_REPO="https://github.com/your-org/lingzhou.git"  # 替换为实际地址
LINGZHOU_SRC="$LINGZHOU_HOME/src"
LINGZHOU_BIN="$HOME/.local/bin/lingzhou"
MIN_PYTHON="3.12"

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

# ── 1. 检测 uv ──────────────────────────────────────────────────────────────
if ! command -v uv &>/dev/null; then
  _cyan "» 安装 uv（Python 包管理器）..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.cargo/bin:$PATH"
  if ! command -v uv &>/dev/null; then
    _red "uv 安装失败，请手动安装: https://github.com/astral-sh/uv"
    exit 1
  fi
else
  _green "✓ uv $(uv --version)"
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

# ── 3. 创建虚拟环境并安装依赖 ──────────────────────────────────────────────
cd "$LINGZHOU_SRC"
_cyan "» 创建虚拟环境 (Python $MIN_PYTHON)..."
uv venv .venv --python "$MIN_PYTHON" --quiet

_cyan "» 安装依赖..."
uv pip install -e "." --quiet

_green "✓ 依赖安装完成"

# ── 4. 链接可执行文件 ──────────────────────────────────────────────────────
mkdir -p "$HOME/.local/bin"

# 写包装脚本（兼容 venv 绝对路径）
cat >"$LINGZHOU_BIN" <<EOF
#!/usr/bin/env bash
exec "$LINGZHOU_SRC/.venv/bin/python" "$LINGZHOU_SRC/lingzhou.py" "\$@"
EOF
chmod +x "$LINGZHOU_BIN"

_green "✓ 可执行文件: $LINGZHOU_BIN"

# ── 5. 确保 ~/.local/bin 在 PATH 里 ───────────────────────────────────────
_need_path=0
for _shell_rc in "$HOME/.bashrc" "$HOME/.zshrc"; do
  if [ -f "$_shell_rc" ] && ! grep -q '\.local/bin' "$_shell_rc"; then
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$_shell_rc"
    _need_path=1
  fi
done

# ── 完成 ───────────────────────────────────────────────────────────────────
echo
_bold "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
_green "  安装完成！"
_bold "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo
echo "  下一步:"

if [ "$_need_path" -eq 1 ]; then
  echo "    1. 重新加载 shell:  source ~/.zshrc  (或 ~/.bashrc)"
  echo "    2. 配置向导:        lingzhou setup"
  echo "    3. 初始化环境:      lingzhou init"
  echo "    4. 启动:            lingzhou run"
else
  echo "    1. 配置向导:        lingzhou setup"
  echo "    2. 初始化环境:      lingzhou init"
  echo "    3. 启动:            lingzhou run"
fi

echo
echo "  其他命令:"
echo "    lingzhou doctor     # 诊断运行环境"
echo "    lingzhou --version  # 查看版本"
echo "    lingzhou --help     # 帮助"
echo
