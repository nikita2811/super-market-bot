from app.agent import build_agent

agent = build_agent()  # can be built once and reused across chats

async def handle_telegram_message(chat_id: str, text: str) -> str:
    result = agent.invoke({"messages": [{"role": "user", "content": text}]})
    return result["messages"][-1].content or "Sorry, I couldn't process that."