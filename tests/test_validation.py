import json
from decimal import Decimal
from pathlib import Path

from app.extraction import normalise
from app.validation import extract_issues, has_errors, validate_receipt, validate_tip

SAMPLES = Path(__file__).parent.parent / "samples"


def load_sample(name):
    with open(SAMPLES / name, encoding="utf-8") as file:
        return json.load(file)


def receipt_2():
    receipt, issues = normalise(load_sample("receipt_2.expected.json"))

    return receipt


def not_a_receipt_output():
    return {
        "is_receipt": False,
        "merchant": None,
        "date": None,
        "currency": None,
        "items": [],
        "subtotal": None,
        "charges": [],
        "total": None,
        "warnings": [],
    }


def codes(issues):
    result = []
    for entry in issues:
        result.append(entry["code"])

    return result


def fields_for(issues, code):
    result = []
    for entry in issues:
        if entry["code"] == code:
            result.append(entry["field"])

    return result


def find(issues, code):
    for entry in issues:
        if entry["code"] == code:
            return entry

    return None


def test_normalise_converts_to_paise():
    receipt, issues = normalise(load_sample("receipt_2.expected.json"))

    assert issues == []
    assert receipt["currency"] == "INR"
    assert receipt["bill_date"] == "2026-09-28"
    assert receipt["items"][0]["quantity"] == Decimal("4")
    assert receipt["items"][0]["unit_price_paise"] == 6000
    assert receipt["items"][0]["line_total_paise"] == 24000
    assert receipt["subtotal_paise"] == 145000
    assert receipt["charges"][0]["amount_paise"] == -14500
    assert receipt["charges"][1]["rate_percent"] == Decimal("2.5")
    assert receipt["charges"][3]["amount_paise"] == -26
    assert receipt["total_paise"] == 137000
    assert receipt["suggested_tip_paise"] == 0


def test_normalise_moves_tip_out_of_charges():
    llm_output = load_sample("receipt_2.expected.json")
    llm_output["charges"].append({"label": "Tip", "kind": "tip", "rate_percent": None, "amount": 100.00})

    receipt, issues = normalise(llm_output)

    assert len(receipt["charges"]) == 4
    assert receipt["suggested_tip_paise"] == 10000


def test_clean_receipt_has_no_issues():
    receipt, issues = normalise(load_sample("receipt_2.expected.json"))

    issues.extend(extract_issues(receipt))

    assert issues == []


def test_sample_3_only_flags_items_subtotal_mismatch():
    receipt, issues = normalise(load_sample("receipt_3.expected.json"))

    issues.extend(extract_issues(receipt))

    assert codes(issues) == ["ITEMS_SUBTOTAL_MISMATCH"]
    assert issues[0]["severity"] == "error"
    assert issues[0]["field"] == "subtotal_paise"
    assert issues[0]["expected"] == 118000
    assert issues[0]["actual"] == 113000


def test_not_a_receipt():
    receipt, issues = normalise(not_a_receipt_output())

    issues = extract_issues(receipt)

    assert codes(issues) == ["NOT_A_RECEIPT"]
    assert issues[0]["severity"] == "error"


def test_no_items():
    receipt = receipt_2()
    receipt["items"] = []

    issues = validate_receipt(receipt)

    assert find(issues, "NO_ITEMS")["severity"] == "error"


def test_field_missing():
    receipt = receipt_2()
    receipt["items"][1]["name"] = "  "
    receipt["items"][2]["quantity"] = None
    receipt["items"][3]["line_total_paise"] = None
    receipt["charges"][1]["amount_paise"] = None
    receipt["total_paise"] = None

    issues = validate_receipt(receipt)

    assert fields_for(issues, "FIELD_MISSING") == [
        "items[1].name",
        "items[2].quantity",
        "items[3].line_total_paise",
        "charges[1].amount_paise",
        "total_paise",
    ]
    assert has_errors(issues)


def test_invalid_amount_negative_values():
    receipt = receipt_2()
    receipt["items"][0]["line_total_paise"] = -24000
    receipt["items"][1]["unit_price_paise"] = -100
    receipt["items"][2]["quantity"] = Decimal("0")
    receipt["charges"][1]["amount_paise"] = -3263
    receipt["total_paise"] = 0

    issues = validate_receipt(receipt)

    assert fields_for(issues, "INVALID_AMOUNT") == [
        "items[0].line_total_paise",
        "items[1].unit_price_paise",
        "items[2].quantity",
        "charges[1].amount_paise",
        "total_paise",
    ]


def test_invalid_amount_items_add_up_to_zero():
    receipt = receipt_2()
    for item in receipt["items"]:
        item["line_total_paise"] = 0

    issues = validate_receipt(receipt)

    assert fields_for(issues, "INVALID_AMOUNT") == ["items"]


def test_invalid_amount_more_than_two_decimals():
    llm_output = load_sample("receipt_2.expected.json")
    llm_output["items"][0]["line_total"] = 240.005
    llm_output["total"] = 1370.001

    receipt, issues = normalise(llm_output)

    assert fields_for(issues, "INVALID_AMOUNT") == ["items[0].line_total_paise", "total_paise"]
    assert receipt["items"][0]["line_total_paise"] == 24001
    assert receipt["total_paise"] == 137000


def test_items_subtotal_mismatch():
    receipt = receipt_2()
    receipt["subtotal_paise"] = 150000

    issues = validate_receipt(receipt)

    mismatch = find(issues, "ITEMS_SUBTOTAL_MISMATCH")
    assert mismatch["severity"] == "error"
    assert mismatch["expected"] == 150000
    assert mismatch["actual"] == 145000


def test_total_mismatch():
    receipt = receipt_2()
    receipt["total_paise"] = 137050

    issues = validate_receipt(receipt)

    mismatch = find(issues, "TOTAL_MISMATCH")
    assert mismatch["severity"] == "error"
    assert mismatch["field"] == "total_paise"
    assert mismatch["expected"] == 137000
    assert mismatch["actual"] == 137050
    assert mismatch["message"] == "Subtotal plus charges is ₹1,370.00 but the total says ₹1,370.50"


def test_discount_sign():
    receipt = receipt_2()
    receipt["charges"][0]["amount_paise"] = 14500

    issues = validate_receipt(receipt)

    assert fields_for(issues, "DISCOUNT_SIGN") == ["charges[0].amount_paise"]
    assert find(issues, "DISCOUNT_SIGN")["severity"] == "error"


def test_tip_invalid():
    assert codes(validate_tip(-1, None)) == ["TIP_INVALID"]
    assert codes(validate_tip(0, Decimal("150"))) == ["TIP_INVALID"]
    assert codes(validate_tip(0, Decimal("-5"))) == ["TIP_INVALID"]
    assert validate_tip(14500, Decimal("10")) == []


def test_line_math():
    receipt = receipt_2()
    receipt["items"][0]["unit_price_paise"] = 6500

    issues = validate_receipt(receipt)

    assert codes(issues) == ["LINE_MATH"]
    assert issues[0]["severity"] == "warning"
    assert issues[0]["expected"] == 26000
    assert issues[0]["actual"] == 24000
    assert not has_errors(issues)


def test_subtotal_computed():
    receipt = receipt_2()
    receipt["subtotal_paise"] = None

    issues = validate_receipt(receipt)

    assert codes(issues) == ["SUBTOTAL_COMPUTED"]
    assert receipt["subtotal_paise"] == 145000
    assert not has_errors(issues)


def test_tax_rate_mismatch():
    receipt = receipt_2()
    receipt["charges"][1]["rate_percent"] = Decimal("5")

    issues = validate_receipt(receipt)

    assert codes(issues) == ["TAX_RATE_MISMATCH"]
    assert issues[0]["field"] == "charges[1].amount_paise"
    assert not has_errors(issues)


def test_tax_rate_within_one_rupee_is_fine():
    receipt = receipt_2()
    receipt["charges"][1]["amount_paise"] = 3350
    receipt["charges"][2]["amount_paise"] = 3350
    receipt["total_paise"] = 137174

    issues = validate_receipt(receipt)

    assert issues == []


def test_cgst_sgst_unequal():
    receipt = receipt_2()
    receipt["charges"][2]["amount_paise"] = 3264
    receipt["total_paise"] = 137001

    issues = validate_receipt(receipt)

    assert codes(issues) == ["CGST_SGST_UNEQUAL"]
    assert issues[0]["field"] == "charges[2].amount_paise"
    assert issues[0]["expected"] == 3263
    assert issues[0]["actual"] == 3264


def test_unusual_charge():
    receipt = receipt_2()
    receipt["charges"][3]["amount_paise"] = -100
    receipt["total_paise"] = 136926

    issues = validate_receipt(receipt)

    assert codes(issues) == ["UNUSUAL_CHARGE"]
    assert issues[0]["field"] == "charges[3].amount_paise"
    assert not has_errors(issues)


def test_possible_duplicate():
    receipt = receipt_2()
    receipt["items"].append(dict(receipt["items"][0]))
    receipt["subtotal_paise"] = 169000
    receipt["total_paise"] = 161000

    issues = validate_receipt(receipt)

    assert fields_for(issues, "POSSIBLE_DUPLICATE") == ["items[5].name"]
    assert find(issues, "POSSIBLE_DUPLICATE")["severity"] == "warning"


def test_non_integer_qty():
    receipt = receipt_2()
    receipt["items"][2]["quantity"] = Decimal("1.5")
    receipt["items"][2]["unit_price_paise"] = None

    issues = validate_receipt(receipt)

    assert codes(issues) == ["NON_INTEGER_QTY"]
    assert issues[0]["field"] == "items[2].quantity"
    assert not has_errors(issues)


def test_not_inr():
    receipt = receipt_2()
    receipt["currency"] = "USD"

    issues = validate_receipt(receipt)

    assert codes(issues) == ["NOT_INR"]
    assert not has_errors(issues)


def test_model_warning():
    llm_output = load_sample("receipt_2.expected.json")
    llm_output["warnings"] = ["The total is smudged"]
    receipt, issues = normalise(llm_output)

    issues = extract_issues(receipt)

    assert codes(issues) == ["MODEL_WARNING"]
    assert issues[0]["message"] == "The total is smudged"
    assert not has_errors(issues)


def test_has_errors():
    receipt = receipt_2()
    receipt["total_paise"] = 1

    assert has_errors(validate_receipt(receipt))
    assert not has_errors(validate_receipt(receipt_2()))
