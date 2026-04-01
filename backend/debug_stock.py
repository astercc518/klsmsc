
import asyncio
from datetime import date
from sqlalchemy import select
from app.database import AsyncSessionLocal
from app.modules.data.models import DataProduct, DataNumber
from app.api.v1.data.helpers import calculate_stock

async def test():
    async with AsyncSessionLocal() as db:
        # Check product 36
        res = await db.execute(select(DataProduct).where(DataProduct.id == 36))
        p = res.scalar_one_or_none()
        if not p:
            print("Product 36 not found")
            return
            
        print(f"Product: {p.product_name}")
        print(f"Criteria: {p.filter_criteria}")
        
        stock = await calculate_stock(db, p.filter_criteria, public_only=True)
        print(f"Calculated Stock: {stock}")
        
        # Check without freshness
        crit_no_fresh = p.filter_criteria.copy()
        crit_no_fresh.pop('freshness', None)
        stock_no_fresh = await calculate_stock(db, crit_no_fresh, public_only=True)
        print(f"Stock without freshness filter: {stock_no_fresh}")

if __name__ == "__main__":
    asyncio.run(test())
