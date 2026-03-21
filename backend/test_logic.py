import asyncio
import sys
import os

# Backend root is current dir in container
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database import AsyncSessionLocal as async_session_maker
from app.core.invitation import InvitationService
from app.core.audit import AuditService
from app.core.pricing import PricingEngine
from app.models.admin_user import AdminUser
from app.models.account import Account
from app.models.sms_batch import SMSBatch
from sqlalchemy import select

async def main():
    print("🚀 Starting Phase 3 Logic Integration Test...")
    
    async with async_session_maker() as db:
        # 1. Setup: Ensure Sales Admin exists
        print("\n[1] Setup Sales Admin...")
        result = await db.execute(select(AdminUser).where(AdminUser.username == 'sales_test'))
        sales = result.scalar_one_or_none()
        if not sales:
            sales = AdminUser(
                username='sales_test',
                password_hash='hash_placeholder',
                role='sales',
                real_name='Test Sales',
                tg_id=999999
            )
            db.add(sales)
            await db.commit()
            print("    Created sales_test admin.")
        else:
            print("    sales_test admin exists.")
            
        # 2. Invitation Service: Generate Code
        print("\n[2] Testing Invitation Service...")
        invitation_service = InvitationService(db)
        config = {"country": "CN", "price": 0.06, "business_type": "sms"}
        code = await invitation_service.create_code(sales.id, config)
        print(f"    Generated Invite Code: {code}")
        
        # 3. Customer Activate
        print("\n[3] Testing Customer Activation...")
        tg_id = 888888
        try:
            account, api_key = await invitation_service.activate_code(code, tg_id)
            print(f"    Account Created: ID={account.id}, Name={account.account_name}")
            print(f"    API Key: {api_key}")
        except Exception as e:
            print(f"    Activation Failed: {e}")
            return

        # Verify Pricing
        pricing_engine = PricingEngine(db)
        price_info = await pricing_engine.get_price(1, 'CN', account_id=account.id)
        print(f"    Pricing Check (CN): {price_info}")
        if price_info and price_info['price'] == 0.06:
            print("    ✅ Custom Pricing Applied Successfully!")
        else:
            print("    ❌ Custom Pricing Mismatch!")

        # 4. Bulk Submission & Audit
        print("\n[4] Testing Bulk Submission & Audit...")
        audit_service = AuditService(db)
        content = "Test Batch Content [1234]"
        batch_id = "BATCH_TEST_001"
        
        # Submit
        batch = await audit_service.submit_batch(
            account_id=account.id,
            file_path="/tmp/test.txt",
            content=content,
            total_count=100,
            total_cost=6.0,
            batch_id=batch_id
        )
        print(f"    Batch Submitted: Status={batch.status}")
        
        if batch.status != 'pending_audit':
            print("    ❌ Expected pending_audit status!")
        
        # Approve
        print("    Approving Batch...")
        approved_batch = await audit_service.approve_batch(batch_id, sales.id)
        print(f"    Batch Status: {approved_batch.status}")
        
        if approved_batch.status == 'sending':
            print("    ✅ Batch Approved & Sending!")
        else:
            print("    ❌ Batch Approval Failed!")
            
        # 5. Test Auto-Pass (Allowlist)
        print("\n[5] Testing Auto-Pass Logic...")
        batch_id_2 = "BATCH_TEST_002"
        batch2 = await audit_service.submit_batch(
            account_id=account.id,
            file_path="/tmp/test2.txt",
            content=content, # Same content
            total_count=50,
            total_cost=3.0,
            batch_id=batch_id_2
        )
        print(f"    Second Batch Status: {batch2.status}")
        
        if batch2.status == 'sending':
            print("    ✅ Auto-Pass Worked! (Skipped Audit)")
        else:
            print(f"    ❌ Auto-Pass Failed! Status: {batch2.status}")

if __name__ == "__main__":
    asyncio.run(main())
