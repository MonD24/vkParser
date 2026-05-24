#!/bin/bash
# deploy.sh — разворачивает бота на Linux VPS
# Запускать на VPS: bash deploy.sh

set -e

BOT_DIR="/opt/botwim"
PYTHON="python3"

echo "=== VK Contest Bot — деплой ==="

# 1. Зависимости
apt-get update -qq
apt-get install -y -qq python3 python3-pip python3-venv git

# 2. Создаём директорию
mkdir -p "$BOT_DIR"
cd "$BOT_DIR"

# 3. Виртуальное окружение
if [ ! -d ".venv" ]; then
    $PYTHON -m venv .venv
    echo "Создано .venv"
fi

# 4. Устанавливаем зависимости
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r requirements.txt
echo "Зависимости установлены"

# 5. Создаём systemd unit
cat > /etc/systemd/system/botwim.service << 'EOF'
[Unit]
Description=VK Contest Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/botwim
ExecStart=/opt/botwim/.venv/bin/python main.py
Restart=always
RestartSec=30
Environment=PYTHONUTF8=1
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable botwim
echo "Systemd unit создан и включён"

# 6. Запуск
systemctl restart botwim
sleep 2
systemctl status botwim --no-pager

echo ""
echo "=== Готово! ==="
echo "Управление:"
echo "  systemctl start botwim    — запустить"
echo "  systemctl stop botwim     — остановить"
echo "  systemctl restart botwim  — перезапустить"
echo "  journalctl -u botwim -f   — логи в реальном времени"
echo ""
echo "Или через Telegram: /start /stop /now /status /list"
