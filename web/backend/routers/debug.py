"""
Debug endpoint — runs the sheriff sale pipeline with full verbose logging
and returns a downloadable plain-text diagnostic report.
"""
import io
import os
import subprocess
import sys
import tempfile
import traceback
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import PlainTextResponse

sys.path.insert(0, str(Path(__file__).parents[3]))

from sheriff_sale_analyzer import parse_sheriff_text, enrich_property, fetch_wprdc_parcel, fetch_ac_assessment, fetch_ac_search

from uploads import read_pdf_upload


def require_debug_enabled() -> None:
    """Answer 404, as if the route didn't exist, unless ENABLE_DEBUG=true.

    The debug report runs the whole pipeline, including live county lookups,
    and returns raw parser output. It's a troubleshooting tool, so it stays
    off unless deliberately switched on. The setting is read per request.
    """
    if os.getenv("ENABLE_DEBUG", "false").lower() != "true":
        raise HTTPException(404, "Not Found")


router = APIRouter(prefix="/api/debug", tags=["debug"],
                   dependencies=[Depends(require_debug_enabled)])


@router.post("/analyze-pdf", response_class=PlainTextResponse)
async def debug_analyze_pdf(file: UploadFile = File(...)):
    content = await read_pdf_upload(file)

    # Each request works in its own directory, removed once the report is built
    # (even on errors). A fixed /tmp filename used to let concurrent debug runs
    # overwrite each other's extracted text.
    with tempfile.TemporaryDirectory(prefix="sheriff-debug-") as workdir:
        # pdftotext and live county lookups are blocking work: run them in the
        # threadpool so they don't stall the event loop for other requests.
        report = await run_in_threadpool(_build_report, file.filename, content, Path(workdir))

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return PlainTextResponse(
        report,
        media_type="text/plain",
        headers={"Content-Disposition": f'attachment; filename="sheriff_debug_{stamp}.txt"'},
    )


def _build_report(filename: str, content: bytes, workdir: Path) -> str:
    out = io.StringIO()

    def log(msg=""):
        out.write(msg + "\n")

    log("=" * 70)
    log("SHERIFF SALE DEBUG REPORT")
    log(f"Generated : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    log(f"File      : {filename}")
    log("=" * 70)

    # ── Save upload into the working directory ────────────────────────────────
    log(f"\n[FILE] Size: {len(content):,} bytes ({len(content)/1024/1024:.2f} MB)")

    pdf_path = workdir / "upload.pdf"
    pdf_path.write_bytes(content)
    txt_file = workdir / "extracted.txt"

    # ── Step 1: pdftotext ─────────────────────────────────────────────────────
    log("\n" + "─" * 70)
    log("STEP 1 — PDF → TEXT  (pdftotext)")
    log("─" * 70)

    txt_path = None
    raw_text = ""
    try:
        result = subprocess.run(
            ["pdftotext", "-layout", str(pdf_path), str(txt_file)],
            capture_output=True, text=True, timeout=60
        )
        log(f"Exit code : {result.returncode}")
        if result.stderr:
            log(f"Stderr    : {result.stderr.strip()}")

        if result.returncode == 0 and txt_file.exists():
            raw_text = txt_file.read_text(errors="replace")
            txt_path = txt_file
            log(f"Text size : {len(raw_text):,} chars")
            log("\n--- First 2000 characters of extracted text ---")
            log(raw_text[:2000])
            log("--- End preview ---")
        else:
            log("ERROR: pdftotext produced no output file.")
    except FileNotFoundError:
        log("ERROR: pdftotext binary not found. Is poppler-utils installed?")
        log(traceback.format_exc())
    except Exception:
        log("ERROR during PDF extraction:")
        log(traceback.format_exc())

    if not txt_path:
        log("\nCannot continue — no text extracted from PDF.")
        return out.getvalue()

    # ── Step 2: parse_sheriff_text ────────────────────────────────────────────
    log("\n" + "─" * 70)
    log("STEP 2 — PARSE PROPERTY RECORDS")
    log("─" * 70)

    properties = []
    try:
        properties = parse_sheriff_text(txt_path)
        log(f"Total properties parsed : {len(properties)}")
        fc = [p for p in properties if p.free_and_clear]
        log(f"Free & Clear (F&C)      : {len(fc)}")
        not_fc = [p for p in properties if not p.free_and_clear]
        log(f"Non-F&C (skipped)       : {len(not_fc)}")
    except Exception:
        log("ERROR during parsing:")
        log(traceback.format_exc())

    # ── Step 3: dump every property ───────────────────────────────────────────
    log("\n" + "─" * 70)
    log("STEP 3 — ALL PARSED PROPERTIES")
    log("─" * 70)

    for i, p in enumerate(properties):
        log(f"\n  [{i+1:03d}] {'*** FREE & CLEAR ***' if p.free_and_clear else '(not F&C)'}")
        for attr in ["sale_id", "case_number", "address", "municipality",
                     "parcel_id", "min_bid", "tax_bid", "free_and_clear",
                     "active", "fair_market", "assessed_value",
                     "year_built", "sqft", "bedrooms"]:
            val = getattr(p, attr, "MISSING_ATTR")
            log(f"        {attr:<20} {val!r}")

    # ── Step 4: enrich F&C properties ────────────────────────────────────────
    fc_props = [p for p in properties if p.free_and_clear]
    log("\n" + "─" * 70)
    log("STEP 4 — ENRICH F&C PROPERTIES")
    log("─" * 70)

    if not fc_props:
        log("  No F&C properties to enrich.")
    else:
        for i, prop in enumerate(fc_props):
            log(f"\n  [{i+1}] {prop.address}  (parcel: {prop.parcel_id})")

            # Test WPRDC directly and log raw response
            if prop.parcel_id:
                log(f"       → Testing WPRDC fetch_wprdc_parcel({prop.parcel_id!r})")
                try:
                    wprdc_result = fetch_wprdc_parcel(prop.parcel_id)
                    log(f"         raw result: {wprdc_result!r}")
                except Exception:
                    log(f"         EXCEPTION: {traceback.format_exc().splitlines()[-1]}")

            # Test AC assessment directly
            log(f"       → Testing AC fetch_ac_assessment({prop.parcel_id!r})")
            try:
                ac_result = fetch_ac_assessment(prop.parcel_id)
                log(f"         raw result: {ac_result!r}")
            except Exception:
                log(f"         EXCEPTION: {traceback.format_exc().splitlines()[-1]}")

            # Test AC search directly
            log(f"       → Testing AC fetch_ac_search({prop.address[:40]!r}, {prop.municipality!r})")
            try:
                search_result = fetch_ac_search(prop.address, prop.municipality)
                log(f"         raw result: {search_result!r}")
            except Exception:
                log(f"         EXCEPTION: {traceback.format_exc().splitlines()[-1]}")

            # Now run the full enrich_property
            log("       → Running enrich_property()…")
            try:
                enrich_property(prop)
                log(f"       fair_market    : {prop.fair_market!r}")
                log(f"       assessed_value : {prop.assessed_value!r}")
                log(f"       year_built     : {prop.year_built!r}")
                log(f"       sqft           : {prop.sqft!r}")
                log(f"       bedrooms       : {prop.bedrooms!r}")
            except Exception:
                log("       ERROR enriching:")
                log("       " + traceback.format_exc().replace("\n", "\n       "))

    # ── Step 5: deal eligibility ──────────────────────────────────────────────
    log("\n" + "─" * 70)
    log("STEP 5 — DEAL ELIGIBILITY (requires FMV)")
    log("─" * 70)

    eligible = 0
    for i, prop in enumerate(fc_props):
        fmv = prop.fair_market or prop.assessed_value
        status = f"ELIGIBLE  fmv={fmv}" if fmv else "SKIPPED   no FMV — would be excluded from analysis"
        if fmv:
            eligible += 1
        log(f"  [{i+1}] {prop.address[:55]:<55}  {status}")

    log(f"\nEligible for Deal analysis : {eligible} / {len(fc_props)}")

    if eligible == 0 and fc_props:
        log("""
  ROOT CAUSE: All F&C properties have no FMV or assessed value.
  This means the WPRDC / Allegheny County lookup found no data for these
  addresses. The analysis produces 0 deals because there is nothing to score.

  POSSIBLE FIXES:
  1. Verify the parcels exist in WPRDC: https://data.wprdc.org
  2. The property data may use a different address format than the lookup expects.
  3. Try running a spot check manually on one of the addresses above to confirm.
""")

    log("\n" + "=" * 70)
    log("END OF DEBUG REPORT")
    log("=" * 70)

    return out.getvalue()
