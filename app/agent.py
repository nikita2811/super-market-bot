from claude_agent_sdk import create_sdk_mcp_server, ClaudeAgentOptions, ClaudeSDKClient
from app.tools.product_tools import create_product
# from app.tools.billing import add_bill_item, finalize_bill  # etc, as you build them

server = create_sdk_mcp_server(
    name="super-market-tools",
    version="1.0.0",
    tools=[create_product] 
)

def build_agent_options() -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        mcp_servers={"super-market-tools": server},
        allowed_tools=[
            "mcp__super-market-tools__create_product",
            
        ],
        system_prompt=(
            "You run a super market store's operations via chat. "
            "Always use tools for prices, stock, and GST — never invent numbers. "
            "Ask a clarifying question when a product name is ambiguous."
        ),
    )