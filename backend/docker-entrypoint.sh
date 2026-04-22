#!/bin/sh
# 启动 API 前执行迁移，避免 ORM 字段与表结构不一致导致 500（如 private_library_numbers.is_deleted）
# 全量 restart 时 ProxySQL/MySQL 可能尚未就绪，单次失败会导致容器退出、网关 502，故带重试。
echo "[docker-entrypoint] 执行 alembic upgrade head（最多 40 次，间隔 3s）..."
_migrate_ok=0
_i=1
while [ "$_i" -le 40 ]; do
  if alembic upgrade head; then
    _migrate_ok=1
    break
  fi
  echo "[docker-entrypoint] alembic 失败（第 $_i/40 次），3s 后重试…"
  sleep 3
  _i=$((_i + 1))
done
if [ "$_migrate_ok" != 1 ]; then
  echo "[docker-entrypoint] alembic 重试耗尽，退出"
  exit 1
fi
set -e
echo "[docker-entrypoint] 启动: $*"
exec "$@"
