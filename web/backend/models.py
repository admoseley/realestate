from datetime import datetime
from typing import Optional
from pydantic import BaseModel


# ── Requests ──────────────────────────────────────────────────────────────────

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

class JobStarted(BaseModel):
    """Returned by endpoints whose work runs in the background: poll
    ``GET /api/jobs/{job_id}`` until ``status`` is ``done`` or ``error``."""
    job_id: str


class JobStatus(BaseModel):
    job_id:    str
    status:    str        # pending | running | done | error
    percent:   int
    message:   str
    report_id: Optional[int] = None
    # Set when a job is done. Spot check: {"deal": {...}, "warning": str | null}.
    # Share: {"recipient": str, "count": int}. Sheriff sale: none (see report_id).
    result:    Optional[dict] = None


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


class UpdateAddressRequest(BaseModel):
    address: str


class ClearDealsResult(BaseModel):
    deleted: int
    source:  Optional[str] = None


class SharePropertyRequest(BaseModel):
    recipient_name:  str
    recipient_email: str
    sender_name:     Optional[str] = None
    note:            Optional[str] = None
    deal:            dict


class ShareFavoritesRequest(BaseModel):
    recipient_name:  str
    recipient_email: str
    sender_name:     Optional[str] = None
    note:            Optional[str] = None
    deals:           list[dict]
