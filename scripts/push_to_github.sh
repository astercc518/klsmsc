#!/bin/bash
# 将 SMSC 项目推送到 GitHub
# 使用前：请在 GitHub 创建新仓库，并替换下方 REPO_URL

REPO_URL="${1:-}"
if [ -z "$REPO_URL" ]; then
  echo "用法: $0 <GitHub仓库URL>"
  echo ""
  echo "示例:"
  echo "  $0 https://github.com/你的用户名/smsc.git"
  echo "  $0 git@github.com:你的用户名/smsc.git"
  echo ""
  echo "步骤："
  echo "  1. 访问 https://github.com/new 创建新仓库（如 smsc）"
  echo "  2. 不要勾选 Initialize with README"
  echo "  3. 执行: $0 https://github.com/你的用户名/smsc.git"
  exit 1
fi

cd /var/smsc
git remote add origin "$REPO_URL" 2>/dev/null || git remote set-url origin "$REPO_URL"
git push -u origin main
