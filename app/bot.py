from claude_agent_sdk import ClaudeSDKClient, AssistantMessage, TextBlock
from app.agent import build_agent_options

active_clients: dict[str, ClaudeSDKClient] = {}

async def get_client_for_chat(chat_id: str) -> ClaudeSDKClient:
    if chat_id not in active_clients:
        client = ClaudeSDKClient(options=build_agent_options())
        await client.connect()
        active_clients[chat_id] = client
    return active_clients[chat_id]

async def handle_telegram_message(chat_id: str, text: str) -> str:
    client = await get_client_for_chat(chat_id)
    await client.query(text)

    reply_parts = []
    async for message in client.receive_response():
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    reply_parts.append(block.text)
       

    return "".join(reply_parts) or "Sorry, I couldn't process that."