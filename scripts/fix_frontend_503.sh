#!/bin/bash
# 修复前端503错误

set -e

echo "=========================================="
echo "修复前端503错误"
echo "=========================================="

cd /var/smsc/frontend

# 1. 创建环境变量文件
echo "1. 配置环境变量..."
cat > .env.local << 'ENV'
VITE_API_BASE_URL=http://103.246.244.237:8000
VITE_API_TARGET=http://103.246.244.237:8000
ENV

echo "✅ 环境变量已配置"

# 2. 检查后端API可访问性
echo ""
echo "2. 检查后端API..."
if curl -s -f http://103.246.244.237:8000/health > /dev/null 2>&1; then
    echo "✅ 后端API可访问"
else
    echo "⚠️  后端API无法访问，请检查后端服务"
fi

# 3. 检查前端服务
echo ""
echo "3. 检查前端服务..."
if ps aux | grep -E "vite|npm.*dev" | grep -v grep > /dev/null; then
    echo "⚠️  前端服务正在运行，需要重启以应用新配置"
    echo "   请手动停止并重启前端服务"
else
    echo "ℹ️  前端服务未运行"
    echo "   启动命令: cd frontend && npm run dev"
fi

echo ""
echo "=========================================="
echo "✅ 配置完成！"
echo ""
echo "📝 下一步："
echo "1. 重启前端服务以应用新配置"
echo "2. 清除浏览器缓存"
echo "3. 重新访问页面"
echo "=========================================="
