"""Input/Output Layer: the only module in the system allowed to call
print()/input(). Handles all terminal boundaries: prompting, validating,
re-prompting, and formatting/display of records and lists.
"""

from datetime import datetime


def print_message(message):
    print(message)


def print_error(message):
    print(f"[ERROR] {message}")


def print_warning(message):
    print(f"[WARNING] {message}")


def press_enter_to_continue():
    input("\nPress Enter to continue...")


def show_main_menu():
    print("\n" + "=" * 50)
    print("  DEAL TRACKER")
    print("=" * 50)
    print("1. Add a new deal")
    print("2. View my deals")
    print("3. Review deals needing attention")
    print("4. Mark a deal as used")
    print("5. Update my profile")
    print("6. View savings summary")
    print("0. Exit")
    return input("Choose an option: ").strip()


def get_raw_deal_text():
    print("\nPaste/type the deal details below (as they appeared in the ad/email/screenshot).")
    print("Example: 'Get 20% off at Starbucks, students only, min spend $10, expires 31 Aug 2026'")
    print("Tip: name the store using 'at <Shop Name>' so it can be picked up reliably.")
    text = input("> ").strip()
    if not text:
        print_error("No text entered. Cancelling.")
        return None
    return text


def show_extraction_result(ai_result):
    if not ai_result["valid"]:
        print_warning(
            f"AI extraction had issues after {ai_result['attempts']} attempt(s): "
            + ", ".join(ai_result["errors"])
        )
    else:
        print_message(f"AI extracted the deal details (attempt {ai_result['attempts']}).")


def show_deal_evaluation(deal, notes):
    print("\n--- Deal Summary ---")
    print(format_deal(deal))
    for note in notes:
        print(f"  * {note}")


def format_deal(deal):
    lines = [
        f"ID: {deal.get('id')}",
        f"Shop: {deal.get('shop_name') or '(unknown)'}",
        f"Category: {deal.get('category') or '(unknown)'}",
        f"Price: {_format_price(deal)}",
        f"Expiry: {deal.get('expiry_date') or '(unknown)'}",
        f"Eligibility: {deal.get('eligibility_raw') or 'Open to everyone'}",
        f"Min spend: {'$' + format(deal['min_spend'], '.2f') if deal.get('min_spend') is not None else '-'}",
        f"Status: {deal.get('status')}"
        + (" [POSSIBLE DUPLICATE]" if deal.get("possible_duplicate") else ""),
        f"Eligible for you: {deal.get('eligible_for_user')}",
        f"Recommended: {deal.get('recommended')}",
        f"Used: {deal.get('used')}"
        + (f" (saved ${deal['amount_saved']:.2f})" if deal.get("used") and deal.get("amount_saved") is not None else ""),
    ]
    return "\n".join(lines)


def _format_price(deal):
    original = deal.get("original_price")
    discounted = deal.get("discounted_price")
    pct = deal.get("discount_percentage")
    parts = []
    if original is not None:
        parts.append(f"was ${original:.2f}")
    if discounted is not None:
        parts.append(f"now ${discounted:.2f}")
    if pct is not None:
        parts.append(f"({pct:.0f}% off)")
    return " ".join(parts) if parts else "(unknown)"


def confirm(prompt_text):
    answer = input(f"{prompt_text} (y/n): ").strip().lower()
    return answer in ("y", "yes")


def confirm_duplicate_save(deal, dup_id):
    return confirm(
        f"This deal looks like a possible duplicate of deal #{dup_id}. Save it anyway as a separate deal?"
    )


def prompt_manual_fields(missing_fields, allowed_categories):
    updates = {}
    for field in missing_fields:
        if field == "shop_name":
            updates["shop_name"] = _prompt_nonempty("Enter the shop/brand name: ")
        elif field == "category":
            updates["category"] = _prompt_category(allowed_categories)
        elif field == "expiry_date":
            updates["expiry_date"] = _prompt_date("Enter the expiry date (YYYY-MM-DD): ")
        elif field == "eligibility":
            condition, raw = _prompt_eligibility()
            updates["eligibility_condition"] = condition
            updates["eligibility_raw"] = raw
    return updates


def _prompt_nonempty(prompt_text):
    while True:
        value = input(prompt_text).strip()
        if value:
            return value
        print_error("This field can't be empty.")


def _prompt_category(allowed_categories):
    while True:
        print("Choose a category:")
        for index, category in enumerate(allowed_categories, start=1):
            print(f"  {index}. {category}")
        choice = input("Enter number: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(allowed_categories):
            return allowed_categories[int(choice) - 1]
        print_error("Invalid choice, try again.")


def _prompt_date(prompt_text):
    while True:
        value = input(prompt_text).strip()
        try:
            datetime.strptime(value, "%Y-%m-%d")
            return value
        except ValueError:
            print_error("Please use the format YYYY-MM-DD (e.g. 2026-08-31).")


def _prompt_eligibility():
    print("Is this deal restricted to certain people?")
    print("  1. No restriction")
    print("  2. Students only")
    print("  3. Minimum age")
    while True:
        choice = input("Enter number: ").strip()
        if choice == "1":
            return None, None
        if choice == "2":
            return {"student_required": True}, "Students only"
        if choice == "3":
            age = _prompt_int("Minimum age: ")
            return {"min_age": age}, f"Age {age}+ only"
        print_error("Invalid choice, try again.")


def _prompt_int(prompt_text):
    while True:
        value = input(prompt_text).strip()
        if value.isdigit():
            return int(value)
        print_error("Please enter a whole number.")


def _prompt_float(prompt_text):
    while True:
        value = input(prompt_text).strip()
        try:
            return float(value)
        except ValueError:
            print_error("Please enter a valid number.")


def show_deal_list(deals, title="Your deals"):
    print(f"\n--- {title} ---")
    if not deals:
        print("(no deals to show)")
        return
    for deal in deals:
        flags = ""
        if deal.get("recommended"):
            flags += " [RECOMMENDED]"
        if deal.get("possible_duplicate"):
            flags += " [POSSIBLE DUPLICATE]"
        print(
            f"#{deal.get('id')} | {deal.get('shop_name') or '?'} | {deal.get('category') or '?'} | "
            f"{deal.get('status')} | eligible={deal.get('eligible_for_user')}{flags}"
        )


def view_deals_menu():
    print("\nView deals:")
    print("1. All deals")
    print("2. Active & eligible for you")
    print("3. Expiring soon")
    print("4. Used deals")
    print("0. Back")
    return input("Choose an option: ").strip()


def prompt_deal_id(deals, action_text="select"):
    if not deals:
        print_error("No deals available.")
        return None
    show_deal_list(deals)
    value = input(f"Enter the deal ID to {action_text} (0 to cancel): ").strip()
    if not value.isdigit():
        print_error("Invalid ID.")
        return None
    deal_id = int(value)
    if deal_id == 0:
        return None
    match = next((deal for deal in deals if deal.get("id") == deal_id), None)
    if not match:
        print_error("No deal with that ID.")
        return None
    return match


def prompt_mark_used(deal):
    print(format_deal(deal))
    if deal.get("min_spend") is not None:
        return _prompt_float(f"This deal needs a minimum spend of ${deal['min_spend']:.2f}. Enter your spend amount: $")
    return None


def prompt_amount_saved():
    return _prompt_float("How much did you save by using this deal? $")


def show_profile(profile):
    print("\n--- Your Profile ---")
    print(f"Student: {'Yes' if profile.get('is_student') else 'No'}")
    print(f"Age: {profile.get('age') if profile.get('age') is not None else '(not set)'}")


def prompt_profile():
    is_student = confirm("Are you a student?")
    age = _prompt_int("Enter your age: ")
    return {"is_student": is_student, "age": age}


def show_summary(summary):
    print("\n--- Savings Summary ---")
    print(f"Total savings: ${summary['total_savings']:.2f}")
    print(f"Deals used: {summary['used_count']}")
    print(f"Deals unused (active/expiring soon): {summary['unused_count']}")


def show_needs_review_list(deals):
    show_deal_list(deals, title="Deals needing review")
