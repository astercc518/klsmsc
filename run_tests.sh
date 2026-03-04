#!/bin/bash
# 运行测试脚本

set -e

echo "🚀 开始运行测试..."

cd "$(dirname "$0")/backend"

# 检查Python环境
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 未安装"
    exit 1
fi

# 安装测试依赖
echo "📦 安装测试依赖..."
pip3 install -q pytest pytest-asyncio pytest-cov pytest-mock aiosqlite 2>&1 | grep -v "already satisfied" || true

# 运行单元测试
echo ""
echo "🧪 运行单元测试..."
python3 -m pytest tests/unit/ -v --tb=short

# 运行集成测试
echo ""
echo "🧪 运行集成测试..."
python3 -m pytest tests/integration/ -v --tb=short

# 生成覆盖率报告
echo ""
echo "📊 生成覆盖率报告..."
python3 -m pytest tests/ --cov=app --cov-report=term-missing --cov-report=html --tb=short || true

echo ""
echo "✅ 测试完成！"
echo "📄 覆盖率报告: backend/htmlcov/index.html"
