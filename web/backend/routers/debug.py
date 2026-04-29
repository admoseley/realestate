"""
Debug endpoint — runs the sheriff sale pipeline with full verbose logging
and returns a downloadable plain-text diagnostic report.
"""
import io
import sys
import subprocess
import tempfile
import traceback
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import PlainTextResponse

sys.path.insert(0, str(Path(__file__).parents[3]))

from sheriff_sale_analyzer import pdf_to_text, parse_sheriff_text, enrich_property, fetch_wprdc_parcel, fetch_ac_assessment, fetch_ac_search

router = APIRouter(prefix="/api/debug", tags=["debug"])

SHERIFF_TXT_CACHE = Path("/tmp/sheriff_debug.txt")


@router.post("/analyze-pdf", response_class=PlainTextResponse)
async def debug_analyze_pdf(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Must upload a PDF file.")

    out = io.StringIO()

    def log(msg=""):
        out.write(msg + "\n")

    log("=" * 70)
    log("SHERIFF SALE DEBUG REPORT")
    log(f"Generated : {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    log(f"File      : {file.filename}")
    log("=" * 70)

    # ── Save upload to temp file ──────────────────────────────────────────────
    content = await file.read()
    log(f"\n[FILE] Size: {len(content):,} bytes ({len(content)/1024/1024:.2f} MB)")

    tmp_pdf = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp_pdf.write(content)
    tmp_pdf.close()
    pdf_path = Path(tmp_pdf.name)

    # ── Step 1: pdftotext ─────────────────────────────────────────────────────
    log("\n" + "─" * 70)
    log("STEP 1 — PDF → TEXT  (pdftotext)")
    log("─" * 70)

    txt_path = None
    raw_text = ""
    try:
        SHERIFF_TXT_CACHE.unlink(missing_ok=True)
        result = subprocess.run(
            ["pdftotext", "-layout", str(pdf_path), str(SHERIFF_TXT_CACHE)],
            capture_output=True, text=True, timeout=60
        )
        log(f"Exit code : {result.returncode}")
        if result.stderr:
            log(f"Stderr    : {result.stderr.strip()}")

        if result.returncode == 0 and SHERIFF_TXT_CACHE.exists():
            raw_text = SHERIFF_TXT_CACHE.read_text(errors="replace")
            txt_path = SHERIFF_TXT_CACHE
            log(f"Text size : {len(raw_text):,} chars")
            log(f"\n--- First 2000 characters of extracted text ---")
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
        pdf_path.unlink(missing_ok=True)
        return PlainTextResponse(out.getvalue(), media_type="text/plain")

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
            log(f"       → Running enrich_property()…")
            try:
                enrich_property(prop)
                log(f"       fair_market    : {prop.fair_market!r}")
                log(f"       assessed_value : {prop.assessed_value!r}")
                log(f"       year_built     : {prop.year_built!r}")
                log(f"       sqft           : {prop.sqft!r}")
                log(f"       bedrooms       : {prop.bedrooms!r}")
            except Exception:
                log(f"       ERROR enriching:")
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

    # ── Cleanup ───────────────────────────────────────────────────────────────
    pdf_path.unlink(missing_ok=True)

    log("\n" + "=" * 70)
    log("END OF DEBUG REPORT")
    log("=" * 70)

    return PlainTextResponse(
        out.getvalue(),
        media_type="text/plain",
        headers={"Content-Disposition": f'attachment; filename="sheriff_debug_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}.txt"'},
    )
