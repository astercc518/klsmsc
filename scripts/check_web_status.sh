#!/bin/bash
# 网站 Error 521 排查脚本 - 在部署服务器上执行
# 用法: bash scripts/check_web_status.sh

set -e
cd "$(dirname "$0")/.."

echo "========== 考拉出海 Web 服务状态检查 =========="
echo ""

# 1. Docker 服务
echo "1. Docker 服务状态"
if command -v docker &>/dev/null; then
  docker ps -a --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep -E "frontend|api|NAMES" || true
  echo ""
else
  echo "   Docker 未安装或未在 PATH 中"
fi

# 2. 前端容器
echo "2. 前端容器 (smsc-frontend)"
if docker ps -a --format '{{.Names}}' | grep -q smsc-frontend; then
  STATUS=$(docker inspect smsc-frontend --format '{{.State.Status}}')
  echo "   状态: $STATUS"
  if [ "$STATUS" = "running" ]; then
    echo "   端口映射: $(docker port smsc-frontend 2>/dev/null || echo '无')"
    echo "   测试本地 80: $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:80/ 2>/dev/null || echo '连接失败')"
    echo "   测试本地 443: $(curl -sk -o /dev/null -w '%{http_code}' https://127.0.0.1:443/ 2>/dev/null || echo '连接失败')"
  fi
else
  echo "   容器不存在，请执行: docker compose up -d frontend"
fi
echo ""

# 3. 端口监听
echo "3. 端口 80/443 监听"
ss -tlnp 2>/dev/null | grep -E ':80|:443' || netstat -tlnp 2>/dev/null | grep -E ':80|:443' || echo "   无法获取"
echo ""

# 4. 防火墙
echo "4. 防火墙规则 (若使用 ufw)"
if command -v ufw &>/dev/null; then
  ufw status 2>/dev/null | head -5 || true
else
  echo "   ufw 未安装"
fi
echo ""

# 5. Cloudflare 相关
echo "5. Cloudflare 配置提示"
echo "   - 若使用 Cloudflare 代理，源站需开放 80/443"
echo "   - SSL 模式: Full 时源站需有效 HTTPS 证书"
echo "   - 检查 Cloudflare 防火墙是否封禁了源站 IP"
echo ""

echo "========== 快速修复命令 =========="
echo "  # 重启前端容器"
echo "  docker compose restart frontend"
echo ""
echo "  # 查看前端日志"
echo "  docker compose logs frontend --tail 50"
echo ""
echo "  # 完整重启"
echo "  docker compose down && docker compose up -d"
