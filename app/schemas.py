import uuid

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
