from claude_agent_sdk import tool, create_sdk_mcp_server, ClaudeAgentOptions, ClaudeSDKClient
from sqlalchemy.orm import Session
from app.model import Product, Bill, BillItem ,gen_id # your models
from app.db import SessionLocal  # your session factory
from sqlalchemy.exc import IntegrityError


VALID_UNITS = {"kg", "g", "litre", "ml", "packet", "dozen", "piece"}
VALID_GST_SLABS = {0, 5, 12, 18, 28}

@tool(
    "create_product",
    "Add a new product to the catalog with its SKU, unit, prices, GST slab, and HSN code. "
    "Use this only when the owner explicitly wants to add a new item that doesn't already exist — "
    "check with get_stock_level or search first if you're unsure whether it already exists. "
    "Ask the owner for any missing required detail (unit, GST slab, HSN code) rather than guessing.",
    {
        "sku": str,
        "name": str,
        "unit": str,           
        "is_loose": bool,
        "cost_price": float,
        "sell_price": float,   
        "hsn_code": str,
        "gst_slab": float,     
        "reorder_level": float,
        "initial_qty": float,  
    }
)
async def create_product(args):
    db = SessionLocal()
    try:
        unit = args["unit"].strip().lower()
        if unit not in VALID_UNITS:
            return {
                "content": [{"type": "text", "text": f"Invalid unit '{unit}'. Must be one of: {', '.join(sorted(VALID_UNITS))}"}],
                "is_error": True
            }

        if args["gst_slab"] not in VALID_GST_SLABS:
            return {
                "content": [{"type": "text", "text": f"Invalid GST slab {args['gst_slab']}%. Must be one of: {sorted(VALID_GST_SLABS)}"}],
                "is_error": True
            }

        if args["cost_price"] <= 0 or args["sell_price"] <= 0:
            return {
                "content": [{"type": "text", "text": "Cost price and sell price must both be greater than zero"}],
                "is_error": True
            }

        if args["sell_price"] < args["cost_price"]:
            return {
                "content": [{"type": "text", "text": f"Warning: sell price (₹{args['sell_price']}) is below cost price (₹{args['cost_price']}) — confirm this is intentional before I proceed"}],
                "is_error": True
            }

        existing = db.query(Product).filter(Product.sku == args["sku"]).first()
        if existing:
            return {
                "content": [{"type": "text", "text": f"A product with SKU '{args['sku']}' already exists: {existing.name}"}],
                "is_error": True
            }

        product = Product(
            id=gen_id(),
            sku=args["sku"],
            name=args["name"],
            unit=unit,
            is_loose=1 if args["is_loose"] else 0,
            cost_price=args["cost_price"],
            sell_price=args["sell_price"],
            hsn_code=args["hsn_code"],
            gst_slab=args["gst_slab"],
            qty_on_hand=args.get("initial_qty", 0),
            reorder_level=args["reorder_level"],
        )
        db.add(product)
        db.commit()

        return {
            "content": [{
                "type": "text",
                "text": f"Created product '{product.name}' (SKU: {product.sku}), MRP ₹{product.sell_price}, GST {product.gst_slab}%, stock: {product.qty_on_hand} {product.unit}"
            }]
        }

    except IntegrityError:
        db.rollback()
        return {"content": [{"type": "text", "text": "A product with this SKU already exists (constraint violation)"}], "is_error": True}
    finally:
        db.close()




