#!/usr/bin/env python3
"""
Real Estate Investment Analyzer — Allegheny County Sheriff Sale
Evaluates each Free & Clear property using professional investment frameworks:
  - BUY / NO BUY decision with "Perfect vs Pass vs Avoid" rating
  - FLIP vs RENT vs HOLD analysis
  - Stress testing: ARV down, rehab overrun, DOM longer, rent down, vacancy up
  - Precise MAO formula (not just the 70% shortcut)
  - DSCR, annualized IRR, payback period, negative leverage test
  - EGI → NOI waterfall with explicit reserves
  - Red flag detection for deal-killers

  Framework source: "Real-Estate Investor Decision Rules for Perfect vs Pass"
"""

import json
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path

try:
    from tabulate import tabulate
    HAS_TABULATE = True
except ImportError:
    HAS_TABULATE = False

# ─── Market Constants (Pittsburgh Metro, 2026) ────────────────────────────────

APPRECIATION_RATE    = 0.035   # 3.5% annual (Pittsburgh historical avg)
PROPERTY_TAX_RATE    = 0.022   # ~2.2% of assessed value annually
INSURANCE_ANNUAL     = 1_400   # base annual landlord insurance
VACANCY_RATE         = 0.08    # 8% (Pittsburgh: 7–8% per underwriting standard)
MGMT_RATE            = 0.09    # 9% of EGI
MAINTENANCE_RATE     = 0.01    # 1% of all-in cost/year
RESERVE_ANNUAL       = 900     # capital reserve (separate from maintenance; ~$75/mo)
CLOSING_BUY_PCT      = 0.03    # 3% purchase closing costs
CLOSING_SELL_PCT     = 0.08    # 8% selling costs (agent + transfer tax + concessions)
HOLDING_MONTHS_FLIP  = 6       # months to complete and sell a flip
HOLDING_COST_MONTH   = 400     # utilities + taxes + insurance per month while flipping
CONTINGENCY_PCT      = 0.05    # 5% of rehab as contingency (Pittsburgh older stock)
TARGET_PROFIT_FLIP   = 25_000  # minimum target profit included in MAO calculation

# Negative leverage threshold: at 7.25% rate, 30-yr amort, mortgage constant ≈ 8.19%.
# If cap rate < this, leverage HURTS cash-on-cash return.
MORTGAGE_CONSTANT    = 8.19    # percent — source: PDF p.5

# Leveraged hold assumptions (DSCR / CoC with financing — sheriff sale is all-cash,
# but BRRRR investors need to know if a cash-out refi will pencil)
LTV                  = 0.75    # 75% loan-to-value
INTEREST_RATE        = 0.0725  # 7.25% mortgage rate
AMORT_MONTHS         = 360     # 30-year amortization
_r = INTEREST_RATE / 12
MONTHLY_MORTGAGE_FACTOR = _r / (1 - (1 + _r) ** -AMORT_MONTHS)  # ≈ 0.006824

# ─── Neighborhood Intelligence (schools + crime) ─────────────────────────────
# Sources: PublicSchoolReview 2026, GreatSchools, AreaVibes, NeighborhoodScout
# Crime index: 1–100 scale where 100 = safest (NeighborhoodScout / AreaVibes)
# School rating: 1–10 composite (district avg from PublicSchoolReview / GreatSchools)
# Update these as new data becomes available each year.

NEIGHBORHOOD = {
    # municipality: {
    #   "school_rating": float,       # avg district rating /10
    #   "school_district": str,
    #   "elem_rating": float,         # elementary /10
    #   "hs_rating": float,           # high school /10
    #   "district_rank_pct": str,     # percentile rank in PA
    #   "crime_index": int,           # 1–100, 100 = safest
    #   "violent_per_1k": float,      # violent crimes per 1,000 residents
    #   "property_per_1k": float,     # property crimes per 1,000 residents
    #   "crime_grade": str,           # letter grade summary
    #   "crime_note": str,            # key investor takeaway
    # }
    "Verona": {
        "school_rating":    7.7,
        "school_district":  "Riverview SD",
        "elem_rating":      8.0,   # Verner El: 8/10 (PublicSchoolReview 2026)
        "hs_rating":        7.0,   # Riverview Jr/Sr HS: 7/10
        "district_rank_pct":"Top 10% in PA (#62 of 685)",
        "crime_index":      6,     # NeighborhoodScout — safer than 6% of US cities
        "violent_per_1k":   0.83,  # well below PA avg (2.46) and US avg (4.0)
        "property_per_1k":  33.29, # nearly 2× national avg (18/1k) — theft primary driver
        "crime_grade":      "B-",  # AreaVibes: low violent, HIGH property crime
        "crime_note":       "Very low violent crime; property crime 2× national avg (theft-driven)",
    },
    "Pittsburgh": {
        "school_rating":    4.0,
        "school_district":  "Pittsburgh Public Schools",
        "elem_rating":      4.0,
        "hs_rating":        4.0,
        "district_rank_pct":"Below average (varies widely by neighborhood)",
        "crime_index":      5,
        "violent_per_1k":   9.5,
        "property_per_1k":  38.0,
        "crime_grade":      "D+",
        "crime_note":       "High crime city overall; varies significantly block by block",
    },
    "Millvale": {
        "school_rating":    6.0,
        "school_district":  "Shaler Area SD",
        "elem_rating":      6.0,
        "hs_rating":        6.0,
        "district_rank_pct":"Average",
        "crime_index":      18,
        "violent_per_1k":   3.5,
        "property_per_1k":  20.0,
        "crime_grade":      "C+",
        "crime_note":       "Moderate crime; improving neighborhood near Pittsburgh",
    },
    "Wilkinsburg": {
        "school_rating":    2.0,
        "school_district":  "Wilkinsburg SD",
        "elem_rating":      2.0,
        "hs_rating":        2.0,
        "district_rank_pct":"Bottom 10% in PA",
        "crime_index":      3,
        "violent_per_1k":   18.5,
        "property_per_1k":  45.0,
        "crime_grade":      "F",
        "crime_note":       "Very high violent and property crime; significant landlord risk",
    },
    "Munhall": {
        "school_rating":    5.5,
        "school_district":  "Steel Valley SD",
        "elem_rating":      5.5,
        "hs_rating":        5.5,
        "district_rank_pct":"Average",
        "crime_index":      22,
        "violent_per_1k":   4.2,
        "property_per_1k":  22.0,
        "crime_grade":      "C",
        "crime_note":       "Average crime; stable working-class area",
    },
    "Elizabeth Twp": {
        "school_rating":    6.5,
        "school_district":  "Elizabeth Forward SD",
        "elem_rating":      6.5,
        "hs_rating":        6.5,
        "district_rank_pct":"Above average",
        "crime_index":      45,
        "violent_per_1k":   1.8,
        "property_per_1k":  12.0,
        "crime_grade":      "B+",
        "crime_note":       "Low crime rural/suburban area; good for long-term hold",
    },
    "Elizabeth Boro": {
        "school_rating":    6.5,
        "school_district":  "Elizabeth Forward SD",
        "elem_rating":      6.5,
        "hs_rating":        6.5,
        "district_rank_pct":"Above average",
        "crime_index":      38,
        "violent_per_1k":   2.1,
        "property_per_1k":  14.0,
        "crime_grade":      "B",
        "crime_note":       "Below-average crime; solid rental market fundamentals",
    },
    "Liberty": {
        "school_rating":    5.0,
        "school_district":  "Cornell SD / Steel Valley SD",
        "elem_rating":      5.0,
        "hs_rating":        5.0,
        "district_rank_pct":"Average",
        "crime_index":      15,
        "violent_per_1k":   5.8,
        "property_per_1k":  28.0,
        "crime_grade":      "C-",
        "crime_note":       "Above-average crime; McKeesport-adjacent risk area",
    },
    "North Braddock": {
        # Sources: NeighborhoodScout, AreaVibes, CrimeGrade.org, PublicSchoolReview 2025-26
        "school_rating":    2.5,
        "school_district":  "Woodland Hills SD",
        "elem_rating":      3.0,   # Woodland Hills Intermediate: below avg
        "hs_rating":        2.0,   # Woodland Hills Senior HS: GreatSchools 2/10
        "district_rank_pct":"Bottom 20% in PA (ranked ~#640 of 685)",
        "crime_index":      22,    # NeighborhoodScout/AreaVibes composite; low violent crime
        "violent_per_1k":   2.5,   # below PA avg (2.46) and US avg (4.0)
        "property_per_1k":  22.0,  # slightly above national avg (18.0)
        "crime_grade":      "C-",  # AreaVibes grade; adjacent to Braddock (one of PA's highest-crime)
        "crime_note":       "Low violent crime for the area but high property crime; immediately adjacent to Braddock Borough (very high crime) — verify block conditions",
    },
    "default": {
        "school_rating":    5.0,
        "school_district":  "Unknown — verify",
        "elem_rating":      5.0,
        "hs_rating":        5.0,
        "district_rank_pct":"Unknown",
        "crime_index":      25,
        "violent_per_1k":   4.0,
        "property_per_1k":  18.0,
        "crime_grade":      "C",
        "crime_note":       "No neighborhood data — research before committing",
    },
}

def get_neighborhood(municipality: str) -> dict:
    return NEIGHBORHOOD.get(municipality, NEIGHBORHOOD["default"])


# ─── Neighborhood score modifier for deal scoring ─────────────────────────────
def neighborhood_score_modifier(nbhd: dict) -> int:
    """Return a score delta (-15 to +10) based on school rating and crime index."""
    pts = 0
    sr = nbhd["school_rating"]
    if   sr >= 8:  pts += 5
    elif sr >= 6:  pts += 2
    elif sr < 4:   pts -= 8
    ci = nbhd["crime_index"]
    if   ci >= 50: pts += 5
    elif ci >= 30: pts += 2
    elif ci < 10:  pts -= 10
    elif ci < 20:  pts -= 5
    return pts


# ─── Pittsburgh area rent estimates (2BR/3BR base by municipality tier) ────────
RENT_BASE = {
    "2BR": {
        "Pittsburgh":      1_150,
        "Millvale":          950,
        "Verona":            975,
        "Wilkinsburg":       925,
        "Munhall":           875,
        "Elizabeth Twp":     775,
        "Elizabeth Boro":    800,
        "Liberty":           750,
        "North Braddock":    875,   # Zillow/Rentometer comps; below Wilkinsburg due to school/crime drag
        "default":           875,
    },
    "3BR": {
        "Pittsburgh":      1_350,
        "Millvale":        1_100,
        "Verona":          1_100,
        "Wilkinsburg":     1_050,
        "Munhall":           950,
        "Elizabeth Twp":     875,
        "Elizabeth Boro":    900,
        "Liberty":           850,
        "North Braddock":    975,   # Zillow/Rentometer comps for 15104 zip
        "default":         1_000,
    },
}

# Repair cost per sqft by decade of construction (conservative Pittsburgh estimates)
REPAIR_COST_PSF = {
    1880: 65,   # full gut; historical structure
    1900: 58,
    1910: 52,
    1920: 48,
    1930: 42,
    1940: 36,
    1950: 28,
    1960: 22,
    1970: 18,
    1980: 14,
    1990: 10,
}

# ─── Data ─────────────────────────────────────────────────────────────────────

@dataclass
class Deal:
    # ── Inputs ────────────────────────────────────────────────────────────────
    sale_id:      str
    case:         str
    address:      str
    municipality: str
    parcel:       str
    min_bid:      float
    tax_bid:      float
    fmv:          float
    assessed:     float
    year_built:   int
    sqft:         int
    bedrooms:     int
    fullbaths:    int   = 1
    stories:      float = 1.5
    condition:    str   = "Average"
    style:        str   = ""
    postponed:    bool  = False

    # ── Flip outputs ──────────────────────────────────────────────────────────
    repair_cost:         float = 0.0
    contingency:         float = 0.0
    arv:                 float = 0.0
    total_all_in:        float = 0.0
    flip_net_profit:     float = 0.0
    flip_roi_pct:        float = 0.0
    flip_irr_pct:        float = 0.0   # annualized IRR for the flip hold period
    precise_mao:         float = 0.0   # MAO via full formula (not just 70% shortcut)
    max_bid_70:          float = 0.0   # simplified 70% rule cap

    # Flip stress tests (all show resulting profit under that scenario)
    stress_flip_arv5:    float = 0.0   # profit if ARV falls 5%
    stress_flip_arv8:    float = 0.0   # profit if ARV falls 8%
    stress_flip_rehab10: float = 0.0   # profit if rehab costs +$10/sqft
    stress_flip_dom30:   float = 0.0   # profit if hold extends +30 days
    flip_stress_passes:  bool  = False  # True only if all stress cases stay positive

    # ── Rental / NOI waterfall ────────────────────────────────────────────────
    gross_potential_rent: float = 0.0  # monthly_rent × 12
    egi:                  float = 0.0  # EGI = GPR × (1 - vacancy)
    monthly_rent:         float = 0.0
    annual_noi:           float = 0.0  # EGI − operating expenses
    monthly_noi:          float = 0.0
    operating_exp_ratio:  float = 0.0  # opex / EGI; Pittsburgh target ≤ 40%
    cap_rate:             float = 0.0  # NOI / all-in cost
    gross_rent_mult:      float = 0.0  # price / gross annual rent
    passes_1pct_rule:     bool  = False
    cash_flow_yr1:        float = 0.0  # NOI − reserve (all-cash, pre-debt)

    # ── Leveraged hold metrics (hypothetical refi / BRRRR scenario) ───────────
    loan_amount:              float = 0.0
    annual_debt_service:      float = 0.0
    dscr:                     float = 0.0   # NOI / debt service
    cash_on_cash_levered:     float = 0.0   # (NOI − reserve − debt) / cash invested
    leveraged_cash_invested:  float = 0.0
    payback_yrs:              float = 0.0   # cash invested / annual leveraged CF

    # Negative leverage flag
    negative_leverage:        bool  = False  # cap rate < 8.19% mortgage constant

    # Hold stress tests (all show annual year-1 cash flow under that scenario)
    stress_hold_rent5:  float = 0.0   # CF if rent −5%
    stress_hold_vac2:   float = 0.0   # CF if vacancy +2 pts
    stress_hold_tax15:  float = 0.0   # CF if taxes +12.5%
    stress_hold_ins20:  float = 0.0   # CF if insurance +20%
    hold_stress_passes: bool  = False  # True if all hold stress CFs ≥ 0

    # ── Hold appreciation projections ─────────────────────────────────────────
    hold_5yr_equity:  float = 0.0
    hold_10yr_equity: float = 0.0

    # ── Neighborhood intelligence ─────────────────────────────────────────────
    school_district:     str   = ""
    school_rating:       float = 0.0   # composite /10
    elem_rating:         float = 0.0
    hs_rating:           float = 0.0
    district_rank_pct:   str   = ""
    crime_index:         int   = 0     # 1–100, 100 = safest
    violent_per_1k:      float = 0.0
    property_per_1k:     float = 0.0
    crime_grade:         str   = ""
    crime_note:          str   = ""

    # ── Decision outputs ──────────────────────────────────────────────────────
    red_flags:           list = field(default_factory=list)
    perfect_pass_rating: str  = ""  # "PERFECT" | "PASS" | "MARGINAL" | "AVOID" | "WATCH"
    verdict:             str  = ""  # "BUY" | "CONSIDER" | "NO BUY" | "WATCH"
    strategy:            str  = ""
    score:               int  = 0


# ─── Analysis Engine ──────────────────────────────────────────────────────────

def repair_cost_psf(year_built: int) -> float:
    decade = (year_built // 10) * 10
    decade = max(1880, min(1990, decade))
    for d in sorted(REPAIR_COST_PSF.keys(), reverse=True):
        if decade >= d:
            return REPAIR_COST_PSF[d]
    return 50.0


def estimate_rent(bedrooms: int, municipality: str) -> float:
    key = f"{bedrooms}BR" if bedrooms <= 3 else "3BR"
    if key not in RENT_BASE:
        key = "3BR"
    m = RENT_BASE[key]
    return m.get(municipality, m["default"])


def _annualized_irr(roi_pct: float, hold_months: float) -> float:
    """Convert simple project ROI to annualized IRR. Formula: (1+ROI)^(12/months) - 1."""
    if hold_months <= 0 or roi_pct <= -100:
        return 0.0
    return round(((1 + roi_pct / 100) ** (12 / hold_months) - 1) * 100, 1)


def _annual_debt_service(loan: float) -> float:
    """Annual P&I on a 7.25%, 30-yr fully amortizing loan."""
    return round(loan * MONTHLY_MORTGAGE_FACTOR * 12)


def analyze(deal: Deal) -> Deal:

    # ── 1. Repair Cost + Contingency ─────────────────────────────────────────
    psf              = repair_cost_psf(deal.year_built)
    deal.repair_cost = round(deal.sqft * psf * 0.85)   # 0.85 = not every room needs full work
    deal.contingency = round(deal.repair_cost * CONTINGENCY_PCT)

    # ── 2. ARV (after-repair value) ───────────────────────────────────────────
    arv_uplift = 1.10 if deal.fmv < 80_000 else 1.07
    deal.arv   = round(deal.fmv * arv_uplift)

    # ── 3. Flip All-In Cost ───────────────────────────────────────────────────
    buy_close       = round(deal.min_bid * CLOSING_BUY_PCT)
    carry_cost      = HOLDING_MONTHS_FLIP * HOLDING_COST_MONTH
    deal.total_all_in = round(
        deal.min_bid + buy_close + deal.repair_cost + deal.contingency + carry_cost
    )

    # ── 4. Precise MAO Formula ────────────────────────────────────────────────
    # MAO = ARV × (1 − sell%) − rehab − contingency − carry − buy_close − target_profit
    deal.precise_mao = round(
        deal.arv * (1 - CLOSING_SELL_PCT)
        - deal.repair_cost
        - deal.contingency
        - carry_cost
        - buy_close
        - TARGET_PROFIT_FLIP
    )
    deal.max_bid_70  = round(0.70 * deal.arv - deal.repair_cost)  # quick-screen shortcut

    # ── 5. Flip Profit + Annualized IRR ──────────────────────────────────────
    sell_net           = round(deal.arv * (1 - CLOSING_SELL_PCT))
    deal.flip_net_profit = round(sell_net - deal.total_all_in)
    deal.flip_roi_pct    = round(deal.flip_net_profit / deal.total_all_in * 100, 1) if deal.total_all_in else 0
    deal.flip_irr_pct    = _annualized_irr(deal.flip_roi_pct, HOLDING_MONTHS_FLIP)

    # ── 6. Flip Stress Tests ──────────────────────────────────────────────────
    def _flip_profit(arv_adj=0.0, extra_rehab=0.0, extra_hold_months=0):
        adj_arv      = deal.arv * (1 + arv_adj)
        adj_sell_net = round(adj_arv * (1 - CLOSING_SELL_PCT))
        adj_all_in   = deal.total_all_in + round(extra_rehab * deal.sqft) + extra_hold_months * HOLDING_COST_MONTH
        return round(adj_sell_net - adj_all_in)

    deal.stress_flip_arv5    = _flip_profit(arv_adj=-0.05)
    deal.stress_flip_arv8    = _flip_profit(arv_adj=-0.08)
    deal.stress_flip_rehab10 = _flip_profit(extra_rehab=10)
    deal.stress_flip_dom30   = _flip_profit(extra_hold_months=1)

    deal.flip_stress_passes = (
        deal.stress_flip_arv5    > 0 and
        deal.stress_flip_rehab10 > 0 and
        deal.stress_flip_dom30   > 0
    )

    # ── 7. Rental NOI Waterfall ───────────────────────────────────────────────
    # Gross Potential Rent → EGI (−vacancy) → EGI − OpEx = NOI → NOI − Reserve = Year-1 CF
    deal.monthly_rent         = estimate_rent(deal.bedrooms, deal.municipality)
    deal.gross_potential_rent = round(deal.monthly_rent * 12)
    deal.egi                  = round(deal.gross_potential_rent * (1 - VACANCY_RATE))

    all_in_rental = round(deal.min_bid * (1 + CLOSING_BUY_PCT) + deal.repair_cost)

    opex_mgmt    = round(deal.egi    * MGMT_RATE)
    opex_maint   = round(all_in_rental * MAINTENANCE_RATE)
    opex_tax     = round(deal.assessed  * PROPERTY_TAX_RATE)
    opex_ins     = INSURANCE_ANNUAL
    total_opex   = opex_mgmt + opex_maint + opex_tax + opex_ins

    deal.annual_noi          = round(deal.egi - total_opex)
    deal.monthly_noi         = round(deal.annual_noi / 12)
    deal.operating_exp_ratio = round(total_opex / deal.egi * 100, 1) if deal.egi else 0.0
    deal.cap_rate            = round(deal.annual_noi / all_in_rental * 100, 1) if all_in_rental else 0.0
    deal.gross_rent_mult     = round(all_in_rental / deal.gross_potential_rent, 2) if deal.gross_potential_rent else 99.0
    deal.passes_1pct_rule    = deal.monthly_rent >= (all_in_rental * 0.01)
    deal.cash_flow_yr1       = round(deal.annual_noi - RESERVE_ANNUAL)

    # ── 8. Leveraged Hold Metrics (BRRRR / cash-out refi scenario) ───────────
    deal.loan_amount             = round(all_in_rental * LTV)
    deal.annual_debt_service     = _annual_debt_service(deal.loan_amount)
    deal.dscr                    = round(deal.annual_noi / deal.annual_debt_service, 2) if deal.annual_debt_service else 0.0

    down_payment                 = all_in_rental - deal.loan_amount
    deal.leveraged_cash_invested = round(down_payment + buy_close)
    levered_cf                   = deal.annual_noi - RESERVE_ANNUAL - deal.annual_debt_service
    deal.cash_on_cash_levered    = round(levered_cf / deal.leveraged_cash_invested * 100, 1) if deal.leveraged_cash_invested else 0.0
    deal.payback_yrs             = round(deal.leveraged_cash_invested / max(levered_cf, 1), 1) if levered_cf > 0 else 999.0

    # Negative leverage: if cap rate < mortgage constant, debt drag > yield
    deal.negative_leverage = deal.cap_rate < MORTGAGE_CONSTANT

    # ── 9. Hold Stress Tests ─────────────────────────────────────────────────
    def _hold_cf(rent_pct=0.0, vac_pts=0.0, tax_pct=0.0, ins_pct=0.0) -> float:
        adj_rent = deal.monthly_rent * (1 + rent_pct)
        adj_egi  = adj_rent * 12 * (1 - (VACANCY_RATE + vac_pts))
        adj_opex = (
            adj_egi * MGMT_RATE
            + all_in_rental * MAINTENANCE_RATE
            + opex_tax * (1 + tax_pct)
            + opex_ins * (1 + ins_pct)
        )
        return round(adj_egi - adj_opex - RESERVE_ANNUAL)

    deal.stress_hold_rent5  = _hold_cf(rent_pct=-0.05)
    deal.stress_hold_vac2   = _hold_cf(vac_pts=0.02)
    deal.stress_hold_tax15  = _hold_cf(tax_pct=0.125)   # midpoint of 10–15% range
    deal.stress_hold_ins20  = _hold_cf(ins_pct=0.20)

    deal.hold_stress_passes = (
        deal.stress_hold_rent5  >= 0 and
        deal.stress_hold_vac2   >= 0 and
        deal.stress_hold_tax15  >= 0
    )

    # ── 10. Hold Appreciation ─────────────────────────────────────────────────
    deal.hold_5yr_equity  = round(deal.fmv * ((1 + APPRECIATION_RATE) **  5) - all_in_rental)
    deal.hold_10yr_equity = round(deal.fmv * ((1 + APPRECIATION_RATE) ** 10) - all_in_rental)

    # ── 11. Neighborhood Intelligence ────────────────────────────────────────
    nbhd = get_neighborhood(deal.municipality)
    deal.school_district   = nbhd["school_district"]
    deal.school_rating     = nbhd["school_rating"]
    deal.elem_rating       = nbhd["elem_rating"]
    deal.hs_rating         = nbhd["hs_rating"]
    deal.district_rank_pct = nbhd["district_rank_pct"]
    deal.crime_index       = nbhd["crime_index"]
    deal.violent_per_1k    = nbhd["violent_per_1k"]
    deal.property_per_1k   = nbhd["property_per_1k"]
    deal.crime_grade       = nbhd["crime_grade"]
    deal.crime_note        = nbhd["crime_note"]

    # ── 12. Red Flag Detection ────────────────────────────────────────────────
    flags = []

    if deal.postponed:
        flags.append("Property postponed — verify active status before bidding")
    if deal.min_bid > deal.precise_mao:
        flags.append(
            f"Bid ${deal.min_bid:,.0f} exceeds precise MAO ${deal.precise_mao:,.0f} "
            f"— no margin-of-safety at this price"
        )
    if deal.flip_net_profit < 0:
        flags.append("Flip is loss-making at current bid (even before stress)")
    elif deal.flip_net_profit < TARGET_PROFIT_FLIP:
        flags.append(
            f"Flip profit ${deal.flip_net_profit:,.0f} below target ${TARGET_PROFIT_FLIP:,.0f} "
            f"— no margin-of-safety buffer"
        )
    if deal.stress_flip_arv5 < 0:
        flags.append("Flip profit wiped out if ARV misses by only 5%")
    if deal.stress_flip_rehab10 < 0:
        flags.append("Flip profit wiped out if rehab runs +$10/sqft over estimate")
    if deal.cash_flow_yr1 < 0:
        flags.append(
            "Negative year-one cash flow (all-cash, after reserve) — "
            "deal requires appreciation to survive"
        )
    if deal.negative_leverage:
        flags.append(
            f"NEGATIVE LEVERAGE — cap rate {deal.cap_rate}% is below the 8.19% mortgage "
            f"constant; adding debt hurts cash-on-cash"
        )
    if 0 < deal.dscr < 1.20:
        flags.append(
            f"DSCR {deal.dscr:.2f}x is below safe minimum (1.20x) — "
            f"NOI does not cover debt service with adequate margin"
        )
    if deal.year_built < 1910:
        flags.append(
            "Pre-1910 construction — high risk of hidden systems failure; "
            "budget as full gut until scopes prove otherwise"
        )
    elif deal.year_built < 1950:
        flags.append(
            "Pre-1950 — Pittsburgh sewer/lateral compliance and dye-test risk; "
            "inspect PGH2O records before bidding"
        )
    if deal.gross_rent_mult > 9.0:
        flags.append(
            f"GRM {deal.gross_rent_mult:.1f}x exceeds Pittsburgh attractive threshold "
            f"(<7 strong, ≤9 workable)"
        )
    if deal.operating_exp_ratio > 45.0:
        flags.append(
            f"Operating expense ratio {deal.operating_exp_ratio}% is high "
            f"(Pittsburgh target ≤40% of EGI)"
        )
    if deal.flip_net_profit < 15_000 and deal.cash_flow_yr1 < 100:
        flags.append(
            "Marginal on BOTH flip and hold — no clear strategy pencils "
            "without aggressive assumptions"
        )
    if deal.crime_index < 10:
        flags.append(
            f"HIGH CRIME area — crime index {deal.crime_index}/100 "
            f"(violent: {deal.violent_per_1k}/1k, property: {deal.property_per_1k}/1k); "
            f"expect higher vacancy, insurance, and tenant turnover"
        )
    if deal.school_rating < 4.0:
        flags.append(
            f"LOW-RATED schools ({deal.school_rating}/10, {deal.school_district}) — "
            f"limits buyer pool on exit and reduces family-renter demand"
        )

    deal.red_flags = flags

    # ── 12. Perfect / Pass / Marginal / Avoid Rating ──────────────────────────
    # A "perfect" deal survives stress tests AND clears all key thresholds.
    # A "pass" deal works only if every assumption goes right.
    # An "avoid" deal fails on multiple critical dimensions.
    critical = [f for f in flags if any(kw in f for kw in [
        "exceeds precise MAO",
        "loss-making",
        "wiped out",
        "Negative year-one",
        "NEGATIVE LEVERAGE",
        "DSCR",
        "Marginal on BOTH",
    ])]

    if deal.postponed:
        deal.perfect_pass_rating = "WATCH"
    elif len(critical) >= 2:
        deal.perfect_pass_rating = "AVOID"
    elif len(critical) == 1:
        deal.perfect_pass_rating = "MARGINAL"
    elif (deal.flip_stress_passes and deal.hold_stress_passes
          and deal.cap_rate >= 7 and not deal.negative_leverage):
        deal.perfect_pass_rating = "PERFECT"
    elif (deal.flip_net_profit >= TARGET_PROFIT_FLIP
          or (deal.cash_flow_yr1 >= 0 and not deal.negative_leverage)):
        deal.perfect_pass_rating = "PASS"
    else:
        deal.perfect_pass_rating = "MARGINAL"

    # ── 13. Deal Score ────────────────────────────────────────────────────────
    score = 0

    if deal.postponed:
        score -= 20

    # Equity steal ratio (up to 40 pts)
    steal_ratio = (deal.fmv - deal.min_bid) / deal.fmv if deal.fmv else 0
    score += int(steal_ratio * 40)

    # Flip profitability
    if   deal.flip_net_profit > 40_000: score += 20
    elif deal.flip_net_profit > 25_000: score += 13
    elif deal.flip_net_profit > 15_000: score +=  7
    elif deal.flip_net_profit <      0: score -= 15

    # Flip survives stress
    if   deal.flip_stress_passes:    score +=  8
    elif deal.stress_flip_arv5 < 0:  score -= 10

    # Cap rate / rental quality
    if   deal.cap_rate >= 9: score += 18
    elif deal.cap_rate >= 7: score += 10
    elif deal.cap_rate >= 5: score +=  4
    elif deal.cap_rate <= 0: score -= 10

    # DSCR quality
    if   deal.dscr >= 1.35:          score +=  8
    elif deal.dscr >= 1.20:          score +=  4
    elif 0 < deal.dscr < 1.10:       score -= 10

    # Hold stress passes
    if   deal.hold_stress_passes:    score +=  6
    elif deal.stress_hold_rent5 < 0: score -=  8

    # Negative leverage penalty
    if deal.negative_leverage:       score -= 12

    # MAO compliance (precise formula vs bid)
    if   deal.min_bid <= deal.precise_mao: score += 10
    elif deal.min_bid <= deal.max_bid_70:  score +=  5

    # Age / condition risk
    if   deal.year_built < 1910: score -= 12
    elif deal.year_built < 1930: score -=  6

    # GRM quality
    if   deal.gross_rent_mult < 7: score +=  5
    elif deal.gross_rent_mult > 9: score -=  3

    # Neighborhood modifier (schools + crime)
    score += neighborhood_score_modifier(nbhd)

    # Perfect/Avoid modifier
    if   deal.perfect_pass_rating == "PERFECT": score +=  5
    elif deal.perfect_pass_rating == "AVOID":   score -= 15

    deal.score = max(0, min(100, score))

    # ── 14. Verdict & Strategy ────────────────────────────────────────────────
    if deal.postponed:
        deal.verdict  = "WATCH"
        deal.strategy = "Postponed — monitor and re-evaluate closer to sale date"

    elif deal.perfect_pass_rating == "AVOID":
        deal.verdict  = "NO BUY"
        top_flags     = "; ".join(flags[:2]) if flags else "Fails multiple critical thresholds"
        deal.strategy = top_flags[:120]

    elif deal.flip_stress_passes and deal.flip_net_profit >= TARGET_PROFIT_FLIP:
        if deal.cap_rate >= 7 and deal.hold_stress_passes and not deal.negative_leverage:
            deal.verdict  = "BUY"
            deal.strategy = (
                "FLIP or BRRRR — strong on both strategies; all stress tests pass. "
                "Confirm sewer/lateral and title before bidding."
            )
        else:
            deal.verdict  = "BUY"
            deal.strategy = (
                "FLIP — solid profit and survives ARV-5% / rehab overrun stress. "
                "Hold metrics weaker; exit via sale."
            )

    elif deal.cap_rate >= 7 and deal.hold_stress_passes and not deal.negative_leverage:
        deal.verdict  = "BUY"
        deal.strategy = (
            "RENT/HOLD — cap rate clears hurdle, DSCR safe, all hold stress tests pass. "
            "Strong keep-and-rent candidate."
        )

    elif deal.flip_net_profit > 15_000 and deal.perfect_pass_rating != "AVOID":
        deal.verdict  = "CONSIDER"
        deal.strategy = (
            "Potential FLIP — confirm ARV with tight sold comps; "
            "inspect sewer/systems and get contractor bids before committing."
        )

    elif deal.cash_flow_yr1 > 0 and not deal.negative_leverage:
        deal.verdict  = "CONSIDER"
        deal.strategy = (
            "Marginal HOLD — positive all-cash year-1 cash flow but does not clear "
            "all stress tests. Needs on-site inspection to confirm condition."
        )

    else:
        deal.verdict  = "NO BUY"
        deal.strategy = (
            "Insufficient margin on both flip and rental; "
            "too many stress-test failures to call this a safe investment."
        )

    return deal


# ─── Report Helpers ───────────────────────────────────────────────────────────

def fmt(v: float, prefix: str = "$") -> str:
    if v is None: return "N/A"
    if v < 0:     return f"-{prefix}{abs(v):,.0f}"
    return f"{prefix}{v:,.0f}"


def _rtag(r: str) -> str:
    return {
        "PERFECT":  "★ PERFECT",
        "PASS":     "✓ PASS",
        "MARGINAL": "~ MARGINAL",
        "AVOID":    "✗ AVOID",
        "WATCH":    "⏳ WATCH",
    }.get(r, r)


# ─── Main Report ──────────────────────────────────────────────────────────────

def print_investment_report(deals: list[Deal]) -> None:
    sorted_deals = sorted(deals, key=lambda d: d.score, reverse=True)

    W = 122
    print("\n" + "═" * W)
    print("  ALLEGHENY COUNTY SHERIFF SALE — FREE & CLEAR INVESTMENT ANALYSIS")
    print("  Date of Sale: May 4, 2026  |  Methodology: All-cash purchase; stress-tested flip & hold")
    print("  Framework: Perfect vs Pass (Real-Estate Investor Decision Rules, 2026)")
    print("═" * W)

    buy_ct     = sum(1 for d in deals if d.verdict == "BUY")
    maybe_ct   = sum(1 for d in deals if d.verdict == "CONSIDER")
    skip_ct    = sum(1 for d in deals if d.verdict == "NO BUY")
    perfect_ct = sum(1 for d in deals if d.perfect_pass_rating == "PERFECT")
    avoid_ct   = sum(1 for d in deals if d.perfect_pass_rating == "AVOID")
    print(
        f"\n  Properties: {len(deals)}  |  "
        f"BUY: {buy_ct}  CONSIDER: {maybe_ct}  NO BUY: {skip_ct}  |  "
        f"PERFECT: {perfect_ct}  AVOID: {avoid_ct}\n"
    )

    # ── Quick-Reference Table ─────────────────────────────────────────────────
    print("─" * W)
    print("  QUICK COMPARISON  (ranked by score, highest first)")
    print("─" * W)
    rows = []
    for d in sorted_deals:
        v_tag = {
            "BUY":     "✅ BUY",
            "NO BUY":  "❌ SKIP",
            "WATCH":   "⏳ WATCH",
            "CONSIDER":"🔍 MAYBE",
        }.get(d.verdict, d.verdict)
        rows.append([
            v_tag,
            _rtag(d.perfect_pass_rating),
            f"{d.score}/100",
            d.address[:32],
            d.municipality[:13],
            fmt(d.min_bid),
            fmt(d.fmv),
            fmt(d.arv),
            fmt(d.flip_net_profit),
            fmt(d.stress_flip_arv5),
            fmt(d.monthly_noi),
            f"{d.cap_rate}%",
            f"{d.dscr:.2f}x",
            "✓" if d.flip_stress_passes else "✗",
            "✓" if d.hold_stress_passes else "✗",
            f"{d.school_rating}/10",
            f"{d.crime_index}/100",
            d.crime_grade,
        ])
    hdrs = [
        "Verdict", "Rating", "Score", "Address", "Muni",
        "Min Bid", "FMV", "ARV", "Flip $", "Stress(ARV-5%)",
        "Mo.NOI", "Cap%", "DSCR", "FlipStr", "HoldStr",
        "Schools", "Safety", "Crime",
    ]
    if HAS_TABULATE:
        print(tabulate(rows, headers=hdrs, tablefmt="simple"))
    else:
        col_w = [max(len(str(r[i])) for r in rows + [hdrs]) for i in range(len(hdrs))]
        def _frow(r): return "  ".join(str(r[i]).ljust(col_w[i]) for i in range(len(r)))
        print(_frow(hdrs))
        print("  ".join("-" * w for w in col_w))
        for r in rows:
            print(_frow(r))

    # ── Detailed Deal Cards ────────────────────────────────────────────────────
    print("\n" + "═" * W)
    print("  DETAILED DEAL ANALYSIS CARDS  (ranked by Deal Score)")
    print("═" * W)
    for d in sorted_deals:
        _print_deal_card(d)


def _print_deal_card(d: Deal) -> None:
    W = 120  # inner width between │ borders

    v_line = {
        "BUY":     "✅  VERDICT: BUY",
        "NO BUY":  "❌  VERDICT: NO BUY / SKIP",
        "WATCH":   "⏳  VERDICT: WATCH (Postponed)",
        "CONSIDER":"🔍  VERDICT: CONSIDER (Inspect First)",
    }.get(d.verdict, d.verdict)

    steal    = (d.fmv - d.min_bid) / d.fmv * 100 if d.fmv else 0
    mao_line = (
        f"PASSES ✓  (bid ${d.min_bid:,.0f} ≤ MAO ${d.precise_mao:,.0f})"
        if d.min_bid <= d.precise_mao
        else f"FAILS ✗  (bid ${d.min_bid:,.0f} > MAO ${d.precise_mao:,.0f})"
    )
    r70_line = (
        f"PASSES ✓  (bid ${d.min_bid:,.0f} ≤ ${d.max_bid_70:,.0f})"
        if d.min_bid <= d.max_bid_70
        else f"fails ✗  (max ${d.max_bid_70:,.0f})"
    )
    lev_line = "⚠ NEGATIVE LEVERAGE" if d.negative_leverage else "OK"
    dscr_line= f"SAFE ✓  ({d.dscr:.2f}x)" if d.dscr >= 1.20 else f"BELOW MIN ✗  ({d.dscr:.2f}x)"

    v5  = d.fmv * ((1 + APPRECIATION_RATE) **  5)
    v10 = d.fmv * ((1 + APPRECIATION_RATE) ** 10)

    flags_body = (
        "\n".join(f"│    ⚠  {f}" for f in d.red_flags)
        if d.red_flags else "│    None"
    )

    def _school_bar(rating: float) -> str:
        filled = int(round(rating))
        return "█" * filled + "░" * (10 - filled) + f"  {rating:.1f}/10"

    def _crime_bar(index: int) -> str:
        filled = index // 10
        return "█" * filled + "░" * (10 - filled) + f"  {index}/100 (100=safest)"

    print(f"""
┌{'─'*W}┐
│  {d.sale_id:<10}  {d.case:<16}  Score: {d.score}/100  Rating: {_rtag(d.perfect_pass_rating):<12}  {v_line}
│  Address:      {d.address:<68} Parcel: {d.parcel:<14}│
│  Municipality: {d.municipality:<22} Style: {d.style or 'N/A':<14} Built: {d.year_built}  SqFt: {d.sqft:,}  Beds: {d.bedrooms}
│{'─'*W}│
│  ── PURCHASE ─────────────────────────────────────────────────────────────────────────────────────────│
│  Min Bid:   {fmt(d.min_bid):<12}  Tax Upset:  {fmt(d.tax_bid):<12}  FMV:        {fmt(d.fmv):<12}  Equity below market: {steal:.0f}%
│  Repair:    {fmt(d.repair_cost):<12}  Contingency:{fmt(d.contingency):<12}  Buy Close:  {fmt(round(d.min_bid*CLOSING_BUY_PCT)):<12}  Carrying ({HOLDING_MONTHS_FLIP}mo): {fmt(HOLDING_MONTHS_FLIP*HOLDING_COST_MONTH)}
│  Total All-In: {fmt(d.total_all_in):<10}  (bid + repair + contingency + close + carry)
│{'─'*W}│
│  ── FLIP ANALYSIS ─────────────────────────────────────────────────────────────────────────────────────│
│  ARV: {fmt(d.arv):<12}  Net proceeds (8% sell cost): {fmt(round(d.arv*(1-CLOSING_SELL_PCT))):<12}  Flip Profit: {fmt(d.flip_net_profit):<12}  ROI: {d.flip_roi_pct:.0f}%  IRR(ann): {d.flip_irr_pct:.0f}%
│  Precise MAO:      {mao_line}
│  Simplified 70% rule: {r70_line}
│{'─'*W}│
│  ── FLIP STRESS TESTS ─────────────────────────────────────────────────────────────────────────────────│
│  ARV −5%:  {fmt(d.stress_flip_arv5):<12}  ARV −8%: {fmt(d.stress_flip_arv8):<12}  Rehab +$10/sqft: {fmt(d.stress_flip_rehab10):<12}  DOM +30d: {fmt(d.stress_flip_dom30):<12}  All pass: {'✓ YES' if d.flip_stress_passes else '✗ NO'}
│{'─'*W}│
│  ── RENTAL / NOI WATERFALL ────────────────────────────────────────────────────────────────────────────│
│  Gross Potential Rent: {fmt(d.gross_potential_rent)}/yr  →  EGI after {VACANCY_RATE*100:.0f}% vacancy: {fmt(d.egi)}/yr  →  OpEx ratio: {d.operating_exp_ratio}% of EGI (target ≤40%)
│  Annual NOI: {fmt(d.annual_noi)}/yr  ({fmt(d.monthly_noi)}/mo)   Cap Rate: {d.cap_rate}%   GRM: {d.gross_rent_mult:.1f}x   1% Rule: {'✓ PASS' if d.passes_1pct_rule else '✗ fail'}
│  Year-1 Cash Flow (all-cash, after reserve): {fmt(d.cash_flow_yr1)}/yr
│{'─'*W}│
│  ── LEVERAGE SCENARIO (75% LTV, 7.25%, 30yr) — useful for BRRRR / refi planning ─────────────────────│
│  Loan: {fmt(d.loan_amount):<12}  Annual Debt Service: {fmt(d.annual_debt_service)}/yr   DSCR: {dscr_line}
│  Leverage test: {lev_line}  (cap rate {d.cap_rate}% vs 8.19% mortgage constant)
│  Cash-on-Cash (levered): {d.cash_on_cash_levered}%   Cash Invested: {fmt(d.leveraged_cash_invested)}   Payback: {d.payback_yrs:.1f} yrs
│{'─'*W}│
│  ── HOLD STRESS TESTS ─────────────────────────────────────────────────────────────────────────────────│
│  Rent −5%: {fmt(d.stress_hold_rent5)}/yr   Vac +2pts: {fmt(d.stress_hold_vac2)}/yr   Tax +12.5%: {fmt(d.stress_hold_tax15)}/yr   Ins +20%: {fmt(d.stress_hold_ins20)}/yr   All pass: {'✓ YES' if d.hold_stress_passes else '✗ NO'}
│{'─'*W}│
│  ── APPRECIATION SCENARIOS ────────────────────────────────────────────────────────────────────────────│
│   5-Yr value: {fmt(v5):<12}   5-yr equity: {fmt(d.hold_5yr_equity):<12}   Cumul. NOI 5yr:  {fmt(d.annual_noi*5)}
│  10-Yr value: {fmt(v10):<12}  10-yr equity: {fmt(d.hold_10yr_equity):<12}  Cumul. NOI 10yr: {fmt(d.annual_noi*10)}
│{'─'*W}│
│  ── NEIGHBORHOOD — SCHOOLS & CRIME ────────────────────────────────────────────────────────────────────│
│  District: {d.school_district:<30}  PA Rank: {d.district_rank_pct}
│  Elementary:  {_school_bar(d.elem_rating):<30}  High School: {_school_bar(d.hs_rating)}
│  Crime Grade: {d.crime_grade:<6}  Safety Index: {_crime_bar(d.crime_index):<35}
│  Violent: {d.violent_per_1k:.2f}/1k residents  |  Property: {d.property_per_1k:.1f}/1k residents  (US avg: 4.0 violent / 18.0 property)
│  Note: {d.crime_note[:W-10]}
│{'─'*W}│
│  ── RED FLAGS ─────────────────────────────────────────────────────────────────────────────────────────│
{flags_body}
│{'─'*W}│
│  ── RECOMMENDATION ────────────────────────────────────────────────────────────────────────────────────│
│  {d.strategy[:W-4]}
└{'─'*W}┘""")


# ─── Load and Run ─────────────────────────────────────────────────────────────

def load_deals_from_json(path: str) -> list[Deal]:
    with open(path) as f:
        raw = json.load(f)

    deals = []
    for r in raw:
        fmv = float(r.get("fmv") or 0)
        if fmv == 0:
            continue

        sqft  = int(float(r.get("sqft")      or 0)) or 1_000
        beds  = int(float(r.get("bedrooms")   or 3))
        yr    = int(float(r.get("year_built") or 1950))
        baths = int(float(r.get("fullbaths")  or 1))

        postponed = (
            "postponed" in r.get("case", "").lower() or
            r.get("sale_id", "") in ("40JUL19",)
        )

        d = Deal(
            sale_id      = r.get("sale_id", ""),
            case         = r.get("case", ""),
            address      = r.get("address", ""),
            municipality = r.get("municipality", ""),
            parcel       = r.get("parcel", ""),
            min_bid      = float(r.get("min_bid") or r.get("tax_bid") or 0),
            tax_bid      = float(r.get("tax_bid") or 0),
            fmv          = fmv,
            assessed     = float(r.get("assessed") or fmv),
            year_built   = yr,
            sqft         = sqft,
            bedrooms     = beds,
            fullbaths    = baths,
            style        = str(r.get("style")     or ""),
            condition    = str(r.get("condition") or "Average"),
            postponed    = postponed,
        )
        deals.append(analyze(d))

    return deals


if __name__ == "__main__":
    import sys

    data_file = "/tmp/fc_properties.json"
    if len(sys.argv) > 1:
        data_file = sys.argv[1]

    if not Path(data_file).exists():
        print(f"Data file not found: {data_file}")
        print("Run sheriff_sale_analyzer.py --enrich first to generate the JSON.")
        sys.exit(1)

    deals = load_deals_from_json(data_file)
    print_investment_report(deals)
