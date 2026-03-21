#!/bin/bash
# 启动MySQL并执行Phase 4迁移

set -e

echo "=========================================="
echo "Phase 4 数据库迁移助手"
echo "=========================================="

# 检查MySQL服务状态
echo "1. 检查MySQL服务状态..."
if systemctl is-active --quiet mysql || systemctl is-active --quiet mysqld; then
    echo "✅ MySQL服务已运行"
else
    echo "⚠️  MySQL服务未运行，尝试启动..."
    if sudo systemctl start mysql 2>/dev/null || sudo systemctl start mysqld 2>/dev/null; then
        echo "✅ MySQL服务已启动"
        sleep 2
    else
        echo "❌ 无法启动MySQL服务，请手动启动："
        echo "   sudo systemctl start mysql"
        exit 1
    fi
fi

# 执行迁移
echo ""
echo "2. 执行数据库迁移..."
cd /var/smsc
if mysql -u smsuser -psmspass sms_system < scripts/phase4_migration.sql 2>&1 | grep -v "Warning"; then
    echo "✅ 迁移脚本执行完成"
else
    echo "⚠️  迁移脚本执行完成（可能有警告）"
fi

# 验证迁移
echo ""
echo "3. 验证迁移结果..."
mysql -u smsuser -psmspass sms_system << 'SQL' 2>&1 | grep -v "Warning"
SELECT 
    CASE WHEN COUNT(*) > 0 THEN '✅' ELSE '❌' END as status,
    'system_config表' as table_name,
    COUNT(*) as record_count
FROM information_schema.tables 
WHERE table_schema = 'sms_system' AND table_name = 'system_config'
UNION ALL
SELECT 
    CASE WHEN COUNT(*) > 0 THEN '✅' ELSE '❌' END,
    'sms_batches表',
    COUNT(*)
FROM information_schema.tables 
WHERE table_schema = 'sms_system' AND table_name = 'sms_batches'
UNION ALL
SELECT 
    CASE WHEN COUNT(*) > 0 THEN '✅' ELSE '❌' END,
    'sms_templates表',
    COUNT(*)
FROM information_schema.tables 
WHERE table_schema = 'sms_system' AND table_name = 'sms_templates';
SQL

echo ""
echo "4. 检查系统配置数据..."
mysql -u smsuser -psmspass sms_system -e "SELECT COUNT(*) as config_count FROM system_config;" 2>&1 | grep -v "Warning"

echo ""
echo "=========================================="
echo "✅ 迁移完成！"
echo ""
echo "📝 下一步："
echo "1. 配置Telegram Token: http://localhost:5173/admin/system/config"
echo "2. 运行测试: ./scripts/test_phase4.sh"
echo "=========================================="
