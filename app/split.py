KINDS = ["tax", "service_charge", "discount", "round_off", "other", "tip"]


def claim_mode(quantity):
    if quantity > 1 and quantity == int(quantity):
        return "units"

    return "shared"


def total_weight(weights):
    total = 0
    for key, weight in weights:
        total += weight

    return total


def remainder_of(entry):
    return entry[1]


def keys_by_largest_remainder(remainders):
    ordered = sorted(remainders, key=remainder_of, reverse=True)

    keys = []
    for key, remainder in ordered:
        keys.append(key)

    return keys


def allocate(amount, weights):
    shares = {}
    for key, weight in weights:
        shares[key] = 0

    weight_sum = total_weight(weights)
    if amount == 0 or weight_sum == 0:
        return shares

    sign = 1
    if amount < 0:
        sign = -1
    amount = abs(amount)

    given = 0
    remainders = []
    for key, weight in weights:
        shares[key] = amount * weight // weight_sum
        remainders.append((key, amount * weight % weight_sum))
        given += shares[key]

    leftover = amount - given
    ordered_keys = keys_by_largest_remainder(remainders)
    for key in ordered_keys[:leftover]:
        shares[key] += 1

    for key in shares:
        shares[key] = sign * shares[key]

    return shares


def claimed_units(item):
    claimed = {}
    for claim in item["claims"]:
        claimed[claim["participant_id"]] = claim["units"]

    return claimed


def shared_weights(claimed, participants):
    weights = []
    for participant in participants:
        if participant["id"] in claimed:
            weights.append((participant["id"], 1))

    if len(weights) == 0:
        weights.append((None, 1))

    return weights


def units_weights(claimed, participants, max_units):
    weights = []
    for participant in participants:
        if participant["id"] in claimed:
            weights.append((participant["id"], claimed[participant["id"]]))

    unclaimed_units = max_units - total_weight(weights)
    if unclaimed_units > 0:
        weights.append((None, unclaimed_units))

    return weights


def item_weights(item, participants):
    claimed = claimed_units(item)

    if claim_mode(item["quantity"]) == "units":
        return units_weights(claimed, participants, int(item["quantity"]))

    return shared_weights(claimed, participants)


def empty_row(participant_id, display_name):
    return {
        "participant_id": participant_id,
        "display_name": display_name,
        "items": [],
        "item_subtotal_paise": 0,
        "tax_paise": 0,
        "service_charge_paise": 0,
        "discount_paise": 0,
        "round_off_paise": 0,
        "other_paise": 0,
        "tip_paise": 0,
        "total_paise": 0,
    }


def build_rows(participants):
    rows = {}
    for participant in participants:
        rows[participant["id"]] = empty_row(participant["id"], participant["display_name"])

    rows[None] = empty_row(None, "Unclaimed")

    return rows


def split_items(rows, items, participants):
    for item in items:
        shares = allocate(item["line_total_paise"], item_weights(item, participants))
        assert sum(shares.values()) == item["line_total_paise"]

        for key in shares:
            rows[key]["items"].append({"item_id": item["id"], "amount_paise": shares[key]})
            rows[key]["item_subtotal_paise"] += shares[key]


def kind_totals(charges, tip_paise):
    totals = {"tax": 0, "service_charge": 0, "discount": 0, "round_off": 0, "other": 0, "tip": tip_paise}
    for charge in charges:
        totals[charge["kind"]] += charge["amount_paise"]

    return totals


def subtotal_weights(rows):
    weights = []
    for key in rows:
        weights.append((key, rows[key]["item_subtotal_paise"]))

    return weights


def split_charges(rows, totals):
    weights = subtotal_weights(rows)

    for kind in KINDS:
        shares = allocate(totals[kind], weights)
        assert sum(shares.values()) == totals[kind]

        for key in shares:
            rows[key][kind + "_paise"] = shares[key]


def fill_row_totals(rows):
    for row in rows.values():
        total = row["item_subtotal_paise"]
        for kind in KINDS:
            total += row[kind + "_paise"]

        row["total_paise"] = total


def items_total(items):
    total = 0
    for item in items:
        total += item["line_total_paise"]

    return total


def rows_total(rows):
    total = 0
    for row in rows.values():
        total += row["total_paise"]

    return total


def compute_split(participants, items, charges, tip_paise):
    rows = build_rows(participants)
    split_items(rows, items, participants)

    totals = kind_totals(charges, tip_paise)
    split_charges(rows, totals)
    fill_row_totals(rows)

    grand_total = items_total(items) + sum(totals.values())
    assert rows_total(rows) == grand_total

    unclaimed = rows.pop(None)

    return {"rows": list(rows.values()), "unclaimed": unclaimed, "grand_total_paise": grand_total}
