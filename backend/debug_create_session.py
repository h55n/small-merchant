import asyncio
import time
from dotenv import load_dotenv

load_dotenv()

from src.database import AsyncSessionLocal
from src.catalog.storage import get_catalog
from src.models import CreateSessionRequest, BuyerSession
from src.database import DBSession

async def debug():
    t0 = time.time()
    print("1. Opening DB session...", flush=True)
    async with AsyncSessionLocal() as db:
        print(f"   Opened in {time.time()-t0:.3f}s", flush=True)
        
        t1 = time.time()
        print("2. Calling get_catalog('merch_DEMO01')...", flush=True)
        catalog = await get_catalog(db, "merch_DEMO01")
        print(f"   Got catalog in {time.time()-t1:.3f}s: {catalog.merchant_name if catalog else None}", flush=True)
        
        t2 = time.time()
        print("3. Creating BuyerSession & DBSession...", flush=True)
        req = CreateSessionRequest(
            merchant_id="merch_DEMO01",
            purchase_intent="test intent",
            spending_limit_inr=2000.0,
        )
        session = BuyerSession(
            merchant_id=req.merchant_id,
            purchase_intent=req.purchase_intent,
            spending_limit_inr=req.spending_limit_inr,
        )
        db_session = DBSession(
            session_id=session.session_id,
            merchant_id=session.merchant_id,
            purchase_intent=session.purchase_intent,
            spending_limit_inr=session.spending_limit_inr,
            status="ACTIVE",
        )
        db.add(db_session)
        print(f"   Added in {time.time()-t2:.3f}s", flush=True)
        
        t3 = time.time()
        print("4. Committing to DB...", flush=True)
        await db.commit()
        print(f"   Committed in {time.time()-t3:.3f}s! Session ID: {session.session_id}", flush=True)
        
    print(f"Total time: {time.time()-t0:.3f}s", flush=True)

if __name__ == "__main__":
    asyncio.run(debug())
