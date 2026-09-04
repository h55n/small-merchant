import asyncio
import time
from dotenv import load_dotenv

load_dotenv()

from src.database import AsyncSessionLocal
from src.models import BuyerSession
from src.database import DBSession

async def test_insert():
    async with AsyncSessionLocal() as db:
        session = BuyerSession(
            merchant_id="merch_DEMO01",
            purchase_intent="test",
            spending_limit_inr=1000.0,
        )
        db_session = DBSession(
            session_id=session.session_id,
            merchant_id=session.merchant_id,
            purchase_intent=session.purchase_intent,
            spending_limit_inr=session.spending_limit_inr,
            status="ACTIVE",
        )
        db.add(db_session)
        print("Committing insert...", flush=True)
        await db.commit()
        print("Success! Inserted:", session.session_id, flush=True)

if __name__ == "__main__":
    asyncio.run(test_insert())
