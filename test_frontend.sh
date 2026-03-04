#!/bin/bash
# 前端功能测试脚本

set -e

echo "🧪 前端功能测试"
echo "=================="
echo ""

cd "$(dirname "$0")"

# 检查后端API
echo "1. 检查后端API服务..."
if curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo "   ✅ 后端API服务运行正常 (http://localhost:8000)"
    API_HEALTH=$(curl -s http://localhost:8000/health)
    echo "   $API_HEALTH"
else
    echo "   ❌ 后端API服务未运行"
    echo "   请先运行: bash start_project.sh"
    exit 1
fi

echo ""

# 检查前端服务
echo "2. 检查前端服务..."
if curl -s http://localhost:5173 > /dev/null 2>&1; then
    echo "   ✅ 前端服务运行正常 (http://localhost:5173)"
    FRONTEND_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:5173)
    echo "   HTTP状态码: $FRONTEND_STATUS"
else
    echo "   ⚠️  前端服务未运行"
    echo "   请运行: bash start_frontend.sh"
    echo ""
    echo "   或者手动启动:"
    echo "   cd frontend && npm install && npm run dev"
fi

echo ""

# 测试API端点
echo "3. 测试后端API端点..."
echo "   - 健康检查: $(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health)"
echo "   - API根路径: $(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/)"
echo "   - API文档: $(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/docs)"

echo ""
echo "4. 前端页面检查清单:"
echo ""
echo "   请在浏览器访问 http://localhost:5173 并测试以下功能:"
echo ""
echo "   ✅ 登录页面 (/login)"
echo "      - 用户登录表单"
echo "      - 管理员登录（JWT）"
echo ""
echo "   ✅ 仪表板 (/dashboard)"
echo "      - 今日发送统计"
echo "      - 成功率显示"
echo ""
echo "   ✅ 短信功能"
echo "      - 发送短信 (/sms/send)"
echo "      - 短信记录 (/sms/records)"
echo ""
echo "   ✅ 账户管理"
echo "      - 账户信息 (/account/info)"
echo "      - 余额查询 (/account/balance)"
echo ""
echo "   ✅ 报表统计 (/reports)"
echo "      - 发送趋势图表"
echo "      - 成功率趋势图表"
echo "      - 费用趋势图表"
echo "      - Excel导出功能"
echo ""
echo "   ✅ 管理员功能（需要管理员登录）"
echo "      - 通道管理 (/admin/channels)"
echo "      - 费率管理 (/admin/pricing)"
echo ""

echo "✅ 基本检查完成"
echo ""
echo "📝 访问地址:"
echo "   前端: http://localhost:5173"
echo "   API文档: http://localhost:8000/docs"
echo ""
