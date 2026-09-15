import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from database import Report, get_db
from models import ReportDetail, ReportSummary
from storage import ReportNotFound, get_storage, key_for

router = APIRouter(prefix="/api/reports", tags=["reports"])


def _to_summary(r: Report) -> ReportSummary:
    return ReportSummary(
        id             = r.id,
        type           = r.type,
        created_at     = r.created_at,
        title          = r.title,
        property_count = r.property_count,
        buy_count      = r.buy_count,
        consider_count = r.consider_count,
        no_buy_count   = r.no_buy_count,
        watch_count    = r.watch_count,
        perfect_count  = r.perfect_count,
        avoid_count    = r.avoid_count,
        # pdf_path is only set after the PDF has been saved, and storage is now
        # durable. Checking the file itself here would cost one storage request
        # per report on every listing.
        has_pdf        = bool(r.pdf_path),
    )


@router.get("", response_model=list[ReportSummary])
def list_reports(skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    rows = db.query(Report).order_by(Report.created_at.desc()).offset(skip).limit(limit).all()
    return [_to_summary(r) for r in rows]


@router.get("/{report_id}", response_model=ReportDetail)
def get_report(report_id: int, db: Session = Depends(get_db)):
    r = db.get(Report, report_id)
    if not r:
        raise HTTPException(404, "Report not found")
    summary = _to_summary(r)
    return ReportDetail(**summary.model_dump(), deals=json.loads(r.deals_json or "[]"))


@router.get("/{report_id}/pdf")
def download_pdf(report_id: int, db: Session = Depends(get_db)):
    r = db.get(Report, report_id)
    if not r:
        raise HTTPException(404, "Report not found")
    if not r.pdf_path:
        raise HTTPException(404, "PDF not available")
    try:
        chunks = get_storage().stream(r.pdf_path)
    except ReportNotFound:
        raise HTTPException(404, "PDF not available")
    return StreamingResponse(
        chunks,
        media_type = "application/pdf",
        headers    = {"Content-Disposition": f'attachment; filename="{key_for(r.pdf_path)}"'},
    )


@router.delete("/{report_id}", status_code=204)
def delete_report(report_id: int, db: Session = Depends(get_db)):
    r = db.get(Report, report_id)
    if not r:
        raise HTTPException(404, "Report not found")
    pdf_key = r.pdf_path
    db.delete(r)
    db.commit()
    # Remove the PDF only after the row is gone: if this fails, the worst case
    # is an orphaned file rather than a report whose PDF has vanished.
    if pdf_key:
        get_storage().delete(pdf_key)
