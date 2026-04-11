#!/usr/bin/env bash
# 验证线上：客户「短信业务」侧栏是否包含 /sms/send-stats（与管理员菜单区分）
# 用法: BASE_URL=https://www.kaolach.com bash scripts/verify_frontend_send_stats.sh
set -euo pipefail
BASE_URL="${BASE_URL:-https://www.kaolach.com}"
echo "检查: $BASE_URL"
html=$(curl -fsSL "$BASE_URL/")
if echo "$html" | grep -q 'app-build-stamp'; then
  echo "OK: 首页含 app-build-stamp（新构建）"
  echo "$html" | grep -o 'app-build-stamp" content="[^"]*"' | head -1
else
  echo "WARN: 首页无 app-build-stamp meta（旧构建或未用当前仓库 Dockerfile）"
fi
main_js=$(echo "$html" | grep -oE '/assets/index-[^"]+\.js' | head -1)
if [[ -z "$main_js" ]]; then
  echo "ERR: 未解析到主 JS"
  exit 1
fi
main_body=$(curl -fsSL "$BASE_URL$main_js")
chunk=$(echo "$main_body" | grep -oE 'MainLayout-[A-Za-z0-9_-]+\.js' | sort -u | head -1)
if [[ -z "$chunk" ]]; then
  echo "ERR: 主包中未找到 MainLayout chunk 名"
  exit 1
fi
ml_path="/assets/$chunk"
echo "拉取: $ml_path"
curl -fsSL "$BASE_URL$ml_path" | python3 -c "
import sys
s = sys.stdin.read()
start = s.find('smsBusiness')
if start < 0:
    print('ERR: MainLayout 中无 smsBusiness')
    sys.exit(1)
end = s.find('dataBusiness', start)
if end < 0:
    end = start + 12000
seg = s[start:end]
if '/sms/send-stats' not in seg:
    print('ERR: 客户侧栏片段（smsBusiness 之后至 dataBusiness 之前）内无 /sms/send-stats')
    print('结论：线上前端仍为旧包，无痕模式无效。请重新构建并重启 frontend 容器。')
    sys.exit(1)
print('OK: 客户短信业务区块已包含 /sms/send-stats')
"
