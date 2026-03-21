#!/bin/bash
# Phase 4 快速测试脚本（不依赖MySQL连接）
# 用于验证代码和API结构

set -e

echo "=========================================="
echo "Phase 4 快速验证脚本"
echo "=========================================="

API_BASE_URL="${API_BASE_URL:-http://localhost:8000}"

echo "API地址: $API_BASE_URL"
echo ""

# 检查后端服务
echo "1. 检查后端服务..."
if curl -s -f "$API_BASE_URL/health" > /dev/null 2>&1; then
    echo "✅ 后端服务运行正常"
    health_info=$(curl -s "$API_BASE_URL/health")
    echo "   健康检查: $health_info"
else
    echo "❌ 后端服务未运行或无法访问"
    echo "   请启动后端服务: cd backend && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000"
    exit 1
fi
echo ""

# 检查API路由
echo "2. 检查API路由..."
routes=(
    "/api/v1/admin/configs"
    "/api/v1/admin/bot/invites"
    "/api/v1/admin/bot/recharges"
    "/api/v1/admin/bot/batches"
    "/api/v1/admin/bot/templates"
)

for route in "${routes[@]}"; do
    status=$(curl -s -o /dev/null -w "%{http_code}" "$API_BASE_URL$route" 2>/dev/null || echo "000")
    if [ "$status" = "401" ] || [ "$status" = "403" ]; then
        echo "✅ $route - 路由存在（需要认证）"
    elif [ "$status" = "404" ]; then
        echo "❌ $route - 路由不存在"
    else
        echo "⚠️  $route - 状态码: $status"
    fi
done
echo ""

# 检查前端文件
echo "3. 检查前端文件..."
frontend_files=(
    "frontend/src/views/system/Config.vue"
    "frontend/src/views/bot/Invites.vue"
    "frontend/src/views/bot/RechargeAudit.vue"
    "frontend/src/views/bot/BatchAudit.vue"
    "frontend/src/views/bot/Templates.vue"
    "frontend/src/api/system.ts"
    "frontend/src/api/bot.ts"
)

for file in "${frontend_files[@]}"; do
    if [ -f "$file" ]; then
        echo "✅ $file"
    else
        echo "❌ $file - 文件不存在"
    fi
done
echo ""

# 检查后端文件
echo "4. 检查后端文件..."
backend_files=(
    "backend/app/api/v1/system_config.py"
    "backend/app/api/v1/bot_admin.py"
    "backend/app/models/system_config.py"
    "backend/app/models/sms_batch.py"
    "scripts/phase4_migration.sql"
)

for file in "${backend_files[@]}"; do
    if [ -f "$file" ]; then
        echo "✅ $file"
    else
        echo "❌ $file - 文件不存在"
    fi
done
echo ""

echo "=========================================="
echo "✅ 快速验证完成！"
echo ""
echo "📝 下一步："
echo "1. 启动MySQL服务并执行数据库迁移"
echo "2. 配置Telegram Bot Token（通过前端页面）"
echo "3. 运行完整测试: ./scripts/test_phase4.sh"
echo "=========================================="
