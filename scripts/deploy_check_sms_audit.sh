#!/bin/bash
# 短信审核功能部署检查脚本
# 用法: ./scripts/deploy_check_sms_audit.sh

set -e
cd "$(dirname "$0")/.."

echo "=========================================="
echo "  短信审核功能 - 部署检查"
echo "=========================================="
echo ""

PASS=0
FAIL=0

check() {
    if [ "$1" = "ok" ]; then
        echo "  ✅ $2"
        ((PASS++)) || true
    else
        echo "  ❌ $2"
        echo "     $3"
        ((FAIL++)) || true
    fi
}

# 1. 检查 .env 中的 TELEGRAM_ADMIN_GROUP_ID
if [ -f .env ]; then
    ADMIN_GROUP=$(grep -E "^TELEGRAM_ADMIN_GROUP_ID=" .env 2>/dev/null | cut -d= -f2- | tr -d '"' | tr -d "'")
    if [ -n "$ADMIN_GROUP" ]; then
        check "ok" "TELEGRAM_ADMIN_GROUP_ID 已配置" "供应商群 ID: ${ADMIN_GROUP:0:10}..."
    else
        check "fail" "TELEGRAM_ADMIN_GROUP_ID 未配置" "请在 .env 中设置：TELEGRAM_ADMIN_GROUP_ID=-100xxxxxxxxxx（将 Bot 加入群后，在群内发送任意消息，用 @userinfobot 获取群 ID）"
    fi
else
    check "fail" ".env 文件不存在" "请创建 .env 并配置 TELEGRAM_ADMIN_GROUP_ID"
fi

# 2. 检查 Telegram Bot Token
if [ -f .env ]; then
    BOT_TOKEN=$(grep -E "^TELEGRAM_BOT_TOKEN=" .env 2>/dev/null | cut -d= -f2- | tr -d '"' | tr -d "'")
    if [ -n "$BOT_TOKEN" ]; then
        check "ok" "TELEGRAM_BOT_TOKEN 已配置"
    else
        check "fail" "TELEGRAM_BOT_TOKEN 未配置" "请在 .env 中设置 Bot Token"
    fi
fi

# 3. 检查 docker-compose 中 Bot 的 API_BASE_URL
if grep -q "API_BASE_URL: http://api:8000" docker-compose.yml 2>/dev/null; then
    check "ok" "Bot API_BASE_URL 已配置为 http://api:8000" "Docker 内可正确访问后端"
else
    check "fail" "Bot 未配置 API_BASE_URL" "docker-compose.yml 中 bot 服务需添加: API_BASE_URL: http://api:8000"
fi

# 4. 检查 Bot 容器是否运行
if docker compose ps bot 2>/dev/null | grep -q "Up"; then
    check "ok" "Bot 服务正在运行"
else
    check "fail" "Bot 服务未运行" "执行: docker compose up -d bot"
fi

# 5. 检查 API 服务是否运行
if docker compose ps api 2>/dev/null | grep -q "Up"; then
    check "ok" "API 服务正在运行"
else
    check "fail" "API 服务未运行" "执行: docker compose up -d api"
fi

# 6. 系统配置（需数据库）
echo ""
echo "  数据库配置检查（需 API 服务运行）:"
if curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health 2>/dev/null | grep -q "200"; then
    API_OK=1
else
    API_OK=0
fi

if [ "$API_OK" = "1" ]; then
    # 尝试通过管理接口获取配置（需登录，此处仅作提示）
    check "ok" "API 服务可访问" "localhost:8000"
    echo ""
    echo "  📌 系统配置（Web 后台 → Bot 配置）:"
    echo "     - telegram_admin_group_id: 供应商群 ID（与 .env 同步）"
    echo "     - telegram_enable_sms_content_review: 建议为 true"
else
    check "fail" "API 服务不可访问" "请确认 API 已启动: docker compose up -d api"
fi

echo ""
echo "=========================================="
echo "  检查结果: $PASS 通过, $FAIL 失败"
echo "=========================================="
echo ""

if [ "$FAIL" -gt 0 ]; then
    echo "📋 待办事项:"
    [ -z "$ADMIN_GROUP" ] && echo "   1. 获取供应商群 ID: 将 Bot 加入群 → 在群内发消息 → 用 @userinfobot 或 @getidsbot 获取群 ID"
    [ -z "$ADMIN_GROUP" ] && echo "   2. 在 .env 中设置: TELEGRAM_ADMIN_GROUP_ID=-100xxxxxxxxxx"
    echo "   3. 重启 Bot: docker compose up -d bot"
    echo ""
    exit 1
fi

echo "✅ 部署检查通过，短信审核功能可正常使用。"
exit 0
