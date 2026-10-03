# Architecture — Retail Insights Assistant

## Overview

This document explains the architecture of the Retail Insights Assistant, a GenAI-powered business analytics chatbot that answers natural-language questions about a retail sales dataset stored in MySQL.

---

## Core Principle

```
LLM = understand the user's question + explain the result
MySQL/Python = retrieve and calculate the actual data
```

Gemini does **NOT** know the current database values by itself. It never calculates metrics. Instead:

1. **Gemini understands the question** and extracts a structured intent.
2. **Python selects the correct analytical operation** based on the intent.
3. **MySQL retrieves/calculates exact values** from the `retail_analytics` view.
4. **Gemini explains those values** in business-friendly language.

---

## Architecture Diagram

```
User (natural language question)
    ↓
Streamlit UI (app.py)
    ↓
Gemini API — Intent Extraction (gemini.py)
    ↓
Structured Intent JSON (schemas.py)
    ↓
Schema Validation (schemas.py)
    ↓
Analytics Dispatcher (analytics.py)
    ↓
Pre-approved SQL Function
    ↓
Parameterized SQL Query
    ↓
MySQL — retail_analytics VIEW
    ↓
Exact analytical results (DataFrame)
    ↓
Gemini API — Response Generation (gemini.py)
    ↓
Business-friendly response
    ↓
Streamlit UI → User
```

---

## Module Responsibilities

### `config.py` — Configuration
- Loads environment variables (database credentials, API keys)
- Defines dataset metadata (date range, available quarters)
- Catches missing config early with clear error messages

### `database.py` — Database Connection Layer
- Manages MySQL connection pool (3 connections)
- Executes parameterized SELECT queries only
- **Blocks all write operations** (INSERT, UPDATE, DELETE, DROP, etc.)
- Returns rows as Python dictionaries

### `schemas.py` — Structured Intent Schema
- Defines the `AnalyticsIntent` dataclass (the contract between LLM and analytics)
- Validates intent fields against allowlists (metrics, dimensions, aggregations)
- Validates time-period filters against the actual dataset range
- Parses raw JSON from Gemini into validated intents

### `analytics.py` — Controlled Analytics Registry
- **The ONLY module that generates SQL**
- Pre-approved functions for each analytical operation
- Maps structured intents to the correct function via `dispatch()`
- Uses consistent metric definitions everywhere
- Supports time filtering (year, month, quarter)

### `gemini.py` — Gemini API Integration
- **Intent extraction**: Sends user question → gets structured JSON intent
- **Response generation**: Sends data results → gets English explanation
- **Executive summary**: Combines multiple metrics into a narrative
- Uses low temperature (0.1) for intent extraction (deterministic)
- Uses slightly higher temperature (0.3) for response generation (natural)

### `prompts.py` — Prompt Engineering Layer
- Centralizes all LLM prompts in one place
- **Prompt A (Intent Extraction)**: Converts question → JSON, with schema docs
- **Prompt B (Response Generation)**: Converts data → English, with formatting rules
- **Prompt C (Executive Summary)**: Generates structured narrative from multi-metric data

### `app.py` — Streamlit UI
- Chat interface with `st.chat_input()` and `st.chat_message()`
- Sidebar with KPI metrics, connection status, example questions
- Charts (Plotly) generated from SQL results
- Session state for conversation memory

---

## Security Design

### What the app ALLOWS:
- Pre-approved SELECT queries through allowlisted analytics functions
- Parameterized SQL (user values never concatenated into SQL)
- Read-only database access

### What the app BLOCKS:
- Arbitrary SQL from the LLM
- INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, TRUNCATE, GRANT, REVOKE
- Unknown metrics, dimensions, or aggregations
- Time periods outside the dataset range

### Safety layers:
```
Layer 1: Gemini → structured intent (not SQL)
Layer 2: Schema validation (allowlists)
Layer 3: Analytics dispatcher (pre-approved functions only)
Layer 4: SQL keyword blocker (defence in depth)
Layer 5: Parameterized queries (prevent injection)
```

---

## Data Flow Example

### Question: "Which category generated the most sales?"

```
1. User types question in Streamlit

2. Gemini extracts intent:
   {
     "intent": "ranking",
     "metric": "sales",
     "dimension": "category",
     "aggregation": "sum",
     "sort_order": "desc"
   }

3. Schema validates: ✅ all fields in allowlists

4. Analytics dispatcher routes to get_sales_by_category()

5. SQL executed:
   SELECT category AS dimension_value,
          SUM(sales_amount) AS metric_value,
          COUNT(DISTINCT order_id) AS orders,
          SUM(qty) AS units,
          SUM(sales_amount) AS sales
   FROM retail_analytics
   GROUP BY category
   ORDER BY metric_value DESC
   LIMIT 10

6. MySQL returns:
   | category      | metric_value   |
   |---------------|----------------|
   | Set           | 39,202,022.03  |
   | kurta         | 21,299,013.70  |
   | Western Dress | 11,216,072.69  |
   | ...           | ...            |

7. Gemini generates response:
   "Set generated the highest sales at ₹39,202,022.03..."

8. Response + chart displayed in Streamlit
```

---

## Why This Architecture?

| Design Choice | Why |
|---|---|
| MySQL (not CSV) | CSV can't efficiently query 128K rows, has no indexing, and risks inconsistent parsing |
| `retail_analytics` view | Centralizes data transformations (type casting, column extraction) at the database level |
| Structured intent (not SQL) | Prevents LLM from generating arbitrary/dangerous SQL |
| Pre-approved functions | Each function is reviewed, tested, and uses parameterized queries |
| Gemini for NLU only | LLMs are good at language, bad at exact math — use each tool for what it does best |
| Streamlit | Simple Python-native UI framework, perfect for data apps |
