import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import PropertyDeal, get_db, utcnow
from deal_utils import deal_record
from models import UpdateAddressRequest, ClearDealsResult

router = APIRouter(prefix="/api/deals", tags=["deals"])


def list_statement(source: Optional[str], skip: int, limit: int):
    """Paged query for deal rows.

    SQL Server rejects OFFSET/FETCH without an ORDER BY (SQLite doesn't care),
    so paging is anchored to the primary key.
    """
    statement = select(PropertyDeal).order_by(PropertyDeal.id)
    if source:
        statement = statement.where(PropertyDeal.source == source)
    return statement.offset(skip).limit(limit)


@router.get("")
def list_deals(
    skip:   int = 0,
    limit:  int = 500,
    source: Optional[str] = None,
    db:     Session = Depends(get_db),
):
    rows    = db.scalars(list_statement(source, skip, limit)).all()
    records = [deal_record(r) for r in rows]
    # The score lives inside deal_json, so ranking happens after loading. The
    # default page size covers the whole deal list in normal use.
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
    row.updated_at = utcnow()
    db.commit()
    return {"sale_id": sale_id, "address": new_address}
