import sys
import os
import asyncio
from sqlalchemy import select

# 添加 backend 到路径
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from app.database import AsyncSessionLocal
from app.models import AdminUser
from app.core.auth import AuthService

async def reset_admin_password():
    async with AsyncSessionLocal() as db:
        # 查询 admin 用户
        result = await db.execute(select(AdminUser).where(AdminUser.username == 'admin'))
        admin = result.scalar_one_or_none()
        
        if not admin:
            print("❌ Admin user not found! Creating...")
            # 创建新管理员
            hashed = AuthService.hash_password('admin123')
            admin = AdminUser(
                username='admin',
                role='super_admin',
                real_name='Super Admin',
                status='active',
                password_hash=hashed
            )
            db.add(admin)
            await db.commit()
            print(f"✅ Created admin user, password: admin123")
            return
        
        # 重置密码
        new_password = 'admin123'
        hashed = AuthService.hash_password(new_password)
        admin.password_hash = hashed
        admin.login_failed_count = 0
        admin.status = 'active'
        
        await db.commit()
        print(f"✅ Password for 'admin' reset to '{new_password}'")

if __name__ == "__main__":
    asyncio.run(reset_admin_password())
