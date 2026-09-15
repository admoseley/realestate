from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

# The most properties one share email may cover. It bounds the PDF and email a
# single request can make the (single-instance) API build.
MAX_SHARED_PROPERTIES = 100


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


class ShareRequest(BaseModel):
    # Length limits bound what a request can put into an email sent from the
    # business domain. 320 characters is the longest valid email address.
    recipient_name:  str           = Field(min_length=1, max_length=100)
    recipient_email: str           = Field(max_length=320)
    sender_name:     Optional[str] = Field(None, max_length=100)
    note:            Optional[str] = Field(None, max_length=2000)


# Shares name deals by sale_id, and the server loads them from property_deals.
# Clients used to post whole deal objects, which put whatever the browser sent
# (addresses, verdicts, red flags) into an email from the business domain.
class SharePropertyRequest(ShareRequest):
    sale_id: str


class ShareFavoritesRequest(ShareRequest):
    sale_ids: list[str] = Field(min_length=1, max_length=MAX_SHARED_PROPERTIES)
