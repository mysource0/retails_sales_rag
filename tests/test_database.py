"""
test_database.py — Tests for database connectivity and view existence.

These tests verify that:
1. MySQL is reachable with the configured credentials.
2. The retail_analytics view exists and is queryable.
3. The SQL safety validator blocks dangerous operations.
"""

import os
import sys
import unittest

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import DatabaseConnection


class TestDatabaseConnection(unittest.TestCase):
    """Test MySQL connectivity."""

    @classmethod
    def setUpClass(cls):
        """Create a shared database connection for all tests."""
        try:
            cls.db = DatabaseConnection()
        except Exception as e:
            raise unittest.SkipTest(f"Cannot connect to MySQL: {e}")

    def test_connection_works(self):
        """MySQL should be reachable and respond to a simple query."""
        self.assertTrue(self.db.test_connection())

    def test_retail_analytics_view_exists(self):
        """The retail_analytics view must exist in the database."""
        self.assertTrue(self.db.check_view_exists("retail_analytics"))

    def test_retail_analytics_has_rows(self):
        """retail_analytics should have a significant number of rows."""
        rows = self.db.execute_query(
            "SELECT COUNT(*) AS cnt FROM retail_analytics"
        )
        count = rows[0]["cnt"]
        self.assertGreater(count, 100000, f"Expected >100K rows, got {count}")

    def test_retail_analytics_columns(self):
        """retail_analytics must contain the expected key columns."""
        rows = self.db.execute_query(
            "SELECT * FROM retail_analytics LIMIT 1"
        )
        self.assertTrue(len(rows) > 0, "View returned no rows")
        columns = set(rows[0].keys())
        required = {
            "order_id", "order_date", "order_year", "order_month",
            "order_quarter", "sales_amount", "category", "ship_state",
            "fulfilment", "b2b", "qty",
        }
        missing = required - columns
        self.assertEqual(missing, set(), f"Missing columns: {missing}")

    def test_blocked_keywords_insert(self):
        """INSERT should be blocked by the safety validator."""
        with self.assertRaises(PermissionError):
            self.db.execute_query("INSERT INTO retail_analytics VALUES (1)")

    def test_blocked_keywords_drop(self):
        """DROP should be blocked."""
        with self.assertRaises(PermissionError):
            self.db.execute_query("DROP TABLE retail_analytics")

    def test_blocked_keywords_delete(self):
        """DELETE should be blocked."""
        with self.assertRaises(PermissionError):
            self.db.execute_query("DELETE FROM retail_analytics WHERE 1=1")

    def test_blocked_keywords_update(self):
        """UPDATE should be blocked."""
        with self.assertRaises(PermissionError):
            self.db.execute_query("UPDATE retail_analytics SET qty=0")

    def test_blocked_keywords_truncate(self):
        """TRUNCATE should be blocked."""
        with self.assertRaises(PermissionError):
            self.db.execute_query("TRUNCATE TABLE retail_analytics")

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "db"):
            cls.db.close()


if __name__ == "__main__":
    unittest.main()
