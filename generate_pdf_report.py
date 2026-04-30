#!/usr/bin/env python3
"""
Estella Wilson Properties LLC — Sheriff Sale PDF Report Generator
Produces a professional, branded PDF from investment_analyzer deal data.
"""

import json
import math
import time
import urllib.request
import urllib.parse
from io import BytesIO
from pathlib import Path
from datetime import date, datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer,
    Table, TableStyle, HRFlowable, Image, KeepTogether, PageBreak,
)
from reportlab.graphics.shapes import (
    Drawing, Rect, Circle, String, Line, Wedge, Polygon,
)
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics import renderPDF
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from investment_analyzer import Deal, analyze, load_deals_from_json

# ─── Brand Colors (from Estella Wilson logo) ─────────────────────────────────

ORANGE      = colors.HexColor("#F5A51B")   # roof / primary accent
ORANGE_DARK = colors.HexColor("#D4880A")   # darker orange for headings
SKY_BLUE    = colors.HexColor("#87C9E8")   # window accent
CHARCOAL    = colors.HexColor("#2B2B2B")   # primary text
GRAY_MID    = colors.HexColor("#666666")   # secondary text
GRAY_LIGHT  = colors.HexColor("#F4F4F4")   # card backgrounds
GRAY_LINE   = colors.HexColor("#DDDDDD")   # divider lines
WHITE       = colors.white
GREEN_OK    = colors.HexColor("#27AE60")
RED_BAD     = colors.HexColor("#E74C3C")
YELLOW_WARN = colors.HexColor("#F39C12")
BLUE_INFO   = colors.HexColor("#2980B9")
ORANGE_TINT = colors.HexColor("#FFF5E0")   # very light orange for card bg

PAGE_W, PAGE_H = letter  # 8.5 × 11 inches
MARGIN        = 0.55 * inch
CONTENT_W     = PAGE_W - 2 * MARGIN

LOGO_PATH     = Path(__file__).parent / "estellawilson_logo.jpg"
DATA_FILE     = "/tmp/fc_analysis_input.json"
OUTPUT_PDF    = Path(__file__).parent / "Estella_Wilson_Sheriff_Sale_Report.pdf"

# ─── Geocode cache (pre-fetched to avoid rate limits) ────────────────────────

GEOCACHE = {
    "46OCT25":  (40.5095646, -79.8383347),
    "37JUL19":  (40.2676590, -79.8329460),
    "40JUL19":  (40.4530000, -79.9900000),   # Pittsburgh 30th ward approx
    "6AUG24":   (40.4811850, -79.9765797),
    "64NOV24":  (40.2712863, -79.8860727),
    "39DEC25":  (40.4513786, -79.8561369),
    "164DEC25": (40.4045739, -79.9021765),
    "67FEB26":  (40.4284840, -80.0133772),
    "12JUL17":  (40.3222161, -79.8557996),
}

# ─── Map image fetcher (OpenStreetMap tiles via tile.openstreetmap.org) ───────

def _deg2tile(lat, lon, zoom):
    n = 2 ** zoom
    x = int((lon + 180.0) / 360.0 * n)
    y = int((1.0 - math.log(math.tan(math.radians(lat)) +
             1.0 / math.cos(math.radians(lat))) / math.pi) / 2.0 * n)
    return x, y


_MAP_TILE_TIMEOUT   = 3   # seconds per tile HTTP request
_MAP_TOTAL_BUDGET   = 12  # seconds max for the entire 3×3 grid fetch


def fetch_map_tile(lat: float, lon: float, zoom: int = 16) -> bytes | None:
    """Fetch a single OSM tile as PNG bytes."""
    x, y = _deg2tile(lat, lon, zoom)
    url = f"https://tile.openstreetmap.org/{zoom}/{x}/{y}.png"
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "EstellaWilsonProperties/1.0 (property analysis)"}
        )
        with urllib.request.urlopen(req, timeout=_MAP_TILE_TIMEOUT) as r:
            return r.read()
    except Exception:
        return None


def fetch_map_image(lat: float, lon: float) -> BytesIO | None:
    """
    Build a 3×3 grid of OSM tiles centred on the property, stitched with Pillow.
    Returns a BytesIO PNG ready for ReportLab Image(), or None on failure.
    Aborts early if the total fetch time exceeds _MAP_TOTAL_BUDGET seconds.
    """
    try:
        from PIL import Image as PILImage, ImageDraw, ImageFont
        zoom = 17
        cx, cy = _deg2tile(lat, lon, zoom)
        tile_size = 256
        grid_w, grid_h = 3, 3
        composite = PILImage.new("RGB", (tile_size * grid_w, tile_size * grid_h), (240, 240, 240))
        deadline = time.monotonic() + _MAP_TOTAL_BUDGET
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                if time.monotonic() >= deadline:
                    break
                tx, ty = cx + dx, cy + dy
                url = f"https://tile.openstreetmap.org/{zoom}/{tx}/{ty}.png"
                try:
                    req = urllib.request.Request(
                        url, headers={"User-Agent": "EstellaWilsonProperties/1.0"}
                    )
                    with urllib.request.urlopen(req, timeout=_MAP_TILE_TIMEOUT) as r:
                        tile_data = r.read()
                    tile_img = PILImage.open(BytesIO(tile_data)).convert("RGB")
                    composite.paste(tile_img, ((dx + 1) * tile_size, (dy + 1) * tile_size))
                except Exception:
                    pass
        # Draw a red pin at center
        draw = ImageDraw.Draw(composite)
        cx_px = tile_size + tile_size // 2
        cy_px = tile_size + tile_size // 2
        r = 10
        draw.ellipse([cx_px - r, cy_px - r, cx_px + r, cy_px + r],
                     fill=(220, 50, 50), outline=(255, 255, 255), width=3)
        draw.ellipse([cx_px - 3, cy_px - 3, cx_px + 3, cy_px + 3],
                     fill=(255, 255, 255))
        out = BytesIO()
        composite.save(out, format="PNG")
        out.seek(0)
        return out
    except Exception as e:
        return None


# ─── Utility drawing helpers ──────────────────────────────────────────────────

def _verdict_color(verdict: str) -> colors.Color:
    return {
        "BUY":     GREEN_OK,
        "CONSIDER":ORANGE,
        "NO BUY":  RED_BAD,
        "WATCH":   YELLOW_WARN,
    }.get(verdict, GRAY_MID)


def _rating_color(rating: str) -> colors.Color:
    return {
        "PERFECT": GREEN_OK,
        "PASS":    ORANGE,
        "MARGINAL":YELLOW_WARN,
        "AVOID":   RED_BAD,
        "WATCH":   GRAY_MID,
    }.get(rating, GRAY_MID)


def _maps_url(address: str, municipality: str) -> str:
    """Return a Google Maps search URL for the property address."""
    query = f"{address.replace(chr(10), ' ')}, {municipality}, PA"
    return f"https://maps.google.com/?q={urllib.parse.quote_plus(query)}"


def fmt(v: float, prefix: str = "$") -> str:
    if v is None: return "N/A"
    if v < 0:    return f"-{prefix}{abs(v):,.0f}"
    return f"{prefix}{v:,.0f}"


def pct(v: float) -> str:
    return f"{v:.1f}%"


# ─── Reusable paragraph styles ────────────────────────────────────────────────

def make_styles():
    base = getSampleStyleSheet()
    S = {}
    common = dict(fontName="Helvetica", textColor=CHARCOAL)

    S["h1"] = ParagraphStyle("h1", fontSize=22, leading=28,
                              fontName="Helvetica-Bold", textColor=ORANGE_DARK,
                              alignment=TA_CENTER)
    S["h2"] = ParagraphStyle("h2", fontSize=14, leading=18,
                              fontName="Helvetica-Bold", textColor=CHARCOAL,
                              spaceAfter=4)
    S["h3"] = ParagraphStyle("h3", fontSize=10, leading=13,
                              fontName="Helvetica-Bold", textColor=ORANGE_DARK,
                              spaceBefore=6, spaceAfter=2)
    S["body"] = ParagraphStyle("body", fontSize=8.5, leading=12, **common)
    S["small"] = ParagraphStyle("small", fontSize=7.5, leading=10,
                                 textColor=GRAY_MID, fontName="Helvetica")
    S["label"] = ParagraphStyle("label", fontSize=7, leading=9,
                                 textColor=GRAY_MID, fontName="Helvetica",
                                 alignment=TA_CENTER)
    S["value"] = ParagraphStyle("value", fontSize=11, leading=14,
                                 fontName="Helvetica-Bold", textColor=CHARCOAL,
                                 alignment=TA_CENTER)
    S["center"] = ParagraphStyle("center", fontSize=8.5, leading=12,
                                  alignment=TA_CENTER, **common)
    S["flag"]  = ParagraphStyle("flag", fontSize=7.5, leading=10,
                                 textColor=RED_BAD, fontName="Helvetica",
                                 leftIndent=8)
    S["note"]  = ParagraphStyle("note", fontSize=7.5, leading=10,
                                 textColor=GRAY_MID, fontName="Helvetica-Oblique")
    return S


# ─── Mini metric tile ─────────────────────────────────────────────────────────

def metric_tile(label: str, value: str, color: colors.Color = ORANGE,
                bg: colors.Color = ORANGE_TINT) -> Table:
    """A small colored metric box: label on top, value below."""
    data = [
        [Paragraph(label, ParagraphStyle("tl", fontSize=7, leading=8,
                                          fontName="Helvetica", textColor=GRAY_MID,
                                          alignment=TA_CENTER))],
        [Paragraph(value, ParagraphStyle("tv", fontSize=10, leading=12,
                                          fontName="Helvetica-Bold", textColor=color,
                                          alignment=TA_CENTER))],
    ]
    t = Table(data, colWidths=[1.12 * inch])
    t.setStyle(TableStyle([
        ("BACKGROUND",  (0, 0), (-1, -1), bg),
        ("ROUNDEDCORNERS", [4]),
        ("TOPPADDING",  (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING",(0, 0), (-1, -1), 4),
        ("BOX",         (0, 0), (-1, -1), 0.5, color),
    ]))
    return t


# ─── Score gauge (drawn with ReportLab graphics) ─────────────────────────────

def score_gauge(score: int, size: float = 1.2 * inch) -> Drawing:
    """Draw a semicircular gauge for the deal score 0–100."""
    d = Drawing(size, size * 0.65)
    cx, cy = size / 2, size * 0.55
    r = size * 0.42

    # Background arc segments: red / yellow / green
    segments = [
        (180, 120, colors.HexColor("#FDECEA")),
        (120, 60,  colors.HexColor("#FFF3CD")),
        (60,  0,   colors.HexColor("#D4EDDA")),
    ]
    for start, end, col in segments:
        w = Wedge(cx, cy, r, start, end, fillColor=col, strokeColor=None)
        d.add(w)

    # Needle
    angle_deg = 180 - (score / 100 * 180)
    angle_rad = math.radians(angle_deg)
    needle_len = r * 0.85
    nx = cx + needle_len * math.cos(angle_rad)
    ny = cy + needle_len * math.sin(angle_rad)
    d.add(Line(cx, cy, nx, ny, strokeColor=CHARCOAL, strokeWidth=2))
    d.add(Circle(cx, cy, 4, fillColor=CHARCOAL, strokeColor=WHITE, strokeWidth=1))

    # Score text
    color = GREEN_OK if score >= 70 else (ORANGE if score >= 40 else RED_BAD)
    d.add(String(cx, cy - r * 0.3, f"{score}", fontSize=14,
                 fillColor=color, textAnchor="middle",
                 fontName="Helvetica-Bold"))
    d.add(String(cx, cy - r * 0.55, "/100", fontSize=7,
                 fillColor=GRAY_MID, textAnchor="middle"))
    return d


# ─── Rating badge ─────────────────────────────────────────────────────────────

def rating_badge(rating: str, verdict: str) -> Drawing:
    """Colored pill badge for verdict + rating."""
    w, h = 1.6 * inch, 0.38 * inch
    d = Drawing(w, h)
    vc = _verdict_color(verdict)
    rc = _rating_color(rating)
    d.add(Rect(0, 0, w, h, rx=6, ry=6, fillColor=vc, strokeColor=None))
    label = {"BUY": "✔ BUY", "NO BUY": "✘ NO BUY",
             "CONSIDER": "? CONSIDER", "WATCH": "⏳ WATCH"}.get(verdict, verdict)
    d.add(String(w / 2, h * 0.28, label, fontSize=10,
                 fillColor=WHITE, textAnchor="middle", fontName="Helvetica-Bold"))
    return d


# ─── Stat bar (school / crime) ────────────────────────────────────────────────

def stat_bar(value: float, max_val: float, color: colors.Color,
             width: float = 1.5 * inch, height: float = 0.12 * inch) -> Drawing:
    d = Drawing(width, height)
    d.add(Rect(0, 0, width, height, fillColor=GRAY_LINE, strokeColor=None))
    filled = min(value / max_val, 1.0) * width
    d.add(Rect(0, 0, filled, height, fillColor=color, strokeColor=None))
    return d


# ─── Page header / footer canvas callback ─────────────────────────────────────

_DEFAULT_REPORT_TITLE  = "Estella Wilson Properties LLC — Sheriff Sale Property Analysis"
_DEFAULT_FOOTER_LABEL  = "Allegheny County Sheriff Sale"


class BrandedCanvas(canvas.Canvas):
    def __init__(self, *args, logo_path=None, report_title=None, footer_label=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._logo_path    = logo_path
        self._report_title = report_title or _DEFAULT_REPORT_TITLE
        self._footer_label = footer_label or _DEFAULT_FOOTER_LABEL

    def _header_footer(self):
        self.saveState()
        w, h = self._pagesize

        # Top orange bar
        self.setFillColor(ORANGE)
        self.rect(0, h - 0.42 * inch, w, 0.42 * inch, fill=1, stroke=0)

        # Logo on top-left
        if self._logo_path and Path(self._logo_path).exists():
            try:
                self.drawImage(str(self._logo_path),
                               MARGIN, h - 0.40 * inch,
                               width=0.9 * inch, height=0.36 * inch,
                               preserveAspectRatio=True, mask="auto")
            except Exception:
                pass

        # Title in orange bar
        self.setFont("Helvetica-Bold", 9)
        self.setFillColor(WHITE)
        self.drawCentredString(w / 2, h - 0.26 * inch, self._report_title)
        self.setFont("Helvetica", 7)
        self.drawRightString(w - MARGIN, h - 0.26 * inch,
                             f"{date.today().strftime('%B %d, %Y')}  |  Confidential")

        # Bottom footer bar
        self.setFillColor(CHARCOAL)
        self.rect(0, 0, w, 0.28 * inch, fill=1, stroke=0)
        self.setFont("Helvetica", 7)
        self.setFillColor(WHITE)
        self.drawCentredString(w / 2, 0.09 * inch,
                               f"Page {self._pageNumber}  |  {self._footer_label}  |  "
                               f"Analysis prepared {date.today().strftime('%B %d, %Y')}")
        self.restoreState()

    def showPage(self):
        self._header_footer()
        super().showPage()

    def save(self):
        self._header_footer()
        super().save()


# ─── Cover page ───────────────────────────────────────────────────────────────

def build_cover(deals: list[Deal], S: dict,
                subtitle: str = None, cover_note: str = None) -> list:
    story = []
    story.append(Spacer(1, 0.5 * inch))

    # Logo centered
    if LOGO_PATH.exists():
        story.append(Image(str(LOGO_PATH), width=2.2 * inch, height=2.2 * inch,
                           hAlign="CENTER"))
    story.append(Spacer(1, 0.2 * inch))

    # Title
    story.append(Paragraph(
        "Estella Wilson Properties LLC", S["h1"]
    ))
    story.append(Paragraph(
        '<font color="#666666" size="14">Sheriff Sale Property Analysis</font>',
        ParagraphStyle("sub", fontSize=14, leading=18, alignment=TA_CENTER,
                       fontName="Helvetica-Oblique", textColor=GRAY_MID)
    ))
    story.append(Paragraph(
        subtitle or "Allegheny County  ·  May 4, 2026",
        ParagraphStyle("date", fontSize=11, leading=14, alignment=TA_CENTER,
                       fontName="Helvetica", textColor=GRAY_MID, spaceBefore=4)
    ))
    story.append(Spacer(1, 0.3 * inch))
    story.append(HRFlowable(width="100%", thickness=2, color=ORANGE, spaceAfter=16))

    # Summary scorecard
    buy_ct     = sum(1 for d in deals if d.verdict == "BUY")
    consider_ct= sum(1 for d in deals if d.verdict == "CONSIDER")
    skip_ct    = sum(1 for d in deals if d.verdict == "NO BUY")
    watch_ct   = sum(1 for d in deals if d.verdict == "WATCH")
    perfect_ct = sum(1 for d in deals if d.perfect_pass_rating == "PERFECT")
    avoid_ct   = sum(1 for d in deals if d.perfect_pass_rating == "AVOID")

    summary_data = [
        [Paragraph("Total Properties", S["label"]),
         Paragraph("BUY",    S["label"]),
         Paragraph("CONSIDER",S["label"]),
         Paragraph("NO BUY",  S["label"]),
         Paragraph("WATCH",   S["label"]),
         Paragraph("PERFECT", S["label"]),
         Paragraph("AVOID",   S["label"])],
        [Paragraph(f"<b>{len(deals)}</b>",  S["value"]),
         Paragraph(f'<font color="#27AE60"><b>{buy_ct}</b></font>',  S["value"]),
         Paragraph(f'<font color="#F5A51B"><b>{consider_ct}</b></font>', S["value"]),
         Paragraph(f'<font color="#E74C3C"><b>{skip_ct}</b></font>',  S["value"]),
         Paragraph(f'<font color="#F39C12"><b>{watch_ct}</b></font>',  S["value"]),
         Paragraph(f'<font color="#27AE60"><b>{perfect_ct}</b></font>',S["value"]),
         Paragraph(f'<font color="#E74C3C"><b>{avoid_ct}</b></font>',  S["value"])],
    ]
    t = Table(summary_data, colWidths=[CONTENT_W / 7] * 7)
    t.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, -1), ORANGE_TINT),
        ("BACKGROUND",   (0, 0), (-1, 0),  ORANGE),
        ("TEXTCOLOR",    (0, 0), (-1, 0),  WHITE),
        ("TOPPADDING",   (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 8),
        ("BOX",          (0, 0), (-1, -1), 1, ORANGE),
        ("INNERGRID",    (0, 0), (-1, -1), 0.5, GRAY_LINE),
        ("ROUNDEDCORNERS", [6]),
    ]))
    story.append(t)
    story.append(Spacer(1, 0.3 * inch))

    # Quick-glance leaderboard table
    story.append(Paragraph("Property Leaderboard — Ranked by Deal Score", S["h2"]))
    story.append(Spacer(1, 0.06 * inch))

    sorted_deals = sorted(deals, key=lambda d: d.score, reverse=True)
    hdr = ["#", "Address", "Municipality", "Min Bid", "FMV", "ARV",
           "Flip Profit", "Cap%", "Score", "Verdict"]
    addr_cell_style = ParagraphStyle(
        "addr_cell", fontSize=7.5, leading=10, fontName="Helvetica", textColor=CHARCOAL
    )
    rows = [hdr]
    for i, d in enumerate(sorted_deals, 1):
        vc = _verdict_color(d.verdict)
        rows.append([
            str(i),
            Paragraph(
                f'<a href="{_maps_url(d.address, d.municipality)}">'
                f'<u>{d.address.replace(chr(10), " ")}</u></a>',
                addr_cell_style
            ),
            d.municipality,
            fmt(d.min_bid),
            fmt(d.fmv),
            fmt(d.arv),
            fmt(d.flip_net_profit),
            pct(d.cap_rate),
            f"{d.score}/100",
            d.verdict,
        ])

    col_w = [0.25, 2.2, 1.0, 0.7, 0.7, 0.7, 0.8, 0.55, 0.6, 0.7]
    col_w = [c * inch for c in col_w]
    tbl = Table(rows, colWidths=col_w, repeatRows=1)
    style = [
        ("BACKGROUND",   (0, 0), (-1, 0),  CHARCOAL),
        ("TEXTCOLOR",    (0, 0), (-1, 0),  WHITE),
        ("FONTNAME",     (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",     (0, 0), (-1, 0),  7.5),
        ("FONTSIZE",     (0, 1), (-1, -1), 7.5),
        ("FONTNAME",     (0, 1), (-1, -1), "Helvetica"),
        ("TOPPADDING",   (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
        ("LEFTPADDING",  (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("ROWBACKGROUNDS",(0, 1),(-1, -1), [WHITE, GRAY_LIGHT]),
        ("INNERGRID",    (0, 0), (-1, -1), 0.4, GRAY_LINE),
        ("BOX",          (0, 0), (-1, -1), 0.8, ORANGE),
        ("ALIGN",        (3, 0), (-1, -1), "RIGHT"),
        ("ALIGN",        (0, 0), (0, -1),  "CENTER"),
    ]
    # Color verdict cells
    for i, d in enumerate(sorted_deals, 1):
        vc = _verdict_color(d.verdict)
        style.append(("TEXTCOLOR", (9, i), (9, i), vc))
        style.append(("FONTNAME",  (9, i), (9, i), "Helvetica-Bold"))
    tbl.setStyle(TableStyle(style))
    story.append(tbl)

    story.append(Spacer(1, 0.25 * inch))
    _note = (cover_note if cover_note is not None else
             "★ Only properties with Fair Market Value data from WPRDC assessments are included. "
             "All analysis uses cash-purchase methodology per the Perfect vs Pass investor framework.")
    if _note:
        story.append(Paragraph(_note, S["note"]))
    story.append(PageBreak())
    return story


# ─── Individual property page ─────────────────────────────────────────────────

def build_property_page(d: Deal, S: dict) -> list:
    story = []

    # ── Property header banner ────────────────────────────────────────────────
    addr_clean = d.address.replace("\n", " ").strip()
    verdict_color = _verdict_color(d.verdict)
    rating_color  = _rating_color(d.perfect_pass_rating)

    _addr_url = _maps_url(d.address, d.municipality)
    banner_data = [[
        Paragraph(
            f'<a href="{_addr_url}"><font color="white"><b><u>{addr_clean}</u></b></font></a><br/>'
            f'<font color="#FFDDAA" size="8">{d.municipality} · Parcel {d.parcel} · '
            f'Built {d.year_built} · {d.sqft:,} sqft · {d.bedrooms}BR / {d.fullbaths}BA</font>',
            ParagraphStyle("bh", fontSize=10, leading=14, fontName="Helvetica-Bold",
                           textColor=WHITE, leftIndent=4)
        ),
        Paragraph(
            f'<font color="white" size="8">Case: {d.case}<br/>ID: {d.sale_id}</font>',
            ParagraphStyle("bid", fontSize=8, leading=11, fontName="Helvetica",
                           textColor=WHITE, alignment=TA_RIGHT)
        ),
    ]]
    banner = Table(banner_data, colWidths=[CONTENT_W * 0.72, CONTENT_W * 0.28])
    banner.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, -1), CHARCOAL),
        ("TOPPADDING",   (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 8),
        ("LEFTPADDING",  (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(banner)
    story.append(Spacer(1, 0.08 * inch))

    # ── Two-column layout: map | metrics ─────────────────────────────────────
    map_w   = CONTENT_W * 0.42
    right_w = CONTENT_W * 0.55
    gap_w   = CONTENT_W * 0.03

    # Map image
    map_col = []
    lat_lon = GEOCACHE.get(d.sale_id)
    map_img_obj = None
    if lat_lon:
        print(f"  Fetching map for {d.sale_id} ({d.address[:30]})…", flush=True)
        map_bytes = fetch_map_image(*lat_lon)
        if map_bytes:
            map_img_obj = Image(map_bytes, width=map_w, height=map_w * 0.68)

    if map_img_obj:
        map_col.append(map_img_obj)
    else:
        # Styled placeholder
        placeholder_data = [[
            Paragraph(
                f'<font color="#888888">📍 Map Unavailable<br/>'
                f'<font size="8">{addr_clean}</font></font>',
                ParagraphStyle("mp", fontSize=9, leading=13, alignment=TA_CENTER,
                               textColor=GRAY_MID)
            )
        ]]
        ph = Table(placeholder_data,
                   colWidths=[map_w],
                   rowHeights=[map_w * 0.68])
        ph.setStyle(TableStyle([
            ("BACKGROUND",   (0, 0), (-1, -1), GRAY_LIGHT),
            ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
            ("BOX",          (0, 0), (-1, -1), 0.5, GRAY_LINE),
        ]))
        map_col.append(ph)

    # Address label under map
    map_col.append(Spacer(1, 0.04 * inch))
    map_col.append(Paragraph(
        f'📍 <a href="{_addr_url}"><u>{addr_clean}, {d.municipality}, PA</u></a>',
        ParagraphStyle("mapl", fontSize=6.5, leading=9, textColor=GRAY_MID,
                       fontName="Helvetica-Oblique")
    ))

    # ── Right column: verdict badge + score gauge + key metrics ──────────────
    right_col = []

    # Verdict + score row
    verdict_label = {
        "BUY": "✔  BUY",
        "NO BUY": "✘  NO BUY",
        "CONSIDER": "?  CONSIDER",
        "WATCH": "⏳  WATCH",
    }.get(d.verdict, d.verdict)

    rating_labels = {
        "PERFECT": "★ PERFECT",
        "PASS":    "✓ PASS",
        "MARGINAL":"~ MARGINAL",
        "AVOID":   "✗ AVOID",
        "WATCH":   "⏳ WATCH",
    }

    v_badge_data = [[
        Paragraph(verdict_label,
                  ParagraphStyle("vb", fontSize=13, fontName="Helvetica-Bold",
                                  textColor=WHITE, alignment=TA_CENTER)),
        Paragraph(rating_labels.get(d.perfect_pass_rating, ""),
                  ParagraphStyle("rb", fontSize=10, fontName="Helvetica-Bold",
                                  textColor=WHITE, alignment=TA_CENTER)),
    ]]
    v_badge = Table(v_badge_data, colWidths=[right_w * 0.5, right_w * 0.5])
    v_badge.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (0, 0), verdict_color),
        ("BACKGROUND",   (1, 0), (1, 0), rating_color),
        ("TOPPADDING",   (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 7),
        ("INNERGRID",    (0, 0), (-1, -1), 1, WHITE),
    ]))
    right_col.append(v_badge)
    right_col.append(Spacer(1, 0.08 * inch))

    # Score gauge + key metrics tiles
    gauge = score_gauge(d.score, size=1.1 * inch)

    tile_data = [[
        gauge,
        metric_tile("Min Bid",      fmt(d.min_bid),   ORANGE),
        metric_tile("FMV",          fmt(d.fmv),       BLUE_INFO),
        metric_tile("ARV",          fmt(d.arv),       GREEN_OK),
    ]]
    tiles = Table(tile_data,
                  colWidths=[1.15 * inch, 1.12 * inch, 1.12 * inch, 1.12 * inch])
    tiles.setStyle(TableStyle([
        ("VALIGN",      (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING",(0, 0), (-1, -1), 2),
    ]))
    right_col.append(tiles)
    right_col.append(Spacer(1, 0.06 * inch))

    tile2_data = [[
        metric_tile("Flip Profit",
                    fmt(d.flip_net_profit),
                    GREEN_OK if d.flip_net_profit > 0 else RED_BAD),
        metric_tile("Cap Rate",     pct(d.cap_rate),  GREEN_OK if d.cap_rate >= 7 else ORANGE),
        metric_tile("DSCR",         f"{d.dscr:.2f}x", GREEN_OK if d.dscr >= 1.2 else RED_BAD),
        metric_tile("Mo. NOI",      fmt(d.monthly_noi), BLUE_INFO),
    ]]
    tiles2 = Table(tile2_data,
                   colWidths=[1.12 * inch] * 4)
    tiles2.setStyle(TableStyle([
        ("VALIGN",      (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING",(0, 0), (-1, -1), 2),
    ]))
    right_col.append(tiles2)

    # ── Assemble two-column layout ────────────────────────────────────────────
    two_col = Table(
        [[map_col, Spacer(gap_w, 1), right_col]],
        colWidths=[map_w, gap_w, right_w]
    )
    two_col.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(two_col)
    story.append(Spacer(1, 0.1 * inch))
    story.append(HRFlowable(width="100%", thickness=1, color=ORANGE_DARK, spaceAfter=6))

    # ── Financial analysis section ────────────────────────────────────────────
    fin_left  = CONTENT_W * 0.48
    fin_right = CONTENT_W * 0.48
    fin_gap   = CONTENT_W * 0.04

    # Left: flip analysis + stress tests
    flip_section = []
    flip_section.append(Paragraph("FLIP ANALYSIS", S["h3"]))

    flip_rows = [
        ["Total All-In Cost",   fmt(d.total_all_in)],
        ["  Purchase / Bid",    fmt(d.min_bid)],
        ["  Repair Est.",       fmt(d.repair_cost)],
        ["  Contingency (5%)",  fmt(d.contingency)],
        ["  Carrying Costs",    fmt(6 * 400)],
        ["ARV",                 fmt(d.arv)],
        ["Net Sale Proceeds",   fmt(round(d.arv * 0.92))],
        ["Flip Net Profit",     fmt(d.flip_net_profit)],
        ["Project ROI",         pct(d.flip_roi_pct)],
        ["Annualized IRR",      pct(d.flip_irr_pct)],
        ["Precise MAO",         fmt(d.precise_mao)],
        ["70% Rule Max Bid",    fmt(d.max_bid_70)],
    ]
    ft = Table(flip_rows, colWidths=[fin_left * 0.62, fin_left * 0.38])
    fstyle = [
        ("FONTNAME",    (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE",    (0, 0), (-1, -1), 7.5),
        ("FONTNAME",    (0, 7), (0, 7),   "Helvetica-Bold"),
        ("FONTNAME",    (1, 7), (1, 7),   "Helvetica-Bold"),
        ("TEXTCOLOR",   (1, 7), (1, 7),   GREEN_OK if d.flip_net_profit > 0 else RED_BAD),
        ("TOPPADDING",  (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING",(0,0), (-1, -1), 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING",(0, 0), (-1, -1), 4),
        ("ALIGN",       (1, 0), (1, -1),  "RIGHT"),
        ("ROWBACKGROUNDS",(0,0),(-1,-1),  [WHITE, GRAY_LIGHT]),
        ("BOX",         (0, 0), (-1, -1), 0.5, GRAY_LINE),
        ("LINEBELOW",   (0, 6), (-1, 6),  0.8, ORANGE),
    ]
    ft.setStyle(TableStyle(fstyle))
    flip_section.append(ft)
    flip_section.append(Spacer(1, 0.08 * inch))

    # Stress test table
    flip_section.append(Paragraph("FLIP STRESS TESTS", S["h3"]))
    stress_rows = [
        ["Scenario", "Profit", "Pass?"],
        ["ARV −5%",          fmt(d.stress_flip_arv5),    "✔" if d.stress_flip_arv5 > 0 else "✘"],
        ["ARV −8%",          fmt(d.stress_flip_arv8),    "✔" if d.stress_flip_arv8 > 0 else "✘"],
        ["Rehab +$10/sqft",  fmt(d.stress_flip_rehab10), "✔" if d.stress_flip_rehab10 > 0 else "✘"],
        ["DOM +30 days",     fmt(d.stress_flip_dom30),   "✔" if d.stress_flip_dom30 > 0 else "✘"],
    ]
    st = Table(stress_rows, colWidths=[fin_left * 0.55, fin_left * 0.30, fin_left * 0.15])
    st_style = [
        ("BACKGROUND",  (0, 0), (-1, 0),  CHARCOAL),
        ("TEXTCOLOR",   (0, 0), (-1, 0),  WHITE),
        ("FONTNAME",    (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTNAME",    (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE",    (0, 0), (-1, -1), 7.5),
        ("TOPPADDING",  (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING",(0, 0),(-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING",(0, 0), (-1, -1), 4),
        ("ALIGN",       (1, 0), (-1, -1), "RIGHT"),
        ("ROWBACKGROUNDS",(0,1),(-1,-1),  [WHITE, GRAY_LIGHT]),
        ("BOX",         (0, 0), (-1, -1), 0.5, GRAY_LINE),
    ]
    for i, row in enumerate(stress_rows[1:], 1):
        ok = row[2] == "✔"
        st_style.append(("TEXTCOLOR", (2, i), (2, i), GREEN_OK if ok else RED_BAD))
        st_style.append(("FONTNAME",  (2, i), (2, i), "Helvetica-Bold"))
        if not ok:
            st_style.append(("TEXTCOLOR", (1, i), (1, i), RED_BAD))
    st.setStyle(TableStyle(st_style))
    flip_section.append(st)

    # Right: rental analysis + hold stress
    rent_section = []
    rent_section.append(Paragraph("RENTAL / HOLD ANALYSIS", S["h3"]))

    rent_rows = [
        ["Gross Potential Rent",   fmt(d.gross_potential_rent) + "/yr"],
        ["EGI (after 8% vacancy)", fmt(d.egi) + "/yr"],
        ["Operating Expenses",     f"{d.operating_exp_ratio}% of EGI"],
        ["Annual NOI",             fmt(d.annual_noi) + "/yr"],
        ["Monthly NOI",            fmt(d.monthly_noi) + "/mo"],
        ["Cap Rate",               pct(d.cap_rate)],
        ["GRM",                    f"{d.gross_rent_mult:.1f}x"],
        ["1% Rule",                "✔ PASS" if d.passes_1pct_rule else "✘ Fail"],
        ["Year-1 Cash Flow",       fmt(d.cash_flow_yr1) + "/yr"],
        ["", ""],
        ["─── LEVERAGE SCENARIO ─────", ""],
        ["Loan (75% LTV)",         fmt(d.loan_amount)],
        ["Annual Debt Service",    fmt(d.annual_debt_service) + "/yr"],
        ["DSCR",                   f"{d.dscr:.2f}x"],
        ["Cash-on-Cash (levered)", pct(d.cash_on_cash_levered)],
        ["Payback Period",         f"{d.payback_yrs:.1f} yrs"],
    ]
    rt = Table(rent_rows, colWidths=[fin_right * 0.60, fin_right * 0.40])
    rt_style = [
        ("FONTNAME",    (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE",    (0, 0), (-1, -1), 7.5),
        ("FONTNAME",    (0, 3), (0, 3),   "Helvetica-Bold"),
        ("FONTNAME",    (1, 3), (1, 3),   "Helvetica-Bold"),
        ("FONTNAME",    (0, 10),(0, 10),  "Helvetica-Bold"),
        ("TEXTCOLOR",   (0, 10),(0, 10),  ORANGE_DARK),
        ("TOPPADDING",  (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING",(0,0), (-1, -1), 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING",(0, 0), (-1, -1), 4),
        ("ALIGN",       (1, 0), (1, -1),  "RIGHT"),
        ("ROWBACKGROUNDS",(0,0),(-1,-1),  [WHITE, GRAY_LIGHT]),
        ("BOX",         (0, 0), (-1, -1), 0.5, GRAY_LINE),
        ("LINEBELOW",   (0, 2), (-1, 2),  0.8, ORANGE),
        ("LINEBELOW",   (0, 9), (-1, 9),  0.5, GRAY_LINE),
        ("TEXTCOLOR",   (1, 5), (1, 5),   GREEN_OK if d.cap_rate >= 7 else ORANGE),
        ("FONTNAME",    (1, 5), (1, 5),   "Helvetica-Bold"),
    ]
    if d.passes_1pct_rule:
        rt_style.append(("TEXTCOLOR", (1, 7), (1, 7), GREEN_OK))
    else:
        rt_style.append(("TEXTCOLOR", (1, 7), (1, 7), RED_BAD))
    rt.setStyle(TableStyle(rt_style))
    rent_section.append(rt)
    rent_section.append(Spacer(1, 0.08 * inch))

    # Hold stress tests
    rent_section.append(Paragraph("HOLD STRESS TESTS", S["h3"]))
    hold_stress_rows = [
        ["Scenario", "Yr-1 Cash Flow", "Pass?"],
        ["Rent −5%",    fmt(d.stress_hold_rent5) + "/yr",  "✔" if d.stress_hold_rent5 >= 0 else "✘"],
        ["Vacancy +2pts",fmt(d.stress_hold_vac2) + "/yr",  "✔" if d.stress_hold_vac2  >= 0 else "✘"],
        ["Tax +12.5%",  fmt(d.stress_hold_tax15) + "/yr",  "✔" if d.stress_hold_tax15 >= 0 else "✘"],
        ["Ins. +20%",   fmt(d.stress_hold_ins20) + "/yr",  "✔" if d.stress_hold_ins20 >= 0 else "✘"],
    ]
    hst = Table(hold_stress_rows, colWidths=[fin_right * 0.48, fin_right * 0.36, fin_right * 0.16])
    hst_style = [
        ("BACKGROUND",  (0, 0), (-1, 0),  CHARCOAL),
        ("TEXTCOLOR",   (0, 0), (-1, 0),  WHITE),
        ("FONTNAME",    (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTNAME",    (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE",    (0, 0), (-1, -1), 7.5),
        ("TOPPADDING",  (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING",(0,0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING",(0, 0), (-1, -1), 4),
        ("ALIGN",       (1, 0), (-1, -1), "RIGHT"),
        ("ROWBACKGROUNDS",(0,1),(-1,-1),  [WHITE, GRAY_LIGHT]),
        ("BOX",         (0, 0), (-1, -1), 0.5, GRAY_LINE),
    ]
    for i, row in enumerate(hold_stress_rows[1:], 1):
        ok = row[2] == "✔"
        hst_style.append(("TEXTCOLOR", (2, i), (2, i), GREEN_OK if ok else RED_BAD))
        hst_style.append(("FONTNAME",  (2, i), (2, i), "Helvetica-Bold"))
        if not ok:
            hst_style.append(("TEXTCOLOR", (1, i), (1, i), RED_BAD))
    hst.setStyle(TableStyle(hst_style))
    rent_section.append(hst)

    fin_tbl = Table(
        [[flip_section, Spacer(fin_gap, 1), rent_section]],
        colWidths=[fin_left, fin_gap, fin_right]
    )
    fin_tbl.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(fin_tbl)
    story.append(Spacer(1, 0.1 * inch))

    # ── Neighborhood section ──────────────────────────────────────────────────
    story.append(HRFlowable(width="100%", thickness=1, color=ORANGE, spaceAfter=4))
    story.append(Paragraph("NEIGHBORHOOD — SCHOOLS & CRIME", S["h3"]))

    school_bar_w = 1.4 * inch
    crime_bar_h  = 0.11 * inch

    nbhd_data = [
        [
            Paragraph("School District", S["label"]),
            Paragraph("PA District Rank", S["label"]),
            Paragraph(f"Elementary  {d.elem_rating}/10", S["label"]),
            Paragraph(f"High School  {d.hs_rating}/10", S["label"]),
            Paragraph("Crime Grade", S["label"]),
            Paragraph("Safety Index", S["label"]),
            Paragraph("Violent /1k", S["label"]),
            Paragraph("Property /1k", S["label"]),
        ],
        [
            Paragraph(d.school_district, S["body"]),
            Paragraph(d.district_rank_pct, S["small"]),
            stat_bar(d.elem_rating, 10, GREEN_OK if d.elem_rating >= 7 else ORANGE,
                     width=school_bar_w, height=crime_bar_h),
            stat_bar(d.hs_rating, 10, GREEN_OK if d.hs_rating >= 7 else ORANGE,
                     width=school_bar_w, height=crime_bar_h),
            Paragraph(
                f'<font color="{"#27AE60" if d.crime_index >= 40 else "#E74C3C" if d.crime_index < 20 else "#F39C12"}">'
                f'<b>{d.crime_grade}</b></font>',
                ParagraphStyle("cg", fontSize=11, fontName="Helvetica-Bold",
                               alignment=TA_CENTER)
            ),
            stat_bar(d.crime_index, 100,
                     GREEN_OK if d.crime_index >= 40 else (ORANGE if d.crime_index >= 20 else RED_BAD),
                     width=school_bar_w, height=crime_bar_h),
            Paragraph(f"{d.violent_per_1k:.2f}", S["body"]),
            Paragraph(f"{d.property_per_1k:.1f}", S["body"]),
        ],
    ]
    nbhd_col_w = [1.2, 1.35, 1.0, 1.0, 0.7, 1.0, 0.65, 0.8]
    nbhd_col_w = [c * inch for c in nbhd_col_w]
    nt = Table(nbhd_data, colWidths=nbhd_col_w)
    nt.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, 0),  ORANGE_TINT),
        ("FONTNAME",     (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",     (0, 0), (-1, 0),  7),
        ("TOPPADDING",   (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
        ("LEFTPADDING",  (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
        ("BOX",          (0, 0), (-1, -1), 0.5, ORANGE),
        ("INNERGRID",    (0, 0), (-1, -1), 0.3, GRAY_LINE),
    ]))
    story.append(nt)
    story.append(Spacer(1, 0.04 * inch))
    story.append(Paragraph(
        f"Crime note: {d.crime_note}  |  US avg: violent 4.0/1k · property 18.0/1k",
        S["note"]
    ))
    story.append(Spacer(1, 0.08 * inch))

    # ── Red flags + recommendation ────────────────────────────────────────────
    story.append(HRFlowable(width="100%", thickness=1, color=ORANGE, spaceAfter=4))

    flags_left  = CONTENT_W * 0.55
    strat_right = CONTENT_W * 0.42
    strat_gap   = CONTENT_W * 0.03

    flag_items = []
    flag_items.append(Paragraph("RED FLAGS", S["h3"]))
    if d.red_flags:
        for flag in d.red_flags:
            flag_items.append(Paragraph(f"⚠  {flag}", S["flag"]))
    else:
        flag_items.append(Paragraph("✔  No critical red flags identified.",
                                     ParagraphStyle("nf", fontSize=8, fontName="Helvetica",
                                                    textColor=GREEN_OK, leftIndent=8)))

    strat_items = []
    strat_items.append(Paragraph("RECOMMENDATION", S["h3"]))
    strat_data = [[Paragraph(d.strategy,
                             ParagraphStyle("strat", fontSize=8, leading=12,
                                            fontName="Helvetica-Bold",
                                            textColor=WHITE))]]
    st_tbl = Table(strat_data, colWidths=[strat_right])
    st_tbl.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, -1), verdict_color),
        ("TOPPADDING",   (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 8),
        ("LEFTPADDING",  (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("ROUNDEDCORNERS", [6]),
    ]))
    strat_items.append(st_tbl)

    # Appreciation outlook
    v5  = d.fmv * ((1 + 0.035) ** 5)
    v10 = d.fmv * ((1 + 0.035) ** 10)
    strat_items.append(Spacer(1, 0.06 * inch))
    strat_items.append(Paragraph("APPRECIATION OUTLOOK", S["h3"]))
    appr_rows = [
        ["5-Yr Est. Value",  fmt(v5)],
        ["10-Yr Est. Value", fmt(v10)],
        ["5-Yr Equity",      fmt(d.hold_5yr_equity)],
        ["10-Yr Equity",     fmt(d.hold_10yr_equity)],
        ["Cumul. NOI 5yr",   fmt(d.annual_noi * 5)],
        ["Cumul. NOI 10yr",  fmt(d.annual_noi * 10)],
    ]
    at = Table(appr_rows, colWidths=[strat_right * 0.58, strat_right * 0.42])
    at.setStyle(TableStyle([
        ("FONTNAME",    (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE",    (0, 0), (-1, -1), 7.5),
        ("TOPPADDING",  (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING",(0,0), (-1, -1), 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING",(0, 0), (-1, -1), 4),
        ("ALIGN",       (1, 0), (1, -1),  "RIGHT"),
        ("ROWBACKGROUNDS",(0,0),(-1,-1),  [WHITE, GRAY_LIGHT]),
        ("BOX",         (0, 0), (-1, -1), 0.5, GRAY_LINE),
    ]))
    strat_items.append(at)

    bottom_tbl = Table(
        [[flag_items, Spacer(strat_gap, 1), strat_items]],
        colWidths=[flags_left, strat_gap, strat_right]
    )
    bottom_tbl.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(bottom_tbl)
    story.append(PageBreak())
    return story


# ─── Glossary page ────────────────────────────────────────────────────────────

GLOSSARY = [
    # ── Property Basics ────────────────────────────────────────────────────────
    ("PROPERTY BASICS", None),
    ("Address",
     "The street address of the property being analyzed."),
    ("Municipality",
     "The city, borough, or township where the property sits — "
     "matters for taxes and local laws."),
    ("Parcel / Parcel ID",
     "The government's unique ID number for a piece of land — like a "
     "social security number for the property."),
    ("sqft",
     "Square feet. How big the property is inside."),
    ("BR / BA",
     "Bedrooms / Bathrooms. How many sleeping rooms and bathrooms "
     "the property has."),
    ("Year Built",
     "The year the house was constructed. Older homes (pre-1950) "
     "often have bigger repair surprises."),
    ("Case / Sale ID",
     "The court case number and auction reference ID assigned to "
     "this property by the Sheriff's office."),

    # ── Auction & Pricing ──────────────────────────────────────────────────────
    ("AUCTION & PRICING", None),
    ("Sheriff Sale",
     "A court-ordered auction where properties with unpaid debts "
     "(taxes, mortgage) are sold to the public, usually at a discount."),
    ("F&C (Foreclosure & Claims)",
     "The legal process that leads to a Sheriff Sale — the bank or "
     "government takes back the property because the owner stopped paying."),
    ("Min Bid",
     "Minimum Bid. The lowest amount the auctioneer will accept. "
     "You cannot buy the property for less than this."),
    ("FMV",
     "Fair Market Value. What the county assessor thinks the property "
     "is worth right now, as-is. Think of it as the 'book value.'"),
    ("ARV",
     "After-Repair Value. What the property will be worth AFTER you "
     "fix it up and bring it to top condition. This is your target "
     "sale price if you flip it."),
    ("MAO / Precise MAO",
     "Maximum Allowable Offer. The absolute most you should pay so "
     "that the deal still makes money. If the auction goes above "
     "this number, walk away."),
    ("70% Rule Max Bid",
     "A quick-and-dirty shortcut: pay no more than 70% of ARV minus "
     "repair costs. Used by many flippers as a safety guardrail."),

    # ── Deal Ratings ───────────────────────────────────────────────────────────
    ("DEAL RATINGS", None),
    ("Score",
     "A 0–100 number we calculate that grades the overall quality of "
     "the deal. Higher = better. Think of it like a grade in school."),
    ("Verdict",
     "Our bottom-line recommendation: BUY (go for it), CONSIDER "
     "(worth a closer look), WATCH (not ready yet), or NO BUY (skip it)."),
    ("PERFECT / PASS / MARGINAL / AVOID",
     "A second rating from the 'Perfect vs. Pass' framework: "
     "PERFECT = hits every target, PASS = meets minimum bars, "
     "MARGINAL = borderline, AVOID = too risky."),

    # ── Flip (Fix & Sell) Metrics ──────────────────────────────────────────────
    ("FLIP (FIX & SELL) METRICS", None),
    ("Flip Profit / Flip Net Profit",
     "The money left in your pocket after you buy, fix, and sell the "
     "property — after ALL costs are paid. If it's negative, you lose money."),
    ("Total All-In Cost",
     "Every dollar you spend: purchase price + repairs + "
     "contingency + carrying costs + closing fees."),
    ("Repair Est.",
     "Estimated cost to fix the property up to sellable condition."),
    ("Contingency (5%)",
     "A 5% buffer added on top of repair costs. Renovations always "
     "surprise you — this cushion absorbs those surprises."),
    ("Carrying Costs",
     "The bills you keep paying while you own and fix the property "
     "— mortgage interest, utilities, insurance, taxes — before you "
     "can sell it."),
    ("Net Sale Proceeds",
     "What you actually pocket from the sale after paying the real "
     "estate agent, transfer taxes, and closing fees (≈ 8% of ARV)."),
    ("Project ROI",
     "Return on Investment. If you made $20,000 on a $100,000 "
     "investment, your ROI is 20%. Higher is better."),
    ("Annualized IRR",
     "Internal Rate of Return, adjusted for time. If you flip a "
     "house in 6 months and make 20% ROI, your annualized IRR is "
     "higher than 20% because you did it in half a year. A quick "
     "flip with the same profit beats a slow one."),
    ("DOM",
     "Days on Market. How long it takes to sell after listing. "
     "Longer = more carrying costs eating into your profit."),

    # ── Flip Stress Tests ──────────────────────────────────────────────────────
    ("FLIP STRESS TESTS", None),
    ("ARV −5% / ARV −8%",
     "What if the market dips and your sale price is 5% or 8% lower "
     "than expected? Does the deal still make money?"),
    ("Rehab +$10/sqft",
     "What if repairs cost $10 more per square foot than estimated? "
     "(Very common.) Does it still work?"),
    ("DOM +30 days",
     "What if it takes 30 extra days to sell? That's 30 more days "
     "of mortgage, taxes, and insurance. Does profit survive?"),

    # ── Rental / Hold Metrics ──────────────────────────────────────────────────
    ("RENTAL / HOLD METRICS", None),
    ("Gross Potential Rent",
     "The maximum rent you COULD collect in a year if the property "
     "was rented 100% of the time at full market rate. "
     "Best-case scenario — reality is always a bit less."),
    ("EGI",
     "Effective Gross Income. Gross rent minus the money lost when "
     "the unit sits empty between tenants (vacancy). "
     "A more realistic income number."),
    ("Vacancy",
     "The percentage of time the property is expected to be empty "
     "with no rent coming in. We use 8% as our baseline."),
    ("NOI",
     "Net Operating Income. Rental income after paying all property "
     "expenses (taxes, insurance, repairs, management) but BEFORE "
     "paying your mortgage. The 'profit before debt.'"),
    ("Mo. NOI / Monthly NOI",
     "Net Operating Income broken down per month. Easier to compare "
     "to your monthly mortgage payment."),
    ("Operating Expenses / Op-Ex Ratio",
     "All the costs to run the property — taxes, insurance, "
     "maintenance, management fees — shown as a percentage of EGI. "
     "Typically 35–55% for most rentals."),
    ("Cap Rate / Cap%",
     "Capitalization Rate. NOI divided by the purchase price, shown "
     "as a percentage. Think of it as the property's 'interest rate' "
     "if you paid all cash. 8%+ = good, below 5% = poor."),
    ("GRM",
     "Gross Rent Multiplier. Purchase price divided by annual gross "
     "rent. Lower = better deal. Think of it as 'how many years of "
     "rent does it take to pay back the purchase price?' Under 10x "
     "is generally strong."),
    ("1% Rule",
     "A quick test: if monthly rent is at least 1% of the purchase "
     "price, the property is likely cash-flow positive. "
     "Example: $100k house should rent for $1,000+/month."),
    ("Year-1 Cash Flow",
     "The actual dollars left over after paying ALL expenses AND the "
     "mortgage in the first year. Positive = the property pays you. "
     "Negative = you subsidize it from your own pocket."),

    # ── Leverage & Financing ───────────────────────────────────────────────────
    ("LEVERAGE & FINANCING", None),
    ("LTV",
     "Loan-to-Value. The percentage of the property's value covered "
     "by a loan. 75% LTV means you borrow 75% and put 25% down "
     "in cash."),
    ("Loan Amount",
     "The mortgage balance — how much money you borrow from the bank."),
    ("Annual Debt Service",
     "The total of all 12 monthly mortgage payments in a year. "
     "This is the money that leaves your account to pay the bank."),
    ("DSCR",
     "Debt Service Coverage Ratio. NOI divided by debt payments. "
     "1.20x means your property earns $1.20 for every $1.00 of "
     "mortgage — a safety cushion. Below 1.0x = the rent doesn't "
     "cover the mortgage."),
    ("Negative Leverage",
     "When your mortgage rate is higher than your cap rate, borrowing "
     "money actually HURTS your returns. The flag warns you that debt "
     "is working against you, not for you."),
    ("Cash-on-Cash (Levered)",
     "The annual cash return on the actual dollars YOU put in "
     "(down payment + closing costs). If you invested $30k and "
     "pocket $3k/year, your cash-on-cash is 10%."),
    ("Payback Period",
     "How many years before the rental income has paid back your "
     "initial cash investment in full."),

    # ── Hold Stress Tests ──────────────────────────────────────────────────────
    ("HOLD STRESS TESTS", None),
    ("Rent −5%",
     "What if rents drop 5% (market softens)? Does the property "
     "still cash-flow positively?"),
    ("Vacancy +2pts",
     "What if the vacancy rate jumps from 8% to 10%? Does it "
     "still make money?"),
    ("Tax +12.5%",
     "What if the county raises your property taxes by 12.5%? "
     "Still profitable?"),
    ("Ins. +20%",
     "What if your insurance premium jumps 20%? (Very possible "
     "in today's market.) Still OK?"),

    # ── Neighborhood ──────────────────────────────────────────────────────────
    ("NEIGHBORHOOD", None),
    ("School District / School Rating",
     "The public school district serving this address and how it's "
     "rated on a 1–10 scale. Higher-rated schools attract better "
     "tenants and support stronger home values."),
    ("PA District Rank",
     "How the school district ranks among all 685 Pennsylvania "
     "school districts. 'Top 10%' means it's in the top 68 districts "
     "in the whole state."),
    ("Elementary / High School Rating",
     "Individual ratings (1–10) for the elementary school and high "
     "school specifically serving this address."),
    ("Crime Grade",
     "A letter grade (A through F) summarizing overall crime in the "
     "neighborhood. A = very safe, F = very dangerous."),
    ("Safety Index / Crime Index",
     "A score from 1–100 where 100 is the SAFEST possible. "
     "Under 20 = high-crime area, 40–70 = average, 70+ = quite safe."),
    ("Violent /1k",
     "Violent crimes (assault, robbery, etc.) per 1,000 residents "
     "per year. US average is about 4.0. Lower is safer."),
    ("Property /1k",
     "Property crimes (burglary, theft, vandalism) per 1,000 "
     "residents per year. US average is about 18.0. Lower is safer."),

    # ── Appreciation Outlook ───────────────────────────────────────────────────
    ("APPRECIATION OUTLOOK", None),
    ("5-Yr / 10-Yr Est. Value",
     "Our projection of what the property could be worth in 5 or "
     "10 years, assuming 3.5% annual appreciation (Pittsburgh's "
     "historical average)."),
    ("5-Yr / 10-Yr Equity",
     "The dollar amount of equity you'd have built up after 5 or "
     "10 years — from both appreciation AND paying down the mortgage."),
    ("Cumul. NOI",
     "Cumulative Net Operating Income. The total NOI stacked up "
     "over 5 or 10 years — your rental income scorecard over time."),
]


def build_glossary(S: dict) -> list:
    story = []
    story.append(Paragraph("Glossary of Terms", S["h1"]))
    story.append(Paragraph(
        "Plain-English definitions for every abbreviation and metric used in this report.",
        ParagraphStyle("gsub", fontSize=10, leading=14, alignment=TA_CENTER,
                       fontName="Helvetica-Oblique", textColor=GRAY_MID, spaceBefore=2)
    ))
    story.append(Spacer(1, 0.15 * inch))
    story.append(HRFlowable(width="100%", thickness=2, color=ORANGE, spaceAfter=10))

    term_w = CONTENT_W * 0.26
    defn_w = CONTENT_W * 0.74

    # Alternating row background tracker
    row_idx = 0

    for term, defn in GLOSSARY:
        if defn is None:
            # Section header — full-width charcoal banner
            sec_data = [[
                Paragraph(
                    term,
                    ParagraphStyle("gsec", fontSize=8, fontName="Helvetica-Bold",
                                   textColor=WHITE, leading=12)
                )
            ]]
            sec_tbl = Table(sec_data, colWidths=[CONTENT_W])
            sec_tbl.setStyle(TableStyle([
                ("BACKGROUND",   (0, 0), (-1, -1), CHARCOAL),
                ("TOPPADDING",   (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
                ("LEFTPADDING",  (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]))
            story.append(Spacer(1, 0.06 * inch))
            story.append(sec_tbl)
            row_idx = 0
        else:
            bg = WHITE if row_idx % 2 == 0 else GRAY_LIGHT
            row_data = [[
                Paragraph(
                    f"<b>{term}</b>",
                    ParagraphStyle("gterm", fontSize=7.5, fontName="Helvetica-Bold",
                                   textColor=ORANGE_DARK, leading=11)
                ),
                Paragraph(
                    defn,
                    ParagraphStyle("gdef", fontSize=7.5, fontName="Helvetica",
                                   textColor=CHARCOAL, leading=11)
                ),
            ]]
            row_tbl = Table(row_data, colWidths=[term_w, defn_w])
            row_tbl.setStyle(TableStyle([
                ("BACKGROUND",   (0, 0), (-1, -1), bg),
                ("VALIGN",       (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING",   (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
                ("LEFTPADDING",  (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("LINEBELOW",    (0, 0), (-1, -1), 0.3, GRAY_LINE),
            ]))
            story.append(row_tbl)
            row_idx += 1

    story.append(Spacer(1, 0.25 * inch))
    story.append(HRFlowable(width="100%", thickness=1, color=GRAY_LINE, spaceAfter=6))
    story.append(Paragraph(
        "This glossary uses simplified language intended for general audiences. "
        "Consult a licensed real estate professional for investment advice specific to your situation.",
        ParagraphStyle("disc", fontSize=7, fontName="Helvetica-Oblique",
                       textColor=GRAY_MID, alignment=TA_CENTER)
    ))
    return story


# ─── Data Sources page ───────────────────────────────────────────────────────

SOURCES = [
    # (source_name, url_or_location, data_provided, used_for)
    (
        "Allegheny County Sheriff Sale — Official Listing",
        "Allegheny County Sheriff's Office (alleghenycounty.us)",
        "Property address, parcel ID, case number, sale ID, minimum bid, tax-upset bid, "
        "postponement status",
        "Raw auction inputs: every Min Bid, Case #, Sale ID, and postponement flag in the report",
    ),
    (
        "WPRDC — Allegheny County Property Assessments",
        "Western Pennsylvania Regional Data Center (wprdc.org) / Allegheny County Real Estate Portal",
        "Fair Market Value (FMV), assessed value, year built, square footage, bedrooms, "
        "bathrooms, structure style, condition",
        "FMV used as the 'book value' baseline; assessed value drives the annual property-tax "
        "expense estimate; year built, sqft, beds, and baths feed repair-cost and rent estimates",
    ),
    (
        "PublicSchoolReview (2026)",
        "publicschoolreview.com",
        "Per-school ratings on a 1–10 composite scale, PA district rank percentile",
        "Elementary and High School ratings displayed on each property page; PA District Rank "
        "percentile shown in the Neighborhood section",
    ),
    (
        "GreatSchools",
        "greatschools.org",
        "School district composite ratings (1–10), cross-validation of per-school scores",
        "Cross-checked against PublicSchoolReview to derive the district-level school_rating "
        "used in the deal-score neighborhood modifier (+/−8 points)",
    ),
    (
        "AreaVibes",
        "areavibes.com",
        "Crime letter grade (A–F), neighborhood livability scores",
        "Crime Grade displayed on each property page (e.g., 'B-', 'D+', 'F'); used to "
        "confirm direction of NeighborhoodScout crime index",
    ),
    (
        "NeighborhoodScout",
        "neighborhoodscout.com",
        "Crime Safety Index (1–100 scale, 100 = safest), violent crimes per 1,000 residents, "
        "property crimes per 1,000 residents",
        "Crime Index and per-1k crime rates shown in the Neighborhood bar on each property page; "
        "index < 10 triggers the HIGH CRIME red flag; index drives the neighborhood score "
        "modifier (−10 to +5 points)",
    ),
    (
        "OpenStreetMap — Tile Server",
        "tile.openstreetmap.org  (© OpenStreetMap contributors, ODbL license)",
        "Street-map tile images at zoom level 17",
        "Property location maps (3×3 tile grid with red pin) shown on each property page",
    ),
    (
        "\"Real-Estate Investor Decision Rules for Perfect vs Pass\" (2026)",
        "Internal framework PDF (Estella Wilson Properties LLC)",
        "Perfect / Pass / Marginal / Avoid rating system, Precise MAO formula, DSCR thresholds, "
        "mortgage constant (8.19%), stress-test scenarios, red-flag criteria",
        "Core decision engine: verdict (BUY / CONSIDER / WATCH / NO BUY), Perfect/Pass rating, "
        "all red-flag thresholds, and the Precise MAO calculation",
    ),
    (
        "Pittsburgh Metro Rental Market Data (2026)",
        "Local market research — Zillow, Rentometer, Pittsburgh MLS comps",
        "Monthly rent estimates by municipality and bedroom count (2BR/3BR tiers)",
        "Gross Potential Rent → EGI → NOI waterfall; 1% Rule test; GRM; Cap Rate; "
        "all hold-strategy cash-flow figures",
    ),
    (
        "Pittsburgh Historical Appreciation Rate",
        "FHFA House Price Index, Allegheny County deed-transfer records (long-run avg)",
        "3.5% annual appreciation rate for the Pittsburgh metro",
        "5-Year and 10-Year estimated property values and equity projections in the "
        "Appreciation Outlook section of each property page",
    ),
    (
        "Repair Cost Benchmarks — Pittsburgh Older Stock",
        "Local contractor quotes, HomeAdvisor cost data, Pittsburgh-area rehab experience",
        "Cost-per-square-foot by decade of construction (ranges $10–$65/sqft)",
        "Repair Estimate on every property; feeds Total All-In Cost, MAO, flip-profit, "
        "and all four flip stress tests",
    ),
    (
        "Allegheny County Property Tax Rate",
        "Allegheny County / municipality millage schedules (2025–2026)",
        "Blended effective tax rate of ~2.2% of assessed value annually",
        "Annual property-tax expense in the NOI waterfall and the Tax +12.5% hold "
        "stress test",
    ),
    (
        "Current Mortgage Market Rate (April 2026)",
        "Freddie Mac Primary Mortgage Market Survey / major lender rate sheets",
        "30-year fixed rate of 7.25%; derived mortgage constant of 8.19%",
        "Leveraged-hold DSCR, Cash-on-Cash, and Negative Leverage flag; BRRRR / "
        "cash-out refi feasibility check",
    ),
]


def build_sources(S: dict) -> list:
    story = []
    story.append(Paragraph("Data Sources &amp; Methodology", S["h1"]))
    story.append(Paragraph(
        "Every number in this report traces back to one of the sources listed below. "
        "The table shows what each source provided and exactly where that data appears.",
        ParagraphStyle("ssub", fontSize=9.5, leading=14, alignment=TA_CENTER,
                       fontName="Helvetica-Oblique", textColor=GRAY_MID, spaceBefore=2)
    ))
    story.append(Spacer(1, 0.15 * inch))
    story.append(HRFlowable(width="100%", thickness=2, color=ORANGE, spaceAfter=10))

    col_w = [
        CONTENT_W * 0.22,   # Source name
        CONTENT_W * 0.22,   # URL / location
        CONTENT_W * 0.30,   # Data provided
        CONTENT_W * 0.26,   # Used for
    ]

    hdr_style = ParagraphStyle("shdr", fontSize=7.5, fontName="Helvetica-Bold",
                                textColor=WHITE, leading=11)
    hdr_row = [
        Paragraph("Source", hdr_style),
        Paragraph("Where to Find It", hdr_style),
        Paragraph("Data Provided", hdr_style),
        Paragraph("Used For in This Report", hdr_style),
    ]

    name_style = ParagraphStyle("sname", fontSize=7.5, fontName="Helvetica-Bold",
                                 textColor=ORANGE_DARK, leading=11)
    url_style  = ParagraphStyle("surl",  fontSize=7,   fontName="Helvetica-Oblique",
                                 textColor=GRAY_MID,   leading=10)
    body_style = ParagraphStyle("sbody", fontSize=7.5, fontName="Helvetica",
                                 textColor=CHARCOAL,   leading=11)

    rows = [hdr_row]
    for name, url, data, used in SOURCES:
        rows.append([
            Paragraph(name, name_style),
            Paragraph(url,  url_style),
            Paragraph(data, body_style),
            Paragraph(used, body_style),
        ])

    tbl = Table(rows, colWidths=col_w, repeatRows=1)
    tbl_style = [
        ("BACKGROUND",    (0, 0), (-1, 0),  CHARCOAL),
        ("TEXTCOLOR",     (0, 0), (-1, 0),  WHITE),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 5),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 5),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [WHITE, GRAY_LIGHT]),
        ("BOX",           (0, 0), (-1, -1), 0.8, ORANGE),
        ("INNERGRID",     (0, 0), (-1, -1), 0.3, GRAY_LINE),
    ]
    tbl.setStyle(TableStyle(tbl_style))
    story.append(tbl)

    story.append(Spacer(1, 0.2 * inch))
    story.append(HRFlowable(width="100%", thickness=1, color=GRAY_LINE, spaceAfter=6))

    # Methodology note
    story.append(Paragraph("Analytical Methodology", S["h2"]))
    story.append(Spacer(1, 0.04 * inch))

    method_rows = [
        ("All-cash purchase assumption",
         "Every analysis assumes you pay the full minimum bid in cash — no financing at auction. "
         "The leveraged-hold section (DSCR, Cash-on-Cash) is a hypothetical post-purchase "
         "BRRRR / cash-out refinance scenario, not a condition of the auction."),
        ("ARV calculation",
         "After-Repair Value = FMV × 1.10 for properties under $80k, or FMV × 1.07 for "
         "properties $80k and above. This conservatively assumes a well-renovated property "
         "commands a 7–10% premium over current assessed FMV."),
        ("Repair cost estimation",
         "Cost per square foot is pulled from the decade-of-construction table ($10–$65/sqft) "
         "and multiplied by sqft × 0.85 (not every room requires full rehabilitation). "
         "A 5% contingency is added on top."),
        ("Rent estimation",
         "Monthly rent is pulled from a municipality-tier table (2BR/3BR) derived from "
         "Zillow/Rentometer comps for each Allegheny County sub-market. "
         "Rents for 4BR+ properties are capped at the 3BR rate."),
        ("NOI waterfall",
         "Gross Potential Rent → Effective Gross Income (−8% vacancy) → Annual NOI "
         "(−management 9%, −maintenance 1% of all-in, −property tax 2.2%, −insurance $1,400). "
         "Year-1 Cash Flow = NOI − $900 capital reserve."),
        ("Deal score (0–100)",
         "Composite of: equity-steal ratio (up to 40 pts), flip profitability (up to 20 pts), "
         "flip stress results (±10 pts), cap rate (up to 18 pts), DSCR quality (±10 pts), "
         "hold stress (±8 pts), negative leverage (−12), MAO compliance (up to 10 pts), "
         "age/condition (up to −12), GRM (±5), and neighborhood modifier (−15 to +10)."),
        ("Appreciation outlook",
         "Uses Pittsburgh's historical 3.5% annual appreciation rate (FHFA HPI long-run). "
         "Projections are illustrative only — actual appreciation varies by neighborhood "
         "and market conditions."),
    ]

    mrow_w = [CONTENT_W * 0.28, CONTENT_W * 0.72]
    mname_s = ParagraphStyle("mname", fontSize=7.5, fontName="Helvetica-Bold",
                               textColor=ORANGE_DARK, leading=11)
    mbody_s = ParagraphStyle("mbody", fontSize=7.5, fontName="Helvetica",
                               textColor=CHARCOAL, leading=11)

    for idx, (label, text) in enumerate(method_rows):
        bg = WHITE if idx % 2 == 0 else GRAY_LIGHT
        mrow = Table(
            [[Paragraph(label, mname_s), Paragraph(text, mbody_s)]],
            colWidths=mrow_w,
        )
        mrow.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), bg),
            ("VALIGN",        (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING",    (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING",   (0, 0), (-1, -1), 6),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
            ("LINEBELOW",     (0, 0), (-1, -1), 0.3, GRAY_LINE),
        ]))
        story.append(mrow)

    story.append(Spacer(1, 0.15 * inch))
    story.append(Paragraph(
        "Market constants (vacancy rate, insurance, maintenance reserve, contingency, "
        "closing-cost percentages, mortgage rate) reflect Pittsburgh-metro underwriting "
        "standards as of Q1 2026 and are updated annually. "
        "All analysis is for informational purposes only and does not constitute investment advice. "
        "Consult a licensed real estate professional before bidding.",
        ParagraphStyle("disc2", fontSize=7, fontName="Helvetica-Oblique",
                       textColor=GRAY_MID, alignment=TA_CENTER)
    ))
    return story


# ─── Shared PDF builder (used by both main() and spot_check.py) ──────────────

def build_and_save_pdf(
    deals: list,
    output_path: Path,
    geocache_extra: dict = None,
    report_title: str = None,
    footer_label: str = None,
    subtitle: str = None,
    cover_note: str = None,
    progress_cb=None,
) -> Path:
    """
    Build and write the branded PDF for any list of analyzed Deal objects.

    Parameters
    ----------
    deals           : list of analyzed Deal objects (already run through analyze())
    output_path     : destination .pdf path
    geocache_extra  : {sale_id: (lat, lon)} entries to merge into GEOCACHE for map tiles
    report_title    : text shown centered in the orange header bar
    footer_label    : text shown in the page footer (e.g. "Allegheny County Sheriff Sale")
    subtitle        : date/context line on the cover page
    cover_note      : italic note below the leaderboard; pass "" to suppress
    progress_cb     : optional callable(current, total, phase) for progress reporting
                      phase is one of: "property", "render", "save"
    """
    if geocache_extra:
        GEOCACHE.update(geocache_extra)

    _title        = report_title or _DEFAULT_REPORT_TITLE
    _footer       = footer_label or _DEFAULT_FOOTER_LABEL
    S             = make_styles()

    doc = BaseDocTemplate(
        str(output_path),
        pagesize=letter,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=0.60 * inch,
        bottomMargin=0.42 * inch,
        title=_title,
        author="Estella Wilson Properties LLC",
        subject=_title,
        creator="EWP Investment Analyzer",
    )
    frame = Frame(
        MARGIN, 0.42 * inch,
        CONTENT_W, PAGE_H - 0.42 * inch - 0.60 * inch,
        leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0,
    )
    doc.addPageTemplates([PageTemplate(id="main", frames=[frame],
                                       onPage=lambda c, d: None)])

    story = []
    story += build_cover(deals, S, subtitle=subtitle, cover_note=cover_note)

    total = len(deals)
    for i, deal in enumerate(deals, 1):
        if progress_cb:
            progress_cb(i, total, "property")
        print(f"  [{i}/{total}] Building page: {deal.address[:45]}")
        story += build_property_page(deal, S)

    print("  Building glossary…")
    story += build_glossary(S)

    print("  Building data sources page…")
    story += build_sources(S)

    if progress_cb:
        progress_cb(0, total, "render")
    print(f"\nRendering PDF → {output_path}")
    doc.build(
        story,
        canvasmaker=lambda fn, **kw: BrandedCanvas(
            fn, pagesize=letter,
            logo_path=str(LOGO_PATH),
            report_title=_title,
            footer_label=_footer,
        ),
    )
    if progress_cb:
        progress_cb(0, total, "save")
    print(f"Done. Saved to: {output_path}")
    return output_path


# ─── Main (sheriff sale batch mode) ──────────────────────────────────────────

def main():
    print("Loading deal data…")
    deals = load_deals_from_json(DATA_FILE)
    deals = sorted(deals, key=lambda d: d.score, reverse=True)
    print(f"  {len(deals)} properties loaded.")

    timestamp  = datetime.now().strftime("%m%d%Y-%H%M")
    output_pdf = Path(__file__).parent / f"Estella_Wilson_Sheriff_Sale_Report_{timestamp}.pdf"

    build_and_save_pdf(deals, output_pdf)


if __name__ == "__main__":
    main()
