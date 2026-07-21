import re
import os
import logging
import time
import asyncio

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("super-market-bot")


FILE_PRODUCING_TOOLS = {"generate_invoice_pdf", "generate_report_pptx"}
FILE_PATH_PATTERN = re.compile(r"FILE_PATH:\s*(\S+)")


async def handle_telegram_message(request, chat_id: str, text: str, update_id: str) -> dict:
    t0 = time.monotonic()
    agent = request.app.state.agent
    config = {
        "configurable": {
            "chat_id": chat_id,
            "thread_id": chat_id,
            "update_id": update_id,
        }
    }

  
    prior_state = agent.get_state(config)
    prior_count = len(prior_state.values.get("messages", [])) if prior_state.values else 0

    result = await asyncio.to_thread( agent.invoke({"messages": [{"role": "user", "content": text}]}), config=config)
    t1 = time.monotonic()
    logger.info(f"agent turn took {t1 - t0:.2f}s for chat {chat_id}")
    all_messages = result["messages"]
    new_messages = all_messages[prior_count:]  

    content = all_messages[-1].content
    if isinstance(content, list):
        reply_text = "".join(
            block["text"] for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ) or "Sorry, I couldn't process that."
    else:
        reply_text = content or "Sorry, I couldn't process that."

    file_paths = []  
    for msg in new_messages:  
        tool_name = getattr(msg, "name", None)
        if tool_name in FILE_PRODUCING_TOOLS:
            tool_content = msg.content if isinstance(msg.content, str) else str(msg.content)
            match = FILE_PATH_PATTERN.search(tool_content)
            if not match:
                continue
            path = match.group(1)
            if os.path.exists(path):
                file_paths.append(path)
            else:
                logger.error(f"Tool {tool_name} reported a path that doesn't exist: {path}")

    return {"text": reply_text, "file_paths": file_paths}
    