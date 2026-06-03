#!/bin/bash
# ╔══════════════════════════════════════════════════════╗
# ║   NodeSeek 自动签到 — 一键部署脚本                    ║
# ║   使用：把 main.py .env install.sh 上传到服务器后执行   ║
# ║         bash /opt/nodeseek/install.sh                ║
# ╚══════════════════════════════════════════════════════╝

set -e
APP_DIR="/opt/nodeseek"

echo "========================================="
echo "  NodeSeek 自动签到 — 一键部署"
echo "========================================="

# ── 1. 安装依赖 ──
echo "[1/4] 安装 Python 依赖..."
pip3 install --break-system-packages curl_cffi 2>&1 | tail -1

# ── 2. 设置时区 ──
echo "[2/4] 设置时区..."
timedatectl set-timezone Asia/Shanghai 2>/dev/null || ln -sf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime

# ── 3. 创建目录 & 定时任务 ──
echo "[3/4] 配置定时任务 & 开机自启..."
mkdir -p $APP_DIR/logs

cat > /etc/systemd/system/nodeseek.service << EOF
[Unit]
Description=NodeSeek 自动签到
After=network-online.target

[Service]
Type=oneshot
WorkingDirectory=$APP_DIR
ExecStart=/usr/bin/python3 $APP_DIR/main.py
EOF

cat > /etc/systemd/system/nodeseek.timer << EOF
[Unit]
Description=NodeSeek 每日自动签到

[Timer]
OnCalendar=*-*-* 09:05:00 Asia/Shanghai
Persistent=true
RandomizedDelaySec=300

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable nodeseek.timer
systemctl start nodeseek.timer

# ── 4. 验证 ──
echo "[4/4] 验证..."
echo ""
echo "========================================="
echo "  ✅ 部署完成！"
echo "========================================="
echo ""
systemctl list-timers nodeseek.timer --no-pager
echo ""
echo "── 管理命令 ──────────────────────────────"
echo "  手动签到：   systemctl start nodeseek.service"
echo "  查看日志：   cat $APP_DIR/logs/checkin.log"
echo "  定时状态：   systemctl status nodeseek.timer"
echo "  改配置重载： systemctl daemon-reload"
echo "──────────────────────────────────────────"
