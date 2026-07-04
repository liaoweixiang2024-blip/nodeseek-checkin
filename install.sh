#!/usr/bin/env bash
# ╔══════════════════════════════════════════════════════════════╗
# ║   NodeSeek 自动签到 — 一键安装 / 升级脚本                      ║
# ║                                                               ║
# ║   用法 1(推荐,服务器上直接一行拉取运行):                    ║
# ║     bash <(curl -fsSL https://raw.githubusercontent.com/        ║
# ║       liaoweixiang2024-blip/nodeseek-checkin/main/install.sh)   ║
# ║                                                               ║
# ║   用法 2(已下载到本地):                                      ║
# ║     bash install.sh                                           ║
# ║                                                               ║
# ║   卸载:                                                       ║
# ║     bash install.sh --uninstall                               ║
# ╚══════════════════════════════════════════════════════════════╝

set -uo pipefail

# ── 配置 ────────────────────────────────────────────────────────
REPO_URL="https://github.com/liaoweixiang2024-blip/nodeseek-checkin.git"
BRANCH="main"
APP_DIR="/opt/nodeseek"
SERVICE="/etc/systemd/system/nodeseek.service"
TIMER="/etc/systemd/system/nodeseek.timer"
NS_BIN="/usr/local/bin/ns"
PYTHON_BIN="python3"

# ── 颜色输出 ────────────────────────────────────────────────────
if [ -t 1 ]; then
  C_CYAN=$'\033[36m'; C_GREEN=$'\033[32m'; C_YELLOW=$'\033[33m'
  C_RED=$'\033[31m'; C_BOLD=$'\033[1m'; C_NC=$'\033[0m'
else
  C_CYAN=""; C_GREEN=""; C_YELLOW=""; C_RED=""; C_BOLD=""; C_NC=""
fi
info() { printf '%s[INFO]%s %s\n' "$C_CYAN" "$C_NC" "$*"; }
ok()   { printf '%s[ OK ]%s %s\n' "$C_GREEN" "$C_NC" "$*"; }
warn() { printf '%s[WARN]%s %s\n' "$C_YELLOW" "$C_NC" "$*"; }
err()  { printf '%s[ERR ]%s %s\n' "$C_RED" "$C_NC" "$*" >&2; }
step() { printf '\n%s==>%s %s\n' "$C_BOLD" "$C_NC" "$*"; }
die()  { err "$*"; exit 1; }

# ── 卸载 ────────────────────────────────────────────────────────
if [ "${1:-}" = "--uninstall" ]; then
  step "卸载 NodeSeek 签到"
  systemctl disable --now nodeseek.timer 2>/dev/null || true
  rm -f "$SERVICE" "$TIMER" "$NS_BIN"
  systemctl daemon-reload
  read -r -p "是否删除代码与配置目录 $APP_DIR(含 .env、cookie、日志)?[y/N] " ans
  case "$ans" in y|Y|yes) rm -rf "$APP_DIR"; ok "已删除 $APP_DIR" ;; *) ok "保留 $APP_DIR" ;; esac
  ok "卸载完成"
  exit 0
fi

# ── root 检查 ────────────────────────────────────────────────────
[ "$(id -u)" -eq 0 ] || die "请使用 root 运行: sudo bash install.sh"

# ── 包管理器 ────────────────────────────────────────────────────
detect_pkg_manager() {
  if command -v apt-get >/dev/null 2>&1; then echo apt-get
  elif command -v dnf >/dev/null 2>&1; then echo dnf
  elif command -v yum >/dev/null 2>&1; then echo yum
  else echo ""; fi
}
PKG="$(detect_pkg_manager)"
[ -n "$PKG" ] || die "不支持的系统:找不到 apt-get / dnf / yum"

PKG_UPDATED=0
pkg_install() {
  if [ "$PKG_UPDATED" -eq 0 ]; then
    case "$PKG" in
      apt-get) apt-get update -qq >/dev/null 2>&1 || true ;;
    esac
    PKG_UPDATED=1
  fi
  case "$PKG" in
    apt-get) apt-get install -y "$@" ;;
    dnf)     dnf install -y "$@" ;;
    yum)     yum install -y "$@" ;;
  esac
}

# pip 安装(兼容 PEP 668 externally-managed 环境)
pip_install() {
  if "$PYTHON_BIN" -m pip install --break-system-packages "$@" 2>/dev/null; then
    return 0
  fi
  "$PYTHON_BIN" -m pip install "$@"
}

echo "${C_BOLD}NodeSeek 自动签到 — 一键安装${C_NC}"

# ── 1. 基础环境:git / python3 ──────────────────────────────────
step "检查基础环境"
info "包管理器: $PKG"

if ! command -v git >/dev/null 2>&1; then
  info "安装 git..."
  pkg_install git || die "git 安装失败"
fi

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  info "安装 python3..."
  pkg_install python3 || die "python3 安装失败"
fi

if ! "$PYTHON_BIN" -c 'import sys; sys.exit(0 if sys.version_info >= (3,8) else 1)' 2>/dev/null; then
  die "Python 版本过低($("$PYTHON_BIN" --version 2>&1)),需要 3.8+"
fi
ok "git $(git --version | awk '{print $3}'), $("$PYTHON_BIN" --version 2>&1)"

# ── 2. pip ──────────────────────────────────────────────────────
if ! "$PYTHON_BIN" -m pip --version >/dev/null 2>&1; then
  step "安装 pip"
  pkg_install python3-pip || die "pip 安装失败,请手动安装 python3-pip"
fi
ok "pip 就绪"

# ── 3. 获取代码(首次 clone / 已有则 pull 升级)────────────────
step "获取代码"
if [ -d "$APP_DIR/.git" ]; then
  info "已存在部署,拉取最新代码..."
  git -C "$APP_DIR" fetch --quiet origin "$BRANCH" \
    || die "git fetch 失败,请检查网络或代理"
  git -C "$APP_DIR" reset --hard --quiet "origin/$BRANCH"
  ok "代码已更新到最新 ($BRANCH)"
else
  ENV_BACKUP=""
  if [ -f "$APP_DIR/.env" ]; then
    ENV_BACKUP="$(mktemp)"
    cp "$APP_DIR/.env" "$ENV_BACKUP"
    info "已备份现有 .env"
  fi
  [ -d "$APP_DIR" ] && rm -rf "$APP_DIR"
  info "从 GitHub 克隆代码..."
  git clone --depth=1 -b "$BRANCH" "$REPO_URL" "$APP_DIR" \
    || die "克隆失败,国内服务器若连不上 GitHub 可配置代理后重试"
  if [ -n "$ENV_BACKUP" ]; then
    cp "$ENV_BACKUP" "$APP_DIR/.env" && rm -f "$ENV_BACKUP"
    ok "已恢复原有 .env"
  fi
fi

# ── 4. Python 依赖:curl_cffi ───────────────────────────────────
step "安装 Python 依赖 (curl_cffi)"
if "$PYTHON_BIN" -c "import curl_cffi" 2>/dev/null; then
  ok "curl_cffi 已安装"
else
  info "安装 curl_cffi..."
  if ! pip_install curl_cffi >/tmp/ns_pip.log 2>&1; then
    warn "预编译包失败,装编译依赖后重试..."
    case "$PKG" in
      apt-get) pkg_install build-essential libcurl4-openssl-dev libssl-dev python3-dev >/dev/null 2>&1 || true ;;
      dnf|yum) pkg_install gcc openssl-devel libcurl-devel python3-devel >/dev/null 2>&1 || true ;;
    esac
    if ! pip_install curl_cffi >>/tmp/ns_pip.log 2>&1; then
      err "curl_cffi 安装失败,日志末尾:"
      tail -20 /tmp/ns_pip.log >&2
      die "完整日志见 /tmp/ns_pip.log"
    fi
  fi
  ok "curl_cffi 安装成功"
fi

# ── 5. .env(只在不存在时生成,绝不覆盖)──────────────────────
step "配置 .env"
NEED_ENV=0
if [ ! -f "$APP_DIR/.env" ]; then
  cp "$APP_DIR/.env.example" "$APP_DIR/.env"
  warn "已从模板生成 $APP_DIR/.env —— 请务必编辑填入账号!"
  NEED_ENV=1
else
  ok ".env 已存在,保留你的配置不动"
fi
mkdir -p "$APP_DIR/logs"

# ── 6. 时区 ─────────────────────────────────────────────────────
if command -v timedatectl >/dev/null 2>&1; then
  if timedatectl set-timezone Asia/Shanghai 2>/dev/null; then
    ok "时区设为 Asia/Shanghai"
  fi
fi

# ── 7. systemd service + timer ─────────────────────────────────
step "配置 systemd 定时任务"
PY_PATH="$(command -v "$PYTHON_BIN")"

cat > "$SERVICE" << EOF
[Unit]
Description=NodeSeek 自动签到
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory=$APP_DIR
ExecStart=$PY_PATH $APP_DIR/main.py
StandardOutput=journal
StandardError=journal
EOF

cat > "$TIMER" << EOF
[Unit]
Description=NodeSeek 每日自动签到

[Timer]
OnCalendar=*-*-* 09:05:00
Persistent=true
RandomizedDelaySec=300

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now nodeseek.timer >/dev/null 2>&1 \
  || die "定时任务启用失败"
ok "定时任务已启用(每天 09:05 ±5分钟)"

# ── 8. 安装 ns 管理命令 ────────────────────────────────────────
step "安装管理命令 ns"
cat > "$NS_BIN" <<'NSCRIPT'
#!/usr/bin/env bash
# NodeSeek 签到管理命令
APP_DIR="/opt/nodeseek"
SERVICE="nodeseek.service"
TIMER="nodeseek.timer"

usage() {
  cat <<EOF
用法: ns <命令>

  run        手动签到一次(并显示日志)
  log        看签到日志
  err        看运行报错(journalctl)
  status     看定时任务和服务状态
  update     升级到最新版
  uninstall  卸载

不带参数显示此帮助。
EOF
}

case "${1:-}" in
  "")
    usage
    ;;
  run)
    systemctl start "$SERVICE"
    echo "已触发签到,等待 2 秒..."
    sleep 2
    tail -n 30 "$APP_DIR/logs/checkin.log" 2>/dev/null
    ;;
  log)
    tail -n 30 "$APP_DIR/logs/checkin.log" 2>/dev/null
    ;;
  err)
    journalctl -u "$SERVICE" -n 50 --no-pager
    ;;
  status)
    systemctl list-timers "$TIMER" --no-pager 2>/dev/null
    echo "── $SERVICE ──"
    systemctl status "$SERVICE" --no-pager 2>/dev/null | head -n 10
    ;;
  update|install)
    bash "$APP_DIR/install.sh"
    ;;
  uninstall)
    bash "$APP_DIR/install.sh" --uninstall
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    echo "未知命令: $1" >&2
    usage
    exit 1
    ;;
esac
NSCRIPT
chmod +x "$NS_BIN"
ok "管理命令已安装: ns"

# ── 9. 完成 ─────────────────────────────────────────────────────
step "完成"
echo
if [ "$NEED_ENV" -eq 1 ]; then
  printf '%s下一步:编辑 .env 填入账号信息%s\n' "$C_YELLOW" "$C_NC"
  echo "    nano $APP_DIR/.env"
  echo
  printf '填好后手动跑一次验证:%s\n' "$C_GREEN"
  echo "    ns run${C_NC}"
else
  printf '%s.env 已配置,手动签到一次:%s\n' "$C_GREEN" "$C_NC"
  echo "    ns run"
fi
echo
echo "── 日常管理(ns 命令)──────────────────────"
echo "  ns           看状态"
echo "  ns run       手动签到"
echo "  ns log       看签到日志"
echo "  ns err       看运行报错"
echo "  ns update    升级到最新版"
echo "──────────────────────────────────────────"
