# 📊 Retail Insights Assistant

A production-quality GenAI business analytics assistant that answers natural-language questions about retail sales data using **MySQL** for exact calculations and **Google Gemini** for natural-language understanding and explanation.

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [Problem Statement](#problem-statement)
3. [Dataset Description](#dataset-description)
4. [Architecture](#architecture)
5. [Why MySQL (Not CSV)](#why-mysql-not-csv)
6. [Gemini's Role](#geminis-role)
7. [Analytics Engine](#analytics-engine)
8. [Prompt Engineering](#prompt-engineering)
9. [Security Design](#security-design)
10. [Example Questions](#example-questions)
11. [Screenshots](#screenshots)
12. [Setup Instructions](#setup-instructions)
13. [Running the App](#running-the-app)
14. [Testing](#testing)
15. [100 GB Architecture](#100-gb-architecture)
16. [Future Enhancements](#future-enhancements)
17. [Limitations](#limitations)
18. [Project Structure](#project-structure)

---

## Project Overview

The Retail Insights Assistant is a chatbot that:

- Accepts natural-language business questions
- Extracts structured intents using Gemini API
- Executes pre-approved SQL queries against a MySQL database
- Returns exact analytical results
- Generates business-friendly explanations using Gemini

**Core Principle:**
```
LLM = understand the user's question + explain the result
MySQL/Python = retrieve and calculate the actual data
```

---

## Problem Statement

Retail businesses need quick insights from their sales data, but not everyone knows SQL. This assistant bridges the gap — users ask questions in plain English, and the system provides accurate, data-backed answers.

The LLM is **never** treated as the source of truth for numerical calculations. All metrics are computed by MySQL.

---

## Dataset Description

- **Source**: Indian retail (Amazon India) sales data
- **Database**: `retails_sales` (MySQL)
- **Primary View**: `retail_analytics` (built on `clean_sales` table)
- **Records**: ~128,969 rows
- **Date Range**: March 31, 2022 – June 29, 2022
- **Currency**: INR (₹)

### Key Metrics (dynamically calculated)
| Metric | Value |
|--------|-------|
| Total Orders | ~120,378 |
| Total Units | ~116,646 |
| Total Sales | ~₹78,590,043.30 |
| Average Line Value | ~₹648.56 |

### Available Dimensions
Categories, States, Cities, Order Status, Fulfilment, Sales Channel, B2B, Styles, SKUs, Sizes

---

## Architecture

```
User (natural language question)
    ↓
Streamlit UI
    ↓
Gemini API — Intent Extraction
    ↓
Structured Intent (JSON) — Validated
    ↓
Analytics Dispatcher — Pre-approved functions only
    ↓
Parameterized SQL — MySQL retail_analytics VIEW
    ↓
Exact results (DataFrame)
    ↓
Gemini API — Response Generation
    ↓
Business-friendly answer + charts
    ↓
Streamlit UI → User
```

See [docs/architecture.md](docs/architecture.md) for full details.

---

## Why MySQL (Not CSV)

| Feature | CSV | MySQL |
|---------|-----|-------|
| Data types | Strings only | Enforced (DECIMAL, DATE, etc.) |
| Indexing | None | Yes |
| Views | None | `retail_analytics` view |
| Concurrent access | File locks | Connection pooling |
| Query performance | Full scan | Optimized |

The CSV was imported during previous ETL work. The application queries MySQL directly.

---

## Gemini's Role

Gemini has **two specific jobs** and strict boundaries:

| What Gemini Does | What Gemini Doesn't Do |
|---|---|
| Understands natural language | Access the database |
| Extracts structured intent | Calculate metrics |
| Explains results in English | Generate arbitrary SQL |
| Detects ambiguity | Know current database values |

---

## Analytics Engine

Every business question maps to a pre-approved function in `analytics.py`:

```python
get_overall_metrics()
get_sales_by_category()
get_sales_by_state()
get_sales_by_month()
get_sales_by_quarter()
get_sales_by_fulfilment()
get_b2b_summary()
get_executive_summary()
# ... and more
```

**Consistent metric definitions** used everywhere:
- Sales = `SUM(sales_amount)`
- Units = `SUM(qty)`
- Orders = `COUNT(DISTINCT order_id)`
- Avg = `AVG(sales_amount)`

---

## Prompt Engineering

Two carefully crafted prompts (in `prompts.py`):

1. **Intent Extraction Prompt**: Converts user question → JSON intent
   - Low temperature (0.1) for deterministic output
   - Schema documentation embedded in prompt
   - Explicit rules for edge cases (Q3 data, ambiguity, out-of-scope)

2. **Response Generation Prompt**: Converts data results → English explanation
   - Uses only supplied data (no invention)
   - INR formatting rules
   - Fact vs. interpretation distinction

---

## Security Design

Five layers of protection:

```
Layer 1: Gemini → structured intent (not SQL)
Layer 2: Schema validation (allowlisted fields/operations)
Layer 3: Analytics dispatcher (pre-approved functions only)
Layer 4: SQL keyword blocker (blocks INSERT, DROP, etc.)
Layer 5: Parameterized queries (prevents SQL injection)
```

The application is **read-only**. No write operations are possible.

---

## Example Questions

```
What were the total sales?
Which category had the highest sales?
Which state had the highest sales?
What were monthly sales?
Which fulfilment method had the highest sales?
How many orders were cancelled?
What percentage of orders were B2B?
Give me an executive summary.
Compare sales between April and May.
Which quarter had the highest sales?
What were sales in May 2022?
Show order status breakdown.
Which city had the most orders?
```

### Questions the assistant correctly handles:
```
"Which region performed best in Q3?"
→ Explains Q3 data is not available (dataset ends June 2022)

"What will sales be next year?"
→ Explains this is descriptive analytics, not predictive

"Why did sales increase?"
→ Explains causation can't be determined from the dataset
```

---

## Screenshots

Screenshots of the application are available in the `screenshots/` directory:

1. Main chatbot interface
2. Sidebar KPI dashboard
3. Category sales question with chart
4. State sales question
5. Monthly sales trend
6. Executive summary
7. Out-of-range period handling

---

## Setup Instructions

### Prerequisites
- Python 3.11+
- MySQL 8.0+ (with the existing `retails_sales` database)
- Google Gemini API key ([get one here](https://aistudio.google.com/app/apikey))

### Installation

```bash
# 1. Navigate to the project
cd retail-insights-assistant

# 2. Install dependencies
pip install -r requirements.txt

# 3. Create .env file
cp .env.example .env

# 4. Edit .env with your actual values
# MYSQL_HOST=localhost
# MYSQL_PORT=3306
# MYSQL_USER=root
# MYSQL_PASSWORD=your_password
# MYSQL_DATABASE=retails_sales
# GEMINI_API_KEY=your_api_key
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `MYSQL_HOST` | MySQL server hostname | `localhost` |
| `MYSQL_PORT` | MySQL server port | `3306` |
| `MYSQL_USER` | MySQL username | — |
| `MYSQL_PASSWORD` | MySQL password | — |
| `MYSQL_DATABASE` | Database name | — |
| `GEMINI_API_KEY` | Google Gemini API key | — |

---

## Running the App

```bash
streamlit run app.py
```

The app will open at `http://localhost:8501`.

---

## Testing

```bash
# Run all tests
python -m pytest tests/ -v

# Or with unittest
python -m unittest discover tests -v

# Individual test modules
python -m pytest tests/test_database.py -v
python -m pytest tests/test_analytics.py -v
python -m pytest tests/test_question_validation.py -v
```

### Test Coverage
- **Database tests**: Connection, view existence, SQL safety
- **Analytics tests**: Metric calculations, rankings, trends, filters
- **Validation tests**: Intent parsing, time-period rejection, edge cases, 17+ question types

---

## 100 GB Architecture

See [docs/scalability_100gb.md](docs/scalability_100gb.md) for the full proposal.

### Summary

| Component | Current | At 100 GB |
|---|---|---|
| Storage | MySQL (local) | Azure Data Lake + Delta Lake |
| Processing | Single-thread | Apache Spark (distributed) |
| Query Engine | MySQL | Databricks SQL / Synapse |
| File Format | MySQL tables | Parquet (columnar) |

The core pattern remains the same: `structured intent → controlled query → exact result → LLM explanation`.

### Proposed Cloud Stack
- Azure Data Lake Storage Gen2
- Azure Databricks + Apache Spark
- Delta Lake
- Databricks SQL / Azure Synapse Analytics

---

## Future Enhancements

- [ ] Add more chart types (pie charts, line charts, heatmaps)
- [ ] Export responses to PDF reports
- [ ] Multi-language support
- [ ] Role-based access control
- [ ] Webhook integration for scheduled reports
- [ ] Caching layer for frequently asked queries
- [ ] Advanced conversation memory with topic tracking

---

## Limitations

1. **Dataset Period**: Only covers March 31 – June 29, 2022
2. **No Predictive Analytics**: Descriptive analysis only
3. **No Causation Analysis**: Cannot explain *why* metrics changed
4. **Single Database**: Designed for one MySQL database
5. **No Real-time Data**: Operates on a static historical dataset
6. **Session-only Memory**: Conversation history resets when the browser tab closes

---

## Project Structure

```
retail-insights-assistant/
│
├── app.py                  # Streamlit UI — main entry point
├── database.py             # MySQL connection + query execution
├── analytics.py            # Controlled analytics functions (SQL)
├── gemini.py               # Gemini API integration
├── prompts.py              # Prompt engineering layer
├── schemas.py              # Structured intent schema + validation
├── config.py               # Configuration loading
│
├── tests/
│   ├── test_database.py            # Database connectivity + safety tests
│   ├── test_analytics.py           # Analytics function tests
│   └── test_question_validation.py # Intent validation + 17 question types
│
├── docs/
│   ├── architecture.md         # System architecture documentation
│   ├── scalability_100gb.md    # 100 GB Azure architecture proposal
│   └── learning_notes.md       # Beginner-friendly concept explanations
│
├── screenshots/                # Application screenshots for submission
│
├── .env.example            # Environment variable template
├── .gitignore              # Git ignore rules
├── requirements.txt        # Python dependencies
└── README.md               # This file
```

---

## Technologies Used

| Technology | Purpose |
|---|---|
| Python 3.11 | Application language |
| MySQL 8.0 | Data storage + exact calculations |
| Google Gemini API | Natural language understanding + explanation |
| Streamlit | Web UI framework |
| Pandas | Data manipulation |
| Plotly | Interactive charts |
| mysql-connector-python | MySQL driver |
| python-dotenv | Environment variable management |

---

## License

This project was created for educational/assignment purposes.
