import uuid
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime
from langchain_core.tools import tool
from app.db import SessionLocal
from app.model import Bill, BillItem, Product, StockMovement, BillStatus, MovementReason,ChatSession, gen_id
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

def _get_or_set_current_bill(db, chat_id: str, bill_id: str | None = None) -> str | None:
    session = db.query(ChatSession).filter(ChatSession.chat_id == chat_id).first()
    if not session:
        session = ChatSession(chat_id=chat_id, owner_id="default", current_draft_bill_id=bill_id)
        db.add(session)
    elif bill_id is not None:
        session.current_draft_bill_id = bill_id
    db.commit()
    return session.current_draft_bill_id


def _round2(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate_gst(line_subtotal: float, gst_slab: float, is_intra_state: bool = True) -> dict:
    """Internal helper — NOT agent-facing. Splits GST into CGST/SGST (intra-state)
    and returns rounded amounts. Call this from other tools, don't register it with the agent."""
    subtotal = Decimal(str(line_subtotal))
    slab = Decimal(str(gst_slab))
    total_tax = _round2(subtotal * slab / Decimal("100"))

    if is_intra_state:
        cgst = _round2(total_tax / 2)
        sgst = total_tax - cgst  
    else:
        cgst = Decimal("0.00")
        sgst = Decimal("0.00")  

    line_total = subtotal + cgst + sgst
    return {
        "cgst": cgst,
        "sgst": sgst,
        "line_total": _round2(line_total),
    }


@tool
def start_bill(customer_id: str | None = None, payment_mode: str | None = None) -> str:
    """Start a new draft bill. Call this when the owner begins cutting a bill
    (e.g. "make a bill: ..."). Returns the bill_id needed for all subsequent
    add_bill_item / finalize_bill calls in this transaction. customer_id is only
    needed if this sale goes on credit (khata) — otherwise leave it unset."""
    db = SessionLocal()
    try:
        bill = Bill(
            id=gen_id(),
            chat_id="",  # set by caller/wrapper if you thread chat_id through; see note below
            status=BillStatus.draft,
            customer_id=customer_id,
            payment_mode=payment_mode,
            subtotal=0,
            cgst=0,
            sgst=0,
            total=0,
        )
        db.add(bill)
        db.commit()
        return f"Started new bill (bill_id: {bill.id}). Add items with add_bill_item."
    finally:
        db.close()


@tool
def add_bill_item(bill_id: str, sku_or_name: str, qty: float) -> str:
    """Add an item to a draft bill by quantity. Enforces stock availability — refuses
    if there isn't enough stock (oversell guard). Call this once per item the owner
    mentions. Does NOT decrement stock yet — stock is only decremented on finalize_bill."""
    db = SessionLocal()
    try:
        if qty <= 0:
            return "Quantity must be greater than zero"

        bill = db.query(Bill).filter(Bill.id == bill_id).first()
        if not bill:
            return f"No draft bill found with id '{bill_id}'"
        if bill.status != BillStatus.draft:
            return f"Bill {bill_id} is already {bill.status.value} — can't add items to it"

        product = db.query(Product).filter(
            (Product.sku == sku_or_name) | (Product.name.ilike(f"%{sku_or_name}%"))
        ).first()
        if not product:
            return f"No product found matching '{sku_or_name}'"

        # Oversell guard: account for qty already reserved on THIS draft bill for the same product
        already_on_bill = sum(
            float(i.qty) for i in bill.items if i.product_id == product.id
        )
        if float(product.qty_on_hand) < already_on_bill + qty:
            available = float(product.qty_on_hand) - already_on_bill
            return (
                f"Not enough stock: only {available} {product.unit} of {product.name} "
                f"available (have {product.qty_on_hand}, {already_on_bill} already on this bill) — can't add {qty}"
            )

        line_subtotal = _round2(float(product.sell_price) * qty)
        gst = calculate_gst(float(line_subtotal), float(product.gst_slab))

        item = BillItem(
            id=gen_id(),
            bill_id=bill.id,
            product_id=product.id,
            product_name=product.name,
            qty=qty,
            unit_price=product.sell_price,
            gst_slab=product.gst_slab,
            hsn_code=product.hsn_code,
            line_subtotal=line_subtotal,
            cgst_amt=gst["cgst"],
            sgst_amt=gst["sgst"],
            line_total=gst["line_total"],
        )
        db.add(item)

        # keep bill's running totals in sync for get_bill_draft
        bill.subtotal = float(bill.subtotal) + float(line_subtotal)
        bill.cgst = float(bill.cgst) + float(gst["cgst"])
        bill.sgst = float(bill.sgst) + float(gst["sgst"])
        bill.total = float(bill.total) + float(gst["line_total"])
        db.commit()

        return f"Added {qty} {product.unit} {product.name} @ ₹{product.sell_price} = ₹{gst['line_total']} (incl. GST) to bill {bill_id}"
    finally:
        db.close()


@tool
def remove_bill_item(bill_id: str, item_id: str) -> str:
    """Remove a specific item from a draft bill (e.g. "drop the butter").
    Use get_bill_draft first if you need the item_id for a named item."""
    db = SessionLocal()
    try:
        bill = db.query(Bill).filter(Bill.id == bill_id).first()
        if not bill:
            return f"No draft bill found with id '{bill_id}'"
        if bill.status != BillStatus.draft:
            return f"Bill {bill_id} is already {bill.status.value} — can't edit it"

        item = next((i for i in bill.items if i.id == item_id), None)
        if not item:
            return f"No item '{item_id}' found on bill {bill_id}"

        bill.subtotal = float(bill.subtotal) - float(item.line_subtotal)
        bill.cgst = float(bill.cgst) - float(item.cgst_amt)
        bill.sgst = float(bill.sgst) - float(item.sgst_amt)
        bill.total = float(bill.total) - float(item.line_total)

        db.delete(item)
        db.commit()
        return f"Removed {item.product_name} from bill {bill_id}"
    finally:
        db.close()


@tool
def update_bill_item(bill_id: str, item_id: str, qty: float) -> str:
    """Change the quantity of an existing item on a draft bill (e.g. "make it 6 Maggi").
    Re-checks stock availability and recalculates GST for the new quantity."""
    db = SessionLocal()
    try:
        if qty <= 0:
            return "Quantity must be greater than zero — use remove_bill_item to remove it instead"

        bill = db.query(Bill).filter(Bill.id == bill_id).first()
        if not bill:
            return f"No draft bill found with id '{bill_id}'"
        if bill.status != BillStatus.draft:
            return f"Bill {bill_id} is already {bill.status.value} — can't edit it"

        item = next((i for i in bill.items if i.id == item_id), None)
        if not item:
            return f"No item '{item_id}' found on bill {bill_id}"

        product = db.query(Product).filter(Product.id == item.product_id).first()

        # oversell guard for the new qty, excluding this item's own current reservation
        already_on_bill_other_items = sum(
            float(i.qty) for i in bill.items if i.product_id == product.id and i.id != item.id
        )
        if float(product.qty_on_hand) < already_on_bill_other_items + qty:
            available = float(product.qty_on_hand) - already_on_bill_other_items
            return f"Not enough stock: only {available} {product.unit} of {product.name} available — can't set qty to {qty}"

        # back out old totals
        bill.subtotal = float(bill.subtotal) - float(item.line_subtotal)
        bill.cgst = float(bill.cgst) - float(item.cgst_amt)
        bill.sgst = float(bill.sgst) - float(item.sgst_amt)
        bill.total = float(bill.total) - float(item.line_total)

        # recompute for new qty
        line_subtotal = _round2(float(item.unit_price) * qty)
        gst = calculate_gst(float(line_subtotal), float(item.gst_slab))

        item.qty = qty
        item.line_subtotal = line_subtotal
        item.cgst_amt = gst["cgst"]
        item.sgst_amt = gst["sgst"]
        item.line_total = gst["line_total"]

        bill.subtotal = float(bill.subtotal) + float(line_subtotal)
        bill.cgst = float(bill.cgst) + float(gst["cgst"])
        bill.sgst = float(bill.sgst) + float(gst["sgst"])
        bill.total = float(bill.total) + float(gst["line_total"])

        db.commit()
        return f"Updated {item.product_name} to qty {qty} — new line total ₹{gst['line_total']}"
    finally:
        db.close()


@tool
def get_bill_draft(bill_id: str) -> str:
    """Show the current running total and line items for a draft bill —
    use this to preview a bill before finalizing, or when the owner asks
    what's on the bill so far."""
    db = SessionLocal()
    try:
        bill = db.query(Bill).filter(Bill.id == bill_id).first()
        if not bill:
            return f"No bill found with id '{bill_id}'"

        if not bill.items:
            return f"Bill {bill_id} is empty so far."

        lines = [
            f"- {i.product_name} x{i.qty} @ ₹{i.unit_price} = ₹{i.line_total} (GST {i.gst_slab}%: CGST ₹{i.cgst_amt} + SGST ₹{i.sgst_amt})"
            for i in bill.items
        ]
        return (
            f"Bill {bill_id} ({bill.status.value}):\n" + "\n".join(lines) +
            f"\nSubtotal: ₹{bill.subtotal} | CGST: ₹{bill.cgst} | SGST: ₹{bill.sgst} | Total: ₹{bill.total}"
        )
    finally:
        db.close()


@tool
def finalize_bill(bill_id: str, idempotency_key: str) -> str:
    """Finalize a draft bill — decrements stock atomically and locks the bill.
    idempotency_key must be a stable value for this specific finalize request
    (e.g. derived from the Telegram update_id) so that a retried request does NOT
    double-decrement stock or create a duplicate finalized bill. Call this only
    when the owner confirms the bill is complete (e.g. says "done", "finalize", "that's it")."""
    db = SessionLocal()
    try:
        # idempotency check FIRST, before touching anything else
        existing_by_key = db.query(Bill).filter(Bill.idempotency_key == idempotency_key).first()
        if existing_by_key:
            return f"Bill already finalized under this request (bill_id: {existing_by_key.id}, total ₹{existing_by_key.total}) — not double-charging."

        bill = db.query(Bill).filter(Bill.id == bill_id).first()
        if not bill:
            return f"No bill found with id '{bill_id}'"
        if bill.status != BillStatus.draft:
            return f"Bill {bill_id} is already {bill.status.value} — can't finalize again"
        if not bill.items:
            return f"Bill {bill_id} has no items — nothing to finalize"

        # Re-verify stock for every line item before committing to the decrement
        # (stock may have moved since add_bill_item due to another concurrent sale)
        for item in bill.items:
            product = db.query(Product).filter(Product.id == item.product_id).with_for_update().first()
            if float(product.qty_on_hand) < float(item.qty):
                db.rollback()
                return f"Cannot finalize: {product.name} now only has {product.qty_on_hand} {product.unit} in stock, but bill requires {item.qty}"

        # Atomic decrement per item, using a locked row (with_for_update above) to
        # prevent a concurrent sale from reading stale qty_on_hand
        for item in bill.items:
            db.execute(
                text("UPDATE products SET qty_on_hand = qty_on_hand - :qty WHERE id = :pid"),
                {"qty": float(item.qty), "pid": item.product_id},
            )
            db.add(StockMovement(
                id=gen_id(),
                product_id=item.product_id,
                delta=-float(item.qty),
                reason=MovementReason.sale,
                ref_id=bill.id,
                created_at=datetime.utcnow(),
            ))

        bill.status = BillStatus.finalized
        bill.idempotency_key = idempotency_key
        bill.finalized_at = datetime.utcnow()
        db.commit()

        return f"Bill {bill_id} finalized. Total: ₹{bill.total} ({bill.payment_mode or 'payment mode not set'})"

    except IntegrityError:
        db.rollback()
        # unique constraint on idempotency_key caught a race between two concurrent retries
        existing_by_key = db.query(Bill).filter(Bill.idempotency_key == idempotency_key).first()
        if existing_by_key:
            return f"Bill already finalized under this request (bill_id: {existing_by_key.id}) — not double-charging."
        return "Finalize failed due to a conflicting request — please retry."
    finally:
        db.close()


@tool
def void_bill(bill_id: str) -> str:
    """Cancel a FINALIZED bill and reverse its stock decrement. Refuses to void a
    draft bill (nothing to reverse) or a bill that's already void. Use this only
    when the owner explicitly wants to cancel a completed sale, not to edit a draft
    (use remove_bill_item / update_bill_item for drafts instead)."""
    db = SessionLocal()
    try:
        bill = db.query(Bill).filter(Bill.id == bill_id).first()
        if not bill:
            return f"No bill found with id '{bill_id}'"
        if bill.status == BillStatus.draft:
            return f"Bill {bill_id} is still a draft — nothing to void. Use remove_bill_item to edit it."
        if bill.status == BillStatus.void:
            return f"Bill {bill_id} is already void."

        for item in bill.items:
            db.execute(
                text("UPDATE products SET qty_on_hand = qty_on_hand + :qty WHERE id = :pid"),
                {"qty": float(item.qty), "pid": item.product_id},
            )
            db.add(StockMovement(
                id=gen_id(),
                product_id=item.product_id,
                delta=float(item.qty),
                reason=MovementReason.adjustment,
                ref_id=bill.id,
                created_at=datetime.utcnow(),
            ))

        bill.status = BillStatus.void
        db.commit()
        return f"Bill {bill_id} voided. Stock for {len(bill.items)} item(s) reversed."
    finally:
        db.close()