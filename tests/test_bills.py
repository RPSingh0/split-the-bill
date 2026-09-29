import json
import uuid
from decimal import Decimal
from pathlib import Path

import pytest
from factories import make_bill
from fastapi.testclient import TestClient

from app.auth import current_user
from app.bill_view import build_bill_view
from app.extraction import normalise
from app.main import app
from app.models import User
from app.routers.bills import tip_from_percent

SAMPLES = Path(__file__).parent.parent / "samples"
HEADERS = {"X-API-Key": "test-api-key"}

client = TestClient(app)


def fake_user():
    return User(id=uuid.uuid4(), username="rupinder", password_hash="x")


@pytest.fixture(autouse=True)
def logged_in():
    app.dependency_overrides[current_user] = fake_user
    yield
    app.dependency_overrides.clear()


def load_sample(name):
    with open(SAMPLES / name, encoding="utf-8") as file:
        return json.load(file)


def item_body(item):
    return {
        "name": item["name"],
        "quantity": float(item["quantity"]),
        "unit_price_paise": item["unit_price_paise"],
        "line_total_paise": item["line_total_paise"],
    }


def charge_body(charge):
    rate_percent = None
    if charge["rate_percent"] is not None:
        rate_percent = float(charge["rate_percent"])

    return {
        "label": charge["label"],
        "kind": charge["kind"],
        "rate_percent": rate_percent,
        "amount_paise": charge["amount_paise"],
    }


def bill_body(sample_name):
    receipt, issues = normalise(load_sample(sample_name))

    items = []
    for item in receipt["items"]:
        items.append(item_body(item))

    charges = []
    for charge in receipt["charges"]:
        charges.append(charge_body(charge))

    return {
        "merchant": receipt["merchant"],
        "bill_date": receipt["bill_date"],
        "currency": receipt["currency"],
        "items": items,
        "charges": charges,
        "subtotal_paise": receipt["subtotal_paise"],
        "total_paise": receipt["total_paise"],
        "tip_paise": 0,
        "tip_percent": None,
    }


def issue_codes(response):
    codes = []
    for entry in response.json()["error"]["issues"]:
        codes.append(entry["code"])

    return codes


def test_bill_view_has_items_claims_and_split():
    bill, host, priya = make_bill()

    view = build_bill_view(bill, host)

    assert view["host_name"] == "rupinder"
    assert view["grand_total_paise"] == 36700
    assert view["split"]["grand_total_paise"] == 36700
    assert view["me"] == {"participant_id": host.id, "is_host": True}

    naan = view["items"][0]
    assert naan["claim_mode"] == "units"
    assert naan["max_units"] == 4
    assert naan["units_claimed"] == 3
    assert naan["claims"] == [{"participant_id": host.id, "units": 3}]

    pizza = view["items"][1]
    assert pizza["claim_mode"] == "shared"
    assert pizza["max_units"] is None
    assert pizza["units_claimed"] == 2


def test_bill_view_participants_and_split_rows():
    bill, host, priya = make_bill()

    view = build_bill_view(bill, priya)

    assert view["participants"][0]["is_host"] is True
    assert view["participants"][1]["is_host"] is False
    assert view["me"] == {"participant_id": priya.id, "is_host": False}

    rows = view["split"]["rows"]
    assert rows[0]["participant_id"] == host.id
    assert rows[0]["item_subtotal_paise"] == 23000
    assert rows[1]["participant_id"] == priya.id
    assert rows[1]["item_subtotal_paise"] == 5000
    assert view["split"]["unclaimed"]["item_subtotal_paise"] == 6000


def test_cancelled_bill_view_is_minimal():
    bill, host, priya = make_bill(status="cancelled")

    view = build_bill_view(bill, priya)

    assert view == {"slug": "Xk3_9aQpL2mZ", "status": "cancelled", "version": 3, "host_name": "rupinder"}


def test_tip_from_percent():
    assert tip_from_percent(145000, Decimal("10")) == 14500
    assert tip_from_percent(33333, Decimal("12.5")) == 4167
    assert tip_from_percent(145000, Decimal("0")) == 0


def test_create_bill_with_mismatch_returns_422_with_issues():
    response = client.post("/bills", json=bill_body("receipt_3.expected.json"), headers=HEADERS)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"
    assert issue_codes(response) == ["ITEMS_SUBTOTAL_MISMATCH"]


def test_create_bill_with_bad_tip_percent_returns_422():
    body = bill_body("receipt_2.expected.json")
    body["tip_percent"] = 150

    response = client.post("/bills", json=body, headers=HEADERS)

    assert response.status_code == 422
    assert issue_codes(response) == ["TIP_INVALID"]


def test_create_bill_with_missing_fields_returns_422():
    body = bill_body("receipt_2.expected.json")
    body["items"][0]["line_total_paise"] = None
    body["total_paise"] = None

    response = client.post("/bills", json=body, headers=HEADERS)

    assert response.status_code == 422
    assert "FIELD_MISSING" in issue_codes(response)


def test_create_bill_with_wrong_shape_returns_400():
    body = bill_body("receipt_2.expected.json")
    body["items"][0]["line_total_paise"] = "abc"

    response = client.post("/bills", json=body, headers=HEADERS)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "BAD_REQUEST"


def test_create_bill_rejects_tip_charge_kind():
    body = bill_body("receipt_2.expected.json")
    body["charges"][0]["kind"] = "tip"

    response = client.post("/bills", json=body, headers=HEADERS)

    assert response.status_code == 400


def test_create_bill_requires_login():
    app.dependency_overrides.clear()

    response = client.post("/bills", json=bill_body("receipt_2.expected.json"), headers=HEADERS)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"
