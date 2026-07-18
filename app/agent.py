from deepagents import create_deep_agent
from app.tools.product_tools import create_product, get_stock_level


def build_agent():
    return create_deep_agent(
        model="gemini-3.1-flash-lite",
        tools=[create_product, get_stock_level],
        system_prompt=(
            "You run a super market store's operations via chat. "
            "Always use tools for prices, stock, and GST — never invent numbers. "
            "Ask a clarifying question when a product name is ambiguous."
        ),
    )