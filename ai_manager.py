"""AI Processing Layer: calls the Groq API to turn raw deal text into a
structured record, and validates the response schema before it's used
downstream.

Every new deal passes through `extract_deal_info`, which calls the real
Groq chat-completions API (JSON mode) and validates the shape of what comes
back, retrying (with the previous errors fed back to the model) on a
malformed response. API failures (missing key, network errors, timeouts,
bad responses) are logged to data/ai_errors.log and returned as a graceful
failure rather than raised -- the caller then routes the deal to
needs_review instead of the app crashing.

This module contains zero domain/business logic (no eligibility rules, no
expiry rules, no duplicate detection) -- only extraction and schema checks.
"""

import json
import logging
import os
import urllib.error
import urllib.request
from datetime import datetime

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-oss-120b"
REQUEST_TIMEOUT_SECONDS = 30
FIXED_SEED = 7

_SCHEMA_KEYS = {
    "shop_name",
    "category",
    "original_price",
    "discounted_price",
    "discount_percentage",
    "expiry_date",
    "eligibility_raw",
    "eligibility_condition",
    "min_spend",
    "description",
}

_EMPTY_RESPONSE = {key: None for key in _SCHEMA_KEYS}

_SYSTEM_PROMPT_TEMPLATE = """You are a data-extraction engine for a deals-tracking app.
Given raw deal/promo text, extract structured JSON with EXACTLY these keys:
shop_name (string or null)
category (one of {categories} or null -- only use one of these, never invent a new category)
original_price (number or null)
discounted_price (number or null)
discount_percentage (number or null)
expiry_date (string "YYYY-MM-DD" or null)
eligibility_raw (short string describing any restriction, or null)
eligibility_condition (null, or the string "unclear", or an object with optional keys \
student_required (bool) and/or min_age (int))
min_spend (number or null)
description (string, a short cleaned summary of the deal)

If a field can't be confidently determined from the text, use null rather than guessing.
Respond with JSON ONLY, no extra commentary, no markdown fences."""


def _load_dotenv():
    """Tiny stdlib-only .env loader (no python-dotenv dependency). Sets
    variables found in a .env file at the project root, without overriding
    anything already present in the real environment (e.g. `docker run -e`)."""
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_path = os.path.join(project_root, ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()


def _get_logger():
    logger = logging.getLogger("ai_manager")
    if not logger.handlers:
        log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
        os.makedirs(log_dir, exist_ok=True)
        handler = logging.FileHandler(os.path.join(log_dir, "ai_errors.log"), encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.ERROR)
        logger.propagate = False
    return logger


def extract_deal_info(raw_text, allowed_categories, max_attempts=2):
    """Calls the Groq API to extract a structured deal record from raw text.

    Returns {"data": <schema dict>, "valid": bool, "errors": [...], "attempts": n}.
    """
    attempts = 0
    response, errors = dict(_EMPTY_RESPONSE), []
    previous_errors = None

    while attempts < max_attempts:
        attempts += 1
        api_response, call_error = _call_groq_api(raw_text, allowed_categories, previous_errors)

        if call_error:
            _get_logger().error("Groq API call failed (attempt %d): %s", attempts, call_error)
            response = dict(_EMPTY_RESPONSE)
            response["description"] = raw_text
            errors = [f"api_error: {call_error}"]
            previous_errors = None
            continue

        valid, schema_errors = _validate_schema(api_response, allowed_categories)
        response, errors = api_response, schema_errors
        if valid:
            return {"data": response, "valid": True, "errors": [], "attempts": attempts}
        previous_errors = schema_errors

    return {"data": response, "valid": False, "errors": errors, "attempts": attempts}


def _call_groq_api(raw_text, allowed_categories, previous_errors):
    """Returns (parsed_dict_or_None, error_message_or_None)."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return None, "GROQ_API_KEY is not set"

    model = os.environ.get("GROQ_MODEL", DEFAULT_MODEL)
    system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(categories=allowed_categories)

    user_content = raw_text
    if previous_errors:
        user_content = (
            f"{raw_text}\n\n"
            f"(Your previous response was rejected for: {', '.join(previous_errors)}. "
            "Fix those specific fields and respond again with JSON only.)"
        )

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0,
        "seed": FIXED_SEED,
        "response_format": {"type": "json_object"},
    }

    request = urllib.request.Request(
        GROQ_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "deal-tracker-cli/1.0",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        return None, f"HTTP {exc.code}: {detail}"
    except urllib.error.URLError as exc:
        return None, f"network error: {exc.reason}"
    except TimeoutError:
        return None, "request timed out"
    except json.JSONDecodeError:
        return None, "response was not valid JSON"

    try:
        content = body["choices"][0]["message"]["content"]
        parsed = json.loads(content)
    except (KeyError, IndexError, TypeError):
        return None, "unexpected response shape"
    except json.JSONDecodeError:
        return None, "model did not return valid JSON"

    if not isinstance(parsed, dict):
        return None, "model response was not a JSON object"

    normalized = dict(_EMPTY_RESPONSE)
    for key in _SCHEMA_KEYS:
        if key in parsed:
            normalized[key] = parsed[key]
    if normalized.get("description") is None:
        normalized["description"] = raw_text
    return normalized, None


def _validate_schema(response, allowed_categories):
    errors = []
    if set(response.keys()) != _SCHEMA_KEYS:
        return False, ["missing_schema_keys"]

    category = response.get("category")
    if category is not None and category not in allowed_categories:
        errors.append("invalid_category")

    for field in ("original_price", "discounted_price", "discount_percentage", "min_spend"):
        value = response.get(field)
        if value is not None and not isinstance(value, (int, float)):
            errors.append(f"invalid_type:{field}")

    expiry = response.get("expiry_date")
    if expiry is not None:
        if not isinstance(expiry, str):
            errors.append("invalid_type:expiry_date")
        else:
            try:
                datetime.strptime(expiry, "%Y-%m-%d")
            except ValueError:
                errors.append("invalid_expiry_format")

    condition = response.get("eligibility_condition")
    if condition is not None and condition != "unclear" and not isinstance(condition, dict):
        errors.append("invalid_type:eligibility_condition")

    return len(errors) == 0, errors
