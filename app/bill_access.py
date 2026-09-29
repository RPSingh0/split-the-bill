import uuid

from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from app.auth import user_from_header
from app.bill_view import build_bill_view
from app.errors import ApiError
from app.models import Bill, BillItem, Participant


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


def lock_open_bill(db, slug):
    statement = (
        update(Bill)
        .where(Bill.slug == slug, Bill.status == "open")
        .values(version=Bill.version + 1)
        .returning(Bill.id)
        .execution_options(synchronize_session=False)
    )
    bill_id = db.scalar(statement)

    if bill_id is None:
        find_bill(db, slug)
        raise ApiError(409, "BILL_NOT_OPEN", "This bill is already closed")

    return db.get(Bill, bill_id, populate_existing=True)


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


def require_owner(db, bill, authorization):
    user = user_from_header(authorization, db)
    if user is None or user.id != bill.owner_id:
        raise ApiError(403, "NOT_OWNER", "Only the host can do this")

    return host_participant(db, bill)


def commit_and_view(db, slug, me):
    db.commit()
    full_bill = load_full_bill(db, slug)

    return build_bill_view(full_bill, me)
