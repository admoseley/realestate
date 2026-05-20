import hashlib
import json
import re
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from database import PropertyDeal


def _fingerprint(address: str, min_bid, municipality: Optional[str]) -> str:
    raw = f"{(address or '').strip().upper()}|{min_bid or 0}|{(municipality or '').strip().upper()}"
    return hashlib.sha256(raw.encode()).hexdigest()


def pdf_hash(pdf_bytes: bytes) -> str:
    return hashlib.sha256(pdf_bytes).hexdigest()


def spot_sale_id(address: str, price: float) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", address.lower())[:40].strip("_")
    return f"spot_{slug}_{int(price)}"


def upsert_deal(
    db:           Session,
    sale_id:      str,
    source:       str,
    address:      str,
    municipality: Optional[str],
    deal_dict:    dict,
    source_pdf_hash: Optional[str] = None,
) -> str:
    """Insert or update a PropertyDeal row. Returns 'inserted' | 'updated' | 'unchanged'."""
    fp       = _fingerprint(address, deal_dict.get("min_bid"), municipality)
    existing = db.query(PropertyDeal).filter(PropertyDeal.sale_id == sale_id).first()

    if existing is None:
        try:
            row = PropertyDeal(
                sale_id      = sale_id,
                source       = source,
                address      = address,
                municipality = municipality,
                deal_json    = json.dumps(deal_dict, default=str),
                fingerprint  = fp,
                pdf_hash     = source_pdf_hash,
                created_at   = datetime.utcnow(),
                updated_at   = datetime.utcnow(),
            )
            db.add(row)
            db.flush()
            return "inserted"
        except IntegrityError:
            db.rollback()
            return "unchanged"

    if existing.fingerprint == fp:
        return "unchanged"

    existing.address      = address
    existing.municipality = municipality
    existing.deal_json    = json.dumps(deal_dict, default=str)
    existing.fingerprint  = fp
    existing.pdf_hash     = source_pdf_hash or existing.pdf_hash
    existing.updated_at   = datetime.utcnow()
    return "updated"
