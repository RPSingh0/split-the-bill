from decimal import Decimal

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from app.split import KINDS, allocate, claim_mode, compute_split

QUANTITIES = [Decimal("1"), Decimal("2"), Decimal("3"), Decimal("4"), Decimal("0.5"), Decimal("1.5")]

CHARGE_RANGES = [
    ("tax", 0, 20000),
    ("tax", 0, 20000),
    ("service_charge", 0, 20000),
    ("discount", -20000, 0),
    ("round_off", -99, 99),
    ("other", 0, 5000),
]


def person(participant_id):
    return {"id": participant_id, "display_name": participant_id}


def claim(participant_id, units=1):
    return {"participant_id": participant_id, "units": units}


def item(item_id, line_total_paise, quantity="1", claims=None):
    if claims is None:
        claims = []

    return {"id": item_id, "quantity": Decimal(quantity), "line_total_paise": line_total_paise, "claims": claims}


def charge(kind, amount_paise):
    return {"kind": kind, "amount_paise": amount_paise}


def row_for(split, participant_id):
    for row in split["rows"]:
        if row["participant_id"] == participant_id:
            return row

    return None


def item_amounts(row):
    amounts = {}
    for share in row["items"]:
        amounts[share["item_id"]] = share["amount_paise"]

    return amounts


def test_allocate_splits_exactly():
    assert allocate(100, [("a", 1), ("b", 1)]) == {"a": 50, "b": 50}


def test_allocate_gives_leftover_to_first_on_tie():
    assert allocate(10000, [("a", 1), ("b", 1), ("c", 1)]) == {"a": 3334, "b": 3333, "c": 3333}


def test_allocate_gives_leftover_to_largest_remainder():
    assert allocate(10, [("a", 1), ("b", 2)]) == {"a": 3, "b": 7}


def test_allocate_zero_amount():
    assert allocate(0, [("a", 1), ("b", 3)]) == {"a": 0, "b": 0}


def test_allocate_zero_weights():
    assert allocate(500, [("a", 0), ("b", 0)]) == {"a": 0, "b": 0}


def test_allocate_zero_weight_gets_nothing():
    assert allocate(7, [("a", 0), ("b", 3), ("c", 0)]) == {"a": 0, "b": 7, "c": 0}


def test_allocate_negative_amount():
    assert allocate(-1, [("a", 1), ("b", 1)]) == {"a": -1, "b": 0}


@pytest.mark.parametrize(
    "quantity, mode",
    [("1", "shared"), ("2", "units"), ("1.5", "shared"), ("0.5", "shared"), ("2.000", "units")],
)
def test_claim_mode(quantity, mode):
    assert claim_mode(Decimal(quantity)) == mode


def test_three_way_pizza_leftover_paisa():
    people = [person("A"), person("B"), person("C")]
    pizza = item("pizza", 10000, claims=[claim("A"), claim("B"), claim("C")])

    split = compute_split(people, [pizza], [], 0)

    assert row_for(split, "A")["item_subtotal_paise"] == 3334
    assert row_for(split, "B")["item_subtotal_paise"] == 3333
    assert row_for(split, "C")["item_subtotal_paise"] == 3333
    assert split["unclaimed"]["total_paise"] == 0


def test_worked_example():
    people = [person("A"), person("B"), person("C")]
    pizza = item("pizza", 10000, claims=[claim("A"), claim("B"), claim("C")])

    split = compute_split(people, [pizza], [charge("tax", 1250)], 0)

    assert row_for(split, "A")["tax_paise"] == 417
    assert row_for(split, "B")["tax_paise"] == 417
    assert row_for(split, "C")["tax_paise"] == 416
    assert row_for(split, "A")["total_paise"] == 3751
    assert row_for(split, "B")["total_paise"] == 3750
    assert row_for(split, "C")["total_paise"] == 3749
    assert split["grand_total_paise"] == 11250


def test_discount_split_by_item_subtotal():
    people = [person("A"), person("B")]
    items = [item("thali", 60000, claims=[claim("A")]), item("biryani", 40000, claims=[claim("B")])]

    split = compute_split(people, items, [charge("discount", -10000)], 0)

    assert row_for(split, "A")["discount_paise"] == -6000
    assert row_for(split, "B")["discount_paise"] == -4000
    assert row_for(split, "A")["total_paise"] == 54000
    assert row_for(split, "B")["total_paise"] == 36000


def test_negative_round_off_tie_goes_to_first():
    people = [person("A"), person("B")]
    pizza = item("pizza", 10000, claims=[claim("A"), claim("B")])

    split = compute_split(people, [pizza], [charge("round_off", -1)], 0)

    assert row_for(split, "A")["round_off_paise"] == -1
    assert row_for(split, "B")["round_off_paise"] == 0
    assert row_for(split, "A")["total_paise"] == 4999
    assert row_for(split, "B")["total_paise"] == 5000


def test_units_item_split_by_units():
    people = [person("A"), person("B")]
    naan = item("naan", 24000, quantity="4", claims=[claim("A", 3), claim("B", 1)])

    split = compute_split(people, [naan], [], 0)

    assert row_for(split, "A")["item_subtotal_paise"] == 18000
    assert row_for(split, "B")["item_subtotal_paise"] == 6000
    assert split["unclaimed"]["total_paise"] == 0


def test_partly_claimed_units_go_to_unclaimed():
    people = [person("A"), person("B")]
    naan = item("naan", 24000, quantity="4", claims=[claim("A", 1)])

    split = compute_split(people, [naan], [charge("tax", 1200)], 0)

    assert row_for(split, "A")["item_subtotal_paise"] == 6000
    assert row_for(split, "A")["tax_paise"] == 300
    assert row_for(split, "A")["total_paise"] == 6300
    assert split["unclaimed"]["item_subtotal_paise"] == 18000
    assert split["unclaimed"]["tax_paise"] == 900
    assert split["unclaimed"]["total_paise"] == 18900
    assert row_for(split, "B")["total_paise"] == 0


def test_no_claims_everything_unclaimed():
    people = [person("A"), person("B")]
    items = [item("pizza", 10000), item("naan", 24000, quantity="4")]

    split = compute_split(people, items, [charge("tax", 1700)], 500)

    assert split["unclaimed"]["participant_id"] is None
    assert split["unclaimed"]["display_name"] == "Unclaimed"
    assert split["unclaimed"]["total_paise"] == 36200
    assert split["grand_total_paise"] == 36200
    assert row_for(split, "A")["total_paise"] == 0
    assert row_for(split, "B")["total_paise"] == 0


def test_single_person_owes_grand_total():
    people = [person("A"), person("B")]
    items = [
        item("pizza", 10000, claims=[claim("A")]),
        item("naan", 24000, quantity="4", claims=[claim("A", 4)]),
    ]
    charges = [
        charge("tax", 1700),
        charge("service_charge", 3400),
        charge("discount", -1000),
        charge("round_off", -3),
    ]

    split = compute_split(people, items, charges, 500)

    assert split["grand_total_paise"] == 38597
    assert row_for(split, "A")["total_paise"] == 38597
    assert row_for(split, "B")["total_paise"] == 0
    assert split["unclaimed"]["total_paise"] == 0


def test_zero_item_changes_nothing():
    people = [person("A"), person("B")]
    items = [item("pizza", 10000, claims=[claim("A")]), item("water", 0, claims=[claim("B")])]

    split = compute_split(people, items, [charge("tax", 500)], 0)

    assert item_amounts(row_for(split, "B")) == {"water": 0}
    assert row_for(split, "B")["total_paise"] == 0
    assert row_for(split, "A")["total_paise"] == 10500


def test_tip_split_by_item_subtotal():
    people = [person("A"), person("B")]
    items = [item("steak", 30000, claims=[claim("A")]), item("salad", 10000, claims=[claim("B")])]

    split = compute_split(people, items, [], 4000)

    assert row_for(split, "A")["tip_paise"] == 3000
    assert row_for(split, "B")["tip_paise"] == 1000
    assert row_for(split, "A")["total_paise"] == 33000
    assert row_for(split, "B")["total_paise"] == 11000
    assert split["grand_total_paise"] == 44000


def draw_participants(draw):
    participants = []
    count = draw(st.integers(1, 10))
    for index in range(count):
        participants.append(person("p" + str(index)))

    return participants


def draw_claims(draw, participants, quantity):
    claims = []
    mode = claim_mode(quantity)
    remaining = int(quantity)

    for participant in participants:
        if not draw(st.booleans()):
            continue

        if mode == "shared":
            claims.append(claim(participant["id"]))
        elif remaining > 0:
            units = draw(st.integers(1, remaining))
            remaining -= units
            claims.append(claim(participant["id"], units))

    return claims


def draw_items(draw, participants):
    items = []
    count = draw(st.integers(1, 8))

    for index in range(count):
        quantity = draw(st.sampled_from(QUANTITIES))
        line_total_paise = draw(st.integers(0, 100000))
        claims = draw_claims(draw, participants, quantity)
        items.append(item("i" + str(index), line_total_paise, quantity, claims))

    return items


def draw_charges(draw):
    charges = []
    for kind, low, high in CHARGE_RANGES:
        if draw(st.booleans()):
            charges.append(charge(kind, draw(st.integers(low, high))))

    return charges


def items_sum(items):
    total = 0
    for bill_item in items:
        total += bill_item["line_total_paise"]

    return total


@st.composite
def bills(draw):
    participants = draw_participants(draw)
    items = draw_items(draw, participants)
    assume(items_sum(items) > 0)

    charges = draw_charges(draw)
    tip_paise = draw(st.integers(0, 10000))

    return {"participants": participants, "items": items, "charges": charges, "tip_paise": tip_paise}


def run_split(bill):
    return compute_split(bill["participants"], bill["items"], bill["charges"], bill["tip_paise"])


def all_rows(split):
    rows = list(split["rows"])
    rows.append(split["unclaimed"])

    return rows


def rows_sum(split):
    total = 0
    for row in all_rows(split):
        total += row["total_paise"]

    return total


def expected_grand_total(bill):
    total = items_sum(bill["items"]) + bill["tip_paise"]
    for bill_charge in bill["charges"]:
        total += bill_charge["amount_paise"]

    return total


def item_share_total(split, item_id):
    total = 0
    for row in all_rows(split):
        for share in row["items"]:
            if share["item_id"] == item_id:
                total += share["amount_paise"]

    return total


def kind_share_total(split, kind):
    total = 0
    for row in all_rows(split):
        total += row[kind + "_paise"]

    return total


def expected_kind_total(bill, kind):
    if kind == "tip":
        return bill["tip_paise"]

    total = 0
    for bill_charge in bill["charges"]:
        if bill_charge["kind"] == kind:
            total += bill_charge["amount_paise"]

    return total


def claimant_ids(bill):
    ids = set()
    for bill_item in bill["items"]:
        for item_claim in bill_item["claims"]:
            ids.add(item_claim["participant_id"])

    return ids


@settings(max_examples=2000, deadline=None)
@given(bills())
def test_rows_sum_to_grand_total(bill):
    split = run_split(bill)

    assert split["grand_total_paise"] == expected_grand_total(bill)
    assert rows_sum(split) == expected_grand_total(bill)


@settings(max_examples=2000, deadline=None)
@given(bills())
def test_each_item_and_kind_sums_exactly(bill):
    split = run_split(bill)

    for bill_item in bill["items"]:
        assert item_share_total(split, bill_item["id"]) == bill_item["line_total_paise"]

    for kind in KINDS:
        assert kind_share_total(split, kind) == expected_kind_total(bill, kind)


@settings(max_examples=2000, deadline=None)
@given(bills())
def test_same_input_gives_same_output(bill):
    assert run_split(bill) == run_split(bill)


@settings(max_examples=2000, deadline=None)
@given(bills())
def test_participant_without_claims_owes_nothing(bill):
    split = run_split(bill)
    claimants = claimant_ids(bill)

    for row in split["rows"]:
        if row["participant_id"] in claimants:
            continue

        assert row["items"] == []
        assert row["item_subtotal_paise"] == 0
        assert row["total_paise"] == 0

        for kind in KINDS:
            assert row[kind + "_paise"] == 0
