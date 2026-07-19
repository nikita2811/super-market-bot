# app/tools/preferences.py
from langchain_core.tools import tool
from app.db import SessionLocal
from app.model import Preference, gen_id
from sqlalchemy.exc import IntegrityError

DEFAULT_OWNER_ID = "default"  # single-owner shop for this assignment; see note below


@tool
def get_preference(key: str) -> str:
    """Look up a standing owner preference by key — e.g. 'default_payment_mode',
    'preferred_atta_brand', 'shop_name', 'gstin'. Use this whenever you need a
    default that the owner may have set previously (e.g. before assuming a
    payment mode wasn't specified, check get_preference('default_payment_mode')
    first). Returns 'not set' if the key doesn't exist yet — don't treat that
    as an error, just proceed without that default or ask the owner."""
    db = SessionLocal()
    try:
        pref = db.query(Preference).filter(
            Preference.owner_id == DEFAULT_OWNER_ID,
            Preference.key == key,
        ).first()
        if not pref:
            return f"Preference '{key}' is not set."
        return f"{key} = {pref.value}"
    finally:
        db.close()


@tool
def set_preference(key: str, value: str) -> str:
    """Store or update a standing owner preference — e.g. "always assume UPI
    unless I say cash" -> set_preference('default_payment_mode', 'UPI'), or
    "default atta = Aashirvaad 5kg" -> set_preference('preferred_atta_brand',
    'Aashirvaad 5kg'). This persists across chats and sessions — use it whenever
    the owner states a standing preference, not just a one-off instruction for
    the current bill."""
    db = SessionLocal()
    try:
        existing = db.query(Preference).filter(
            Preference.owner_id == DEFAULT_OWNER_ID,
            Preference.key == key,
        ).first()

        if existing:
            existing.value = value
            db.commit()
            return f"Updated preference: {key} = {value}"

        db.add(Preference(
            id=gen_id(),
            owner_id=DEFAULT_OWNER_ID,
            key=key,
            value=value,
        ))
        db.commit()
        return f"Saved preference: {key} = {value}"

    except IntegrityError:
        db.rollback()
        # race: two set_preference calls for the same key landed concurrently
        existing = db.query(Preference).filter(
            Preference.owner_id == DEFAULT_OWNER_ID,
            Preference.key == key,
        ).first()
        if existing:
            existing.value = value
            db.commit()
            return f"Updated preference: {key} = {value}"
        return "Failed to save preference due to a conflicting request — please retry."
    finally:
        db.close()