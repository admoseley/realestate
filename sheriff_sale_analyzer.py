#!/usr/bin/env python3
"""
Allegheny County Sheriff Sale Analyzer
Parses the sheriff sale PDF, scores deals, and fetches property valuations.
Priority: Free & Clear (F&C) properties with the best bid-to-value ratios.
"""

import re
import sys
import json
import time
import subprocess
import urllib.request
import urllib.parse
from dataclasses import dataclass, field, asdict
from typing import Optional
from pathlib import Path

try:
    from tabulate import tabulate
    HAS_TABULATE = True
except ImportError:
    HAS_TABULATE = False

# ─── Configuration ────────────────────────────────────────────────────────────

SALE_PDF_URL = "https://sheriffalleghenycounty.com/wp-content/uploads/2026/04/May-Sale-List-Updated-4-24.pdf"
PDF_CACHE    = Path("/tmp/sheriff_sale.pdf")
TXT_CACHE    = Path("/tmp/sheriff_sale.txt")

# Allegheny County property search (public)
AC_SEARCH_URL = "https://assessments.alleghenycounty.us/api/Parcel/Search?SearchType=Address&q={query}"
AC_PARCEL_URL = "https://assessments.alleghenycounty.us/api/Parcel/{parcel_id}"

# ─── Data Model ───────────────────────────────────────────────────────────────

@dataclass
class Property:
    sale_id:        str = ""
    case_number:    str = ""
    sale_type:      str = ""
    status:         str = ""
    tax_bid:        float = 0.0          # Cost & Tax Bid (upset price)
    min_bid:        Optional[float] = None  # F&C negotiated minimum if stated
    free_and_clear: bool = False
    plaintiff:      str = ""
    defendant:      str = ""
    address:        str = ""
    municipality:   str = ""
    parcel_id:      str = ""
    comments:       str = ""
    # Enrichment fields (filled later)
    assessed_value: Optional[float] = None
    fair_market:    Optional[float] = None
    year_built:     Optional[str]   = None
    sqft:           Optional[int]   = None
    bedrooms:       Optional[int]   = None
    # Derived
    deal_score:     float = 0.0
    equity_at_bid:  Optional[float] = None

    @property
    def effective_bid(self) -> float:
        return self.min_bid if self.min_bid else self.tax_bid

    @property
    def active(self) -> bool:
        return self.status.strip().lower() == "active"

# ─── PDF Download + Parse ─────────────────────────────────────────────────────

def download_pdf(url: str, dest: Path) -> Path:
    if dest.exists():
        print(f"  [cache] Using cached PDF: {dest}")
        return dest
    print(f"  [download] Fetching {url}")
    urllib.request.urlretrieve(url, dest)
    print(f"  [download] Saved to {dest}")
    return dest

def pdf_to_text(pdf_path: Path, txt_path: Path) -> Path:
    if txt_path.exists():
        print(f"  [cache] Using cached text: {txt_path}")
        return txt_path
    print("  [parse] Converting PDF to text…")
    result = subprocess.run(
        ["pdftotext", "-layout", str(pdf_path), str(txt_path)],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"pdftotext failed: {result.stderr}")
    print(f"  [parse] Text written to {txt_path}")
    return txt_path

# ─── Record Extractor ─────────────────────────────────────────────────────────

# Matches the sale header line, e.g.:
#   12JUL17   GD-16-022895   Real Estate Sale - Sci Fa Sur Tax Lien   Active   1   $56,785.60
HEADER_RE = re.compile(
    r'^\s{1,6}(\S+)\s+((?:GD|MG)-\d{2}-\d{6})\s+'
    r'(Real Estate Sale - [^\s].*?)\s{2,}'
    r'(Active|Postponed.*?)\s{2,}'
    r'\d+\s+'
    r'\$([\d,]+\.\d{2})',
    re.IGNORECASE
)

# Column header separating plaintiff/defendant/property
COL_HDR_RE = re.compile(
    r'Plaintiff\(s\):\s+Attorney for the Plaintiff:\s+Defendant\(s\):\s+Property\s+Municipality\s+Parcel/Tax ID:',
    re.IGNORECASE
)

# Free & Clear patterns
FC_RE = re.compile(r'\bF[&/]C\b', re.IGNORECASE)

# Min bid from comments: "MIN BID OF $X" or "MIN BID $X" or "MIN OF $X" or "MINIMUM BID OF $X"
MINBID_RE = re.compile(r'MIN(?:IMUM)?\s*(?:BID\s*)?(?:OF\s*)?\$\s*([\d,]+(?:\.\d{2})?)', re.IGNORECASE)

# "UPSET PRICE" as min bid indicator (use tax_bid as the min)
UPSET_RE = re.compile(r'UPSET\s*PRICE', re.IGNORECASE)


def parse_data_line(line: str, col_positions: dict) -> dict:
    """
    Given a data line and approximate column start positions derived from the header,
    extract plaintiff, defendant, address, municipality, parcel_id.
    """
    # The columns are roughly fixed-width, determined by the header line.
    p_start  = col_positions.get("plaintiff",    0)
    a_start  = col_positions.get("attorney",     38)
    d_start  = col_positions.get("defendant",    73)
    pr_start = col_positions.get("property",    115)
    mu_start = col_positions.get("municipality",145)
    pa_start = col_positions.get("parcel",      160)

    def extract(s, start, end=None):
        chunk = s[start:end].strip() if end and end < len(s) else s[start:].strip()
        return chunk

    return {
        "plaintiff":    extract(line, p_start,  a_start).rstrip(),
        "defendant":    extract(line, d_start,  pr_start).rstrip(),
        "address":      extract(line, pr_start, mu_start).rstrip(),
        "municipality": extract(line, mu_start, pa_start).rstrip(),
        "parcel_id":    extract(line, pa_start).rstrip(),
    }


def detect_col_positions(header_line: str) -> dict:
    """Find start positions of each column from the Plaintiff(s): header."""
    return {
        "plaintiff":    header_line.index("Plaintiff(s):"),
        "attorney":     header_line.index("Attorney for the Plaintiff:"),
        "defendant":    header_line.index("Defendant(s):"),
        "property":     header_line.index("Property"),
        "municipality": header_line.index("Municipality"),
        "parcel":       header_line.index("Parcel/Tax ID:"),
    }


def parse_sheriff_text(txt_path: Path) -> list[Property]:
    lines = txt_path.read_text(encoding="utf-8", errors="replace").splitlines()
    properties: list[Property] = []
    col_positions: dict = {}

    i = 0
    while i < len(lines):
        line = lines[i]

        # Update column positions whenever we see the column header
        if COL_HDR_RE.search(line):
            try:
                col_positions = detect_col_positions(line)
            except ValueError:
                pass
            i += 1
            continue

        # Try to match a sale header
        m = HEADER_RE.search(line)
        if m:
            prop = Property(
                sale_id     = m.group(1).strip(),
                case_number = m.group(2).strip(),
                sale_type   = m.group(3).strip(),
                status      = m.group(4).strip(),
                tax_bid     = float(m.group(5).replace(",", "")),
            )
            # Skip the optional "X X X" flags line
            i += 1
            if i < len(lines) and re.match(r'^\s*X\s', lines[i]):
                i += 1

            # Expect the Plaintiff(s) column-header line next (may or may not repeat)
            if i < len(lines) and COL_HDR_RE.search(lines[i]):
                try:
                    col_positions = detect_col_positions(lines[i])
                except ValueError:
                    pass
                i += 1

            # Data line with actual values
            if i < len(lines) and col_positions:
                data_line = lines[i]
                # Protect against a blank line
                if data_line.strip():
                    parsed = parse_data_line(data_line, col_positions)
                    prop.plaintiff    = parsed["plaintiff"]
                    prop.defendant    = parsed["defendant"]
                    prop.address      = parsed["address"]
                    prop.municipality = parsed["municipality"]
                    prop.parcel_id    = parsed["parcel_id"]
                i += 1

                # Next line may be the city/state continuation of the address
                if i < len(lines):
                    next_stripped = lines[i].strip()
                    # Looks like "MCKEESPORT, PA 15133" — no pipe-separated values
                    if (next_stripped and
                        re.match(r'^[A-Z].*,\s*PA\s+\d{5}', next_stripped, re.IGNORECASE) and
                        not COL_HDR_RE.search(lines[i])):
                        if prop.address:
                            prop.address += "\n" + next_stripped
                        else:
                            prop.address = next_stripped
                        i += 1

            # Gather comments block
            comment_lines = []
            while i < len(lines):
                cline = lines[i]
                # Stop on a new sale header or column header
                if HEADER_RE.search(cline) or COL_HDR_RE.search(cline):
                    break
                # Stop on a page-break line
                if "Printed:" in cline or "Date of Sale:" in cline:
                    break
                comment_lines.append(cline)
                i += 1

            comments = " ".join(l.strip() for l in comment_lines if l.strip())
            prop.comments = comments

            # Classify F&C
            if FC_RE.search(comments):
                prop.free_and_clear = True
                mb = MINBID_RE.search(comments)
                if mb:
                    prop.min_bid = float(mb.group(1).replace(",", ""))
                elif UPSET_RE.search(comments):
                    prop.min_bid = prop.tax_bid  # min bid = upset price

            properties.append(prop)
            continue

        i += 1

    return properties

# ─── Allegheny County Assessment Lookup ───────────────────────────────────────

def fetch_ac_assessment(parcel_id: str) -> dict:
    """
    Query the Allegheny County assessment portal for a parcel.
    Returns dict with assessed_value, fair_market, year_built, sqft, bedrooms.
    """
    clean_id = parcel_id.strip()
    url = f"https://assessments.alleghenycounty.us/api/Parcel/{urllib.parse.quote(clean_id)}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())
        # API returns a list; grab first result
        if isinstance(data, list) and data:
            rec = data[0]
        elif isinstance(data, dict):
            rec = data
        else:
            return {}

        return {
            "assessed_value": float(rec.get("TotalValue") or rec.get("AssessedValue") or 0),
            "fair_market":    float(rec.get("FairMarketValue") or rec.get("MarketValue") or 0),
            "year_built":     str(rec.get("YearBuilt") or ""),
            "sqft":           int(rec.get("LivingArea") or rec.get("SquareFeet") or 0) or None,
            "bedrooms":       int(rec.get("Bedrooms") or 0) or None,
        }
    except Exception:
        return {}


def fetch_ac_search(address: str, municipality: str) -> dict:
    """Fall-back: search by address string."""
    query = urllib.parse.quote(f"{address} {municipality} PA")
    url = AC_SEARCH_URL.format(query=query)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())
        if isinstance(data, list) and data:
            rec = data[0]
            return {
                "assessed_value": float(rec.get("TotalValue") or 0),
                "fair_market":    float(rec.get("FairMarketValue") or 0),
                "year_built":     str(rec.get("YearBuilt") or ""),
                "sqft":           int(rec.get("LivingArea") or 0) or None,
                "bedrooms":       int(rec.get("Bedrooms") or 0) or None,
            }
    except Exception:
        pass
    return {}


def fetch_wprdc_parcel(parcel_id: str) -> dict:
    """
    WPRDC open data: Allegheny County parcel assessments.
    https://data.wprdc.org/dataset/property-assessments
    Uses the CKAN API to query by parcel number (PARID).
    """
    clean_id = parcel_id.replace("-", "").replace(" ", "")
    # Also try formatted version: XXXX-X-NNN
    formatted = parcel_id.strip()

    base = "https://data.wprdc.org/api/3/action/datastore_search_sql"
    sql = f"SELECT * FROM \"518b583f-7cc8-4f60-94d0-174cc98310dc\" WHERE \"PARID\" LIKE '%{formatted}%' LIMIT 1"
    url = base + "?" + urllib.parse.urlencode({"sql": sql})
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        records = data.get("result", {}).get("records", [])
        if records:
            r = records[0]
            return {
                "assessed_value": float(r.get("ASSESSEDVALUE") or r.get("TOTALVALUE") or 0),
                "fair_market":    float(r.get("FAIRMARKETVALUE") or r.get("ASSESSEDVALUE") or 0),
                "year_built":     str(r.get("YEARBLT") or ""),
                "sqft":           int(float(r.get("FINISHEDLIVINGAREA") or 0)) or None,
                "bedrooms":       int(float(r.get("BEDROOMS") or 0)) or None,
            }
    except Exception:
        pass
    return {}


def enrich_property(prop: Property, delay: float = 0.5) -> None:
    """Attempt to enrich a property with assessed/market value data."""
    result = {}
    # Try WPRDC first (open data, most reliable)
    if prop.parcel_id:
        result = fetch_wprdc_parcel(prop.parcel_id)
    # Fall back to AC portal search
    if not result and prop.address:
        time.sleep(delay)
        result = fetch_ac_search(prop.address, prop.municipality)

    if result:
        prop.assessed_value = result.get("assessed_value") or None
        prop.fair_market    = result.get("fair_market") or None
        prop.year_built     = result.get("year_built") or None
        prop.sqft           = result.get("sqft") or None
        prop.bedrooms       = result.get("bedrooms") or None


def compute_deal_score(prop: Property) -> None:
    """
    Score the deal on a 0–100 scale.
    Higher = better opportunity.
    Factors:
      - F&C bonus: +30
      - Active (not postponed): +10
      - equity_ratio = (fair_market - effective_bid) / fair_market
        mapped to 0–60 points
    """
    score = 0.0
    if prop.free_and_clear:
        score += 30
    if prop.active:
        score += 10

    ref = prop.fair_market or prop.assessed_value
    if ref and ref > 0:
        bid = prop.effective_bid
        equity = ref - bid
        prop.equity_at_bid = equity
        ratio = equity / ref
        # 60 pts for 100% equity, 0 pts at 0% equity
        score += max(0.0, min(60.0, ratio * 60))
    else:
        prop.equity_at_bid = None

    prop.deal_score = round(score, 1)

# ─── Report ───────────────────────────────────────────────────────────────────

def fmt_money(v: Optional[float]) -> str:
    if v is None:
        return "N/A"
    return f"${v:,.0f}"


def print_report(properties: list[Property], fc_only: bool = False) -> None:
    filtered = [p for p in properties if not fc_only or p.free_and_clear]
    filtered.sort(key=lambda p: p.deal_score, reverse=True)

    print("\n" + "═" * 100)
    print("  ALLEGHENY COUNTY SHERIFF SALE — MAY 4, 2026  |  DEAL ANALYSIS REPORT")
    print("═" * 100)

    total     = len(properties)
    fc_count  = sum(1 for p in properties if p.free_and_clear)
    active_fc = sum(1 for p in properties if p.free_and_clear and p.active)
    print(f"\n  Total listings: {total}   |   Free & Clear: {fc_count}   |   F&C Active (not postponed): {active_fc}\n")

    # ── Priority Table ──────────────────────────────────────────────────────
    print("─" * 100)
    label = "FREE & CLEAR PROPERTIES" if fc_only else "ALL PROPERTIES"
    print(f"  {label}  (sorted by Deal Score ↓)")
    print("─" * 100)

    rows = []
    for p in filtered:
        addr_short = p.address.replace("\n", " ")[:38]
        rows.append([
            f"{'★ ' if p.free_and_clear else '  '}{p.sale_id}",
            p.case_number,
            addr_short,
            p.municipality[:18],
            p.status[:18],
            fmt_money(p.tax_bid),
            fmt_money(p.min_bid),
            fmt_money(p.fair_market or p.assessed_value),
            fmt_money(p.equity_at_bid),
            f"{p.deal_score:.0f}/100",
        ])

    headers = ["Sale ID", "Case #", "Address", "Municipality",
               "Status", "Tax Bid", "Min Bid", "Est. Value",
               "Equity@Bid", "Score"]

    if HAS_TABULATE:
        print(tabulate(rows, headers=headers, tablefmt="simple"))
    else:
        col_widths = [max(len(str(r[i])) for r in rows + [headers]) for i in range(len(headers))]
        fmt_row = lambda r: "  ".join(str(r[i]).ljust(col_widths[i]) for i in range(len(r)))
        print(fmt_row(headers))
        print("  ".join("-" * w for w in col_widths))
        for r in rows:
            print(fmt_row(r))

    # ── Detailed Cards for Top F&C ─────────────────────────────────────────
    top_fc = [p for p in filtered if p.free_and_clear and p.active][:6]
    if top_fc:
        print("\n" + "═" * 100)
        print("  TOP FREE & CLEAR DEAL CARDS")
        print("═" * 100)
        for p in top_fc:
            ref = p.fair_market or p.assessed_value
            ratio_pct = f"{((ref - p.effective_bid)/ref*100):.0f}%" if ref else "N/A"
            print(f"""
  ┌─── {p.sale_id}  |  {p.case_number}  |  Score: {p.deal_score:.0f}/100 ──────────────────────────────────
  │  Address:      {p.address.replace(chr(10), ' ')}
  │  Municipality: {p.municipality}   |  Parcel: {p.parcel_id}
  │  Defendant:    {p.defendant}
  │  Plaintiff:    {p.plaintiff}
  │  Tax Bid:      {fmt_money(p.tax_bid)}   |  Min Bid: {fmt_money(p.min_bid)}   |  Status: {p.status}
  │  Est. Value:   {fmt_money(ref)}  |  Year Built: {p.year_built or 'N/A'}  |  SqFt: {p.sqft or 'N/A'}  |  Beds: {p.bedrooms or 'N/A'}
  │  Equity@Bid:   {fmt_money(p.equity_at_bid)}  ({ratio_pct} below market)
  │  Comments:     {p.comments[:180]}…
  └────────────────────────────────────────────────────────────────────────────""")


def save_json(properties: list[Property], path: Path) -> None:
    with open(path, "w") as f:
        json.dump([asdict(p) for p in properties], f, indent=2)
    print(f"\n  [export] Full dataset saved to {path}")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main(args=None):
    import argparse
    parser = argparse.ArgumentParser(description="Allegheny County Sheriff Sale Analyzer")
    parser.add_argument("--pdf-url",   default=SALE_PDF_URL, help="URL of the sheriff sale PDF")
    parser.add_argument("--fc-only",   action="store_true",   help="Show only Free & Clear properties")
    parser.add_argument("--enrich",    action="store_true",   help="Fetch assessed values from WPRDC")
    parser.add_argument("--export",    metavar="FILE",        help="Save full dataset to JSON file")
    parser.add_argument("--no-cache",  action="store_true",   help="Re-download PDF even if cached")
    ns = parser.parse_args(args)

    if ns.no_cache:
        PDF_CACHE.unlink(missing_ok=True)
        TXT_CACHE.unlink(missing_ok=True)

    print("\n[1/4] Fetching sheriff sale PDF…")
    pdf_path = download_pdf(ns.pdf_url, PDF_CACHE)

    print("[2/4] Converting PDF to text…")
    txt_path = pdf_to_text(pdf_path, TXT_CACHE)

    print("[3/4] Parsing property records…")
    properties = parse_sheriff_text(txt_path)
    print(f"      Found {len(properties)} records  |  "
          f"{sum(1 for p in properties if p.free_and_clear)} Free & Clear")

    if ns.enrich:
        fc_props = [p for p in properties if p.free_and_clear]
        print(f"[4/4] Enriching {len(fc_props)} F&C properties with WPRDC assessment data…")
        for idx, p in enumerate(fc_props, 1):
            print(f"      [{idx}/{len(fc_props)}] {p.parcel_id} — {p.address[:50]}")
            enrich_property(p)
            time.sleep(0.4)
    else:
        print("[4/4] Skipping enrichment (use --enrich to fetch assessed values)")

    for p in properties:
        compute_deal_score(p)

    print_report(properties, fc_only=ns.fc_only or True)

    if ns.export:
        save_json(properties, Path(ns.export))

    return properties


if __name__ == "__main__":
    main()
