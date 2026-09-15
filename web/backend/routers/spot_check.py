import json
import sys
import tempfile
import uuid
from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks

sys.path.insert(0, str(Path(__file__).parents[3]))

from investment_analyzer import Deal, analyze
from generate_pdf_report import build_and_save_pdf
from spot_check import geocode_nominatim, parse_municipality, lookup_property

from database import Report, SessionLocal, utcnow
from models import JobStarted, SpotCheckRequest
from deal_utils import upsert_deal, spot_sale_id
from jobs import complete_job, create_job, run_job, update_job
from storage import get_storage

router = APIRouter(prefix="/api/spot-check", tags=["spot-check"])


def _run_spot_check(job_id: str, req: SpotCheckRequest) -> None:
    """Analyze one property and save its report. Runs as a background job."""
    address      = req.address
    municipality = req.municipality or parse_municipality(address)

    # Optional property data lookup
    enriched: dict = {}
    if not req.no_lookup:
        update_job(job_id, "running", 10, "Looking up county property records…")
        try:
            enriched = lookup_property(address, municipality, req.parcel or "")
        except Exception:
            enriched = {}

    # Resolve FMV: request > enriched > fallback to purchase price
    fmv = req.fmv or enriched.get("fair_market") or enriched.get("assessed_value")
    fmv_warning = None
    if not fmv:
        fmv = req.price
        fmv_warning = (
            "County records returned no assessed value for this address. "
            "FMV has been set equal to the purchase price — results will show "
            "conservative (breakeven) projections. Enter an FMV in Advanced Options "
            "for a more accurate analysis."
        )

    update_job(job_id, "running", 40, "Running investment analysis…")
    deal = Deal(
        sale_id      = "SPOT",
        case         = "N/A",
        address      = address,
        municipality = municipality,
        parcel       = req.parcel or enriched.get("parcel_id", ""),
        min_bid      = req.price,
        tax_bid      = None,
        fmv          = float(fmv),
        assessed     = float(enriched.get("assessed_value") or fmv),
        year_built   = int(req.year or enriched.get("year_built") or 1950),
        sqft         = int(req.sqft or enriched.get("sqft") or 1000),
        bedrooms     = int(req.beds or enriched.get("bedrooms") or 3),
        postponed    = False,
    )
    deal = analyze(deal)

    # Geocode for the map tile
    update_job(job_id, "running", 50, "Locating the property on the map…")
    coords = geocode_nominatim(address)
    geocache_extra = {"SPOT": coords} if coords else {}

    # Build the PDF in a throwaway directory, then move it into report storage.
    # The name gets a random suffix: two spot checks in the same second used to
    # produce the same file name, and storage overwrites on save.
    update_job(job_id, "running", 60, "Generating PDF report…")
    now        = utcnow()
    muni_label = municipality or "Allegheny County"
    with tempfile.TemporaryDirectory(prefix="spot-check-") as workdir:
        pdf_file = Path(workdir) / f"SpotCheck_{now.strftime('%m%d%Y-%H%M%S')}_{uuid.uuid4().hex[:8]}.pdf"
        build_and_save_pdf(
            [deal],
            pdf_file,
            geocache_extra = geocache_extra,
            report_title   = "Estella Wilson Properties LLC — Property Spot Check",
            footer_label   = "Property Spot Check",
            subtitle       = f"{muni_label} · {now.strftime('%B %d, %Y')}",
            cover_note     = f"Listed Price: ${req.price:,.0f}",
        )
        pdf_key = get_storage().save_pdf(pdf_file)

    # The database session opens only now, after the slow lookups and
    # rendering, so the serverless database is free to stay paused meanwhile.
    update_job(job_id, "running", 90, "Saving results…")
    deal_dict = asdict(deal)
    with SessionLocal() as db:
        report = Report(
            type           = "spot_check",
            created_at     = now,
            title          = address,
            property_count = 1,
            buy_count      = 1 if deal.verdict == "BUY" else 0,
            consider_count = 1 if deal.verdict == "CONSIDER" else 0,
            no_buy_count   = 1 if deal.verdict == "NO BUY" else 0,
            watch_count    = 1 if deal.verdict == "WATCH" else 0,
            perfect_count  = 1 if deal.perfect_pass_rating == "PERFECT" else 0,
            avoid_count    = 1 if deal.perfect_pass_rating == "AVOID" else 0,
            pdf_path       = pdf_key,
            deals_json     = json.dumps([deal_dict], default=str),
        )
        db.add(report)
        db.commit()   # report.id stays loaded (expire_on_commit=False), so no refresh query

        # Persist to unified deal list
        upsert_deal(
            db           = db,
            sale_id      = spot_sale_id(address, req.price),
            source       = "spot_check",
            address      = address,
            municipality = municipality,
            deal_dict    = deal_dict,
        )
        db.commit()

    complete_job(job_id, "Analysis complete", report_id=report.id,
                 result={"deal": deal_dict, "warning": fmv_warning})


@router.post("", response_model=JobStarted)
def start_spot_check(req: SpotCheckRequest, background_tasks: BackgroundTasks):
    """Queue a spot check and return its job ID.

    This used to run inline and return the analysis. County lookups,
    geocoding, and PDF rendering together can outlast the 45-second limit
    Static Web Apps puts on proxied API requests, so it's now a background job:
    poll ``GET /api/jobs/{job_id}``, and the finished job carries ``report_id``
    and ``result = {"deal": ..., "warning": ...}``.
    """
    job_id = create_job()
    background_tasks.add_task(run_job, job_id, "Spot check failed", _run_spot_check, req)
    return JobStarted(job_id=job_id)
