"""
schemas.py — Structured Intent Schema

WHY THIS EXISTS:
    This is the "contract" between the LLM and the analytics layer.

    When a user asks a natural-language question, Gemini translates it
    into a structured JSON object (an "intent").  This module defines
    what that JSON must look like, validates it, and rejects anything
    that doesn't conform.

    This is critical for security and correctness:
    - The LLM can only request pre-defined operations.
    - Unknown fields, dimensions, or metrics are rejected.
    - Time-period filters are validated against the actual dataset range.

WHAT STRUCTURED OUTPUT MEANS:
    Instead of letting the LLM produce free-form text, we constrain it
    to return a specific JSON shape.  This lets Python code reliably
    extract the intent and route it to the correct analytics function.

    Example:
        User: "Which category had the highest sales?"
        Gemini → {"intent": "ranking", "metric": "sales",
                  "dimension": "category", "aggregation": "sum",
                  "filters": {}, "limit": 10, "sort_order": "desc"}
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from typing import Any

from config import AVAILABLE_YEARS, AVAILABLE_MONTHS, AVAILABLE_QUARTERS

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Allowed values — the analytics layer only supports these
# ---------------------------------------------------------------------------

ALLOWED_INTENTS = {
    "aggregation",      # single number: total sales, total orders, etc.
    "ranking",          # top/bottom N by a metric across a dimension
    "breakdown",        # full breakdown of metric across a dimension
    "comparison",       # compare two specific groups (e.g. April vs May)
    "trend",            # time-series (monthly, quarterly)
    "distribution",     # share / percentage breakdown
    "executive_summary",# special multi-metric summary
    "clarification",    # model needs more info from user
    "out_of_scope",     # question can't be answered by the dataset
    "data_limitation",  # question asks for data outside available range
    "general_chat",     # greetings, meta questions about the assistant
}

ALLOWED_METRICS = {
    "sales",            # SUM(sales_amount)
    "units",            # SUM(qty)
    "orders",           # COUNT(DISTINCT order_id)
    "avg_line_value",   # AVG(sales_amount)
}

ALLOWED_DIMENSIONS = {
    "category",
    "ship_state",
    "ship_city",
    "order_status",
    "fulfilment",
    "sales_channel",
    "b2b",
    "style",
    "sku",
    "size",
    "order_month",
    "order_quarter",
    "order_year",
    "courier_status",
    "ship_service_level",
    "fulfilled_by",
}

ALLOWED_AGGREGATIONS = {
    "sum",
    "count",
    "count_distinct",
    "avg",
    "min",
    "max",
}

ALLOWED_SORT_ORDERS = {"asc", "desc"}


# ---------------------------------------------------------------------------
# Structured Intent dataclass
# ---------------------------------------------------------------------------

@dataclass
class AnalyticsIntent:
    """
    Validated analytical intent extracted from a user's question.

    Every field has a default so that partial JSON from the LLM
    doesn't crash the parser — instead, missing fields are filled
    with safe defaults and validated afterward.
    """
    intent: str = "aggregation"
    metric: str = "sales"
    dimension: str | None = None
    aggregation: str = "sum"
    filters: dict[str, Any] = field(default_factory=dict)
    limit: int = 10
    sort_order: str = "desc"
    comparison_values: list[str] = field(default_factory=list)
    clarification_message: str = ""
    limitation_message: str = ""
    raw_question: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class IntentValidationError(Exception):
    """Raised when the structured intent is invalid."""
    pass


def validate_intent(intent: AnalyticsIntent) -> AnalyticsIntent:
    """
    Validate every field in the intent against allowlists and dataset range.

    Returns the (possibly cleaned-up) intent or raises IntentValidationError.
    """
    # --- Intent type ---
    if intent.intent not in ALLOWED_INTENTS:
        raise IntentValidationError(
            f"Unknown intent '{intent.intent}'. "
            f"Allowed: {sorted(ALLOWED_INTENTS)}"
        )

    # Non-analytical intents don't need further validation
    if intent.intent in {"clarification", "out_of_scope", "data_limitation", "general_chat"}:
        return intent

    # --- Metric ---
    if intent.metric not in ALLOWED_METRICS:
        raise IntentValidationError(
            f"Unknown metric '{intent.metric}'. "
            f"Allowed: {sorted(ALLOWED_METRICS)}"
        )

    # --- Dimension (optional for aggregation, required for ranking/breakdown) ---
    if intent.dimension is not None and intent.dimension not in ALLOWED_DIMENSIONS:
        raise IntentValidationError(
            f"Unknown dimension '{intent.dimension}'. "
            f"Allowed: {sorted(ALLOWED_DIMENSIONS)}"
        )

    if intent.intent in {"ranking", "breakdown", "distribution", "comparison"} and not intent.dimension:
        raise IntentValidationError(
            f"Intent '{intent.intent}' requires a dimension."
        )

    # --- Aggregation ---
    if intent.aggregation not in ALLOWED_AGGREGATIONS:
        raise IntentValidationError(
            f"Unknown aggregation '{intent.aggregation}'. "
            f"Allowed: {sorted(ALLOWED_AGGREGATIONS)}"
        )

    # --- Sort order ---
    intent.sort_order = intent.sort_order.lower()
    if intent.sort_order not in ALLOWED_SORT_ORDERS:
        intent.sort_order = "desc"

    # --- Limit ---
    if not isinstance(intent.limit, int) or intent.limit < 1:
        intent.limit = 10
    if intent.limit > 100:
        intent.limit = 100

    # --- Time filters ---
    _validate_time_filters(intent)

    return intent


def _validate_time_filters(intent: AnalyticsIntent) -> None:
    """
    Check year / month / quarter filters against the actual dataset range.

    Raises IntentValidationError if the requested period is outside what
    the data contains.
    """
    filters = intent.filters

    year = filters.get("year")
    month = filters.get("month")
    quarter = filters.get("quarter")

    if year is not None:
        year = int(year)
        if year not in AVAILABLE_YEARS:
            raise IntentValidationError(
                f"Year {year} is not available. "
                f"The dataset covers {sorted(AVAILABLE_YEARS)}."
            )
        filters["year"] = year

    if month is not None:
        month = int(month)
        if month not in AVAILABLE_MONTHS:
            raise IntentValidationError(
                f"Month {month} is not available in the dataset. "
                f"Available months: {sorted(AVAILABLE_MONTHS)} (March–June 2022)."
            )
        filters["month"] = month

    if quarter is not None:
        quarter = int(quarter)
        if quarter not in AVAILABLE_QUARTERS:
            raise IntentValidationError(
                f"Q{quarter} data is not available. "
                f"The dataset only covers dates from 2022-03-31 through 2022-06-29, "
                f"which includes partial Q1 and Q2."
            )
        filters["quarter"] = quarter


# ---------------------------------------------------------------------------
# JSON parsing helper
# ---------------------------------------------------------------------------

def parse_intent_json(raw_json: str, raw_question: str = "") -> AnalyticsIntent:
    """
    Parse raw JSON string (from Gemini) into a validated AnalyticsIntent.

    Handles common LLM quirks:
    - JSON wrapped in ```json ... ``` code fences
    - Extra whitespace
    - Missing fields (filled with defaults)
    """
    cleaned = raw_json.strip()
    # Strip code fences
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        # Remove first and last lines (fences)
        lines = [l for l in lines if not l.strip().startswith("```")]
        cleaned = "\n".join(lines)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.error("Failed to parse intent JSON: %s\nRaw: %s", e, raw_json[:500])
        raise IntentValidationError(
            f"Could not parse structured intent from Gemini output. Error: {e}"
        ) from e

    if not isinstance(data, dict):
        raise IntentValidationError("Expected a JSON object, got something else.")

    # Build intent from parsed data, using defaults for missing keys
    intent = AnalyticsIntent(
        intent=data.get("intent", "aggregation"),
        metric=data.get("metric", "sales"),
        dimension=data.get("dimension"),
        aggregation=data.get("aggregation", "sum"),
        filters=data.get("filters", {}),
        limit=data.get("limit", 10),
        sort_order=data.get("sort_order", "desc"),
        comparison_values=data.get("comparison_values", []),
        clarification_message=data.get("clarification_message", ""),
        limitation_message=data.get("limitation_message", ""),
        raw_question=raw_question,
    )

    # Validate
    return validate_intent(intent)
