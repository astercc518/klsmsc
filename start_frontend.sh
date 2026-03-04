#!/bin/bash
# 前端启动脚本

set -e

echo "🚀 启动前端开发服务器..."

cd "$(dirname "$0")/frontend"

# 检查Node.js
if ! command -v node &> /dev/null; then
    echo "❌ Node.js 未安装"
    echo "请先安装 Node.js 18+: https://nodejs.org/"
    exit 1
fi

echo "✅ Node.js 版本: $(node --version)"

# 检查npm
if ! command -v npm &> /dev/null; then
    echo "❌ npm 未安装"
    exit 1
fi

echo "✅ npm 版本: $(npm --version)"

# 检查依赖
if [ ! -d "node_modules" ]; then
    echo "📦 安装依赖..."
    npm install
else
    echo "✅ 依赖已安装"
fi

# 检查后端API
echo ""
echo "🔍 检查后端API服务..."
if curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo "✅ 后端API服务运行中 (http://localhost:8000)"
else
    echo "⚠️  后端API服务未运行"
    echo "   请先启动后端服务: bash start_project.sh"
    echo ""
    read -p "是否继续启动前端? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo ""
echo "🚀 启动前端开发服务器..."
echo "📝 访问地址: http://localhost:5173"
echo ""
echo "按 Ctrl+C 停止服务器"
echo ""

# 启动开发服务器
npm run dev
