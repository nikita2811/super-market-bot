import re
import os
import logging
import time
import asyncio

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("super-market-bot")


FILE_PRODUCING_TOOLS = {"generate_invoice_pdf", "generate_report_pptx"}
FILE_PATH_PATTERN = re.compile(r"FILE_PATH:\s*(\S+)")


def _extract_text(content) -> str:
    """Safely pull plain text out of either a string or a list-of-blocks content."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            block.get("text", "") for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        )
    return str(content)


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

    try:
        result = await asyncio.to_thread(
            agent.invoke,
            {"messages": [{"role": "user", "content": text}]},
            config=config,
        )
    except Exception:
        logger.exception(f"agent invoke failed for chat {chat_id}")
        return {"text": "Sorry, something went wrong processing that.", "file_path": None}

    t1 = time.monotonic()
    logger.info(f"agent turn took {t1 - t0:.2f}s for chat {chat_id}")

    all_messages = result["messages"]
    new_messages = all_messages[prior_count:]

    reply_text = _extract_text(all_messages[-1].content) or "Sorry, I couldn't process that."

    file_path = None
    tool_was_called = False
    for msg in new_messages:
        tool_name = getattr(msg, "name", None)
        if tool_name in FILE_PRODUCING_TOOLS:
            tool_was_called = True
            tool_content = _extract_text(msg.content)
            logger.info(f"tool={tool_name} raw_content={tool_content!r}")
            match = FILE_PATH_PATTERN.search(tool_content)
            if match:
                file_path = match.group(1)

  
    if not tool_was_called and FILE_PATH_PATTERN.search(reply_text):
        logger.warning(
            f"Model referenced a file path without a tool call, chat {chat_id}: {reply_text!r}"
        )
        reply_text = "Let me regenerate that for you — one moment."

    return {"text": reply_text, "file_path": file_path}