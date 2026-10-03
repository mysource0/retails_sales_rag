"""
config.py — Application Configuration

WHY THIS EXISTS:
    Centralizes all configuration loading so no other module
    needs to touch environment variables directly.  This makes
    it easy to change how settings are loaded (e.g. from a YAML
    file in the future) without editing every other module.

    It also catches missing configuration early with clear error
    messages instead of letting the app crash later with cryptic
    "NoneType" errors.
"""

import os
from dataclasses import dataclass
from dotenv import load_dotenv

# Load .env file if it exists (development convenience).
# In production, env vars would be set by the deployment platform.
load_dotenv()


@dataclass(frozen=True)
class DatabaseConfig:
    """Immutable database connection parameters."""
    host: str
    port: int
    user: str
    password: str
    database: str


@dataclass(frozen=True)
class GeminiConfig:
    """Immutable Gemini API parameters."""
    api_key: str
    model_name: str = "gemini-3.8-flash"          # fast + cheap for intent extraction
    response_model_name: str = "gemini-3.8-flash"  # same model for response generation


# ---------------------------------------------------------------------------
# Dataset metadata — the app uses these for validation, NOT for analytics.
# Analytics numbers always come from MySQL.
# ---------------------------------------------------------------------------
DATASET_DATE_MIN = "2022-03-31"
DATASET_DATE_MAX = "2022-06-29"
AVAILABLE_QUARTERS = {1, 2}      # Q1 partial, Q2 full
AVAILABLE_MONTHS = {3, 4, 5, 6}  # March (partial), April-June
AVAILABLE_YEARS = {2022}

# The single analytical view the app queries
ANALYTICS_VIEW = "retail_analytics"


def get_database_config() -> DatabaseConfig:
    """
    Build DatabaseConfig from environment variables.

    Raises ValueError if any required variable is missing so the
    developer sees exactly which one is missing instead of a vague error.
    """
    required = {
        "MYSQL_HOST": os.getenv("MYSQL_HOST"),
        "MYSQL_PORT": os.getenv("MYSQL_PORT", "3306"),
        "MYSQL_USER": os.getenv("MYSQL_USER"),
        "MYSQL_PASSWORD": os.getenv("MYSQL_PASSWORD"),
        "MYSQL_DATABASE": os.getenv("MYSQL_DATABASE"),
    }

    missing = [k for k, v in required.items() if not v and k != "MYSQL_PORT"]
    if missing:
        raise ValueError(
            f"Missing required environment variables: {', '.join(missing)}. "
            "Copy .env.example to .env and fill in real values."
        )

    return DatabaseConfig(
        host=required["MYSQL_HOST"],
        port=int(required["MYSQL_PORT"]),
        user=required["MYSQL_USER"],
        password=required["MYSQL_PASSWORD"],
        database=required["MYSQL_DATABASE"],
    )


def get_gemini_config() -> GeminiConfig:
    """
    Build GeminiConfig from environment variables.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError(
            "Missing GEMINI_API_KEY environment variable. "
            "Get a key from https://aistudio.google.com/app/apikey"
        )
    return GeminiConfig(api_key=api_key)
