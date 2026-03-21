#!/bin/bash
# 备份并迁移 SMSC 项目到新服务器
#
# 用法:
#   1. 备份（在当前服务器执行）:
#      ./scripts/backup_and_migrate.sh backup
#
#   2. 传输到新服务器（需配置目标服务器信息）:
#      MIGRATE_HOST=107.148.34.177 MIGRATE_PORT=31837 MIGRATE_USER=root \
#      MIGRATE_PASS='N.s3RJw1ghuQ6I:9' ./scripts/backup_and_migrate.sh transfer
#
#   3. 在新服务器上恢复:
#      ./scripts/backup_and_migrate.sh restore
#
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
BACKUP_DIR="${ROOT_DIR}/.backup_migrate"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
ARCHIVE_NAME="smsc_backup_${TIMESTAMP}.tar.gz"

# 目标服务器配置（通过环境变量传入）
MIGRATE_HOST="${MIGRATE_HOST:-107.148.34.177}"
MIGRATE_PORT="${MIGRATE_PORT:-31837}"
MIGRATE_USER="${MIGRATE_USER:-root}"
MIGRATE_PASS="${MIGRATE_PASS:-}"
MIGRATE_REMOTE_PATH="${MIGRATE_REMOTE_PATH:-/var/smsc}"

# 数据库配置（与 docker-compose 一致）
DB_USER="${MYSQL_USER:-smsuser}"
DB_PASS="${MYSQL_PASSWORD:-smspass123}"
DB_NAME="${MYSQL_DATABASE:-sms_system}"

do_backup() {
    echo "=========================================="
    echo "📦 SMSC 项目备份"
    echo "=========================================="
    mkdir -p "$BACKUP_DIR"
    cd "$ROOT_DIR"

    # 1. 备份 MySQL 数据库
    echo ""
    echo "1. 备份 MySQL 数据库..."
    if docker compose ps mysql 2>/dev/null | grep -q Up; then
        docker compose exec -T mysql mysqldump -u"$DB_USER" -p"$DB_PASS" "$DB_NAME" \
            --single-transaction --routines --triggers > "$BACKUP_DIR/sms_system.sql"
        echo "   ✅ 数据库已导出到 $BACKUP_DIR/sms_system.sql"
    else
        echo "   ⚠️  MySQL 容器未运行，尝试直接连接..."
        if mysql -h127.0.0.1 -P3306 -u"$DB_USER" -p"$DB_PASS" "$DB_NAME" -e "SELECT 1" &>/dev/null; then
            mysqldump -h127.0.0.1 -P3306 -u"$DB_USER" -p"$DB_PASS" "$DB_NAME" \
                --single-transaction --routines --triggers > "$BACKUP_DIR/sms_system.sql"
            echo "   ✅ 数据库已导出"
        else
            echo "   ❌ 无法连接数据库，请确保 MySQL 运行"
            exit 1
        fi
    fi

    # 2. 备份 .env（若存在）
    if [ -f .env ]; then
        cp .env "$BACKUP_DIR/.env"
        echo "   ✅ .env 已备份"
    else
        echo "   ⚠️  未找到 .env，请在新服务器手动配置"
    fi

    # 3. 打包项目文件（排除大文件和不必要内容）
    echo ""
    echo "2. 打包项目文件..."
    cd "$ROOT_DIR"
    tar czf "$BACKUP_DIR/$ARCHIVE_NAME" \
        --exclude='.git' \
        --exclude='node_modules' \
        --exclude='frontend/node_modules' \
        --exclude='frontend/dist' \
        --exclude='__pycache__' \
        --exclude='.pytest_cache' \
        --exclude='.backup_migrate' \
        --exclude='*.pyc' \
        --exclude='.cursor' \
        --exclude='*.xlsx' \
        backend frontend telegram_bot data scripts docs docker-compose.yml prometheus \
        .env.example frontend/.env.example 2>/dev/null || true
    # 若 backend 有 alembic
    [ -d backend/alembic ] && tar rzf "$BACKUP_DIR/$ARCHIVE_NAME" backend/alembic 2>/dev/null || true

    echo "   ✅ 项目已打包: $BACKUP_DIR/$ARCHIVE_NAME"

    # 4. 创建新服务器用的一键恢复脚本
    cat > "$BACKUP_DIR/restore_on_new_server.sh" << RESTORE_SCRIPT
#!/bin/bash
# 在新服务器上运行此脚本（与 .backup_migrate 同目录）
set -e
RESTORE_ROOT="\$(cd "\$(dirname "\$0")/.." && pwd)"
cd "\$RESTORE_ROOT"
echo "恢复目录: \$RESTORE_ROOT"
ARCHIVE=\$(ls -t .backup_migrate/smsc_backup_*.tar.gz 2>/dev/null | head -1)
[ -n "\$ARCHIVE" ] && tar xzf "\$ARCHIVE" -C "\$RESTORE_ROOT"
[ -f .backup_migrate/.env ] && cp .backup_migrate/.env .env
docker compose up -d mysql
sleep 20
docker compose exec -T mysql mysql -uroot -p"\${MYSQL_ROOT_PASSWORD:-rootpass123}" -e "CREATE DATABASE IF NOT EXISTS sms_system;" 2>/dev/null || true
docker compose exec -T mysql mysql -uroot -p"\${MYSQL_ROOT_PASSWORD:-rootpass123}" sms_system < .backup_migrate/sms_system.sql
docker compose up -d
echo "✅ 恢复完成"
RESTORE_SCRIPT
    chmod +x "$BACKUP_DIR/restore_on_new_server.sh"

    echo ""
    echo "=========================================="
    echo "✅ 备份完成"
    echo "   数据库: $BACKUP_DIR/sms_system.sql"
    echo "   项目包: $BACKUP_DIR/$ARCHIVE_NAME"
    echo "=========================================="
}

do_transfer() {
    echo "=========================================="
    echo "📤 传输到新服务器 $MIGRATE_USER@$MIGRATE_HOST:$MIGRATE_PORT"
    echo "=========================================="

    if [ ! -d "$BACKUP_DIR" ] || [ ! -f "$BACKUP_DIR/sms_system.sql" ]; then
        echo "❌ 请先执行 backup"
        exit 1
    fi

    # 创建远程目录
    if [ -n "$MIGRATE_PASS" ]; then
        if command -v sshpass &>/dev/null; then
            sshpass -p "$MIGRATE_PASS" ssh -o StrictHostKeyChecking=no -p "$MIGRATE_PORT" "$MIGRATE_USER@$MIGRATE_HOST" "mkdir -p $MIGRATE_REMOTE_PATH"
            sshpass -p "$MIGRATE_PASS" scp -o StrictHostKeyChecking=no -P "$MIGRATE_PORT" -r "$BACKUP_DIR" "$MIGRATE_USER@$MIGRATE_HOST:$MIGRATE_REMOTE_PATH/"
            # 传输项目压缩包
            LATEST_ARCHIVE=$(ls -t "$BACKUP_DIR"/smsc_backup_*.tar.gz 2>/dev/null | head -1)
            if [ -n "$LATEST_ARCHIVE" ]; then
                sshpass -p "$MIGRATE_PASS" scp -o StrictHostKeyChecking=no -P "$MIGRATE_PORT" "$LATEST_ARCHIVE" "$MIGRATE_USER@$MIGRATE_HOST:$MIGRATE_REMOTE_PATH/"
            fi
        else
            echo "请安装 sshpass: apt install sshpass"
            exit 1
        fi
    else
        ssh -o StrictHostKeyChecking=no -p "$MIGRATE_PORT" "$MIGRATE_USER@$MIGRATE_HOST" "mkdir -p $MIGRATE_REMOTE_PATH"
        scp -o StrictHostKeyChecking=no -P "$MIGRATE_PORT" -r "$BACKUP_DIR" "$MIGRATE_USER@$MIGRATE_HOST:$MIGRATE_REMOTE_PATH/"
        LATEST_ARCHIVE=$(ls -t "$BACKUP_DIR"/smsc_backup_*.tar.gz 2>/dev/null | head -1)
        [ -n "$LATEST_ARCHIVE" ] && scp -o StrictHostKeyChecking=no -P "$MIGRATE_PORT" "$LATEST_ARCHIVE" "$MIGRATE_USER@$MIGRATE_HOST:$MIGRATE_REMOTE_PATH/"
    fi

    echo ""
    echo "✅ 传输完成"
    echo "   请 SSH 登录新服务器执行: cd $MIGRATE_REMOTE_PATH && ./scripts/backup_and_migrate.sh restore"
}

do_restore() {
    echo "=========================================="
    echo "📥 在新服务器恢复"
    echo "=========================================="

    RESTORE_ROOT="${MIGRATE_REMOTE_PATH:-/var/smsc}"
    cd "$RESTORE_ROOT"

    if [ ! -d .backup_migrate ]; then
        echo "❌ 未找到 .backup_migrate 目录，请先执行 transfer"
        exit 1
    fi

    # 解压项目（若尚未解压）
    ARCHIVE=$(ls -t .backup_migrate/smsc_backup_*.tar.gz 2>/dev/null | head -1)
    if [ -n "$ARCHIVE" ] && [ ! -d backend ]; then
        echo "解压项目..."
        tar xzf "$ARCHIVE" -C .
        echo "✅ 项目已解压"
    elif [ -n "$ARCHIVE" ] && [ -d backend ]; then
        echo "项目已存在，覆盖解压..."
        tar xzf "$ARCHIVE" -C .
    fi

    # 复制 .env
    if [ -f .backup_migrate/.env ]; then
        cp .backup_migrate/.env .env
        echo "✅ .env 已恢复"
    else
        echo "⚠️  无 .env 备份，请复制 .env.example 为 .env 并配置"
    fi

    # 启动 MySQL 并等待就绪
    echo "启动 MySQL..."
    docker compose up -d mysql
    echo "等待 MySQL 就绪..."
    for i in $(seq 1 30); do
        if docker compose exec -T mysql mysqladmin ping -h localhost -u root -p"${MYSQL_ROOT_PASSWORD:-rootpass123}" 2>/dev/null; then
            break
        fi
        sleep 2
    done

    # 恢复数据库
    echo "恢复数据库..."
    docker compose exec -T mysql mysql -uroot -p"${MYSQL_ROOT_PASSWORD:-rootpass123}" -e "CREATE DATABASE IF NOT EXISTS $DB_NAME;" 2>/dev/null || true
    docker compose exec -T mysql mysql -uroot -p"${MYSQL_ROOT_PASSWORD:-rootpass123}" "$DB_NAME" < .backup_migrate/sms_system.sql
    echo "✅ 数据库已恢复"

    # 启动全部服务
    echo "启动全部服务..."
    docker compose up -d
    echo ""
    echo "=========================================="
    echo "✅ 迁移恢复完成"
    IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "localhost")
    echo "   前端: http://${IP}:80"
    echo "   API:  http://${IP}:8000"
    echo "=========================================="
}

case "${1:-}" in
    backup)   do_backup ;;
    transfer) do_transfer ;;
    restore)  do_restore ;;
    *)
        echo "用法: $0 {backup|transfer|restore}"
        echo ""
        echo "  backup   - 在当前服务器备份数据库和项目"
        echo "  transfer - 传输备份到新服务器 (需配置 MIGRATE_* 环境变量)"
        echo "  restore  - 在新服务器上恢复"
        exit 1
        ;;
esac
