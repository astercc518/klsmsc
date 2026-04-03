#!/bin/sh
set -e
# 启动 API 前执行迁移，避免 ORM 字段与表结构不一致导致 500（如 private_library_numbers.is_deleted）
echo "[docker-entrypoint] 执行 alembic upgrade head ..."
alembic upgrade head
echo "[docker-entrypoint] 启动: $*"
exec "$@"
