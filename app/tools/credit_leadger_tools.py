from datetime import datetime
from langchain_core.tools import tool
from app.db import SessionLocal
from app.model import Customer, AccountTransaction, AccountType, gen_id


@tool
def get_or_create_customer(name: str, phone: str | None = None) -> str:
    """Look up a customer by name, or create them if they don't exist yet.
    Use this before add_credit, record_payment, or get_balance if you're not
    sure whether the customer already exists — it's safe to call even if they do,
    it won't create a duplicate. Matches by name (case-insensitive); if phone is
    given and there's an ambiguous match, use it to disambiguate."""
    db = SessionLocal()
    try:
        query = db.query(Customer).filter(Customer.name.ilike(name.strip()))
        if phone:
            query = query.filter(Customer.phone == phone)
        existing = query.first()

        if existing:
            return f"Customer '{existing.name}' (customer_id: {existing.id}), current balance: ₹{existing.account_balance}"

        # No exact match — check for a same-name-different-phone or multiple similar names
        similar = db.query(Customer).filter(Customer.name.ilike(f"%{name.strip()}%")).all()
        if len(similar) > 1:
            lines = "\n".join(f"- {c.name} (id: {c.id}, phone: {c.phone or 'none'})" for c in similar)
            return f"Multiple customers match '{name}' — please confirm which one:\n{lines}"

        customer = Customer(
            id=gen_id(),
            name=name.strip(),
            phone=phone,
            account_balance=0,
        )
        db.add(customer)
        db.commit()
        return f"New customer created: '{customer.name}' (customer_id: {customer.id}), balance: ₹0"
    finally:
        db.close()


@tool
def add_credit(customer_id: str, amount: float, ref_bill_id: str | None = None) -> str:
    """Add an amount to a customer's khata (credit) balance — e.g. "put ₹500 on
    Ramesh's credit". Use get_or_create_customer first if you only have a name,
    not a customer_id. ref_bill_id is optional — pass it if this credit is tied
    to a specific bill being put on account rather than paid immediately."""
    db = SessionLocal()
    try:
        if amount <= 0:
            return "Credit amount must be greater than zero"

        customer = db.query(Customer).filter(Customer.id == customer_id).first()
        if not customer:
            return f"No customer found with id '{customer_id}' — use get_or_create_customer first"

        customer.account_balance = float(customer.account_balance) + amount

        db.add(AccountTransaction(
            id=gen_id(),
            customer_id=customer.id,
            type=AccountType.credit_sale,
            amount=amount,
            ref_bill_id=ref_bill_id,
            created_at=datetime.utcnow(),
        ))
        db.commit()

        return f"Added ₹{amount} credit for {customer.name}. New balance: ₹{customer.account_balance}"
    finally:
        db.close()


@tool
def record_payment(customer_id: str, amount: float) -> str:
    """Record a payment from a customer against their khata balance — e.g.
    "Ramesh paid ₹300". Use get_or_create_customer first if you only have a name.
    Refuses if the payment would take the balance negative — confirm with the
    owner if the customer is overpaying (e.g. clearing an old balance and adding
    extra credit) rather than silently allowing it."""
    db = SessionLocal()
    try:
        if amount <= 0:
            return "Payment amount must be greater than zero"

        customer = db.query(Customer).filter(Customer.id == customer_id).first()
        if not customer:
            return f"No customer found with id '{customer_id}' — use get_or_create_customer first"

        if amount > float(customer.account_balance):
            return (
                f"{customer.name}'s current balance is only ₹{customer.account_balance} — "
                f"₹{amount} would overpay by ₹{amount - float(customer.account_balance)}. "
                f"Confirm with the owner before recording this (they may want to record "
                f"only ₹{customer.account_balance}, or intentionally leave a credit balance)."
            )

        customer.account_balance = float(customer.account_balance) - amount

        db.add(AccountTransaction(
            id=gen_id(),
            customer_id=customer.id,
            type=AccountType.payment,
            amount=amount,
            ref_bill_id=None,
            created_at=datetime.utcnow(),
        ))
        db.commit()

        return f"Recorded ₹{amount} payment from {customer.name}. New balance: ₹{customer.account_balance}"
    finally:
        db.close()


@tool
def get_balance(customer_id: str) -> str:
    """Look up a customer's current khata (credit) balance — e.g. "what's Ramesh's
    balance?". Use get_or_create_customer first if you only have a name, not a
    customer_id."""
    db = SessionLocal()
    try:
        customer = db.query(Customer).filter(Customer.id == customer_id).first()
        if not customer:
            return f"No customer found with id '{customer_id}'"
        return f"{customer.name}'s balance: ₹{customer.account_balance}"
    finally:
        db.close()