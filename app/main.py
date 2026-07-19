import logging
import httpx
from fastapi import FastAPI, Request, Header, HTTPException
from app.config import TELEGRAM_WEBHOOK_SECRET, TELEGRAM_BOT_TOKEN
from app.db import SessionLocal
from app.model import ProcessedUpdate,ChatSession
from app.bot import handle_telegram_message  # the function from agent.py/bot.py
from contextlib import asynccontextmanager
from app.agent import init_checkpointer,build_agent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("super-market-bot")

@asynccontextmanager
async def lifespan(app: FastAPI):
    with init_checkpointer() as checkpointer:
        app.state.agent = build_agent(checkpointer)
        yield

app = FastAPI()


WEBHOOK_PATH = f"/webhook/{TELEGRAM_BOT_TOKEN}"
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

def _chat_session_row(db,chat_id:str)->None:
    existing = db.query(ChatSession).filter(ChatSession.chat_id == chat_id).first()
    if not existing:
        db.add(ChatSession(chat_id=chat_id, owner_id="default", current_draft_bill_id=None))
        db.commit()

@app.post(WEBHOOK_PATH)
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
):
    if x_telegram_bot_api_secret_token != TELEGRAM_WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="Invalid secret token")

    update = await request.json()
    update_id = str(update.get("update_id"))
    

   
    db = SessionLocal()
    try:
        already_seen = db.query(ProcessedUpdate).filter(
            ProcessedUpdate.update_id == update_id
        ).first()
        if already_seen:
            logger.info(f"Duplicate update {update_id}, skipping")
            return {"ok": True}

        db.add(ProcessedUpdate(update_id=update_id))
        db.commit()
    finally:
        db.close()

    message = update.get("message")
    if message and "text" in message:
        chat_id = str(message["chat"]["id"])
        text = message["text"]
        logger.info(f"Message from {chat_id}: {text}")

        db = SessionLocal()
        try:
            _chat_session_row(db,chat_id)
        finally:
            db.close()

        # Run the agent and get its reply
        reply_text = await handle_telegram_message(request,chat_id, text)

        # Send the reply back to Telegram
        async with httpx.AsyncClient() as http_client:
            await http_client.post(
                f"{TELEGRAM_API}/sendMessage",
                json={"chat_id": chat_id, "text": reply_text},
            )

    return {"ok": True}