import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from database import Report, get_db
from models import ReportDetail, ReportSummary

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
        has_pdf        = bool(r.pdf_path and Path(r.pdf_path).exists()),
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
    if not r.pdf_path or not Path(r.pdf_path).exists():
        raise HTTPException(404, "PDF not available")
    return FileResponse(
        r.pdf_path,
        media_type  = "application/pdf",
        filename    = Path(r.pdf_path).name,
    )


@router.delete("/{report_id}", status_code=204)
def delete_report(report_id: int, db: Session = Depends(get_db)):
    r = db.get(Report, report_id)
    if not r:
        raise HTTPException(404, "Report not found")
    if r.pdf_path:
        p = Path(r.pdf_path)
        if p.exists():
            p.unlink()
    db.delete(r)
    db.commit()
