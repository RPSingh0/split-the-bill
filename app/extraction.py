from decimal import Decimal

from app.money import round_half_up
from app.validation import error


def to_decimal(value):
    if value is None:
        return None

    return Decimal(str(value))


def to_paise(value):
    if value is None:
        return None

    return round_half_up(Decimal(str(value)) * 100)


def has_more_than_two_decimals(value):
    if value is None:
        return False

    amount = Decimal(str(value)) * 100

    return amount != amount.to_integral_value()


def check_decimals(value, field, label, issues):
    if has_more_than_two_decimals(value):
        issues.append(error("INVALID_AMOUNT", field, f"{label} has more than 2 decimals"))


def currency_or_inr(currency):
    if currency is None:
        return "INR"

    return currency


def normalise_item(llm_item, index, issues):
    label = f"Item {index + 1}"
    check_decimals(llm_item["unit_price"], f"items[{index}].unit_price_paise", f"{label} unit price", issues)
    check_decimals(llm_item["line_total"], f"items[{index}].line_total_paise", f"{label} amount", issues)

    return {
        "name": llm_item["name"],
        "quantity": to_decimal(llm_item["quantity"]),
        "unit_price_paise": to_paise(llm_item["unit_price"]),
        "line_total_paise": to_paise(llm_item["line_total"]),
    }


def normalise_items(llm_items, issues):
    items = []
    for index, llm_item in enumerate(llm_items):
        items.append(normalise_item(llm_item, index, issues))

    return items


def normalise_charge(llm_charge, index, issues):
    check_decimals(llm_charge["amount"], f"charges[{index}].amount_paise", llm_charge["label"], issues)

    return {
        "label": llm_charge["label"],
        "kind": llm_charge["kind"],
        "rate_percent": to_decimal(llm_charge["rate_percent"]),
        "amount_paise": to_paise(llm_charge["amount"]),
    }


def normalise_charges(llm_charges, issues):
    charges = []
    for llm_charge in llm_charges:
        if llm_charge["kind"] != "tip":
            charges.append(normalise_charge(llm_charge, len(charges), issues))

    return charges


def suggested_tip(llm_charges, issues):
    total = 0
    for llm_charge in llm_charges:
        if llm_charge["kind"] == "tip" and llm_charge["amount"] is not None:
            check_decimals(llm_charge["amount"], "tip", "Tip", issues)
            total += to_paise(llm_charge["amount"])

    return total


def normalise(llm_output):
    issues = []

    items = normalise_items(llm_output["items"], issues)
    check_decimals(llm_output["subtotal"], "subtotal_paise", "Subtotal", issues)
    charges = normalise_charges(llm_output["charges"], issues)
    check_decimals(llm_output["total"], "total_paise", "Total", issues)
    suggested_tip_paise = suggested_tip(llm_output["charges"], issues)

    receipt = {
        "is_receipt": llm_output["is_receipt"],
        "merchant": llm_output["merchant"],
        "bill_date": llm_output["date"],
        "currency": currency_or_inr(llm_output["currency"]),
        "items": items,
        "subtotal_paise": to_paise(llm_output["subtotal"]),
        "charges": charges,
        "total_paise": to_paise(llm_output["total"]),
        "suggested_tip_paise": suggested_tip_paise,
        "warnings": llm_output["warnings"],
    }

    return receipt, issues
