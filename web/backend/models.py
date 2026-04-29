from datetime import datetime
from typing import Optional
from pydantic import BaseModel


# ── Requests ──────────────────────────────────────────────────────────────────

class SheriffSaleUrlRequest(BaseModel):
    url: str
    enrich: bool = True


class SpotCheckRequest(BaseModel):
    address: str
    price: float
    fmv: Optional[float]        = None
    sqft: Optional[int]         = None
    year: Optional[int]         = None
    beds: Optional[int]         = None
    baths: Optional[int]        = None
    parcel: Optional[str]       = None
    municipality: Optional[str] = None
    no_lookup: bool             = False


# ── Responses ─────────────────────────────────────────────────────────────────

class JobStatus(BaseModel):
    job_id:    str
    status:    str        # pending | running | done | error
    percent:   int
    message:   str
    report_id: Optional[int] = None


class ReportSummary(BaseModel):
    id:             int
    type:           str
    created_at:     datetime
    title:          str
    property_count: int
    buy_count:      int
    consider_count: int
    no_buy_count:   int
    watch_count:    int
    perfect_count:  int
    avoid_count:    int
    has_pdf:        bool

    model_config = {"from_attributes": True}


class ReportDetail(ReportSummary):
    deals: list[dict]     # list of analyzed Deal dicts


class SpotCheckResponse(BaseModel):
    report_id: int
    deal:      dict
    warning:   Optional[str] = None
