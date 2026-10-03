"""
analytics.py — Controlled Analytics Registry

WHY THIS EXISTS:
    This is the ONLY module that generates SQL.  Every analytical
    question the user can ask is routed to a specific, pre-written
    function here.  This is the "controlled analytics layer" in the
    architecture diagram.

    The key safety property:  Gemini never writes SQL.
    Instead, Gemini produces a structured intent (see schemas.py),
    and this module maps that intent to the correct pre-approved function.

WHY SQL CALCULATES BUSINESS METRICS:
    SQL engines like MySQL are purpose-built for exact numerical
    computation over millions of rows.  The LLM doesn't have access
    to the database and can't count rows or sum columns.  So we let
    MySQL do what it does best (math) and then let Gemini do what it
    does best (explain the results in plain English).

METRIC DEFINITIONS (used consistently everywhere):
    Sales  = SUM(sales_amount)
    Units  = SUM(qty)
    Orders = COUNT(DISTINCT order_id)
    Avg    = AVG(sales_amount)
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from database import DatabaseConnection
from schemas import AnalyticsIntent
from config import ANALYTICS_VIEW

logger = logging.getLogger(__name__)


class AnalyticsService:
    """
    Pre-approved analytical functions that query the retail_analytics view.

    Each public method returns a pandas DataFrame with the results.
    """

    def __init__(self, db: DatabaseConnection):
        self._db = db
        self._view = ANALYTICS_VIEW

    # ==================================================================
    # Internal helpers
    # ==================================================================

    def _build_where(
        self, filters: dict[str, Any]
    ) -> tuple[str, tuple]:
        """
        Build a WHERE clause from validated filters.

        Returns (where_clause_str, params_tuple).
        Only supports allowlisted filter keys.
        """
        conditions: list[str] = []
        params: list[Any] = []

        if "year" in filters:
            conditions.append("order_year = %s")
            params.append(filters["year"])

        if "month" in filters:
            conditions.append("order_month = %s")
            params.append(filters["month"])

        if "quarter" in filters:
            conditions.append("order_quarter = %s")
            params.append(filters["quarter"])

        if "order_status" in filters:
            conditions.append("order_status = %s")
            params.append(filters["order_status"])

        if "category" in filters:
            conditions.append("category = %s")
            params.append(filters["category"])

        if "b2b" in filters:
            conditions.append("b2b = %s")
            params.append(filters["b2b"])

        if "fulfilment" in filters:
            conditions.append("fulfilment = %s")
            params.append(filters["fulfilment"])

        if "sales_channel" in filters:
            conditions.append("sales_channel = %s")
            params.append(filters["sales_channel"])

        if "ship_state" in filters:
            conditions.append("ship_state = %s")
            params.append(filters["ship_state"])

        if "ship_city" in filters:
            conditions.append("ship_city = %s")
            params.append(filters["ship_city"])

        where = ""
        if conditions:
            where = " WHERE " + " AND ".join(conditions)

        return where, tuple(params)

    def _metric_sql(self, metric: str) -> str:
        """
        Return the SQL expression for a given metric name.
        Consistent definitions used everywhere.
        """
        mapping = {
            "sales": "SUM(sales_amount)",
            "units": "SUM(qty)",
            "orders": "COUNT(DISTINCT order_id)",
            "avg_line_value": "AVG(sales_amount)",
        }
        if metric not in mapping:
            raise ValueError(f"Unknown metric: {metric}")
        return mapping[metric]

    def _query_to_df(self, sql: str, params: tuple | None = None) -> pd.DataFrame:
        """Execute query and return as DataFrame."""
        rows = self._db.execute_query(sql, params)
        return pd.DataFrame(rows) if rows else pd.DataFrame()

    # ==================================================================
    # Overall / aggregate metrics
    # ==================================================================

    def get_overall_metrics(self, filters: dict | None = None) -> pd.DataFrame:
        """
        Total sales, units, orders, and avg line value.
        Used for the sidebar KPIs and executive summary.
        """
        filters = filters or {}
        where, params = self._build_where(filters)

        sql = f"""
            SELECT
                SUM(sales_amount)           AS total_sales,
                SUM(qty)                    AS total_units,
                COUNT(DISTINCT order_id)    AS total_orders,
                AVG(sales_amount)           AS avg_line_value,
                MIN(order_date)             AS date_min,
                MAX(order_date)             AS date_max
            FROM {self._view}
            {where}
        """
        return self._query_to_df(sql, params)

    # ==================================================================
    # Breakdown / ranking by dimension
    # ==================================================================

    def _get_metric_by_dimension(
        self,
        metric: str,
        dimension: str,
        filters: dict | None = None,
        sort_order: str = "desc",
        limit: int = 10,
    ) -> pd.DataFrame:
        """
        Generic:  SELECT dimension, METRIC FROM view GROUP BY dimension ORDER BY …
        """
        filters = filters or {}
        where, params = self._build_where(filters)
        metric_expr = self._metric_sql(metric)
        order = "DESC" if sort_order == "desc" else "ASC"

        sql = f"""
            SELECT
                {dimension}                 AS dimension_value,
                {metric_expr}               AS metric_value,
                COUNT(DISTINCT order_id)    AS orders,
                SUM(qty)                    AS units,
                SUM(sales_amount)           AS sales
            FROM {self._view}
            {where}
            GROUP BY {dimension}
            ORDER BY metric_value {order}
            LIMIT %s
        """
        return self._query_to_df(sql, (*params, limit))

    # Convenience wrappers — keep the API self-documenting
    def get_sales_by_category(self, **kw) -> pd.DataFrame:
        return self._get_metric_by_dimension("sales", "category", **kw)

    def get_sales_by_state(self, **kw) -> pd.DataFrame:
        return self._get_metric_by_dimension("sales", "ship_state", **kw)

    def get_sales_by_city(self, **kw) -> pd.DataFrame:
        return self._get_metric_by_dimension("sales", "ship_city", **kw)

    def get_sales_by_month(self, **kw) -> pd.DataFrame:
        return self._get_metric_by_dimension("sales", "order_month", **kw)

    def get_sales_by_quarter(self, **kw) -> pd.DataFrame:
        return self._get_metric_by_dimension("sales", "order_quarter", **kw)

    def get_sales_by_order_status(self, **kw) -> pd.DataFrame:
        return self._get_metric_by_dimension("sales", "order_status", **kw)

    def get_sales_by_fulfilment(self, **kw) -> pd.DataFrame:
        return self._get_metric_by_dimension("sales", "fulfilment", **kw)

    def get_sales_by_sales_channel(self, **kw) -> pd.DataFrame:
        return self._get_metric_by_dimension("sales", "sales_channel", **kw)

    def get_sales_by_b2b(self, **kw) -> pd.DataFrame:
        return self._get_metric_by_dimension("sales", "b2b", **kw)

    def get_top_products(self, **kw) -> pd.DataFrame:
        return self._get_metric_by_dimension("sales", "category", **kw)

    def get_top_styles(self, **kw) -> pd.DataFrame:
        return self._get_metric_by_dimension("sales", "style", **kw)

    def get_top_skus(self, **kw) -> pd.DataFrame:
        return self._get_metric_by_dimension("sales", "sku", **kw)

    def get_units_by_category(self, **kw) -> pd.DataFrame:
        return self._get_metric_by_dimension("units", "category", **kw)

    def get_orders_by_category(self, **kw) -> pd.DataFrame:
        return self._get_metric_by_dimension("orders", "category", **kw)

    def get_order_status_summary(self, **kw) -> pd.DataFrame:
        return self._get_metric_by_dimension("orders", "order_status", **kw)

    # ==================================================================
    # Monthly trend (always sorted chronologically)
    # ==================================================================

    def get_monthly_trend(self, filters: dict | None = None) -> pd.DataFrame:
        filters = filters or {}
        where, params = self._build_where(filters)

        sql = f"""
            SELECT
                order_year,
                order_month,
                SUM(sales_amount)           AS sales,
                SUM(qty)                    AS units,
                COUNT(DISTINCT order_id)    AS orders
            FROM {self._view}
            {where}
            GROUP BY order_year, order_month
            ORDER BY order_year, order_month
        """
        return self._query_to_df(sql, params)

    # ==================================================================
    # Quarterly trend
    # ==================================================================

    def get_quarterly_trend(self, filters: dict | None = None) -> pd.DataFrame:
        filters = filters or {}
        where, params = self._build_where(filters)

        sql = f"""
            SELECT
                order_year,
                order_quarter,
                SUM(sales_amount)           AS sales,
                SUM(qty)                    AS units,
                COUNT(DISTINCT order_id)    AS orders
            FROM {self._view}
            {where}
            GROUP BY order_year, order_quarter
            ORDER BY order_year, order_quarter
        """
        return self._query_to_df(sql, params)

    # ==================================================================
    # B2B analytics
    # ==================================================================

    def get_b2b_summary(self, filters: dict | None = None) -> pd.DataFrame:
        """B2B vs non-B2B breakdown with percentage calculations."""
        filters = filters or {}
        where, params = self._build_where(filters)

        sql = f"""
            SELECT
                b2b,
                COUNT(DISTINCT order_id)    AS orders,
                SUM(qty)                    AS units,
                SUM(sales_amount)           AS sales
            FROM {self._view}
            {where}
            GROUP BY b2b
        """
        df = self._query_to_df(sql, params)

        if not df.empty:
            total_orders = df["orders"].sum()
            total_sales = df["sales"].sum()
            df["order_pct"] = (df["orders"] / total_orders * 100).round(2)
            df["sales_pct"] = (df["sales"] / total_sales * 100).round(2)

        return df

    # ==================================================================
    # Executive summary (multiple queries in one call)
    # ==================================================================

    def get_executive_summary(self, filters: dict | None = None) -> dict:
        """
        Collect all key metrics for an executive summary.
        Returns a dict of DataFrames / values.
        """
        overall = self.get_overall_metrics(filters)
        by_category = self.get_sales_by_category(filters=filters, limit=5)
        by_state = self.get_sales_by_state(filters=filters, limit=5)
        monthly = self.get_monthly_trend(filters)
        by_fulfilment = self.get_sales_by_fulfilment(filters=filters, limit=5)
        b2b = self.get_b2b_summary(filters)
        status = self.get_order_status_summary(filters=filters, limit=15)

        return {
            "overall": overall,
            "top_categories": by_category,
            "top_states": by_state,
            "monthly_trend": monthly,
            "fulfilment": by_fulfilment,
            "b2b": b2b,
            "order_status": status,
        }

    # ==================================================================
    # Dispatcher — maps structured intents to functions
    # ==================================================================

    def dispatch(self, intent: AnalyticsIntent) -> dict[str, Any]:
        """
        Route a validated AnalyticsIntent to the correct analytics function.

        Returns a dict with:
            - "data":   DataFrame of results
            - "query_description":  human-readable description of what was queried
            - "intent": the original intent dict
        """
        filters = intent.filters
        metric = intent.metric
        dimension = intent.dimension
        sort_order = intent.sort_order
        limit = intent.limit

        # --- Special intents ---
        if intent.intent == "executive_summary":
            summary = self.get_executive_summary(filters)
            return {
                "data": summary,
                "query_description": "Executive summary of all key metrics",
                "intent": intent.to_dict(),
                "is_executive_summary": True,
            }

        # --- Aggregation (single number) ---
        if intent.intent == "aggregation":
            df = self.get_overall_metrics(filters)
            return {
                "data": df,
                "query_description": f"Overall {metric} metrics",
                "intent": intent.to_dict(),
            }

        # --- Ranking / Breakdown / Distribution ---
        if intent.intent in {"ranking", "breakdown", "distribution"}:
            # Map dimension to the best function
            dispatch_map = {
                "category": self.get_sales_by_category,
                "ship_state": self.get_sales_by_state,
                "ship_city": self.get_sales_by_city,
                "order_month": self.get_sales_by_month,
                "order_quarter": self.get_sales_by_quarter,
                "order_status": self.get_sales_by_order_status,
                "fulfilment": self.get_sales_by_fulfilment,
                "sales_channel": self.get_sales_by_sales_channel,
                "b2b": self.get_sales_by_b2b,
                "style": self.get_top_styles,
                "sku": self.get_top_skus,
                "size": lambda **kw: self._get_metric_by_dimension(metric, "size", **kw),
                "courier_status": lambda **kw: self._get_metric_by_dimension(metric, "courier_status", **kw),
                "ship_service_level": lambda **kw: self._get_metric_by_dimension(metric, "ship_service_level", **kw),
                "fulfilled_by": lambda **kw: self._get_metric_by_dimension(metric, "fulfilled_by", **kw),
            }

            # If the metric isn't "sales", use the generic method
            func = dispatch_map.get(dimension)
            if func and metric != "sales":
                df = self._get_metric_by_dimension(
                    metric, dimension, filters=filters,
                    sort_order=sort_order, limit=limit,
                )
            elif func:
                df = func(filters=filters, sort_order=sort_order, limit=limit)
            else:
                df = self._get_metric_by_dimension(
                    metric, dimension, filters=filters,
                    sort_order=sort_order, limit=limit,
                )

            # Special handling for B2B distribution
            if dimension == "b2b" and intent.intent == "distribution":
                df = self.get_b2b_summary(filters)

            return {
                "data": df,
                "query_description": f"{metric.title()} by {dimension} ({sort_order})",
                "intent": intent.to_dict(),
            }

        # --- Trend ---
        if intent.intent == "trend":
            if dimension == "order_quarter":
                df = self.get_quarterly_trend(filters)
            else:
                df = self.get_monthly_trend(filters)
            return {
                "data": df,
                "query_description": f"{metric.title()} trend over time",
                "intent": intent.to_dict(),
            }

        # --- Comparison ---
        if intent.intent == "comparison":
            df = self._get_metric_by_dimension(
                metric, dimension, filters=filters,
                sort_order=sort_order, limit=100,
            )
            return {
                "data": df,
                "query_description": (
                    f"Comparison of {metric} across {dimension}"
                ),
                "intent": intent.to_dict(),
            }

        # Fallback
        df = self.get_overall_metrics(filters)
        return {
            "data": df,
            "query_description": "Overall metrics (fallback)",
            "intent": intent.to_dict(),
        }
