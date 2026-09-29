from decimal import Decimal

from app.money import round_half_up, rupees


def issue(code, severity, field, message, expected=None, actual=None):
    return {
        "code": code,
        "severity": severity,
        "field": field,
        "message": message,
        "expected": expected,
        "actual": actual,
    }


def error(code, field, message, expected=None, actual=None):
    return issue(code, "error", field, message, expected, actual)


def warning(code, field, message, expected=None, actual=None):
    return issue(code, "warning", field, message, expected, actual)


def is_blank(text):
    return text is None or text.strip() == ""


def item_label(index):
    return f"Item {index + 1}"


def charge_label(charge, index):
    if is_blank(charge["label"]):
        return f"Charge {index + 1}"

    return charge["label"]


def format_number(value):
    if value == int(value):
        return str(int(value))

    return str(value.normalize())


def items_sum(receipt):
    total = 0
    for item in receipt["items"]:
        if item["line_total_paise"] is not None:
            total += item["line_total_paise"]

    return total


def charges_sum(receipt):
    total = 0
    for charge in receipt["charges"]:
        if charge["amount_paise"] is not None:
            total += charge["amount_paise"]

    return total


def kind_sum(receipt, kind):
    total = 0
    for charge in receipt["charges"]:
        if charge["kind"] == kind and charge["amount_paise"] is not None:
            total += charge["amount_paise"]

    return total


def has_missing_line_totals(receipt):
    for item in receipt["items"]:
        if item["line_total_paise"] is None:
            return True

    return False


def has_missing_charge_amounts(receipt):
    for charge in receipt["charges"]:
        if charge["amount_paise"] is None:
            return True

    return False


def first_charge_of_kind(receipt, kind):
    for index, charge in enumerate(receipt["charges"]):
        if charge["kind"] == kind:
            return index

    return None


def first_charge_with_label(receipt, text):
    for index, charge in enumerate(receipt["charges"]):
        if charge["label"] is not None and text in charge["label"].lower():
            return index

    return None


def fill_subtotal(receipt):
    if receipt["subtotal_paise"] is not None:
        return []

    subtotal = items_sum(receipt)
    receipt["subtotal_paise"] = subtotal
    message = f"No subtotal was printed, so it was set to the items' total {rupees(subtotal)}"

    return [warning("SUBTOTAL_COMPUTED", "subtotal_paise", message)]


def check_no_items(receipt):
    if len(receipt["items"]) == 0:
        return [error("NO_ITEMS", "items", "The receipt has no items")]

    return []


def missing_item_fields(item, index):
    issues = []
    label = item_label(index)

    if is_blank(item["name"]):
        issues.append(error("FIELD_MISSING", f"items[{index}].name", f"{label} has no name"))

    if item["quantity"] is None:
        issues.append(error("FIELD_MISSING", f"items[{index}].quantity", f"{label} has no quantity"))

    if item["line_total_paise"] is None:
        issues.append(error("FIELD_MISSING", f"items[{index}].line_total_paise", f"{label} has no amount"))

    return issues


def check_missing_fields(receipt):
    issues = []

    for index, item in enumerate(receipt["items"]):
        issues.extend(missing_item_fields(item, index))

    for index, charge in enumerate(receipt["charges"]):
        if charge["amount_paise"] is None:
            message = f"{charge_label(charge, index)} has no amount"
            issues.append(error("FIELD_MISSING", f"charges[{index}].amount_paise", message))

    if receipt["total_paise"] is None:
        issues.append(error("FIELD_MISSING", "total_paise", "The total is missing"))

    return issues


def invalid_item_amounts(item, index):
    issues = []
    label = item_label(index)

    if item["line_total_paise"] is not None and item["line_total_paise"] < 0:
        message = f"{label} amount can't be negative"
        issues.append(error("INVALID_AMOUNT", f"items[{index}].line_total_paise", message))

    if item["unit_price_paise"] is not None and item["unit_price_paise"] < 0:
        message = f"{label} unit price can't be negative"
        issues.append(error("INVALID_AMOUNT", f"items[{index}].unit_price_paise", message))

    if item["quantity"] is not None and item["quantity"] <= 0:
        message = f"{label} quantity must be more than 0"
        issues.append(error("INVALID_AMOUNT", f"items[{index}].quantity", message))

    return issues


def invalid_charge_amount(charge, index):
    if charge["amount_paise"] is None or charge["amount_paise"] >= 0:
        return []

    if charge["kind"] != "tax" and charge["kind"] != "service_charge":
        return []

    message = f"{charge_label(charge, index)} can't be negative"

    return [error("INVALID_AMOUNT", f"charges[{index}].amount_paise", message)]


def check_invalid_amounts(receipt):
    issues = []

    for index, item in enumerate(receipt["items"]):
        issues.extend(invalid_item_amounts(item, index))

    for index, charge in enumerate(receipt["charges"]):
        issues.extend(invalid_charge_amount(charge, index))

    if receipt["total_paise"] is not None and receipt["total_paise"] <= 0:
        issues.append(error("INVALID_AMOUNT", "total_paise", "The total must be more than ₹0.00"))

    has_items = len(receipt["items"]) > 0
    if has_items and not has_missing_line_totals(receipt) and items_sum(receipt) <= 0:
        issues.append(error("INVALID_AMOUNT", "items", "Items must add up to more than ₹0.00"))

    return issues


def check_items_subtotal(receipt):
    if receipt["subtotal_paise"] is None or has_missing_line_totals(receipt):
        return []

    subtotal = receipt["subtotal_paise"]
    total = items_sum(receipt)
    if total == subtotal:
        return []

    message = f"Items add up to {rupees(total)} but the subtotal says {rupees(subtotal)}"

    return [error("ITEMS_SUBTOTAL_MISMATCH", "subtotal_paise", message, subtotal, total)]


def check_total(receipt):
    if receipt["subtotal_paise"] is None or receipt["total_paise"] is None:
        return []

    if has_missing_charge_amounts(receipt):
        return []

    computed = receipt["subtotal_paise"] + charges_sum(receipt)
    printed = receipt["total_paise"]
    if computed == printed:
        return []

    message = f"Subtotal plus charges is {rupees(computed)} but the total says {rupees(printed)}"

    return [error("TOTAL_MISMATCH", "total_paise", message, computed, printed)]


def check_discount_sign(receipt):
    issues = []

    for index, charge in enumerate(receipt["charges"]):
        if charge["kind"] != "discount" or charge["amount_paise"] is None:
            continue

        if charge["amount_paise"] > 0:
            message = f"{charge_label(charge, index)} should be a negative amount"
            issues.append(error("DISCOUNT_SIGN", f"charges[{index}].amount_paise", message))

    return issues


def validate_tip(tip_paise, tip_percent):
    issues = []

    if tip_paise < 0:
        issues.append(error("TIP_INVALID", "tip", "Tip can't be negative"))

    if tip_percent is not None and (tip_percent < 0 or tip_percent > 100):
        issues.append(error("TIP_INVALID", "tip", "Tip % must be between 0 and 100"))

    return issues


def line_math_issue(item, index):
    if item["unit_price_paise"] is None or item["quantity"] is None or item["line_total_paise"] is None:
        return []

    expected = round_half_up(item["quantity"] * item["unit_price_paise"])
    actual = item["line_total_paise"]
    if expected == actual:
        return []

    quantity = format_number(item["quantity"])
    unit_price = rupees(item["unit_price_paise"])
    message = f"{item_label(index)}: {quantity} × {unit_price} is {rupees(expected)} but the line says {rupees(actual)}"

    return [warning("LINE_MATH", f"items[{index}].line_total_paise", message, expected, actual)]


def check_line_math(receipt):
    issues = []

    for index, item in enumerate(receipt["items"]):
        issues.extend(line_math_issue(item, index))

    return issues


def tax_bases(receipt):
    subtotal = receipt["subtotal_paise"]
    service = kind_sum(receipt, "service_charge")
    discount = kind_sum(receipt, "discount")

    return [subtotal, subtotal + service, subtotal + discount, subtotal + discount + service]


def matches_some_base(amount, rate, bases):
    for base in bases:
        expected = Decimal(base) * rate / 100
        if abs(Decimal(amount) - expected) <= 100:
            return True

    return False


def tax_rate_issue(receipt, charge, index, bases):
    if charge["kind"] != "tax" or charge["rate_percent"] is None or charge["amount_paise"] is None:
        return []

    if matches_some_base(charge["amount_paise"], charge["rate_percent"], bases):
        return []

    expected = round_half_up(Decimal(receipt["subtotal_paise"]) * charge["rate_percent"] / 100)
    rate = format_number(charge["rate_percent"])
    message = f"{charge_label(charge, index)} doesn't match {rate}% of the subtotal"

    return [warning("TAX_RATE_MISMATCH", f"charges[{index}].amount_paise", message, expected, charge["amount_paise"])]


def check_tax_rates(receipt):
    if receipt["subtotal_paise"] is None:
        return []

    issues = []
    bases = tax_bases(receipt)

    for index, charge in enumerate(receipt["charges"]):
        issues.extend(tax_rate_issue(receipt, charge, index, bases))

    return issues


def check_cgst_sgst(receipt):
    cgst_index = first_charge_with_label(receipt, "cgst")
    sgst_index = first_charge_with_label(receipt, "sgst")
    if cgst_index is None or sgst_index is None:
        return []

    cgst = receipt["charges"][cgst_index]["amount_paise"]
    sgst = receipt["charges"][sgst_index]["amount_paise"]
    if cgst is None or sgst is None or cgst == sgst:
        return []

    message = f"CGST is {rupees(cgst)} but SGST is {rupees(sgst)}"

    return [warning("CGST_SGST_UNEQUAL", f"charges[{sgst_index}].amount_paise", message, cgst, sgst)]


def unusual_kind(receipt, kind, percent, message):
    index = first_charge_of_kind(receipt, kind)
    subtotal = receipt["subtotal_paise"]
    if index is None or subtotal is None or subtotal <= 0:
        return []

    if kind_sum(receipt, kind) * 100 <= subtotal * percent:
        return []

    return [warning("UNUSUAL_CHARGE", f"charges[{index}].amount_paise", message)]


def unusual_round_offs(receipt):
    issues = []

    for index, charge in enumerate(receipt["charges"]):
        if charge["kind"] != "round_off" or charge["amount_paise"] is None:
            continue

        if abs(charge["amount_paise"]) >= 100:
            message = f"Round off of {rupees(charge['amount_paise'])} is ₹1.00 or more"
            issues.append(warning("UNUSUAL_CHARGE", f"charges[{index}].amount_paise", message))

    return issues


def check_unusual_charges(receipt):
    issues = []
    issues.extend(unusual_kind(receipt, "service_charge", 20, "Service charge is more than 20% of the subtotal"))
    issues.extend(unusual_kind(receipt, "tax", 30, "Tax is more than 30% of the subtotal"))
    issues.extend(unusual_round_offs(receipt))

    return issues


def name_key(name):
    return " ".join(name.split()).lower()


def check_duplicates(receipt):
    issues = []
    seen = []

    for index, item in enumerate(receipt["items"]):
        if is_blank(item["name"]):
            continue

        key = (name_key(item["name"]), item["line_total_paise"])
        if key in seen:
            message = f"{item['name']} appears more than once with the same amount"
            issues.append(warning("POSSIBLE_DUPLICATE", f"items[{index}].name", message))

        seen.append(key)

    return issues


def check_quantities(receipt):
    issues = []

    for index, item in enumerate(receipt["items"]):
        quantity = item["quantity"]
        if quantity is None or quantity <= 0 or quantity == int(quantity):
            continue

        message = f"{item_label(index)} quantity {format_number(quantity)} isn't a whole number, so it will be shared equally"
        issues.append(warning("NON_INTEGER_QTY", f"items[{index}].quantity", message))

    return issues


def check_currency(receipt):
    if receipt["currency"] == "INR":
        return []

    message = f"Currency is {receipt['currency']}, but amounts are treated as INR"

    return [warning("NOT_INR", "currency", message)]


def validate_receipt(receipt):
    issues = []
    issues.extend(fill_subtotal(receipt))
    issues.extend(check_no_items(receipt))
    issues.extend(check_missing_fields(receipt))
    issues.extend(check_invalid_amounts(receipt))
    issues.extend(check_items_subtotal(receipt))
    issues.extend(check_total(receipt))
    issues.extend(check_discount_sign(receipt))
    issues.extend(check_line_math(receipt))
    issues.extend(check_tax_rates(receipt))
    issues.extend(check_cgst_sgst(receipt))
    issues.extend(check_unusual_charges(receipt))
    issues.extend(check_duplicates(receipt))
    issues.extend(check_quantities(receipt))
    issues.extend(check_currency(receipt))

    return issues


def model_warnings(receipt):
    issues = []
    for text in receipt["warnings"]:
        issues.append(warning("MODEL_WARNING", "receipt", text))

    return issues


def extract_issues(receipt):
    if not receipt["is_receipt"]:
        return [error("NOT_A_RECEIPT", "is_receipt", "This doesn't look like a receipt")]

    issues = validate_receipt(receipt)
    issues.extend(model_warnings(receipt))

    return issues


def has_errors(issues):
    for entry in issues:
        if entry["severity"] == "error":
            return True

    return False
