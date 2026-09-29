import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel


class Credentials(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: uuid.UUID
    username: str


class AuthResponse(BaseModel):
    user: UserOut
    token: str


class ReceiptItemOut(BaseModel):
    name: str | None
    quantity: float | None
    unit_price_paise: int | None
    line_total_paise: int | None


class ReceiptChargeOut(BaseModel):
    label: str | None
    kind: str
    rate_percent: float | None
    amount_paise: int | None


class ReceiptOut(BaseModel):
    is_receipt: bool
    merchant: str | None
    bill_date: str | None
    currency: str
    items: list[ReceiptItemOut]
    subtotal_paise: int | None
    charges: list[ReceiptChargeOut]
    total_paise: int | None
    suggested_tip_paise: int
    warnings: list[str]


class IssueOut(BaseModel):
    code: str
    severity: str
    field: str
    message: str
    expected: int | None
    actual: int | None


class ExtractResponse(BaseModel):
    receipt: ReceiptOut
    issues: list[IssueOut]


class BillItemIn(BaseModel):
    name: str | None = None
    quantity: Decimal | None = None
    unit_price_paise: int | None = None
    line_total_paise: int | None = None


class BillChargeIn(BaseModel):
    label: str
    kind: Literal["tax", "service_charge", "discount", "round_off", "other"]
    rate_percent: Decimal | None = None
    amount_paise: int | None = None


class BillCreate(BaseModel):
    merchant: str | None = None
    bill_date: date | None = None
    currency: str | None = None
    items: list[BillItemIn]
    charges: list[BillChargeIn]
    subtotal_paise: int | None = None
    total_paise: int | None = None
    tip_paise: int = 0
    tip_percent: Decimal | None = None


class JoinRequest(BaseModel):
    name: str
    confirm: bool = False


class ClaimRequest(BaseModel):
    units: int


class BillSummary(BaseModel):
    slug: str
    merchant: str | None
    bill_date: date | None
    grand_total_paise: int
    status: str
    participant_count: int
    created_at: datetime
