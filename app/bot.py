from app.agent import build_agent




async def handle_telegram_message(request,chat_id: str, text: str) -> str:
     agent = request.app.state.agent
     result = agent.invoke(
        {"messages": [{"role": "user", "content": text}]},
        config={
            "configurable": {
                "chat_id": chat_id,
                "thread_id": chat_id,
            }
        },
     )
     content = result["messages"][-1].content
     
     if isinstance(content, list):
         # content blocks — pull text parts and join
         return "".join(
             block["text"] for block in content
             if isinstance(block, dict) and block.get("type") == "text"
         ) or "Sorry, I couldn't process that."
     return content or "Sorry, I couldn't process that."

