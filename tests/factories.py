import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from app.models import Bill, BillCharge, BillItem, Claim, Participant, User


def make_bill(status="open"):
    owner = User(id=uuid.uuid4(), username="rupinder", password_hash="x")
    joined = datetime(2026, 9, 28, 20, 0, tzinfo=timezone.utc)
    host = Participant(id=uuid.uuid4(), display_name="rupinder", name_key="rupinder", user_id=owner.id, joined_at=joined)
    priya = Participant(id=uuid.uuid4(), display_name="Priya", name_key="priya", user_id=None, joined_at=joined + timedelta(minutes=1))

    naan = BillItem(id=uuid.uuid4(), position=0, name="Butter Naan", quantity=Decimal("4.000"), unit_price_paise=6000, line_total_paise=24000)
    naan.claims = [Claim(item_id=naan.id, participant_id=host.id, units=3)]

    pizza = BillItem(id=uuid.uuid4(), position=1, name="Pizza", quantity=Decimal("1.000"), unit_price_paise=None, line_total_paise=10000)
    pizza.claims = [Claim(item_id=pizza.id, participant_id=host.id, units=1), Claim(item_id=pizza.id, participant_id=priya.id, units=1)]

    tax = BillCharge(id=uuid.uuid4(), position=0, label="CGST 2.5%", kind="tax", rate_percent=Decimal("2.500"), amount_paise=1700)

    bill = Bill(
        id=uuid.uuid4(),
        slug="Xk3_9aQpL2mZ",
        owner_id=owner.id,
        status=status,
        merchant="THE CURRY LEAF",
        bill_date=date(2026, 9, 28),
        currency="INR",
        subtotal_paise=34000,
        total_paise=35700,
        tip_paise=1000,
        tip_percent=None,
        version=3,
    )
    bill.owner = owner
    bill.items = [naan, pizza]
    bill.charges = [tax]
    bill.participants = [host, priya]

    return bill, host, priya
