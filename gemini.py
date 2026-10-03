"""
gemini.py — Gemini API Integration

WHY THIS EXISTS:
    This module wraps all communication with the Gemini API.
    It has two jobs:

    1. INTENT EXTRACTION:  Send the user's question (+ conversation
       history) to Gemini and get back a structured JSON intent.

    2. RESPONSE GENERATION:  Send the analytical results (from MySQL)
       to Gemini and get back a business-friendly English explanation.

    The key insight:  Gemini does NOT know the database values.
    It only understands the question and explains the results we give it.

WHAT GEMINI DOES vs WHAT IT DOESN'T:
    ✅  Understands natural language
    ✅  Extracts structured intent from a question
    ✅  Explains numbers in plain English
    ❌  Does NOT have access to the database
    ❌  Does NOT calculate metrics
    ❌  Does NOT generate SQL
"""

from __future__ import annotations

import logging
import time
from typing import Any

from google import genai
from google.genai import types

from config import get_gemini_config
from prompts import (
    INTENT_EXTRACTION_PROMPT,
    RESPONSE_GENERATION_PROMPT,
    EXECUTIVE_SUMMARY_PROMPT,
)
from schemas import AnalyticsIntent, parse_intent_json, IntentValidationError

logger = logging.getLogger(__name__)


class GeminiService:
    """
    Manages Gemini API calls for intent extraction and response generation.
    """

    # Maximum retry attempts for transient API errors (503, rate limits)
    MAX_RETRIES = 3
    RETRY_BASE_DELAY = 2  # seconds; doubles each attempt (2 → 4 → 8)

    def __init__(self):
        config = get_gemini_config()
        self._client = genai.Client(api_key=config.api_key)
        self._model_name = config.model_name
        self._response_model_name = config.response_model_name

    # ------------------------------------------------------------------
    # Retry helper for transient Gemini API errors
    # ------------------------------------------------------------------

    def _call_with_retry(self, model: str, contents: str, config: types.GenerateContentConfig):
        """
        Call Gemini API with automatic retry on transient errors.

        Retries up to MAX_RETRIES times with exponential backoff when the
        API returns 503 UNAVAILABLE (high demand) or 429 RESOURCE_EXHAUSTED
        (rate limit).  Other errors are raised immediately.
        """
        last_error = None
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                response = self._client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=config,
                )
                return response
            except Exception as e:
                error_str = str(e)
                is_transient = (
                    "503" in error_str
                    or "UNAVAILABLE" in error_str
                    or "429" in error_str
                    or "RESOURCE_EXHAUSTED" in error_str
                    or "high demand" in error_str.lower()
                )
                if is_transient and attempt < self.MAX_RETRIES:
                    delay = self.RETRY_BASE_DELAY * (2 ** (attempt - 1))
                    logger.warning(
                        "Gemini API transient error (attempt %d/%d): %s — retrying in %ds",
                        attempt, self.MAX_RETRIES, e, delay,
                    )
                    time.sleep(delay)
                    last_error = e
                else:
                    raise
        # Should not reach here, but just in case
        raise last_error  # type: ignore[misc]

    # ------------------------------------------------------------------
    # Intent extraction
    # ------------------------------------------------------------------

    def extract_intent(
        self,
        question: str,
        conversation_history: list[dict[str, str]] | None = None,
    ) -> AnalyticsIntent:
        """
        Convert a natural-language question into a validated AnalyticsIntent.

        Args:
            question:  The user's question.
            conversation_history:  Recent messages for context resolution
                                   (e.g., "it" → previous category).

        Returns:
            Validated AnalyticsIntent.

        Raises:
            IntentValidationError if the intent is malformed or out-of-range.
            RuntimeError if the Gemini API call fails.
        """
        # Build the full prompt with conversation context
        context_block = ""
        if conversation_history:
            recent = conversation_history[-6:]  # last 3 exchanges (user+assistant)
            context_lines = []
            for msg in recent:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                # Truncate long assistant responses for context
                if role == "assistant" and len(content) > 300:
                    content = content[:300] + "..."
                context_lines.append(f"{role}: {content}")
            context_block = (
                "\n\n## RECENT CONVERSATION CONTEXT\n"
                + "\n".join(context_lines)
            )

        full_prompt = (
            INTENT_EXTRACTION_PROMPT
            + context_block
            + f"\n\n## USER QUESTION\n{question}"
        )

        try:
            response = self._call_with_retry(
                model=self._model_name,
                contents=full_prompt,
                config=types.GenerateContentConfig(
                    temperature=0.1,         # low randomness for structured output
                    max_output_tokens=1024,
                ),
            )
            raw_text = response.text.strip()
            logger.info("Gemini intent response: %s", raw_text[:500])

            intent = parse_intent_json(raw_text, raw_question=question)
            return intent

        except IntentValidationError:
            # Re-raise validation errors as-is (they have user-friendly messages)
            raise
        except Exception as e:
            logger.error("Gemini intent extraction failed: %s", e)
            raise RuntimeError(
                f"Failed to extract intent from your question. "
                f"Please try rephrasing. Error: {e}"
            ) from e

    # ------------------------------------------------------------------
    # Response generation
    # ------------------------------------------------------------------

    def generate_response(
        self,
        question: str,
        data_results: dict[str, Any],
        query_description: str = "",
    ) -> str:
        """
        Generate a business-friendly response from analytical results.

        Args:
            question:           The original user question.
            data_results:       Dict with "data" (DataFrame or dict of DataFrames).
            query_description:  What was queried (for context).

        Returns:
            Natural-language response string.
        """
        # Format the data for the prompt
        data_text = self._format_data_for_prompt(data_results)

        full_prompt = (
            RESPONSE_GENERATION_PROMPT
            + f"\n\n## USER QUESTION\n{question}"
            + f"\n\n## QUERY EXECUTED\n{query_description}"
            + f"\n\n## ANALYTICAL RESULTS (from MySQL database)\n{data_text}"
            + "\n\nGenerate your response now."
        )

        try:
            response = self._call_with_retry(
                model=self._response_model_name,
                contents=full_prompt,
                config=types.GenerateContentConfig(
                    temperature=0.3,
                    max_output_tokens=2048,
                ),
            )
            return response.text.strip()

        except Exception as e:
            logger.error("Gemini response generation failed: %s", e)
            return (
                f"I retrieved the data but encountered an error generating "
                f"the response: {e}. Here's the raw data:\n\n{data_text}"
            )

    # ------------------------------------------------------------------
    # Executive summary
    # ------------------------------------------------------------------

    def generate_executive_summary(
        self, summary_data: dict[str, Any]
    ) -> str:
        """
        Generate an executive summary from pre-calculated metrics.
        """
        data_text = self._format_executive_data(summary_data)

        full_prompt = (
            EXECUTIVE_SUMMARY_PROMPT
            + f"\n\n## ANALYTICAL DATA\n{data_text}"
            + "\n\nGenerate the executive summary now."
        )

        try:
            response = self._call_with_retry(
                model=self._response_model_name,
                contents=full_prompt,
                config=types.GenerateContentConfig(
                    temperature=0.3,
                    max_output_tokens=2048,
                ),
            )
            return response.text.strip()
        except Exception as e:
            logger.error("Executive summary generation failed: %s", e)
            return f"Error generating executive summary: {e}"

    # ------------------------------------------------------------------
    # Data formatting helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _format_data_for_prompt(data_results: dict[str, Any]) -> str:
        """Convert analytical results into a text block for the LLM prompt."""
        import pandas as pd

        data = data_results.get("data")

        if data is None:
            return "No data available."

        if isinstance(data, pd.DataFrame):
            if data.empty:
                return "Query returned no results."
            return data.to_string(index=False)

        if isinstance(data, dict):
            # Executive summary returns a dict of DataFrames
            parts = []
            for key, value in data.items():
                if isinstance(value, pd.DataFrame):
                    if not value.empty:
                        parts.append(f"### {key}\n{value.to_string(index=False)}")
                else:
                    parts.append(f"### {key}\n{value}")
            return "\n\n".join(parts) if parts else "No data available."

        return str(data)

    @staticmethod
    def _format_executive_data(summary_data: dict[str, Any]) -> str:
        """Format executive summary data for the LLM prompt."""
        import pandas as pd

        parts = []
        for key, value in summary_data.items():
            if isinstance(value, pd.DataFrame) and not value.empty:
                parts.append(f"### {key.replace('_', ' ').title()}\n{value.to_string(index=False)}")
            elif isinstance(value, dict):
                for sub_key, sub_val in value.items():
                    if isinstance(sub_val, pd.DataFrame) and not sub_val.empty:
                        parts.append(
                            f"### {sub_key.replace('_', ' ').title()}\n"
                            f"{sub_val.to_string(index=False)}"
                        )

        return "\n\n".join(parts) if parts else "No data available."
