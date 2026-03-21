#!/bin/bash
# 强制清除指定员工的 Telegram 绑定，并重启 Bot
# 用法: ./scripts/fix_kl04_tg.sh [username]
# 默认清除 KL04。需在项目根目录执行。

set -e
cd "$(dirname "$0")/.."
USERNAME="${1:-KL04}"

echo "=== 清除员工 $USERNAME 的 Telegram 绑定 ==="
docker exec smsc-mysql mysql -usmsuser -psmspass123 sms_system -e "
UPDATE admin_users SET tg_id = NULL, tg_username = NULL WHERE username = '$USERNAME';
SELECT CONCAT('已更新 ', ROW_COUNT(), ' 条记录') as result;
"

echo ""
echo "=== 重启 Bot ==="
docker compose restart bot

echo ""
echo "完成。请让该用户重新发送 /start 验证。"
