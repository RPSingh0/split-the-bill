from app.split import claim_mode, compute_split


def claim_list(item):
    claims = []
    for claim in item.claims:
        claims.append({"participant_id": claim.participant_id, "units": claim.units})

    return claims


def units_claimed(item):
    total = 0
    for claim in item.claims:
        total += claim.units

    return total


def item_view(item):
    mode = claim_mode(item.quantity)

    max_units = None
    if mode == "units":
        max_units = int(item.quantity)

    return {
        "id": item.id,
        "name": item.name,
        "quantity": item.quantity,
        "unit_price_paise": item.unit_price_paise,
        "line_total_paise": item.line_total_paise,
        "claim_mode": mode,
        "max_units": max_units,
        "units_claimed": units_claimed(item),
        "claims": claim_list(item),
    }


def charge_view(charge):
    return {
        "label": charge.label,
        "kind": charge.kind,
        "rate_percent": charge.rate_percent,
        "amount_paise": charge.amount_paise,
    }


def participant_view(participant):
    return {
        "id": participant.id,
        "display_name": participant.display_name,
        "is_host": participant.user_id is not None,
        "joined_at": participant.joined_at,
    }


def me_view(participant):
    return {"participant_id": participant.id, "is_host": participant.user_id is not None}


def item_views(bill):
    views = []
    for item in bill.items:
        views.append(item_view(item))

    return views


def charge_views(bill):
    views = []
    for charge in bill.charges:
        views.append(charge_view(charge))

    return views


def participant_views(bill):
    views = []
    for participant in bill.participants:
        views.append(participant_view(participant))

    return views


def participants_for_split(bill):
    participants = []
    for participant in bill.participants:
        participants.append({"id": participant.id, "display_name": participant.display_name})

    return participants


def items_for_split(bill):
    items = []
    for item in bill.items:
        items.append({
            "id": item.id,
            "quantity": item.quantity,
            "line_total_paise": item.line_total_paise,
            "claims": claim_list(item),
        })

    return items


def charges_for_split(bill):
    charges = []
    for charge in bill.charges:
        charges.append({"kind": charge.kind, "amount_paise": charge.amount_paise})

    return charges


def bill_split(bill):
    return compute_split(
        participants_for_split(bill),
        items_for_split(bill),
        charges_for_split(bill),
        bill.tip_paise,
    )


def cancelled_view(bill):
    return {
        "slug": bill.slug,
        "status": bill.status,
        "version": bill.version,
        "host_name": bill.owner.username,
    }


def build_bill_view(bill, me):
    if bill.status == "cancelled":
        return cancelled_view(bill)

    return {
        "slug": bill.slug,
        "status": bill.status,
        "version": bill.version,
        "merchant": bill.merchant,
        "bill_date": bill.bill_date,
        "currency": bill.currency,
        "host_name": bill.owner.username,
        "items": item_views(bill),
        "charges": charge_views(bill),
        "subtotal_paise": bill.subtotal_paise,
        "total_paise": bill.total_paise,
        "tip_paise": bill.tip_paise,
        "tip_percent": bill.tip_percent,
        "grand_total_paise": bill.total_paise + bill.tip_paise,
        "participants": participant_views(bill),
        "split": bill_split(bill),
        "me": me_view(me),
    }
