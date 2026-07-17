from claude_agent_sdk import ClaudeSDKClient
from app.agent import build_agent_options

# one client per chat_id, so each Telegram conversation keeps its own context
active_clients: dict[str, ClaudeSDKClient] = {}

async def get_client_for_chat(chat_id: str) -> ClaudeSDKClient:
    if chat_id not in active_clients:
        client = ClaudeSDKClient(options=build_agent_options())
        await client.connect()
        active_clients[chat_id] = client
    return active_clients[chat_id]

async def handle_telegram_message(chat_id: str, text: str):
    client = await get_client_for_chat(chat_id)
    await client.query(text)

    reply_parts = []
    async for message in client.receive_response():
        if message.type == "text":
            reply_parts.append(message.text)
        # tool_use / tool_result messages will also stream through here if you want to log them

    return "".join(reply_parts)