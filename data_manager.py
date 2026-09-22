"""Data Layer: flat-file persistence for deals and the user profile.

No print()/input() calls live here (all terminal I/O belongs to io_manager),
and no business rules live here (that belongs to logic_manager).
"""

import json
import os

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
DEALS_FILE = os.path.join(DATA_DIR, "deals.json")
PROFILE_FILE = os.path.join(DATA_DIR, "profile.json")

DEFAULT_PROFILE = {
    "is_student": False,
    "age": None,
}


def _ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def load_deals():
    _ensure_data_dir()
    if not os.path.exists(DEALS_FILE):
        save_deals([])
        return []
    with open(DEALS_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []


def save_deals(deals):
    _ensure_data_dir()
    with open(DEALS_FILE, "w", encoding="utf-8") as f:
        json.dump(deals, f, indent=2)


def load_profile():
    _ensure_data_dir()
    if not os.path.exists(PROFILE_FILE):
        save_profile(dict(DEFAULT_PROFILE))
        return dict(DEFAULT_PROFILE)
    with open(PROFILE_FILE, "r", encoding="utf-8") as f:
        try:
            profile = json.load(f)
        except json.JSONDecodeError:
            profile = {}
    merged = dict(DEFAULT_PROFILE)
    merged.update(profile)
    return merged


def save_profile(profile):
    _ensure_data_dir()
    with open(PROFILE_FILE, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2)


def next_deal_id(deals):
    if not deals:
        return 1
    return max(deal.get("id", 0) for deal in deals) + 1
