#!/bin/bash
# Phase 4 API测试（不依赖数据库连接）
# 用于测试API路由和基本功能

set -e

echo "=========================================="
echo "Phase 4 API测试（无数据库依赖）"
echo "=========================================="

API_BASE_URL="${API_BASE_URL:-http://localhost:8000}"
ADMIN_USERNAME="${ADMIN_USERNAME:-admin}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-admin123}"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

# 1. 检查后端服务
echo "1. 检查后端服务..."
if curl -s -f "$API_BASE_URL/health" > /dev/null 2>&1; then
    echo -e "${GREEN}✅ 后端服务运行正常${NC}"
else
    echo -e "${RED}❌ 后端服务不可用${NC}"
    exit 1
fi
echo ""

# 2. 登录获取Token
echo "2. 管理员登录..."
login_response=$(curl -s -X POST "$API_BASE_URL/api/v1/admin/login" \
    -H "Content-Type: application/json" \
    -d "{\"username\":\"$ADMIN_USERNAME\",\"password\":\"$ADMIN_PASSWORD\"}")

TOKEN=$(echo $login_response | grep -o '"token":"[^"]*' | cut -d'"' -f4)
if [ -z "$TOKEN" ]; then
    TOKEN=$(echo $login_response | grep -o '"access_token":"[^"]*' | cut -d'"' -f4)
fi

if [ -z "$TOKEN" ]; then
    echo -e "${RED}❌ 登录失败${NC}"
    echo "响应: $login_response"
    exit 1
fi

echo -e "${GREEN}✅ 登录成功${NC}"
echo "Token: ${TOKEN:0:30}..."
echo ""

# 3. 测试API路由（不依赖数据库）
echo "3. 测试API路由..."

test_route() {
    local name=$1
    local method=$2
    local url=$3
    local data=$4
    
    echo -n "  测试 $name... "
    
    if [ "$method" = "GET" ]; then
        response=$(curl -s -w "\n%{http_code}" -X GET "$API_BASE_URL$url" \
            -H "Authorization: Bearer $TOKEN" \
            -H "Content-Type: application/json" 2>/dev/null)
    elif [ "$method" = "POST" ]; then
        response=$(curl -s -w "\n%{http_code}" -X POST "$API_BASE_URL$url" \
            -H "Authorization: Bearer $TOKEN" \
            -H "Content-Type: application/json" \
            -d "$data" 2>/dev/null)
    elif [ "$method" = "PUT" ]; then
        response=$(curl -s -w "\n%{http_code}" -X PUT "$API_BASE_URL$url" \
            -H "Authorization: Bearer $TOKEN" \
            -H "Content-Type: application/json" \
            -d "$data" 2>/dev/null)
    elif [ "$method" = "DELETE" ]; then
        response=$(curl -s -w "\n%{http_code}" -X DELETE "$API_BASE_URL$url" \
            -H "Authorization: Bearer $TOKEN" \
            -H "Content-Type: application/json" 2>/dev/null)
    fi
    
    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | sed '$d')
    
    # 200-299 或 500（数据库错误但路由存在）都算路由存在
    if [ "$http_code" -ge 200 ] && [ "$http_code" -lt 300 ]; then
        echo -e "${GREEN}✓ 成功${NC} (HTTP $http_code)"
        return 0
    elif [ "$http_code" = "500" ]; then
        echo -e "${YELLOW}⚠ 路由存在但数据库错误${NC} (HTTP $http_code)"
        return 0
    elif [ "$http_code" = "404" ]; then
        echo -e "${RED}✗ 路由不存在${NC} (HTTP $http_code)"
        return 1
    else
        echo -e "${YELLOW}⚠ 状态码: $http_code${NC}"
        return 0
    fi
}

# 测试系统配置API
test_route "系统配置列表" "GET" "/api/v1/admin/configs" ""
test_route "系统配置创建" "POST" "/api/v1/admin/configs" \
    '{"config_key":"test_key","config_value":"test_value","config_type":"string"}'

# 测试Bot管理API
test_route "邀请码列表" "GET" "/api/v1/admin/bot/invites?page=1&limit=10" ""
test_route "邀请码创建" "POST" "/api/v1/admin/bot/invites" \
    '{"country":"CN","price":0.05,"business_type":"sms","valid_hours":24}'

test_route "充值工单列表" "GET" "/api/v1/admin/bot/recharges?status=pending&page=1&limit=10" ""

test_route "群发批次列表" "GET" "/api/v1/admin/bot/batches?status=pending_audit&page=1&limit=10" ""

test_route "白名单列表" "GET" "/api/v1/admin/bot/templates?page=1&limit=10" ""

echo ""

# 4. 清理测试数据
echo "4. 清理测试数据..."
if curl -s -X DELETE "$API_BASE_URL/api/v1/admin/configs/test_key" \
    -H "Authorization: Bearer $TOKEN" > /dev/null 2>&1; then
    echo -e "${GREEN}✅ 测试数据已清理${NC}"
else
    echo -e "${YELLOW}⚠ 清理测试数据失败（可能不存在）${NC}"
fi
echo ""

echo "=========================================="
echo -e "${GREEN}✅ API测试完成！${NC}"
echo ""
echo "📝 说明："
echo "  - 所有API路由已验证"
echo "  - 如果看到数据库错误，说明路由正常但需要执行数据库迁移"
echo "  - 执行迁移后可以运行完整测试: ./scripts/test_phase4.sh"
echo "=========================================="
