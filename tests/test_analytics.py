"""
test_analytics.py — Tests for the analytics layer.

These tests verify that:
1. Overall metrics (total orders, sales, units) match expected ranges.
2. Category rankings return expected top categories.
3. State rankings return expected top states.
4. Monthly and quarterly aggregations produce correct groupings.
5. B2B summary includes percentage calculations.
6. Executive summary returns all expected data sections.
"""

import os
import sys
import unittest
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import DatabaseConnection
from analytics import AnalyticsService


class TestAnalytics(unittest.TestCase):
    """Test analytical functions against the live MySQL database."""

    @classmethod
    def setUpClass(cls):
        try:
            cls.db = DatabaseConnection()
            if not cls.db.test_connection():
                raise unittest.SkipTest("MySQL not reachable")
            cls.analytics = AnalyticsService(cls.db)
        except Exception as e:
            raise unittest.SkipTest(f"Cannot set up analytics: {e}")

    # ------------------------------------------------------------------
    # Overall metrics
    # ------------------------------------------------------------------

    def test_total_orders(self):
        """Total unique orders should be ~120K."""
        df = self.analytics.get_overall_metrics()
        orders = int(df.iloc[0]["total_orders"])
        self.assertGreater(orders, 100_000)
        self.assertLess(orders, 150_000)

    def test_total_sales(self):
        """Total sales should be ~78.5M INR."""
        df = self.analytics.get_overall_metrics()
        sales = float(df.iloc[0]["total_sales"])
        self.assertGreater(sales, 70_000_000)
        self.assertLess(sales, 90_000_000)

    def test_total_units(self):
        """Total units should be ~116K."""
        df = self.analytics.get_overall_metrics()
        units = int(df.iloc[0]["total_units"])
        self.assertGreater(units, 100_000)
        self.assertLess(units, 130_000)

    def test_avg_line_value(self):
        """Average line value should be ~649 INR."""
        df = self.analytics.get_overall_metrics()
        avg = float(df.iloc[0]["avg_line_value"])
        self.assertGreater(avg, 500)
        self.assertLess(avg, 800)

    # ------------------------------------------------------------------
    # Category rankings
    # ------------------------------------------------------------------

    def test_top_category_is_set(self):
        """The top-selling category should be 'Set'."""
        df = self.analytics.get_sales_by_category(limit=1)
        top = df.iloc[0]["dimension_value"]
        self.assertEqual(top, "Set")

    def test_category_count(self):
        """There should be at least 5 categories."""
        df = self.analytics.get_sales_by_category(limit=50)
        self.assertGreaterEqual(len(df), 5)

    # ------------------------------------------------------------------
    # State rankings
    # ------------------------------------------------------------------

    def test_top_state_is_maharashtra(self):
        """MAHARASHTRA should be the top state by sales."""
        df = self.analytics.get_sales_by_state(limit=1)
        top = df.iloc[0]["dimension_value"]
        self.assertEqual(top, "MAHARASHTRA")

    # ------------------------------------------------------------------
    # Monthly sales
    # ------------------------------------------------------------------

    def test_monthly_trend_has_four_months(self):
        """Dataset covers March through June = 4 months."""
        df = self.analytics.get_monthly_trend()
        self.assertEqual(len(df), 4)

    def test_monthly_trend_april_highest(self):
        """April should have the highest monthly sales."""
        df = self.analytics.get_monthly_trend()
        top_month = df.loc[df["sales"].idxmax()]["order_month"]
        self.assertEqual(int(top_month), 4)  # April

    # ------------------------------------------------------------------
    # Quarterly sales
    # ------------------------------------------------------------------

    def test_quarterly_trend_has_two_quarters(self):
        """Dataset should have Q1 (partial) and Q2."""
        df = self.analytics.get_quarterly_trend()
        self.assertEqual(len(df), 2)

    def test_quarterly_q2_much_larger(self):
        """Q2 sales should be much larger than Q1 (only 1 day of Q1)."""
        df = self.analytics.get_quarterly_trend()
        q1_sales = float(df.loc[df["order_quarter"] == 1, "sales"].values[0])
        q2_sales = float(df.loc[df["order_quarter"] == 2, "sales"].values[0])
        self.assertGreater(q2_sales, q1_sales * 100)

    # ------------------------------------------------------------------
    # B2B
    # ------------------------------------------------------------------

    def test_b2b_summary_has_percentages(self):
        """B2B summary should include order_pct and sales_pct."""
        df = self.analytics.get_b2b_summary()
        self.assertIn("order_pct", df.columns)
        self.assertIn("sales_pct", df.columns)
        # Percentages should sum to ~100
        total_pct = df["order_pct"].sum()
        self.assertAlmostEqual(total_pct, 100.0, delta=0.1)

    # ------------------------------------------------------------------
    # Order status
    # ------------------------------------------------------------------

    def test_order_status_has_cancelled(self):
        """'Cancelled' should appear in order status summary."""
        df = self.analytics.get_order_status_summary(limit=20)
        statuses = df["dimension_value"].tolist()
        self.assertIn("Cancelled", statuses)

    # ------------------------------------------------------------------
    # Executive summary
    # ------------------------------------------------------------------

    def test_executive_summary_structure(self):
        """Executive summary should return all expected sections."""
        summary = self.analytics.get_executive_summary()
        expected_keys = {
            "overall", "top_categories", "top_states",
            "monthly_trend", "fulfilment", "b2b", "order_status",
        }
        self.assertEqual(set(summary.keys()), expected_keys)

    # ------------------------------------------------------------------
    # Filtered queries
    # ------------------------------------------------------------------

    def test_filter_by_month(self):
        """Filtering by month=4 should return April data only."""
        df = self.analytics.get_overall_metrics(filters={"month": 4})
        sales = float(df.iloc[0]["total_sales"])
        # April sales should be ~28.8M
        self.assertGreater(sales, 25_000_000)
        self.assertLess(sales, 35_000_000)

    def test_filter_by_category(self):
        """Filtering by category='Set' should return Set data only."""
        df = self.analytics.get_overall_metrics(filters={"category": "Set"})
        sales = float(df.iloc[0]["total_sales"])
        # Set sales should be ~39.2M
        self.assertGreater(sales, 35_000_000)
        self.assertLess(sales, 45_000_000)

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "db"):
            cls.db.close()


if __name__ == "__main__":
    unittest.main()
