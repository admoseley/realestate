import json
import os
import sys
import tempfile
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import requests as http_requests

from fastapi import APIRouter, BackgroundTasks, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).parents[3]))

from investment_analyzer import Deal, analyze
from generate_pdf_report import build_and_save_pdf
from sheriff_sale_analyzer import pdf_to_text, parse_sheriff_text, enrich_property

from database import Report, get_db
from jobs import create_job, update_job, fail_job
from models import SheriffSaleUrlRequest, JobStatus

router      = APIRouter(prefix="/api/sheriff-sale", tags=["sheriff-sale"])
REPORTS_DIR = Path(os.getenv("REPORTS_DIR", str(Path(__file__).parent.parent / "reports")))
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

SHERIFF_PDF_CACHE = Path("/tmp/sheriff_sale_web.pdf")
SHERIFF_TXT_CACHE = Path("/tmp/sheriff_sale_web.txt")

# Browser headers so sheriff sale sites don't reject the request
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept":          "application/pdf,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer":         "https://www.google.com/",
}


def _download_pdf(url: str, dest: Path):
    """Download a PDF via HTTP with browser-like headers."""
    resp = http_requests.get(url, headers=_BROWSER_HEADERS, timeout=60, stream=True)
    resp.raise_for_status()
    content_type = resp.headers.get("Content-Type", "")
    if "pdf" not in content_type and not url.lower().endswith(".pdf"):
        raise ValueError(f"URL did not return a PDF (Content-Type: {content_type})")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "wb") as f:
        for chunk in resp.iter_content(chunk_size=65536):
            f.write(chunk)


def _run_pipeline(job_id: str, pdf_source: str, is_url: bool,
                  enrich: bool, fc_only: bool, db_factory, cleanup_path: str = None):
    db: Session = next(db_factory())
    try:
        # Step 1 — get PDF
        update_job(job_id, "running", 5, "Fetching sheriff sale PDF…")
        if is_url:
            SHERIFF_PDF_CACHE.unlink(missing_ok=True)
            SHERIFF_TXT_CACHE.unlink(missing_ok=True)
            _download_pdf(pdf_source, SHERIFF_PDF_CACHE)
            pdf_path = SHERIFF_PDF_CACHE
        else:
            pdf_path = Path(pdf_source)

        # Step 2 — convert PDF → text
        update_job(job_id, "running", 15, "Converting PDF to text…")
        SHERIFF_TXT_CACHE.unlink(missing_ok=True)
        txt_path = pdf_to_text(pdf_path, SHERIFF_TXT_CACHE)

        # Step 3 — parse
        update_job(job_id, "running", 25, "Parsing property records…")
        properties = parse_sheriff_text(txt_path)
        fc_props   = [p for p in properties if p.free_and_clear] if fc_only else properties
        label      = "Free & Clear" if fc_only else "total"

        if not fc_props:
            msg = ("No Free & Clear properties found in this PDF." if fc_only
                   else "No properties found in this PDF.")
            fail_job(job_id, msg)
            return

        # Step 4 — enrich
        if enrich:
            for i, prop in enumerate(fc_props):
                pct = 25 + int((i / len(fc_props)) * 30)
                update_job(job_id, "running", pct,
                           f"Enriching property {i+1} of {len(fc_props)} ({label}): {prop.address[:40]}…")
                enrich_property(prop)

        # Step 5 — build Deal objects + analyze
        update_job(job_id, "running", 60, "Running investment analysis…")
        deals = []
        for prop in fc_props:
            fmv = prop.fair_market or prop.assessed_value
            if not fmv:
                # Enrichment found nothing — use min_bid as conservative FMV estimate
                fmv = prop.min_bid or prop.tax_bid
            if not fmv:
                continue
            d = Deal(
                sale_id      = prop.sale_id,
                case         = prop.case_number,
                address      = prop.address,
                municipality = prop.municipality,
                parcel       = prop.parcel_id,
                min_bid      = prop.min_bid or prop.tax_bid,
                tax_bid      = prop.tax_bid,
                fmv          = float(fmv),
                assessed     = float(prop.assessed_value or fmv),
                year_built   = int(prop.year_built or 1950),
                sqft         = int(prop.sqft or 1000),
                bedrooms     = int(prop.bedrooms or 3),
                postponed    = not prop.active,
            )
            analyzed = analyze(d)
            if prop.land_only:
                analyzed.red_flags.insert(0, f"LAND ONLY — no structure on parcel (USEDESC: {prop.use_desc or 'vacant'})")
            deals.append(analyzed)

        deals.sort(key=lambda d: d.score, reverse=True)

        # Step 6 — save to DB
        update_job(job_id, "running", 70, "Saving analysis results…")
        deals_dicts = [asdict(d) for d in deals]
        report = Report(
            type           = "sheriff_sale",
            created_at     = datetime.utcnow(),
            title          = f"Sheriff Sale {'(F&C Only)' if fc_only else '(All Properties)'} — {datetime.utcnow().strftime('%B %d, %Y')}",
            property_count = len(deals),
            buy_count      = sum(1 for d in deals if d.verdict == "BUY"),
            consider_count = sum(1 for d in deals if d.verdict == "CONSIDER"),
            no_buy_count   = sum(1 for d in deals if d.verdict == "NO BUY"),
            watch_count    = sum(1 for d in deals if d.verdict == "WATCH"),
            perfect_count  = sum(1 for d in deals if d.perfect_pass_rating == "PERFECT"),
            avoid_count    = sum(1 for d in deals if d.perfect_pass_rating == "AVOID"),
            deals_json     = json.dumps(deals_dicts, default=str),
        )
        db.add(report)
        db.commit()
        db.refresh(report)

        # Step 7 — generate PDF
        update_job(job_id, "running", 80, "Generating branded PDF report…",
                   report_id=report.id)
        ts      = datetime.utcnow().strftime("%m%d%Y-%H%M%S")
        pdf_out = REPORTS_DIR / f"SheriffSale_{report.id}_{ts}.pdf"
        build_and_save_pdf(deals, pdf_out)
        report.pdf_path = str(pdf_out)
        db.commit()

        update_job(job_id, "done", 100, "Analysis complete!", report_id=report.id)

    except Exception as exc:
        fail_job(job_id, f"Pipeline error: {exc}")
        raise
    finally:
        db.close()
        # Delete uploaded temp file after pipeline finishes
        if cleanup_path:
            try:
                Path(cleanup_path).unlink(missing_ok=True)
            except Exception:
                pass


@router.post("/from-url")
def analyze_from_url(req: SheriffSaleUrlRequest,
                     background_tasks: BackgroundTasks,
                     db: Session = Depends(get_db)):
    job_id = create_job()
    background_tasks.add_task(
        _run_pipeline, job_id, req.url, True, req.enrich, req.fc_only, get_db
    )
    return {"job_id": job_id}


@router.post("/upload")
async def analyze_from_upload(background_tasks: BackgroundTasks,
                               enrich:  bool = Form(True),
                               fc_only: bool = Form(True),
                               file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Uploaded file must be a PDF.")
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    content = await file.read()
    tmp.write(content)
    tmp.close()
    job_id = create_job()
    background_tasks.add_task(
        _run_pipeline, job_id, tmp.name, False, enrich, fc_only, get_db,
        cleanup_path=tmp.name,
    )
    return {"job_id": job_id}
