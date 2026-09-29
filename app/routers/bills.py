import secrets
import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, Header
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.auth import current_user, user_from_header
from app.bill_view import build_bill_view
from app.db import get_db
from app.errors import ApiError
from app.models import Bill, BillCharge, BillItem, Participant, User
from app.money import round_half_up
from app.schemas import BillCreate, BillSummary
from app.validation import has_errors, items_sum, validate_receipt, validate_tip

router = APIRouter(prefix="/bills", tags=["bills"])


def receipt_from_body(body):
    receipt = body.model_dump()

    if receipt["currency"] is None:
        receipt["currency"] = "INR"

    return receipt


def bill_issues(receipt):
    issues = validate_receipt(receipt)
    issues.extend(validate_tip(receipt["tip_paise"], receipt["tip_percent"]))

    return issues


def tip_from_percent(items_total, tip_percent):
    return round_half_up(Decimal(items_total) * tip_percent / 100)


def new_slug(db):
    while True:
        slug = secrets.token_urlsafe(9)
        if db.scalar(select(Bill.id).where(Bill.slug == slug)) is None:
            return slug


def new_item(position, item):
    return BillItem(
        position=position,
        name=item["name"],
        quantity=item["quantity"],
        unit_price_paise=item["unit_price_paise"],
        line_total_paise=item["line_total_paise"],
    )


def new_charge(position, charge):
    return BillCharge(
        position=position,
        label=charge["label"],
        kind=charge["kind"],
        rate_percent=charge["rate_percent"],
        amount_paise=charge["amount_paise"],
    )


def new_bill(receipt, user, slug):
    bill = Bill(
        slug=slug,
        owner_id=user.id,
        merchant=receipt["merchant"],
        bill_date=receipt["bill_date"],
        currency=receipt["currency"],
        subtotal_paise=receipt["subtotal_paise"],
        total_paise=receipt["total_paise"],
        tip_paise=receipt["tip_paise"],
        tip_percent=receipt["tip_percent"],
    )

    for position, item in enumerate(receipt["items"]):
        bill.items.append(new_item(position, item))

    for position, charge in enumerate(receipt["charges"]):
        bill.charges.append(new_charge(position, charge))

    bill.participants.append(Participant(display_name=user.username, name_key=user.username, user_id=user.id))

    return bill


def find_bill(db, slug):
    bill = db.scalar(select(Bill).where(Bill.slug == slug))
    if bill is None:
        raise ApiError(404, "BILL_NOT_FOUND", "This bill link doesn't exist")

    return bill


def load_full_bill(db, slug):
    query = (
        select(Bill)
        .where(Bill.slug == slug)
        .options(
            selectinload(Bill.items).selectinload(BillItem.claims),
            selectinload(Bill.charges),
            selectinload(Bill.participants),
            selectinload(Bill.owner),
        )
    )

    return db.scalar(query)


def host_participant(db, bill):
    query = select(Participant).where(Participant.bill_id == bill.id, Participant.user_id == bill.owner_id)

    return db.scalar(query)


def participant_from_header(db, bill, header):
    if header is None:
        return None

    try:
        participant_id = uuid.UUID(header)
    except ValueError:
        return None

    participant = db.get(Participant, participant_id)
    if participant is None or participant.bill_id != bill.id:
        return None

    return participant


def find_me(db, bill, authorization, participant_header):
    user = user_from_header(authorization, db)
    if user is not None and user.id == bill.owner_id:
        return host_participant(db, bill)

    participant = participant_from_header(db, bill, participant_header)
    if participant is None:
        raise ApiError(403, "NOT_A_PARTICIPANT", "You're not on this bill")

    return participant


def bill_summary(bill):
    return {
        "slug": bill.slug,
        "merchant": bill.merchant,
        "bill_date": bill.bill_date,
        "grand_total_paise": bill.total_paise + bill.tip_paise,
        "status": bill.status,
        "participant_count": len(bill.participants),
        "created_at": bill.created_at,
    }


@router.post("", status_code=201)
def create_bill(body: BillCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    receipt = receipt_from_body(body)

    issues = bill_issues(receipt)
    if has_errors(issues):
        raise ApiError(422, "VALIDATION_FAILED", "Please fix the issues on the receipt", issues=issues)

    if receipt["tip_percent"] is not None:
        receipt["tip_paise"] = tip_from_percent(items_sum(receipt), receipt["tip_percent"])

    bill = new_bill(receipt, user, new_slug(db))
    db.add(bill)
    db.commit()

    full_bill = load_full_bill(db, bill.slug)
    me = host_participant(db, full_bill)

    return {"slug": full_bill.slug, "bill": build_bill_view(full_bill, me)}


@router.get("", response_model=list[BillSummary])
def list_bills(user: User = Depends(current_user), db: Session = Depends(get_db)):
    query = (
        select(Bill)
        .where(Bill.owner_id == user.id)
        .order_by(Bill.created_at.desc())
        .options(selectinload(Bill.participants))
    )

    summaries = []
    for bill in db.scalars(query):
        summaries.append(bill_summary(bill))

    return summaries


@router.get("/{slug}")
def get_bill(
    slug: str,
    since: int | None = None,
    authorization: str | None = Header(default=None),
    x_participant_id: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    bill = find_bill(db, slug)
    me = find_me(db, bill, authorization, x_participant_id)

    if since is not None and since == bill.version:
        return {"changed": False, "version": bill.version}

    full_bill = load_full_bill(db, slug)

    return {"changed": True, "bill": build_bill_view(full_bill, me)}
