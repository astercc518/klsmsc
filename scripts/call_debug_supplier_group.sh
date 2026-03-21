#!/bin/bash
# 调用供应商群诊断接口
# 用法: ./scripts/call_debug_supplier_group.sh [account_id|tg_id]
# 需先登录管理后台，从浏览器控制台执行 localStorage.getItem('admin_token') 获取 token
# 或设置环境变量: export ADMIN_TOKEN="your_token"

ACCOUNT_ID="${1:-17}"
API="${API_BASE_URL:-http://localhost:8000}"
TOKEN="${ADMIN_TOKEN:-}"

if [ -z "$TOKEN" ]; then
  echo "请设置 ADMIN_TOKEN 环境变量（从管理后台登录后 localStorage.admin_token 获取）"
  echo "示例: ADMIN_TOKEN=xxx ./scripts/call_debug_supplier_group.sh 17"
  echo ""
  echo "或按 tg_id 查询: ADMIN_TOKEN=xxx ./scripts/call_debug_supplier_group.sh tg_id=6650783812"
  exit 1
fi

if [[ "$ACCOUNT_ID" == tg_id=* ]]; then
  PARAM="${ACCOUNT_ID}"
else
  PARAM="account_id=${ACCOUNT_ID}"
fi

curl -s "${API}/api/v1/admin/debug/supplier-group?${PARAM}" \
  -H "Authorization: Bearer ${TOKEN}" | python3 -m json.tool
