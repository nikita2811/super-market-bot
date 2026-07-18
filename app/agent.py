from deepagents import create_deep_agent
from app.tools.product_tools import (create_product, get_stock_level,update_product,
                                     get_product,search_products,receive_stock,list_low_stock)
from app.tools.credit_leadger_tools import (get_or_create_customer,add_credit,record_payment,get_balance)


def build_agent():
    return create_deep_agent(
        model="google_genai:gemini-3.1-flash-lite",
        tools=[create_product, get_stock_level,update_product,get_product,search_products,receive_stock,list_low_stock,get_or_create_customer,add_credit,record_payment,get_balance],
        system_prompt=(
            "You run a super market store's operations via chat. The owner writes in "
    "short, terse, real-shopkeeper English or Hinglish — messages may be fragments, "
    "missing punctuation, or mix Hindi words. Parse the intent even from casual phrasing. "
    "Always use tools for prices, stock, and GST — never invent numbers. "
    "Ask a clarifying question when a product name is ambiguous or a required detail is missing."
        ),
    )