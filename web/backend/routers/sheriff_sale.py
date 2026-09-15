import json
import shutil
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, UploadFile, File, Form, HTTPException

sys.path.insert(0, str(Path(__file__).parents[3]))

from investment_analyzer import Deal, analyze
from generate_pdf_report import build_and_save_pdf
from sheriff_sale_analyzer import pdf_to_text, parse_sheriff_text, enrich_property

from database import Report, SessionLocal, utcnow
from jobs import create_job, update_job, fail_job
from deal_utils import upsert_deal, pdf_hash as compute_pdf_hash
from storage import get_storage

router = APIRouter(prefix="/api/sheriff-sale", tags=["sheriff-sale"])

UPLOAD_FILENAME = "upload.pdf"


def _run_pipeline(job_id: str, workdir: str, enrich: bool):
    """Analyze one uploaded sheriff-sale PDF. Runs as a background task.

    ``workdir`` belongs to this job alone and is deleted when the job ends.
    It replaces a single fixed /tmp text file that every upload shared:
    ``pdf_to_text`` reuses an existing output file, so concurrent uploads
    could delete each other's text or silently analyze the other's PDF.
    """
    work     = Path(workdir)
    pdf_path = work / UPLOAD_FILENAME
    try:
        update_job(job_id, "running", 5, "Fetching sheriff sale PDF…")
        source_hash = compute_pdf_hash(pdf_path.read_bytes())

        # Step 2 — convert PDF → text
        update_job(job_id, "running", 15, "Converting PDF to text…")
        txt_path = pdf_to_text(pdf_path, work / "sheriff_sale.txt")

        # Step 3 — parse
        update_job(job_id, "running", 25, "Parsing property records…")
        properties = parse_sheriff_text(txt_path)

        if not properties:
            fail_job(job_id, "No properties found in this PDF.")
            return

        # Step 4 — enrich
        if enrich:
            for i, prop in enumerate(properties):
                pct = 25 + int((i / len(properties)) * 30)
                update_job(job_id, "running", pct,
                           f"Enriching property {i+1} of {len(properties)}: {prop.address[:40]}…")
                enrich_property(prop)

        # Step 5 — build Deal objects + analyze
        update_job(job_id, "running", 60, "Running investment analysis…")
        deals = []
        for prop in properties:
            fmv = prop.fair_market or prop.assessed_value
            if not fmv:
                # Enrichment found nothing — use min_bid as conservative FMV estimate
                fmv = prop.min_bid or prop.tax_bid
            if not fmv:
                continue
            d = Deal(
                sale_id        = prop.sale_id,
                case           = prop.case_number,
                address        = prop.address,
                municipality   = prop.municipality,
                parcel         = prop.parcel_id,
                min_bid        = prop.min_bid or prop.tax_bid,
                tax_bid        = prop.tax_bid,
                fmv            = float(fmv),
                assessed       = float(prop.assessed_value or fmv),
                year_built     = int(prop.year_built or 1950),
                sqft           = int(prop.sqft or 1000),
                bedrooms       = int(prop.bedrooms or 3),
                postponed      = not prop.active,
                free_and_clear = prop.free_and_clear,
            )
            analyzed = analyze(d)
            if prop.land_only:
                analyzed.red_flags.insert(0, f"LAND ONLY — no structure on parcel (USEDESC: {prop.use_desc or 'vacant'})")
            deals.append(analyzed)

        deals.sort(key=lambda d: d.score, reverse=True)

        # The database session opens only once there's something to save:
        # enrichment can take minutes, and the database should be free to
        # auto-pause meanwhile.
        with SessionLocal() as db:
            # Step 6 — save to DB
            update_job(job_id, "running", 70, "Saving analysis results…")
            now         = utcnow()
            deals_dicts = [asdict(d) for d in deals]
            report = Report(
                type           = "sheriff_sale",
                created_at     = now,
                title          = f"Sheriff Sale (All Properties) — {now.strftime('%B %d, %Y')}",
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
            db.commit()   # report.id stays loaded (expire_on_commit=False), so no refresh query

            # Step 7 — generate the PDF in the job's working directory, then
            # move it to durable report storage (no transaction is open while
            # it renders or uploads).
            update_job(job_id, "running", 80, "Generating branded PDF report…",
                       report_id=report.id)
            ts       = now.strftime("%m%d%Y-%H%M%S")
            pdf_file = work / f"SheriffSale_{report.id}_{ts}.pdf"
            n_deals  = len(deals)

            def _pdf_progress(current, total, phase):
                if phase == "property":
                    pct = 80 + int(current / max(total, 1) * 10)
                    update_job(job_id, "running", pct,
                               f"Building PDF: property {current} of {total}…",
                               report_id=report.id)
                elif phase == "render":
                    update_job(job_id, "running", 91,
                               f"Rendering PDF ({n_deals} properties)…",
                               report_id=report.id)
                elif phase == "save":
                    update_job(job_id, "running", 96, "Saving PDF file…",
                               report_id=report.id)

            build_and_save_pdf(deals, pdf_file, progress_cb=_pdf_progress)
            report.pdf_path = get_storage().save_pdf(pdf_file)
            db.commit()

            # Step 8 — upsert individual deal rows into property_deals
            update_job(job_id, "running", 98, "Persisting deal records…", report_id=report.id)
            counts = {"inserted": 0, "updated": 0, "unchanged": 0}
            for analyzed_deal in deals:
                outcome = upsert_deal(
                    db               = db,
                    sale_id          = analyzed_deal.sale_id,
                    source           = "sheriff_sale",
                    address          = analyzed_deal.address,
                    municipality     = analyzed_deal.municipality,
                    deal_dict        = asdict(analyzed_deal),
                    source_pdf_hash  = source_hash,
                )
                counts[outcome] += 1
            db.commit()

        done_msg = (f"Done — {counts['inserted']} new, "
                    f"{counts['updated']} updated, "
                    f"{counts['unchanged']} unchanged")
        update_job(job_id, "done", 100, done_msg, report_id=report.id)

    except Exception as exc:
        fail_job(job_id, f"Pipeline error: {exc}")
        raise
    finally:
        shutil.rmtree(work, ignore_errors=True)


@router.post("/upload")
async def analyze_from_upload(background_tasks: BackgroundTasks,
                               enrich: bool = Form(True),
                               file:   UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Uploaded file must be a PDF.")
    workdir = Path(tempfile.mkdtemp(prefix="sheriff-sale-"))
    try:
        (workdir / UPLOAD_FILENAME).write_bytes(await file.read())
        job_id = create_job()
    except Exception:
        shutil.rmtree(workdir, ignore_errors=True)
        raise
    background_tasks.add_task(_run_pipeline, job_id, str(workdir), enrich)
    return {"job_id": job_id}
