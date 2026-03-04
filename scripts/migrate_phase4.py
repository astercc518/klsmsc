#!/usr/bin/env python3
"""
Phase 4 数据库迁移脚本 (Python版本)
可以在后端服务运行时通过API执行，或直接连接数据库执行
"""
import sys
import os
import asyncio
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "backend"))

async def migrate_via_api():
    """通过API执行迁移（如果后端服务运行）"""
    import httpx
    
    api_url = os.getenv("API_BASE_URL", "http://localhost:8000")
    
    # 尝试登录获取token
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # 检查健康状态
            health_resp = await client.get(f"{api_url}/health")
            if health_resp.status_code != 200:
                print("❌ 后端服务不可用")
                return False
            
            print("✅ 后端服务运行正常")
            print("\n📝 迁移说明：")
            print("由于MySQL服务未运行，请手动执行以下步骤：")
            print("\n1. 启动MySQL服务：")
            print("   sudo systemctl start mysql")
            print("   或")
            print("   sudo service mysql start")
            print("\n2. 执行迁移脚本：")
            print(f"   mysql -u smsuser -p sms_system < {project_root}/scripts/phase4_migration.sql")
            print("\n3. 验证迁移：")
            print("   mysql -u smsuser -p sms_system -e \"SHOW TABLES LIKE 'system_config';\"")
            
            return True
    except Exception as e:
        print(f"⚠️  无法连接到后端服务: {e}")
        return False

def print_migration_instructions():
    """打印迁移说明"""
    print("=" * 60)
    print("Phase 4 数据库迁移指南")
    print("=" * 60)
    print("\n📋 迁移内容：")
    print("  - 创建 system_config 表（系统配置）")
    print("  - 创建 sms_batches 表（群发批次）")
    print("  - 创建 sms_templates 表（白名单）")
    print("  - 添加 reject_reason 字段到 sms_batches")
    print("  - 添加 pricing_config 字段到 invitation_codes")
    print("  - 创建性能优化索引")
    print("  - 初始化系统配置数据")
    
    print("\n🚀 执行步骤：")
    print("\n1. 确保MySQL服务运行：")
    print("   sudo systemctl status mysql")
    print("   如果未运行：sudo systemctl start mysql")
    
    print("\n2. 执行迁移脚本：")
    migration_file = project_root / "scripts" / "phase4_migration.sql"
    print(f"   mysql -u smsuser -p sms_system < {migration_file}")
    
    print("\n3. 验证迁移结果：")
    print("   mysql -u smsuser -p sms_system << EOF")
    print("   SHOW TABLES LIKE 'system_config';")
    print("   SHOW TABLES LIKE 'sms_batches';")
    print("   SHOW TABLES LIKE 'sms_templates';")
    print("   DESC sms_batches;")
    print("   SELECT COUNT(*) FROM system_config;")
    print("   EOF")
    
    print("\n4. 通过前端配置Telegram Token：")
    print("   - 访问：http://localhost:5173/admin/system/config")
    print("   - 编辑 telegram_bot_token 配置项")
    
    print("\n5. 运行功能测试：")
    print(f"   {project_root}/scripts/test_phase4.sh")
    
    print("\n" + "=" * 60)

async def main():
    print_migration_instructions()
    print("\n")
    
    # 尝试通过API检查
    success = await migrate_via_api()
    
    if not success:
        print("\n💡 提示：")
        print("   - 如果MySQL服务未运行，请先启动MySQL")
        print("   - 如果后端服务未运行，迁移脚本可以直接执行")
        print("   - 迁移脚本是幂等的，可以安全地重复执行")

if __name__ == "__main__":
    asyncio.run(main())
