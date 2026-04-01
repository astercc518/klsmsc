
import asyncio
from app.workers.data_worker import _refresh_all_stock

async def run():
    print("Starting stock refresh...")
    result = await _refresh_all_stock()
    print(f"Refresh completed: {result}")

if __name__ == "__main__":
    asyncio.run(run())
