import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import PropertyDeal, get_db
from models import UpdateAddressRequest, ClearDealsResult

router = APIRouter(prefix="/api/deals", tags=["deals"])


def _to_record(row: PropertyDeal) -> dict:
    deal = json.loads(row.deal_json)
    deal["address"]      = row.address   # always use the (possibly patched) column value
    deal["sale_id"]      = row.sale_id
    deal["source"]       = row.source
    deal["municipality"] = row.municipality
    deal["created_at"]   = row.created_at.isoformat() if row.created_at else None
    deal["updated_at"]   = row.updated_at.isoformat() if row.updated_at else None
    return deal


@router.get("")
def list_deals(
    skip:   int = 0,
    limit:  int = 500,
    source: Optional[str] = None,
    db:     Session = Depends(get_db),
):
    q = db.query(PropertyDeal)
    if source:
        q = q.filter(PropertyDeal.source == source)
    rows    = q.offset(skip).limit(limit).all()
    records = [_to_record(r) for r in rows]
    records.sort(key=lambda d: d.get("score") or 0, reverse=True)
    return records


@router.delete("", response_model=ClearDealsResult)
def clear_deals(source: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(PropertyDeal)
    if source:
        q = q.filter(PropertyDeal.source == source)
    deleted = q.delete(synchronize_session=False)
    db.commit()
    return ClearDealsResult(deleted=deleted, source=source)


@router.patch("/{sale_id}/address")
def update_deal_address(
    sale_id: str,
    req:     UpdateAddressRequest,
    db:      Session = Depends(get_db),
):
    row = db.query(PropertyDeal).filter(PropertyDeal.sale_id == sale_id).first()
    if not row:
        raise HTTPException(404, f"Deal '{sale_id}' not found")
    new_address = req.address.strip()
    if not new_address:
        raise HTTPException(422, "Address cannot be blank")
    row.address = new_address
    deal_data = json.loads(row.deal_json)
    deal_data["address"] = new_address
    row.deal_json  = json.dumps(deal_data, default=str)
    row.updated_at = datetime.utcnow()
    db.commit()
    return {"sale_id": sale_id, "address": new_address}
