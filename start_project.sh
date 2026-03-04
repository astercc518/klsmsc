#!/bin/bash
# 项目启动脚本

set -e

echo "🚀 启动短信网关系统..."

cd "$(dirname "$0")"

# 检查Docker
if command -v docker &> /dev/null; then
    # 检查是否使用docker compose (v2) 或 docker-compose (v1)
    if docker compose version &>/dev/null; then
        DOCKER_COMPOSE_CMD="docker compose"
    elif command -v docker-compose &> /dev/null; then
        DOCKER_COMPOSE_CMD="docker-compose"
    else
        DOCKER_COMPOSE_CMD=""
    fi
    
    if [ -n "$DOCKER_COMPOSE_CMD" ]; then
    echo "📦 使用Docker Compose启动..."
    
    # 检查服务状态
    if docker ps | grep -q smsc-api; then
        echo "✅ 服务已在运行中"
        echo ""
        echo "📊 运行中的服务:"
        docker ps --format "  - {{.Names}}: {{.Status}}" | grep smsc
    else
        echo "🚀 启动所有服务..."
        $DOCKER_COMPOSE_CMD up -d
        
        echo "⏳ 等待服务启动..."
        sleep 5
        
        echo "📊 服务状态:"
        docker ps --format "  - {{.Names}}: {{.Status}}" | grep smsc
        
        echo ""
        echo "✅ 服务启动完成！"
        echo ""
        echo "📝 访问地址:"
        echo "  - API文档: http://localhost:8000/docs"
        echo "  - RabbitMQ管理: http://localhost:15672 (guest/guest)"
        echo "  - Prometheus: http://localhost:9090"
        echo "  - Grafana: http://localhost:3000 (admin/admin)"
        echo ""
        echo "📋 查看日志: docker logs -f smsc-api"
    fi
    else
        echo "⚠️  Docker Compose未安装"
        echo ""
        echo "可以使用docker命令手动管理服务"
    fi
else
    echo "⚠️  Docker未安装，使用本地启动模式..."
    echo ""
    echo "后端启动:"
    echo "  cd backend"
    echo "  pip install -r requirements.txt"
    echo "  uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"
    echo ""
    echo "前端启动:"
    echo "  cd frontend"
    echo "  npm install"
    echo "  npm run dev"
fi
