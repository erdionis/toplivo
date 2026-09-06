#!/bin/bash
# Одноразовая установка сервиса в systemd
# После выполнения этого скрипта используйте:
#   systemctl start toplivo-monitor
#   systemctl stop toplivo-monitor
#   systemctl status toplivo-monitor
#   journalctl -u toplivo-monitor -f

set -e

SERVICE_NAME="toplivo-monitor.service"
SERVICE_FILE="$(dirname "$0")/$SERVICE_NAME"
TARGET="/etc/systemd/system/$SERVICE_NAME"

if [ ! -f "$SERVICE_FILE" ]; then
    echo "ОШИБКА: $SERVICE_FILE не найден"
    exit 1
fi

echo "Копирование $SERVICE_NAME в $TARGET ..."
sudo cp "$SERVICE_FILE" "$TARGET"

echo "Перезагрузка systemd..."
sudo systemctl daemon-reload

echo "Включение автозапуска..."
sudo systemctl enable toplivo-monitor

echo ""
echo "Готово. Сервис установлен."
echo ""
echo "Управление:"
echo "  systemctl start toplivo-monitor    # запустить"
echo "  systemctl stop toplivo-monitor     # остановить"
echo "  systemctl status toplivo-monitor   # статус"
echo "  journalctl -u toplivo-monitor -f   # логи"
