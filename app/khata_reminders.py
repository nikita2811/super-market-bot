from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.db import SessionLocal
from app.model import Customer

async def send_khata_reminders(bot_send_fn):
    db = SessionLocal()
    try:
        overdue = db.query(Customer).filter(Customer.account_balance > 0).all()
        for c in overdue:
            await bot_send_fn(c.chat_id, f"Reminder: ₹{c.account_balance} outstanding.")
    finally:
        db.close()