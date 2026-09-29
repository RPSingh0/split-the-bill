import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.bill_access import commit_and_view, find_bill, find_me, load_full_bill, lock_open_bill, require_owner
from app.bill_view import bill_split, build_bill_view
from app.db import get_db
from app.errors import ApiError
from app.models import BillItem, Claim, Participant
from app.schemas import ClaimRequest, JoinRequest
from app.split import claim_mode

router = APIRouter(prefix="/bills", tags=["bill actions"])

MAX_PARTICIPANTS = 10
MAX_NAME_LENGTH = 30


def clean_name(raw):
    name = " ".join(raw.split())
    if len(name) < 1 or len(name) > MAX_NAME_LENGTH:
        raise ApiError(400, "INVALID_NAME", "Enter a name between 1 and 30 characters")

    return name


def find_by_name_key(db, bill, name_key):
    query = select(Participant).where(Participant.bill_id == bill.id, Participant.name_key == name_key)

    return db.scalar(query)


def participant_count(db, bill):
    query = select(func.count()).select_from(Participant).where(Participant.bill_id == bill.id)

    return db.scalar(query)


def name_exists_error(participant):
    return ApiError(
        409,
        "NAME_EXISTS",
        f"{participant.display_name} is already on this bill",
        existing_name=participant.display_name,
        can_confirm=participant.user_id is None,
    )


def rejoin(db, bill, participant, confirm):
    if not confirm or participant.user_id is not None:
        raise name_exists_error(participant)

    full_bill = load_full_bill(db, bill.slug)

    return {"participant_id": participant.id, "bill": build_bill_view(full_bill, participant)}


def join_as_new(db, slug, name):
    bill = lock_open_bill(db, slug)
    name_key = name.lower()

    existing = find_by_name_key(db, bill, name_key)
    if existing is not None:
        raise name_exists_error(existing)

    if participant_count(db, bill) >= MAX_PARTICIPANTS:
        raise ApiError(409, "BILL_FULL", "This bill already has 10 people")

    participant = Participant(bill_id=bill.id, display_name=name, name_key=name_key)
    db.add(participant)
    view = commit_and_view(db, slug, participant)

    return {"participant_id": participant.id, "bill": view}


def find_item(db, bill, item_id):
    item = db.get(BillItem, item_id)
    if item is None or item.bill_id != bill.id:
        raise ApiError(404, "ITEM_NOT_FOUND", "This item isn't on the bill")

    return item


def other_units(item, me):
    total = 0
    for claim in item.claims:
        if claim.participant_id != me.id:
            total += claim.units

    return total


def check_claim_units(item, units, units_by_others):
    mode = claim_mode(item.quantity)

    if mode == "shared" and units != 1:
        raise ApiError(400, "INVALID_UNITS", "A shared item is claimed with 1 unit")

    if mode == "units":
        available = int(item.quantity) - units_by_others
        if units > available:
            raise ApiError(409, "UNITS_EXCEEDED", f"Only {available} left to claim", available_units=available)


def save_claim(db, item, me, units):
    claim = db.get(Claim, (item.id, me.id))
    if claim is None:
        claim = Claim(item_id=item.id, participant_id=me.id)
        db.add(claim)

    claim.units = units
    claim.updated_at = datetime.now(timezone.utc)


def find_participant(db, bill, participant_id):
    participant = db.get(Participant, participant_id)
    if participant is None or participant.bill_id != bill.id:
        raise ApiError(404, "PARTICIPANT_NOT_FOUND", "This person isn't on the bill")

    return participant


def unclaimed_total(bill):
    return bill_split(bill)["unclaimed"]["total_paise"]


def close_bill(bill, status):
    bill.status = status
    bill.closed_at = datetime.now(timezone.utc)


@router.post("/{slug}/join")
def join_bill(slug: str, body: JoinRequest, db: Session = Depends(get_db)):
    name = clean_name(body.name)

    bill = find_bill(db, slug)
    if bill.status == "cancelled":
        raise ApiError(410, "BILL_CANCELLED", "This bill was cancelled")

    existing = find_by_name_key(db, bill, name.lower())
    if existing is not None:
        return rejoin(db, bill, existing, body.confirm)

    if bill.status == "done":
        raise ApiError(409, "BILL_DONE", "This bill is already settled")

    return join_as_new(db, slug, name)


@router.put("/{slug}/claims/{item_id}")
def claim_item(
    slug: str,
    item_id: uuid.UUID,
    body: ClaimRequest,
    authorization: str | None = Header(default=None),
    x_participant_id: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    if body.units < 1:
        raise ApiError(400, "INVALID_UNITS", "Units must be at least 1")

    bill = lock_open_bill(db, slug)
    me = find_me(db, bill, authorization, x_participant_id)
    item = find_item(db, bill, item_id)

    check_claim_units(item, body.units, other_units(item, me))
    save_claim(db, item, me, body.units)

    return commit_and_view(db, slug, me)


@router.delete("/{slug}/claims/{item_id}")
def unclaim_item(
    slug: str,
    item_id: uuid.UUID,
    authorization: str | None = Header(default=None),
    x_participant_id: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    bill = lock_open_bill(db, slug)
    me = find_me(db, bill, authorization, x_participant_id)
    item = find_item(db, bill, item_id)

    claim = db.get(Claim, (item.id, me.id))
    if claim is not None:
        db.delete(claim)

    return commit_and_view(db, slug, me)


@router.delete("/{slug}/participants/{participant_id}")
def remove_participant(
    slug: str,
    participant_id: uuid.UUID,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    bill = lock_open_bill(db, slug)
    host = require_owner(db, bill, authorization)
    participant = find_participant(db, bill, participant_id)

    if participant.user_id is not None:
        raise ApiError(409, "CANNOT_REMOVE_HOST", "The host can't be removed")

    db.delete(participant)

    return commit_and_view(db, slug, host)


@router.post("/{slug}/done")
def mark_done(slug: str, authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    lock_open_bill(db, slug)
    full_bill = load_full_bill(db, slug)
    host = require_owner(db, full_bill, authorization)

    unclaimed = unclaimed_total(full_bill)
    if unclaimed != 0:
        raise ApiError(409, "HAS_UNCLAIMED", "Some items are still unclaimed", unclaimed_paise=unclaimed)

    close_bill(full_bill, "done")

    return commit_and_view(db, slug, host)


@router.post("/{slug}/cancel")
def cancel_bill(slug: str, authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    bill = lock_open_bill(db, slug)
    host = require_owner(db, bill, authorization)

    close_bill(bill, "cancelled")

    return commit_and_view(db, slug, host)
