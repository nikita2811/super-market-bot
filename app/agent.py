from deepagents import create_deep_agent
from app.tools.products import create_product, get_stock_level
# from app.tools.billing import add_bill_item, finalize_bill  # as you build more

def build_agent():
    return create_deep_agent(
        model="google_genai:gemini-3-flash",  # free-tier-eligible model
        tools=[create_product, get_stock_level],
        system_prompt=(
            "You run a super market store's operations via chat. "
            "Always use tools for prices, stock, and GST — never invent numbers. "
            "Ask a clarifying question when a product name is ambiguous."
        ),
    )