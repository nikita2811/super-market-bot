import logging
from fastapi import FastAPI, Request, Header, HTTPException
from app.config import TELEGRAM_WEBHOOK_SECRET, TELEGRAM_BOT_TOKEN

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("super-market-bot")

app = FastAPI()



WEBHOOK_PATH = f"/webhook/{TELEGRAM_BOT_TOKEN}"


@app.post(WEBHOOK_PATH)
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
):
    if x_telegram_bot_api_secret_token != TELEGRAM_WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="Invalid secret token")

    update = await request.json()
    message = update.get("message")

    if message and "text" in message:
        chat_id = message["chat"]["id"]
        text = message["text"]
        logger.info(f"Message from {chat_id}: {text}")

    return {"ok": True}  # respond fast so Telegram doesn't retry