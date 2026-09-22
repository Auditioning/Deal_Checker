"""Logic Layer: business rules applied to AI-enriched deal records.

Owns all domain decisions (eligibility, expiry, duplicates, needs-review,
recommendations, usage/savings). No print()/input() and no persistence here.
"""

import difflib
from datetime import date, datetime, timedelta

ALLOWED_CATEGORIES = ["Food", "Retail", "Subscription", "Electronics", "Cosmetics", "Apparel"]

REQUIRED_FIELDS_FOR_ACTIVE = ["shop_name", "category", "expiry_date"]

EXPIRING_SOON_WINDOW_DAYS = 7
DUPLICATE_NAME_SIMILARITY_THRESHOLD = 0.8
DUPLICATE_PERCENTAGE_TOLERANCE = 5
DUPLICATE_PRICE_TOLERANCE_RATIO = 0.1


def missing_required_fields(deal):
    missing = [field for field in REQUIRED_FIELDS_FOR_ACTIVE if not deal.get(field)]
    if deal.get("eligibility_condition") == "unclear":
        missing.append("eligibility")
    return missing


def compute_expiry_status(expiry_date_str, today=None):
    if not expiry_date_str:
        return None
    try:
        expiry = datetime.strptime(expiry_date_str, "%Y-%m-%d").date()
    except ValueError:
        return None
    today = today or date.today()
    if expiry < today:
        return "expired"
    if expiry <= today + timedelta(days=EXPIRING_SOON_WINDOW_DAYS):
        return "expiring_soon"
    return "active"


def check_eligibility(eligibility_condition, profile):
    """Returns True/False, or None when eligibility can't be determined."""
    if eligibility_condition is None:
        return True
    if eligibility_condition == "unclear" or not isinstance(eligibility_condition, dict):
        return None
    if eligibility_condition.get("student_required") and not profile.get("is_student"):
        return False
    min_age = eligibility_condition.get("min_age")
    if min_age is not None:
        age = profile.get("age")
        if age is None or age < min_age:
            return False
    return True


def is_possible_duplicate(new_deal, existing_deals):
    new_shop = (new_deal.get("shop_name") or "").strip().lower()
    if not new_shop:
        return False, None
    for existing in existing_deals:
        if existing.get("status") == "expired":
            continue
        existing_shop = (existing.get("shop_name") or "").strip().lower()
        if not existing_shop:
            continue
        similarity = difflib.SequenceMatcher(None, new_shop, existing_shop).ratio()
        if similarity < DUPLICATE_NAME_SIMILARITY_THRESHOLD:
            continue
        if new_deal.get("category") != existing.get("category"):
            continue
        if _discount_is_similar(new_deal, existing):
            return True, existing.get("id")
    return False, None


def _discount_is_similar(deal_a, deal_b):
    pct_a, pct_b = deal_a.get("discount_percentage"), deal_b.get("discount_percentage")
    if pct_a is not None and pct_b is not None:
        return abs(pct_a - pct_b) <= DUPLICATE_PERCENTAGE_TOLERANCE

    price_a, price_b = deal_a.get("discounted_price"), deal_b.get("discounted_price")
    if price_a is not None and price_b is not None and price_b != 0:
        return abs(price_a - price_b) / price_b <= DUPLICATE_PRICE_TOLERANCE_RATIO

    return pct_a is None and pct_b is None and price_a is None and price_b is None


def is_recommended(deal):
    """Multi-condition rule combining several AI-derived fields: only
    recommend a deal that is eligible for this user AND currently usable
    (active/expiring soon, not already used)."""
    if deal.get("eligible_for_user") is not True:
        return False
    if deal.get("status") not in ("active", "expiring_soon"):
        return False
    if deal.get("used"):
        return False
    return True


def evaluate_new_deal(deal, profile, existing_deals):
    """Applies every business rule to a single AI-extracted deal record and
    returns (updated_deal, human_readable_notes)."""
    notes = []

    missing = missing_required_fields(deal)
    deal["missing_fields"] = missing
    if missing:
        deal["status"] = "needs_review"
        deal["eligible_for_user"] = None
        deal["possible_duplicate"] = False
        deal["duplicate_of"] = None
        deal["recommended"] = False
        notes.append("Missing required fields: " + ", ".join(missing))
        return deal, notes

    is_dup, dup_id = is_possible_duplicate(deal, existing_deals)
    deal["possible_duplicate"] = is_dup
    deal["duplicate_of"] = dup_id if is_dup else None

    expiry_status = compute_expiry_status(deal.get("expiry_date"))
    eligible = check_eligibility(deal.get("eligibility_condition"), profile)
    deal["eligible_for_user"] = eligible
    deal["status"] = expiry_status or "active"
    deal["recommended"] = is_recommended(deal)

    if is_dup:
        notes.append(f"Possible duplicate of deal #{dup_id}.")
    notes.append(f"Expiry status: {deal['status']}")
    notes.append(f"Eligible for you: {eligible}")
    return deal, notes


def refresh_deal_status(deal, today=None):
    """Re-checks a stored deal's expiry status against the current date."""
    if deal.get("status") in ("needs_review", "used"):
        return deal
    new_status = compute_expiry_status(deal.get("expiry_date"), today)
    if new_status:
        deal["status"] = new_status
        deal["recommended"] = is_recommended(deal)
    return deal


def refresh_all_statuses(deals, today=None):
    for deal in deals:
        refresh_deal_status(deal, today)
    return deals


def can_use_deal(deal, user_spend=None):
    min_spend = deal.get("min_spend")
    if min_spend is None:
        return True, None
    if user_spend is None:
        return False, f"This deal requires a minimum spend of ${min_spend:.2f}."
    if user_spend < min_spend:
        return False, f"Your spend (${user_spend:.2f}) is below the minimum spend of ${min_spend:.2f}."
    return True, None


def mark_deal_used(deal, amount_saved):
    deal["used"] = True
    deal["status"] = "used"
    deal["amount_saved"] = amount_saved
    deal["recommended"] = False
    return deal


def compute_savings_summary(deals):
    used = [deal for deal in deals if deal.get("used")]
    unused = [deal for deal in deals if not deal.get("used") and deal.get("status") in ("active", "expiring_soon")]
    total_savings = sum(deal.get("amount_saved") or 0 for deal in used)
    return {
        "total_savings": total_savings,
        "used_count": len(used),
        "unused_count": len(unused),
    }
