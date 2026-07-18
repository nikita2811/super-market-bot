from langchain_core.tools import tool
from app.db import SessionLocal
from app.model import Product, gen_id
from sqlalchemy.exc import IntegrityError

VALID_UNITS = {"kg", "g", "litre", "ml", "packet", "dozen", "piece"}
VALID_GST_SLABS = {0, 5, 12, 18, 28}


@tool
def create_product(
    sku: str,
    name: str,
    unit: str,
    is_loose: bool,
    cost_price: float,
    sell_price: float,
    hsn_code: str,
    gst_slab: float,
    reorder_level: float,
    initial_qty: float = 0,
) -> str:
    """Add a new product to the catalog with its SKU, unit, prices, GST slab, and HSN code.
    Use this only when the owner explicitly wants to add a new item that doesn't already exist —
    check with get_stock_level or search first if you're unsure whether it already exists.
    Ask the owner for any missing required detail (unit, GST slab, HSN code) rather than guessing.
    """
    db = SessionLocal()
    try:
        unit = unit.strip().lower()
        if unit not in VALID_UNITS:
            return f"Invalid unit '{unit}'. Must be one of: {', '.join(sorted(VALID_UNITS))}"

        if gst_slab not in VALID_GST_SLABS:
            return f"Invalid GST slab {gst_slab}%. Must be one of: {sorted(VALID_GST_SLABS)}"

        if cost_price <= 0 or sell_price <= 0:
            return "Cost price and sell price must both be greater than zero"

        if sell_price < cost_price:
            return f"Warning: sell price (₹{sell_price}) is below cost price (₹{cost_price}) — confirm this is intentional before I proceed"

        existing = db.query(Product).filter(Product.sku == sku).first()
        if existing:
            return f"A product with SKU '{sku}' already exists: {existing.name}"

        product = Product(
            id=gen_id(),
            sku=sku,
            name=name,
            unit=unit,
            is_loose=1 if is_loose else 0,
            cost_price=cost_price,
            sell_price=sell_price,
            hsn_code=hsn_code,
            gst_slab=gst_slab,
            qty_on_hand=initial_qty,
            reorder_level=reorder_level,
        )
        db.add(product)
        db.commit()
        return f"Created product '{product.name}' (SKU: {product.sku}), MRP ₹{product.sell_price}, GST {product.gst_slab}%, stock: {product.qty_on_hand} {product.unit}"

    except IntegrityError:
        db.rollback()
        return "A product with this SKU already exists (constraint violation)"
    finally:
        db.close()


@tool
def get_stock_level(sku_or_name: str) -> str:
    """Look up the current stock quantity for a product by SKU or name.
    Use this whenever the owner asks how much of an item is left."""
    db = SessionLocal()
    try:
        product = db.query(Product).filter(
            (Product.sku == sku_or_name) | (Product.name.ilike(f"%{sku_or_name}%"))
        ).first()
        if not product:
            return f"No product found matching '{sku_or_name}'"
        return f"{product.name}: {product.qty_on_hand} {product.unit} in stock"
    finally:
        db.close()