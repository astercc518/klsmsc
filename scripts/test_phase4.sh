#!/bin/bash
# Phase 4 功能测试脚本
# 创建时间: 2025-12-31

set -e

echo "=========================================="
echo "Phase 4 功能测试脚本"
echo "=========================================="

API_BASE_URL="${API_BASE_URL:-http://localhost:8000}"
ADMIN_USERNAME="${ADMIN_USERNAME:-admin}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-admin123}"

echo "API地址: $API_BASE_URL"
echo "管理员账号: $ADMIN_USERNAME"
echo ""

# 颜色输出
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 测试函数
test_api() {
    local name=$1
    local method=$2
    local url=$3
    local data=$4
    local expected_status=$5
    
    echo -n "测试 $name... "
    
    if [ "$method" = "GET" ]; then
        response=$(curl -s -w "\n%{http_code}" -X GET "$API_BASE_URL$url" \
            -H "Authorization: Bearer $TOKEN" \
            -H "Content-Type: application/json")
    elif [ "$method" = "POST" ]; then
        response=$(curl -s -w "\n%{http_code}" -X POST "$API_BASE_URL$url" \
            -H "Authorization: Bearer $TOKEN" \
            -H "Content-Type: application/json" \
            -d "$data")
    elif [ "$method" = "PUT" ]; then
        response=$(curl -s -w "\n%{http_code}" -X PUT "$API_BASE_URL$url" \
            -H "Authorization: Bearer $TOKEN" \
            -H "Content-Type: application/json" \
            -d "$data")
    elif [ "$method" = "DELETE" ]; then
        response=$(curl -s -w "\n%{http_code}" -X DELETE "$API_BASE_URL$url" \
            -H "Authorization: Bearer $TOKEN" \
            -H "Content-Type: application/json")
    fi
    
    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | sed '$d')
    
    if [ "$http_code" = "$expected_status" ]; then
        echo -e "${GREEN}✓ 通过${NC} (HTTP $http_code)"
        return 0
    else
        echo -e "${RED}✗ 失败${NC} (期望 $expected_status, 实际 $http_code)"
        echo "响应: $body"
        return 1
    fi
}

# 1. 登录获取Token
echo "1. 管理员登录..."
login_response=$(curl -s -X POST "$API_BASE_URL/api/v1/admin/login" \
    -H "Content-Type: application/json" \
    -d "{\"username\":\"$ADMIN_USERNAME\",\"password\":\"$ADMIN_PASSWORD\"}")

# 尝试多种token字段名
TOKEN=$(echo $login_response | grep -o '"access_token":"[^"]*' | cut -d'"' -f4)
if [ -z "$TOKEN" ]; then
    TOKEN=$(echo $login_response | grep -o '"token":"[^"]*' | cut -d'"' -f4)
fi

if [ -z "$TOKEN" ]; then
    echo -e "${RED}登录失败！无法获取Token${NC}"
    echo "响应: $login_response"
    exit 1
fi

echo -e "${GREEN}登录成功${NC}"
echo ""

# 2. 测试系统配置API
echo "2. 测试系统配置管理..."
test_api "获取配置列表" "GET" "/api/v1/admin/configs" "" "200"
test_api "创建配置" "POST" "/api/v1/admin/configs" \
    '{"config_key":"test_config","config_value":"test_value","config_type":"string","description":"测试配置"}' "200"
test_api "获取单个配置" "GET" "/api/v1/admin/configs/test_config" "" "200"
test_api "更新配置" "PUT" "/api/v1/admin/configs/test_config" \
    '{"config_value":"updated_value"}' "200"
test_api "删除配置" "DELETE" "/api/v1/admin/configs/test_config" "" "200"
echo ""

# 3. 测试邀请码管理API
echo "3. 测试邀请码管理..."
test_api "获取邀请码列表" "GET" "/api/v1/admin/bot/invites?page=1&limit=10" "" "200"
test_api "创建邀请码" "POST" "/api/v1/admin/bot/invites" \
    '{"country":"CN","price":0.05,"business_type":"sms","valid_hours":24}' "200"
echo ""

# 4. 测试充值审核API
echo "4. 测试充值审核..."
test_api "获取充值工单列表" "GET" "/api/v1/admin/bot/recharges?status=pending&page=1&limit=10" "" "200"
echo ""

# 5. 测试群发审核API
echo "5. 测试群发审核..."
test_api "获取群发批次列表" "GET" "/api/v1/admin/bot/batches?status=pending_audit&page=1&limit=10" "" "200"
echo ""

# 6. 测试白名单管理API
echo "6. 测试白名单管理..."
test_api "获取白名单列表" "GET" "/api/v1/admin/bot/templates?page=1&limit=10" "" "200"
echo ""

# 7. 测试Telegram配置
echo "7. 检查Telegram配置..."
telegram_config=$(curl -s -X GET "$API_BASE_URL/api/v1/admin/configs/telegram_bot_token" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json")

if echo "$telegram_config" | grep -q "telegram_bot_token"; then
    echo -e "${GREEN}✓ Telegram配置存在${NC}"
    token_value=$(echo $telegram_config | grep -o '"config_value":"[^"]*' | cut -d'"' -f4)
    if [ -z "$token_value" ] || [ "$token_value" = "" ]; then
        echo -e "${YELLOW}⚠ Telegram Bot Token 未配置，请在前端系统配置页面设置${NC}"
    else
        echo -e "${GREEN}✓ Telegram Bot Token 已配置${NC}"
    fi
else
    echo -e "${YELLOW}⚠ Telegram配置不存在，请先运行数据库迁移${NC}"
fi
echo ""

echo "=========================================="
echo -e "${GREEN}所有测试完成！${NC}"
echo "=========================================="
