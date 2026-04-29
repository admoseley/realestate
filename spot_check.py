#!/usr/bin/env python3
"""
Estella Wilson Properties LLC — Single-Property Spot Check

Evaluate any address (on-market listing, off-market lead, wholesale deal, etc.)
using the same investment framework as the sheriff sale batch report.

Usage examples
--------------
# Minimal — will prompt for any missing data it can't look up
  python3 spot_check.py "123 Main St, Pittsburgh, PA 15209" --price 65000

# Fully specified — runs without prompts
  python3 spot_check.py "456 Oak Ave, Verona, PA 15147" \\
      --price 82000 --fmv 110000 --sqft 1450 --year 1948 --beds 3 --baths 1

# Provide the county parcel ID for the most accurate WPRDC lookup
  python3 spot_check.py "789 Elm Dr, Munhall, PA 15120" --price 55000 --parcel "0481-K-00253"

# Fully interactive guided prompts
  python3 spot_check.py --interactive
"""

import argparse
import json
import re
import sys
import time
import urllib.request
import urllib.parse
from datetime import datetime
from pathlib import Path

from investment_analyzer import Deal, analyze
from sheriff_sale_analyzer import fetch_wprdc_parcel, fetch_ac_search
from generate_pdf_report import build_and_save_pdf

_HERE = Path(__file__).parent


# ─── Geocoding ────────────────────────────────────────────────────────────────

def geocode_nominatim(address: str) -> tuple | None:
    """Return (lat, lon) for an address via OpenStreetMap Nominatim, or None."""
    query = urllib.parse.urlencode({
        "q": address + ", Pennsylvania",
        "format": "json",
        "limit": 1,
        "countrycodes": "us",
    })
    url = f"https://nominatim.openstreetmap.org/search?{query}"
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "EstellaWilsonProperties/1.0 (spot-check)"}
        )
        with urllib.request.urlopen(req, timeout=8) as r:
            results = json.loads(r.read())
        if results:
            return float(results[0]["lat"]), float(results[0]["lon"])
    except Exception:
        pass
    return None


# ─── Address parsing ──────────────────────────────────────────────────────────

def parse_municipality(address: str) -> str:
    """
    Extract the city/municipality name from a full address string.

    Handles common formats:
      "123 Main St, Pittsburgh, PA 15201"  →  "Pittsburgh"
      "456 Oak Ave Pittsburgh PA 15201"    →  "Pittsburgh"
    """
    # Comma-separated: last non-state/zip part before "PA XXXXX"
    parts = [p.strip() for p in address.split(",")]
    for part in reversed(parts):
        clean = re.sub(r'\b(PA|pa)\b.*', '', part).strip()
        if clean and not re.match(r'^\d', clean) and len(clean) > 2:
            return clean.title()
    # Space-separated fallback: word(s) immediately before "PA XXXXX"
    m = re.search(r'([A-Za-z][A-Za-z\s\-\.]+?)\s+PA\s+\d{5}', address, re.IGNORECASE)
    if m:
        words = m.group(1).strip().split()
        # Return last 1–2 meaningful words (skip a street suffix like "St")
        return words[-1].title() if words else "Pittsburgh"
    return "Pittsburgh"


# ─── Property data lookup ─────────────────────────────────────────────────────

def lookup_property(address: str, municipality: str, parcel: str = "") -> dict:
    """Try WPRDC (by parcel) then AC portal (by address) for property facts."""
    result = {}
    if parcel:
        print(f"  Querying WPRDC for parcel {parcel}…")
        result = fetch_wprdc_parcel(parcel)
        if result:
            print("  ✔ WPRDC returned data.")
            return result
    print(f"  Searching Allegheny County portal by address…")
    result = fetch_ac_search(address, municipality)
    if result:
        print("  ✔ AC portal returned data.")
    else:
        print("  ✘ No data found — enter values manually.")
    return result


# ─── Interactive prompt helper ────────────────────────────────────────────────

def prompt_field(label: str, default=None, cast=str):
    """Prompt the user for a single field value."""
    if default is not None:
        raw = input(f"  {label} [{default}]: ").strip()
        if not raw:
            return default
    else:
        raw = ""
        while not raw:
            raw = input(f"  {label}: ").strip()
            if not raw:
                print("    → Required.")
    try:
        return cast(raw)
    except (ValueError, TypeError):
        print(f"    → Could not parse as {cast.__name__}, using default.")
        return default


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Single-property investment spot check — produces a branded PDF report",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("address",   nargs="?",      help="Full property address (with city & zip)")
    parser.add_argument("--price",   "-p", type=float, help="Asking / purchase price ($) [REQUIRED]")
    parser.add_argument("--fmv",           type=float, help="Fair Market Value ($) — auto-looked up if omitted")
    parser.add_argument("--sqft",          type=int,   help="Square footage — auto-looked up if omitted")
    parser.add_argument("--year",          type=int,   help="Year built — auto-looked up if omitted")
    parser.add_argument("--beds",          type=int,   help="Bedrooms — auto-looked up if omitted (default 3)")
    parser.add_argument("--baths",         type=int,   help="Full bathrooms (default 1)")
    parser.add_argument("--parcel",        type=str,   help="Allegheny County parcel ID for WPRDC lookup")
    parser.add_argument("--muni",          type=str,   help="Municipality (parsed from address if omitted)")
    parser.add_argument("--no-lookup",  action="store_true", help="Skip automatic WPRDC/AC data lookup")
    parser.add_argument("--interactive","-i", action="store_true", help="Guided prompts for all fields")
    args = parser.parse_args()

    interactive = args.interactive or not args.address

    print("\n" + "═" * 62)
    print("  Estella Wilson Properties LLC — Property Spot Check")
    print("═" * 62 + "\n")

    # ── Address ───────────────────────────────────────────────────
    if interactive and not args.address:
        address = prompt_field("Property address (full, with city & zip)")
    elif not args.address:
        parser.error("Provide an address as the first argument, or use --interactive")
    else:
        address = args.address

    # ── Municipality ──────────────────────────────────────────────
    municipality = args.muni or parse_municipality(address)
    if interactive:
        municipality = prompt_field("Municipality", default=municipality)

    print(f"  Address:      {address}")
    print(f"  Municipality: {municipality}\n")

    # ── Auto data lookup ──────────────────────────────────────────
    lu = {}
    if not args.no_lookup:
        lu = lookup_property(address, municipality, args.parcel or "")
        if lu:
            print(f"    FMV={lu.get('fair_market')}  assessed={lu.get('assessed_value')}  "
                  f"sqft={lu.get('sqft')}  yr={lu.get('year_built')}  "
                  f"beds={lu.get('bedrooms')}\n")

    def _coerce(val, cast, fallback):
        try:
            return cast(val) if val not in (None, "", 0) else fallback
        except (ValueError, TypeError):
            return fallback

    # ── Purchase price ────────────────────────────────────────────
    price = args.price
    if price is None:
        if interactive:
            price = prompt_field("Asking / purchase price ($)", cast=float)
        else:
            parser.error("--price is required (or use --interactive)")

    # ── FMV ───────────────────────────────────────────────────────
    fmv = args.fmv or _coerce(lu.get("fair_market"), float, None)
    if fmv is None:
        if interactive:
            fmv = prompt_field("Fair Market Value ($)", cast=float)
        else:
            parser.error("Could not determine FMV automatically — "
                         "provide --fmv or use --interactive")

    assessed = _coerce(lu.get("assessed_value"), float, fmv)

    # ── Physical attributes ───────────────────────────────────────
    sqft  = args.sqft  or _coerce(lu.get("sqft"),        int,   None)
    year  = args.year  or _coerce(lu.get("year_built"),  int,   None)
    beds  = args.beds  or _coerce(lu.get("bedrooms"),    int,   None)
    baths = args.baths or _coerce(lu.get("fullbaths"),   int,   1)

    if interactive:
        sqft  = prompt_field("Square footage",  default=sqft  or 1_200, cast=int)
        year  = prompt_field("Year built",      default=year  or 1950,  cast=int)
        beds  = prompt_field("Bedrooms",        default=beds  or 3,     cast=int)
        baths = prompt_field("Full bathrooms",  default=baths or 1,     cast=int)
    else:
        sqft  = sqft  or 1_200
        year  = year  or 1950
        beds  = beds  or 3
        baths = baths or 1

    print(f"\n  Purchase price : ${price:,.0f}")
    print(f"  FMV            : ${fmv:,.0f}")
    print(f"  Assessed       : ${assessed:,.0f}")
    print(f"  Sqft / Year    : {sqft:,} sqft  ·  {year}")
    print(f"  Beds / Baths   : {beds}BR / {baths}BA")

    # ── Geocode for map ───────────────────────────────────────────
    print("\n  Geocoding for map tile…")
    coords = geocode_nominatim(address)
    if coords:
        print(f"  ✔ ({coords[0]:.5f}, {coords[1]:.5f})")
    else:
        print("  ✘ Geocoding failed — map will show placeholder.")

    # ── Build & analyze deal ──────────────────────────────────────
    sale_id = "SPOT-CHK"
    deal = Deal(
        sale_id      = sale_id,
        case         = "Spot Check",
        address      = address,
        municipality = municipality,
        parcel       = args.parcel or "",
        min_bid      = float(price),
        tax_bid      = float(price),
        fmv          = float(fmv),
        assessed     = float(assessed),
        year_built   = int(year),
        sqft         = int(sqft),
        bedrooms     = int(beds),
        fullbaths    = int(baths),
    )
    deal = analyze(deal)

    print(f"\n  Score: {deal.score}/100  |  Verdict: {deal.verdict}  |  Rating: {deal.perfect_pass_rating}")

    # ── Generate PDF ──────────────────────────────────────────────
    timestamp   = datetime.now().strftime("%m%d%Y-%H%M")
    output_path = _HERE / f"Estella_Wilson_SpotCheck_{timestamp}.pdf"

    subtitle = (
        f"Property Spot Check  ·  {datetime.now().strftime('%B %d, %Y')}  ·  "
        f"{municipality}, PA"
    )
    cover_note = (
        "★ FMV sourced from Allegheny County WPRDC / AC portal where available; "
        "enter manually if auto-lookup returned no data. "
        "All analysis uses cash-purchase methodology per the Perfect vs Pass investor framework."
    )

    print(f"\n  Building PDF…")
    build_and_save_pdf(
        [deal],
        output_path,
        geocache_extra  = {sale_id: coords} if coords else {},
        report_title    = "Estella Wilson Properties LLC — Property Spot Check",
        footer_label    = "Property Spot Check",
        subtitle        = subtitle,
        cover_note      = cover_note,
    )

    print(f"\n✔ Spot-check report saved to:\n  {output_path}\n")


if __name__ == "__main__":
    main()
