import re


FILE_PRODUCING_TOOLS = {"generate_invoice_pdf", "generate_report_pptx"}
FILE_PATH_PATTERN = re.compile(r"FILE_PATH:\s*(\S+)")




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
     messages = result["messages"]
     content = result["messages"][-1].content
     
     if isinstance(content, list):
         # content blocks — pull text parts and join
         return "".join(
             block["text"] for block in content
             if isinstance(block, dict) and block.get("type") == "text"
         ) or "Sorry, I couldn't process that."
     else:
        reply_text = content or "Sorry, I couldn't process that."
     file_path = None
     for msg in messages:
        tool_name = getattr(msg, "name", None)
        if tool_name in FILE_PRODUCING_TOOLS:
            tool_content = msg.content if isinstance(msg.content, str) else str(msg.content)
            match = FILE_PATH_PATTERN.search(tool_content)
            if match:
                file_path = match.group(1)

     return {"text": reply_text, "file_path": file_path}
     

