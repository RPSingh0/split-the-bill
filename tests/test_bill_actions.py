import uuid
from decimal import Decimal

import pytest
from factories import make_bill
from fastapi.testclient import TestClient

from app.errors import ApiError
from app.main import app
from app.models import BillItem, Claim
from app.routers.bill_actions import check_claim_units, clean_name, other_units, unclaimed_total

HEADERS = {"X-API-Key": "test-api-key"}

client = TestClient(app)


def item_with_quantity(quantity):
    return BillItem(id=uuid.uuid4(), position=0, name="Item", quantity=Decimal(quantity), line_total_paise=10000)


def raised_error(action, *args):
    with pytest.raises(ApiError) as caught:
        action(*args)

    return caught.value


def test_clean_name_collapses_whitespace():
    assert clean_name("  Priya   S ") == "Priya S"
    assert clean_name("x" * 30) == "x" * 30


def test_clean_name_rejects_empty_and_long_names():
    assert raised_error(clean_name, "").code == "INVALID_NAME"
    assert raised_error(clean_name, "    ").code == "INVALID_NAME"
    assert raised_error(clean_name, "x" * 31).code == "INVALID_NAME"


def test_shared_item_takes_one_unit():
    item = item_with_quantity("1")

    check_claim_units(item, 1, 0)
    check_claim_units(item, 1, 5)

    error = raised_error(check_claim_units, item, 2, 0)
    assert error.status_code == 400
    assert error.code == "INVALID_UNITS"


def test_units_item_within_cap():
    item = item_with_quantity("4")

    check_claim_units(item, 4, 0)
    check_claim_units(item, 1, 3)


def test_units_item_over_cap():
    item = item_with_quantity("4")

    error = raised_error(check_claim_units, item, 2, 3)

    assert error.status_code == 409
    assert error.code == "UNITS_EXCEEDED"
    assert error.extra == {"available_units": 1}


def test_units_item_fully_claimed_by_others():
    item = item_with_quantity("4")

    error = raised_error(check_claim_units, item, 1, 4)

    assert error.extra == {"available_units": 0}


def test_other_units_ignores_my_own_claim():
    bill, host, priya = make_bill()
    naan = bill.items[0]
    naan.claims.append(Claim(item_id=naan.id, participant_id=priya.id, units=1))

    assert other_units(naan, priya) == 3
    assert other_units(naan, host) == 1


def test_unclaimed_total():
    bill, host, priya = make_bill()

    assert unclaimed_total(bill) == 6476


def test_nothing_unclaimed_once_every_unit_is_claimed():
    bill, host, priya = make_bill()
    naan = bill.items[0]
    naan.claims.append(Claim(item_id=naan.id, participant_id=priya.id, units=1))

    assert unclaimed_total(bill) == 0


def test_join_with_blank_name_is_rejected():
    response = client.post("/bills/any-slug/join", json={"name": "   "}, headers=HEADERS)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_NAME"


def test_claim_with_zero_units_is_rejected():
    item_id = str(uuid.uuid4())

    response = client.put(f"/bills/any-slug/claims/{item_id}", json={"units": 0}, headers=HEADERS)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_UNITS"


def test_claim_with_malformed_item_id_is_rejected():
    response = client.put("/bills/any-slug/claims/not-a-uuid", json={"units": 1}, headers=HEADERS)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "BAD_REQUEST"
