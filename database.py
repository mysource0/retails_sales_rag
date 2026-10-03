"""
database.py — Secure MySQL Connection Layer

WHY THIS EXISTS:
    Provides a single, reusable way to talk to MySQL.

    Key design decisions:
    1. READ-ONLY:  Only SELECT queries are allowed.
       The app must never INSERT/UPDATE/DELETE/DROP anything.
    2. CONNECTION POOLING:  Reuses connections instead of opening
       a new one for every query — much faster for Streamlit which
       re-runs the script on every interaction.
    3. PARAMETERIZED QUERIES:  User-derived values are passed as
       parameters (%s), never concatenated into SQL strings.
       This prevents SQL injection attacks.
    4. CLEAR ERRORS:  Connection problems produce user-friendly
       messages, not raw stack traces.

HOW PYTHON CONNECTS TO MYSQL:
    Python uses a "connector" library (mysql-connector-python) which
    speaks the MySQL wire protocol.  You give it host/port/user/password/
    database, and it returns a connection object.  You create a "cursor"
    from the connection, execute SQL through the cursor, and fetch rows.
"""

import logging
from typing import Any

import mysql.connector
from mysql.connector import pooling, Error as MySQLError

from config import DatabaseConfig, get_database_config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Dangerous SQL keywords that the application must NEVER execute.
# ---------------------------------------------------------------------------
_BLOCKED_KEYWORDS = {
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER",
    "CREATE", "TRUNCATE", "GRANT", "REVOKE", "REPLACE",
}


class DatabaseConnection:
    """
    Manages a MySQL connection pool and provides safe query execution.

    Usage:
        db = DatabaseConnection()
        rows = db.execute_query("SELECT * FROM retail_analytics LIMIT 5")
        db.close()
    """

    def __init__(self, config: DatabaseConfig | None = None):
        self._config = config or get_database_config()
        self._pool: pooling.MySQLConnectionPool | None = None

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------
    def _get_pool(self) -> pooling.MySQLConnectionPool:
        """Lazily create a connection pool (3 connections by default)."""
        if self._pool is None:
            try:
                self._pool = pooling.MySQLConnectionPool(
                    pool_name="retail_pool",
                    pool_size=3,
                    pool_reset_session=True,
                    host=self._config.host,
                    port=self._config.port,
                    user=self._config.user,
                    password=self._config.password,
                    database=self._config.database,
                    charset="utf8mb4",
                    autocommit=True,          # read-only, no transactions needed
                    connection_timeout=10,
                )
                logger.info("MySQL connection pool created successfully.")
            except MySQLError as e:
                logger.error("Failed to create MySQL connection pool: %s", e)
                raise ConnectionError(
                    f"Cannot connect to MySQL at {self._config.host}:{self._config.port}. "
                    f"Check your .env file and ensure MySQL is running. Error: {e}"
                ) from e
        return self._pool

    def get_connection(self) -> mysql.connector.MySQLConnection:
        """Get a connection from the pool."""
        return self._get_pool().get_connection()

    def close(self) -> None:
        """Close the connection pool (if any)."""
        # mysql-connector-python pools don't have a direct close(),
        # but setting to None lets GC clean up.
        self._pool = None
        logger.info("Connection pool released.")

    # ------------------------------------------------------------------
    # Safe query execution
    # ------------------------------------------------------------------
    @staticmethod
    def _validate_query(sql: str) -> None:
        """
        Reject any SQL that contains dangerous write/DDL operations.

        This is a defence-in-depth measure.  The main safety comes from
        the architecture: only pre-approved analytics functions generate
        SQL.  This check is an extra safety net.
        """
        # Normalise to uppercase for keyword matching
        upper_sql = sql.upper().strip()
        for keyword in _BLOCKED_KEYWORDS:
            # Check that the keyword appears as a standalone token
            # (not inside a column name like "order_status")
            if keyword in upper_sql.split():
                raise PermissionError(
                    f"Blocked: SQL contains disallowed keyword '{keyword}'. "
                    "This application is read-only."
                )

    def execute_query(
        self,
        sql: str,
        params: tuple | None = None,
        fetch: str = "all",
    ) -> list[dict[str, Any]]:
        """
        Execute a SELECT query and return rows as a list of dicts.

        Args:
            sql:    SQL string with %s placeholders for parameters.
            params: Tuple of parameter values (or None).
            fetch:  "all" → fetchall(), "one" → fetchone() wrapped in list.

        Returns:
            List of {column_name: value} dicts.

        Raises:
            PermissionError: If the SQL contains blocked keywords.
            ConnectionError: If MySQL is unreachable.
            RuntimeError:    For other MySQL errors.
        """
        self._validate_query(sql)

        conn = None
        cursor = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute(sql, params)

            if fetch == "one":
                row = cursor.fetchone()
                return [row] if row else []
            else:
                return cursor.fetchall()

        except MySQLError as e:
            logger.error("MySQL query error: %s | SQL: %s | Params: %s", e, sql, params)
            raise RuntimeError(
                f"Database query failed: {e}. "
                "Check logs for details."
            ) from e
        finally:
            if cursor:
                cursor.close()
            if conn:
                try:
                    conn.close()  # returns to pool, doesn't destroy
                except Exception:
                    pass

    def test_connection(self) -> bool:
        """Quick connectivity check.  Returns True if MySQL is reachable."""
        try:
            rows = self.execute_query("SELECT 1 AS ok")
            return bool(rows and rows[0].get("ok") == 1)
        except Exception as e:
            logger.error("Connection test failed: %s", e)
            return False

    def check_view_exists(self, view_name: str = "retail_analytics") -> bool:
        """Verify that the required analytical view exists."""
        try:
            rows = self.execute_query(
                "SELECT TABLE_NAME FROM information_schema.VIEWS "
                "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s",
                (self._config.database, view_name),
            )
            return len(rows) > 0
        except Exception as e:
            logger.error("View check failed: %s", e)
            return False
