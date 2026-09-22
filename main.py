"""Deal Tracker CLI - entry point and orchestration.

Pipeline: io_manager (input) -> ai_manager (structured extraction)
-> logic_manager (business rules) -> data_manager (persistence).

This module only wires the four managers together; it holds no print()/
input() calls of its own and no business rules.
"""

from datetime import date

from managers import ai_manager, data_manager, io_manager, logic_manager


def _load_and_refresh_deals():
    deals = data_manager.load_deals()
    deals = logic_manager.refresh_all_statuses(deals)
    data_manager.save_deals(deals)
    return deals


def _replace_deal(deals, updated_deal):
    for index, existing in enumerate(deals): # Replace the deal in the list with the updated one
        if existing.get("id") == updated_deal.get("id"): # If the deal IDs match
            deals[index] = updated_deal
            break
    return deals


def handle_add_deal():
    raw_text = io_manager.get_raw_deal_text()
    if raw_text is None:
        return

    ai_result = ai_manager.extract_deal_info(raw_text, logic_manager.ALLOWED_CATEGORIES)
    io_manager.show_extraction_result(ai_result)

    deals = _load_and_refresh_deals()
    profile = data_manager.load_profile()

    deal = dict(ai_result["data"])
    deal.update(
        {
            "id": data_manager.next_deal_id(deals),
            "raw_input": raw_text,
            "used": False,
            "amount_saved": None,
            "date_added": date.today().isoformat(),
        }
    )

    deal, notes = logic_manager.evaluate_new_deal(deal, profile, deals)
    io_manager.show_deal_evaluation(deal, notes)

    if deal.get("possible_duplicate"):
        if not io_manager.confirm_duplicate_save(deal, deal.get("duplicate_of")):
            io_manager.print_message("Deal discarded.")
            return

    if deal["status"] == "needs_review":
        if io_manager.confirm(
            f"This deal needs review ({', '.join(deal['missing_fields'])}). Fill in the missing details now?"
        ):
            updates = io_manager.prompt_manual_fields(deal["missing_fields"], logic_manager.ALLOWED_CATEGORIES)
            deal.update(updates)
            deal, notes = logic_manager.evaluate_new_deal(deal, profile, deals)
            io_manager.show_deal_evaluation(deal, notes)
            if deal.get("possible_duplicate"):
                if not io_manager.confirm_duplicate_save(deal, deal.get("duplicate_of")):
                    io_manager.print_message("Deal discarded.")
                    return

    deals.append(deal)
    data_manager.save_deals(deals)
    io_manager.print_message("Deal saved.")


def handle_view_deals():
    deals = _load_and_refresh_deals()
    choice = io_manager.view_deals_menu()
    if choice == "1":
        io_manager.show_deal_list(deals, "All deals")
    elif choice == "2":
        active_eligible = [
            deal for deal in deals
            if deal.get("status") in ("active", "expiring_soon") and deal.get("eligible_for_user")
        ]
        io_manager.show_deal_list(active_eligible, "Active & eligible for you")
    elif choice == "3":
        expiring = [deal for deal in deals if deal.get("status") == "expiring_soon"]
        io_manager.show_deal_list(expiring, "Expiring soon")
    elif choice == "4":
        used = [deal for deal in deals if deal.get("used")]
        io_manager.show_deal_list(used, "Used deals")
    elif choice == "0":
        return
    else:
        io_manager.print_error("Invalid option.")


def handle_needs_review():
    deals = _load_and_refresh_deals()
    review_deals = [deal for deal in deals if deal.get("status") == "needs_review"]
    io_manager.show_needs_review_list(review_deals)
    if not review_deals:
        return

    deal = io_manager.prompt_deal_id(review_deals, "review")
    if deal is None:
        return

    profile = data_manager.load_profile()
    updates = io_manager.prompt_manual_fields(deal["missing_fields"], logic_manager.ALLOWED_CATEGORIES)
    deal.update(updates)

    other_deals = [existing for existing in deals if existing.get("id") != deal.get("id")]
    deal, notes = logic_manager.evaluate_new_deal(deal, profile, other_deals)
    io_manager.show_deal_evaluation(deal, notes)

    deals = _replace_deal(deals, deal)
    data_manager.save_deals(deals)
    io_manager.print_message("Deal updated.")


def handle_mark_used():
    deals = _load_and_refresh_deals()
    usable = [deal for deal in deals if not deal.get("used") and deal.get("status") in ("active", "expiring_soon")]
    deal = io_manager.prompt_deal_id(usable, "mark as used")
    if deal is None:
        return

    user_spend = io_manager.prompt_mark_used(deal)
    can_use, reason = logic_manager.can_use_deal(deal, user_spend)
    if not can_use:
        io_manager.print_error(reason)
        return

    amount_saved = io_manager.prompt_amount_saved()
    deal = logic_manager.mark_deal_used(deal, amount_saved)

    deals = _replace_deal(deals, deal)
    data_manager.save_deals(deals)
    io_manager.print_message("Deal marked as used. Nice savings!")


def handle_profile(): # Handle profile management
    profile = data_manager.load_profile()
    io_manager.show_profile(profile)
    if io_manager.confirm("Update your profile?"):
        profile = io_manager.prompt_profile()
        data_manager.save_profile(profile)
        io_manager.print_message("Profile updated.")


def handle_summary():
    deals = _load_and_refresh_deals()
    summary = logic_manager.compute_savings_summary(deals)
    io_manager.show_summary(summary)


MENU_ACTIONS = {
    "1": handle_add_deal,
    "2": handle_view_deals,
    "3": handle_needs_review,
    "4": handle_mark_used,
    "5": handle_profile,
    "6": handle_summary,
}


def main():
    data_manager.load_profile()
    _load_and_refresh_deals()

    while True:
        choice = io_manager.show_main_menu()
        if choice == "0":
            io_manager.print_message("Goodbye!")
            break
        action = MENU_ACTIONS.get(choice)
        if action is None:
            io_manager.print_error("Invalid option, try again.")
            continue
        action()
        io_manager.press_enter_to_continue()


if __name__ == "__main__":
    main()
