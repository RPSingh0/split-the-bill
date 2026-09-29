from decimal import ROUND_HALF_UP, Decimal


def round_half_up(value):
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def rupees(paise):
    sign = ""
    if paise < 0:
        sign = "-"

    value = Decimal(abs(paise)) / 100

    return f"{sign}₹{value:,.2f}"
