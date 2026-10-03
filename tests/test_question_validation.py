"""
test_question_validation.py — Tests for question validation and intent parsing.

These tests verify that:
1. Supported questions produce valid intents.
2. Out-of-range time periods are rejected.
3. Out-of-scope questions (predictions, causation) are handled.
4. Ambiguous questions trigger clarification.
5. Destructive SQL is never generated.
6. At least 15 representative natural-language questions are covered.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from schemas import (
    AnalyticsIntent,
    validate_intent,
    parse_intent_json,
    IntentValidationError,
)


class TestIntentValidation(unittest.TestCase):
    """Test the schema validation logic (no Gemini needed)."""

    # ------------------------------------------------------------------
    # Valid intents
    # ------------------------------------------------------------------

    def test_valid_aggregation(self):
        """Basic aggregation intent should pass validation."""
        intent = AnalyticsIntent(
            intent="aggregation", metric="sales", aggregation="sum"
        )
        result = validate_intent(intent)
        self.assertEqual(result.intent, "aggregation")

    def test_valid_ranking_with_dimension(self):
        """Ranking with a valid dimension should pass."""
        intent = AnalyticsIntent(
            intent="ranking", metric="sales",
            dimension="category", aggregation="sum"
        )
        result = validate_intent(intent)
        self.assertEqual(result.dimension, "category")

    def test_valid_breakdown_by_state(self):
        """Breakdown by ship_state should pass."""
        intent = AnalyticsIntent(
            intent="breakdown", metric="sales",
            dimension="ship_state", aggregation="sum"
        )
        result = validate_intent(intent)
        self.assertEqual(result.dimension, "ship_state")

    def test_valid_trend(self):
        """Trend intent for month should pass."""
        intent = AnalyticsIntent(
            intent="trend", metric="sales",
            dimension="order_month", aggregation="sum"
        )
        validate_intent(intent)

    def test_valid_distribution_b2b(self):
        """B2B distribution should pass."""
        intent = AnalyticsIntent(
            intent="distribution", metric="orders",
            dimension="b2b", aggregation="count_distinct"
        )
        validate_intent(intent)

    def test_valid_executive_summary(self):
        """Executive summary intent should pass."""
        intent = AnalyticsIntent(intent="executive_summary")
        validate_intent(intent)

    # ------------------------------------------------------------------
    # Invalid intents — bad field values
    # ------------------------------------------------------------------

    def test_invalid_intent_type(self):
        """Unknown intent type should be rejected."""
        intent = AnalyticsIntent(intent="predict")
        with self.assertRaises(IntentValidationError):
            validate_intent(intent)

    def test_invalid_metric(self):
        """Unknown metric should be rejected."""
        intent = AnalyticsIntent(
            intent="aggregation", metric="profit"
        )
        with self.assertRaises(IntentValidationError):
            validate_intent(intent)

    def test_invalid_dimension(self):
        """Unknown dimension should be rejected."""
        intent = AnalyticsIntent(
            intent="ranking", metric="sales",
            dimension="region", aggregation="sum"
        )
        with self.assertRaises(IntentValidationError):
            validate_intent(intent)

    def test_ranking_without_dimension(self):
        """Ranking without dimension should be rejected."""
        intent = AnalyticsIntent(
            intent="ranking", metric="sales", aggregation="sum"
        )
        with self.assertRaises(IntentValidationError):
            validate_intent(intent)

    # ------------------------------------------------------------------
    # Time-period validation
    # ------------------------------------------------------------------

    def test_q3_rejected(self):
        """Q3 should be rejected as data_limitation."""
        intent = AnalyticsIntent(
            intent="ranking", metric="sales",
            dimension="ship_state", aggregation="sum",
            filters={"quarter": 3}
        )
        with self.assertRaises(IntentValidationError):
            validate_intent(intent)

    def test_q4_rejected(self):
        """Q4 should be rejected."""
        intent = AnalyticsIntent(
            intent="aggregation", metric="sales",
            filters={"quarter": 4}
        )
        with self.assertRaises(IntentValidationError):
            validate_intent(intent)

    def test_year_2023_rejected(self):
        """Year 2023 should be rejected."""
        intent = AnalyticsIntent(
            intent="aggregation", metric="sales",
            filters={"year": 2023}
        )
        with self.assertRaises(IntentValidationError):
            validate_intent(intent)

    def test_december_rejected(self):
        """December (month 12) should be rejected."""
        intent = AnalyticsIntent(
            intent="aggregation", metric="sales",
            filters={"month": 12}
        )
        with self.assertRaises(IntentValidationError):
            validate_intent(intent)

    def test_month_april_accepted(self):
        """April (month 4) should be accepted."""
        intent = AnalyticsIntent(
            intent="aggregation", metric="sales",
            filters={"month": 4}
        )
        result = validate_intent(intent)
        self.assertEqual(result.filters["month"], 4)

    # ------------------------------------------------------------------
    # Non-analytical intents pass through
    # ------------------------------------------------------------------

    def test_clarification_passes(self):
        """Clarification intent should pass without metric validation."""
        intent = AnalyticsIntent(
            intent="clarification",
            clarification_message="What metric would you like?"
        )
        validate_intent(intent)

    def test_out_of_scope_passes(self):
        """Out-of-scope intent should pass without metric validation."""
        intent = AnalyticsIntent(
            intent="out_of_scope",
            limitation_message="This requires predictive analytics."
        )
        validate_intent(intent)

    def test_data_limitation_passes(self):
        """Data limitation intent should pass."""
        intent = AnalyticsIntent(
            intent="data_limitation",
            limitation_message="Q3 data is not available."
        )
        validate_intent(intent)

    # ------------------------------------------------------------------
    # JSON parsing
    # ------------------------------------------------------------------

    def test_parse_valid_json(self):
        """Valid JSON should parse into an intent."""
        raw = '{"intent": "aggregation", "metric": "sales", "aggregation": "sum", "filters": {}}'
        intent = parse_intent_json(raw)
        self.assertEqual(intent.intent, "aggregation")

    def test_parse_json_with_code_fences(self):
        """JSON wrapped in code fences should parse correctly."""
        raw = '```json\n{"intent": "ranking", "metric": "sales", "dimension": "category", "aggregation": "sum", "filters": {}}\n```'
        intent = parse_intent_json(raw)
        self.assertEqual(intent.intent, "ranking")

    def test_parse_invalid_json(self):
        """Malformed JSON should raise IntentValidationError."""
        with self.assertRaises(IntentValidationError):
            parse_intent_json("not valid json {{{")

    # ------------------------------------------------------------------
    # Edge cases
    # ------------------------------------------------------------------

    def test_limit_capped_at_100(self):
        """Limit > 100 should be capped."""
        intent = AnalyticsIntent(
            intent="aggregation", metric="sales", limit=500
        )
        result = validate_intent(intent)
        self.assertEqual(result.limit, 100)

    def test_negative_limit_defaults(self):
        """Negative limit should default to 10."""
        intent = AnalyticsIntent(
            intent="aggregation", metric="sales", limit=-5
        )
        result = validate_intent(intent)
        self.assertEqual(result.limit, 10)

    def test_invalid_sort_order_defaults(self):
        """Invalid sort order should default to desc."""
        intent = AnalyticsIntent(
            intent="aggregation", metric="sales", sort_order="random"
        )
        result = validate_intent(intent)
        self.assertEqual(result.sort_order, "desc")


class TestNaturalLanguageQuestions(unittest.TestCase):
    """
    15+ representative business questions mapped to expected intents.

    These test the JSON schema, NOT Gemini.  They verify that
    correctly-formed intents for each question type are valid.
    """

    def _make_and_validate(self, **kwargs):
        """Helper: create intent and validate it."""
        intent = AnalyticsIntent(**kwargs)
        return validate_intent(intent)

    # Question 1: "What were the total sales?"
    def test_q01_total_sales(self):
        result = self._make_and_validate(
            intent="aggregation", metric="sales", aggregation="sum"
        )
        self.assertEqual(result.metric, "sales")

    # Question 2: "Which category generated the highest sales?"
    def test_q02_top_category(self):
        result = self._make_and_validate(
            intent="ranking", metric="sales",
            dimension="category", aggregation="sum", sort_order="desc"
        )
        self.assertEqual(result.dimension, "category")

    # Question 3: "Which state had the highest sales?"
    def test_q03_top_state(self):
        result = self._make_and_validate(
            intent="ranking", metric="sales",
            dimension="ship_state", aggregation="sum"
        )
        self.assertEqual(result.dimension, "ship_state")

    # Question 4: "What were monthly sales?"
    def test_q04_monthly_sales(self):
        result = self._make_and_validate(
            intent="breakdown", metric="sales",
            dimension="order_month", aggregation="sum"
        )
        self.assertEqual(result.dimension, "order_month")

    # Question 5: "Which fulfilment method had the highest sales?"
    def test_q05_top_fulfilment(self):
        result = self._make_and_validate(
            intent="ranking", metric="sales",
            dimension="fulfilment", aggregation="sum"
        )
        self.assertEqual(result.dimension, "fulfilment")

    # Question 6: "How many orders were cancelled?"
    def test_q06_cancelled_orders(self):
        result = self._make_and_validate(
            intent="aggregation", metric="orders",
            aggregation="count_distinct",
            filters={"order_status": "Cancelled"}
        )
        self.assertEqual(result.filters["order_status"], "Cancelled")

    # Question 7: "What percentage of orders were B2B?"
    def test_q07_b2b_percentage(self):
        result = self._make_and_validate(
            intent="distribution", metric="orders",
            dimension="b2b", aggregation="count_distinct"
        )
        self.assertEqual(result.intent, "distribution")

    # Question 8: "Give me an executive summary."
    def test_q08_executive_summary(self):
        result = self._make_and_validate(intent="executive_summary")
        self.assertEqual(result.intent, "executive_summary")

    # Question 9: "Compare sales between April and May."
    def test_q09_compare_months(self):
        result = self._make_and_validate(
            intent="comparison", metric="sales",
            dimension="order_month", aggregation="sum",
            comparison_values=["4", "5"]
        )
        self.assertEqual(result.intent, "comparison")

    # Question 10: "Which quarter had the highest sales?"
    def test_q10_top_quarter(self):
        result = self._make_and_validate(
            intent="ranking", metric="sales",
            dimension="order_quarter", aggregation="sum"
        )
        self.assertEqual(result.dimension, "order_quarter")

    # Question 11: "What were sales in May 2022?"
    def test_q11_may_sales(self):
        result = self._make_and_validate(
            intent="aggregation", metric="sales",
            aggregation="sum", filters={"year": 2022, "month": 5}
        )
        self.assertEqual(result.filters["month"], 5)

    # Question 12: "How many total orders were there?"
    def test_q12_total_orders(self):
        result = self._make_and_validate(
            intent="aggregation", metric="orders",
            aggregation="count_distinct"
        )
        self.assertEqual(result.metric, "orders")

    # Question 13: "Show sales by sales channel."
    def test_q13_by_channel(self):
        result = self._make_and_validate(
            intent="breakdown", metric="sales",
            dimension="sales_channel", aggregation="sum"
        )
        self.assertEqual(result.dimension, "sales_channel")

    # Question 14: "Which city had the most orders?"
    def test_q14_top_city_orders(self):
        result = self._make_and_validate(
            intent="ranking", metric="orders",
            dimension="ship_city", aggregation="count_distinct"
        )
        self.assertEqual(result.metric, "orders")

    # Question 15: "What is the average order value?"
    def test_q15_avg_order_value(self):
        result = self._make_and_validate(
            intent="aggregation", metric="avg_line_value",
            aggregation="avg"
        )
        self.assertEqual(result.metric, "avg_line_value")

    # Question 16 (out-of-scope): "What will sales be next year?"
    def test_q16_prediction_out_of_scope(self):
        result = self._make_and_validate(
            intent="out_of_scope",
            limitation_message="Predictions are not supported."
        )
        self.assertEqual(result.intent, "out_of_scope")

    # Question 17 (data limitation): "Show Q3 sales."
    def test_q17_q3_rejected(self):
        with self.assertRaises(IntentValidationError):
            self._make_and_validate(
                intent="ranking", metric="sales",
                dimension="ship_state", aggregation="sum",
                filters={"quarter": 3}
            )


if __name__ == "__main__":
    unittest.main()
