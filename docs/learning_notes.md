# Learning Notes — Retail Insights Assistant

## Introduction

This document explains the key concepts behind the Retail Insights Assistant in beginner-friendly language. If you're reading the code and wondering *why* something works the way it does, this is your guide.

---

## 1. How Python Connects to MySQL

Python doesn't natively speak to MySQL. We use a **connector library** called `mysql-connector-python` which acts as a translator.

```python
import mysql.connector

# This opens a network connection to the MySQL server
conn = mysql.connector.connect(
    host="localhost",      # where MySQL is running
    port=3306,             # MySQL's default port
    user="root",           # database username
    password="secret",     # database password
    database="retails_sales"  # which database to use
)

# A cursor is like a pointer that executes queries
cursor = conn.cursor(dictionary=True)
cursor.execute("SELECT * FROM retail_analytics LIMIT 5")
rows = cursor.fetchall()  # returns list of dicts

# Always close connections when done
cursor.close()
conn.close()
```

**Connection pooling**: Instead of opening a new connection for every query (slow!), we create a "pool" of 3 connections that get reused. This is especially important in Streamlit, which re-runs the entire script on every user interaction.

---

## 2. What is a Database View?

A **view** is a saved SQL query that acts like a virtual table. When you query a view, MySQL runs the underlying query and returns the results as if they were a real table.

```sql
-- Creating a view (this was done in previous ETL work)
CREATE VIEW retail_analytics AS
SELECT
    order_id,
    order_date,
    YEAR(order_date)    AS order_year,
    MONTH(order_date)   AS order_month,
    QUARTER(order_date) AS order_quarter,
    -- ... other columns ...
    CASE 
        WHEN amount = '' OR amount IS NULL THEN NULL
        ELSE CAST(amount AS DECIMAL(12,2))
    END AS sales_amount
FROM clean_sales;
```

### Why is `retail_analytics` a view?

The original `clean_sales` table has `amount` stored as VARCHAR (text), and some values are blank. Querying it directly for analytics would cause errors or wrong results.

The view:
1. **Converts** `amount` from text to a proper number (`DECIMAL(12,2)`)
2. **Handles blanks** by converting them to NULL (not zero — that would be wrong!)
3. **Extracts** year, month, and quarter from the date (so we don't have to do it in every query)
4. **Doesn't duplicate data** — it's just a saved query, not a copy of the table

---

## 3. Why SQL Should Calculate Business Metrics (Not the LLM)

This is the most important concept in this project.

**❌ BAD approach**: Send 128,000 rows to Gemini and ask "What's the total sales?"
- LLMs can't reliably count or add numbers
- 128K rows won't fit in the context window
- Even if they did, the LLM might hallucinate a number

**✅ GOOD approach**: Let MySQL calculate `SUM(sales_amount)` and tell Gemini "the total is ₹78,590,043.30, explain this to the user"
- MySQL is purpose-built for exact numerical computation
- The result is one number, which easily fits in the prompt
- Gemini can explain the number clearly

### Metric Definitions (used consistently everywhere)

```
Sales  = SUM(sales_amount)         -- total revenue
Units  = SUM(qty)                  -- total items sold
Orders = COUNT(DISTINCT order_id)  -- unique orders
Avg    = AVG(sales_amount)         -- average line value
```

These are defined once in `analytics.py` and used by every function.

---

## 4. What Does Gemini Do?

Gemini is Google's large language model (LLM). In this project, it has TWO specific jobs:

### Job 1: Understand the Question (Intent Extraction)

```
User: "Which category generated the highest sales?"

Gemini output:
{
  "intent": "ranking",
  "metric": "sales",
  "dimension": "category",
  "aggregation": "sum",
  "sort_order": "desc"
}
```

Gemini translates human language into a structured format that Python can understand. It does NOT answer the question — it only categorizes it.

### Job 2: Explain the Results (Response Generation)

```
Input to Gemini:
  Question: "Which category generated the highest sales?"
  Data: Set = ₹39,202,022.03, kurta = ₹21,299,013.70, ...

Gemini output:
  "The Set category generated the highest sales at ₹39,202,022.03,
   followed by kurta at ₹21,299,013.70..."
```

Gemini takes the exact numbers (from MySQL) and writes a business-friendly explanation.

### What Gemini does NOT do:
- ❌ Access the database
- ❌ Calculate SUM, COUNT, or AVG
- ❌ Generate SQL queries
- ❌ Know current database values without being told

---

## 5. What is Prompt Engineering?

Prompt engineering is the practice of carefully writing the instructions given to an LLM to get reliable output.

### Example of a BAD prompt:
```
Tell me what the user wants.
```
→ Output could be anything: a story, a poem, random text.

### Example of a GOOD prompt:
```
You are an intent-extraction engine.
Your ONLY job is to convert the user's question into this JSON format:
{
  "intent": "ranking" | "aggregation" | ...,
  "metric": "sales" | "units" | "orders",
  ...
}
RULES:
- Do NOT answer the question
- Do NOT generate SQL
- Return ONLY JSON
```
→ Output is consistently structured JSON that Python can parse.

### Key prompt engineering techniques used in this project:

1. **Role definition**: "You are an intent-extraction engine" (not "an AI assistant")
2. **Output format specification**: Exact JSON schema with field names and allowed values
3. **Negative constraints**: "Do NOT answer the question", "Do NOT generate SQL"
4. **Examples**: Showing what correct output looks like
5. **Context injection**: Providing the schema, dataset description, and conversation history
6. **Temperature control**: Low temperature (0.1) for intent extraction = more deterministic

---

## 6. What is Structured Output?

Instead of letting the LLM output free-form text, we constrain it to return a specific JSON shape. This lets Python code reliably extract information.

```
Free-form (unreliable):
  "The user seems to be asking about sales by category, 
   specifically which one is highest."

Structured (reliable):
  {"intent": "ranking", "metric": "sales", "dimension": "category"}
```

The structured output is validated against an allowlist (see `schemas.py`). If Gemini outputs an unknown field name like `"dimension": "region"`, the validation catches it immediately.

---

## 7. What is Function/Tool Calling?

In more advanced GenAI applications, the LLM can "call" predefined functions (tools) by outputting a structured request. This project uses a simplified version of this concept:

```
Gemini → structured intent → analytics.dispatch() → correct function
```

For example, an intent with `dimension: "category"` routes to `get_sales_by_category()`.

This is conceptually identical to LLM tool calling, but implemented explicitly in Python for transparency and control.

---

## 8. What is Text-to-SQL?

Text-to-SQL is the idea of having an LLM convert natural language directly into SQL:

```
User: "Which category had the highest sales?"
LLM: "SELECT category, SUM(sales_amount) FROM sales GROUP BY category ORDER BY 2 DESC LIMIT 1"
```

### Why Arbitrary Text-to-SQL is Dangerous

1. **SQL injection**: The LLM might be tricked into generating `DROP TABLE` or `DELETE` statements
2. **Incorrect queries**: The LLM might join wrong tables, use wrong column names, or miss WHERE clauses
3. **No validation**: There's no way to verify the SQL is correct before executing it
4. **Sensitive data exposure**: The LLM might query columns it shouldn't

### Our Safer Alternative

Instead of text-to-SQL, we use **text-to-intent**:
```
User question → Gemini → structured intent → pre-approved function → parameterized SQL
```

Every SQL query in this project was written by a human developer and tested. The LLM only decides WHICH pre-approved query to run, not WHAT the query says.

---

## 9. Why Parameterized SQL is Important

**❌ String concatenation (DANGEROUS):**
```python
# An attacker could type: '; DROP TABLE retail_analytics; --
sql = f"SELECT * FROM retail_analytics WHERE category = '{user_input}'"
```

**✅ Parameterized queries (SAFE):**
```python
sql = "SELECT * FROM retail_analytics WHERE category = %s"
cursor.execute(sql, (user_input,))
```

With parameterized queries, the database treats `user_input` as DATA, not as SQL code. Even if someone types `'; DROP TABLE`, it would literally search for a category named that string.

---

## 10. How Streamlit Works

Streamlit is a Python framework that turns scripts into web apps.

### Key concept: The script re-runs on every interaction

```python
import streamlit as st

st.title("Hello")

# This re-runs EVERY TIME the user types something
user_input = st.chat_input("Ask me anything")

if user_input:
    st.write(f"You said: {user_input}")
```

### Session State

Because the script re-runs, you'd normally lose all variables. `st.session_state` preserves data between re-runs:

```python
# This persists across re-runs
if "messages" not in st.session_state:
    st.session_state.messages = []  # only runs once

# Add a message
st.session_state.messages.append("Hello!")
```

### Caching

`@st.cache_resource` prevents re-creating expensive objects (like database connections) on every re-run:

```python
@st.cache_resource
def get_database():
    return DatabaseConnection()  # created once, reused forever
```

---

## 11. Why RAG is Not Necessary Here

RAG (Retrieval-Augmented Generation) is a technique where you:
1. Convert documents into numerical vectors (embeddings)
2. Store them in a vector database
3. When the user asks a question, find the most similar documents
4. Send those documents to the LLM as context

### When RAG is useful:
- Unstructured data (PDFs, documents, emails)
- Questions that need semantic search ("find similar products")
- Knowledge bases with thousands of documents

### Why RAG is NOT useful for this project:
- Our data is **structured** (rows and columns in MySQL)
- Questions need **exact calculations** (SUM, COUNT, AVG)
- The answer is always a specific number, not a text passage
- MySQL already provides the "retrieval" we need (SQL queries)

Using RAG for "What were total sales?" would be like using a search engine to find a number that's already in your calculator.

---

## 12. Why CSV is Not the Primary Source

The original data started as CSV files, but the application uses MySQL instead.

### CSV limitations:
- No data types (everything is a string)
- No indexing (every query scans the entire file)
- No concurrent access (file locks)
- No joins or views
- No integrity constraints
- Parsing inconsistencies (comma in values, encoding issues)

### MySQL advantages:
- Enforced data types (`DECIMAL(12,2)` for amounts)
- Indexed columns for fast lookups
- Views for clean analytical interfaces
- Connection pooling for concurrent access
- ACID transactions (data consistency)

The CSV was imported into MySQL during previous ETL work. The app now queries MySQL directly.

---

## 13. How the Architecture Changes at 100 GB

See `scalability_100gb.md` for the full proposal. The key changes:

| Component | Current | At 100 GB |
|---|---|---|
| Storage | MySQL (local) | Azure Data Lake + Delta Lake |
| Processing | Single-thread | Apache Spark (distributed) |
| Query Engine | MySQL | Databricks SQL |
| File Format | MySQL tables | Parquet (columnar) |

**What stays the same**: The core pattern of `question → intent → controlled query → exact result → explanation`.

---

## 14. What is Apache Spark?

Spark is a distributed data processing engine. Instead of one machine processing 100 GB, Spark splits the work across many machines that work in parallel.

```
100 GB of data
    ↓
Split into 1000 partitions (~100 MB each)
    ↓
100 machines each process 10 partitions
    ↓
Results combined
    ↓
Done in minutes instead of hours
```

Spark provides:
- DataFrame API (similar to pandas, but distributed)
- SQL interface (write SQL, Spark distributes execution)
- ETL capabilities (read CSV → clean → write Parquet)

---

## 15. What is Parquet?

Parquet is a **columnar** file format. Traditional formats (CSV, JSON) store data row-by-row. Parquet stores data column-by-column.

### Why this matters:

```
Query: SELECT SUM(sales_amount) FROM retail_analytics

CSV (row-based):  Must read ALL columns of ALL rows  = 100 GB
Parquet (columnar): Reads only sales_amount column   = ~5 GB
```

Parquet also compresses data 5-10x, so 100 GB of CSV becomes ~15 GB of Parquet.

---

## 16. What is Delta Lake?

Delta Lake adds reliability features on top of Parquet:

1. **ACID transactions**: Multiple writers won't corrupt the data
2. **Time travel**: Query historical versions (`SELECT * FROM table VERSION AS OF 5`)
3. **Schema enforcement**: Rejects data that doesn't match the expected schema
4. **Merge operations**: Efficiently update/insert records (upserts)

Think of it as "Parquet with superpowers."

---

## 17. What is ADLS Gen2?

Azure Data Lake Storage Gen2 is Microsoft's cloud storage for big data. Key features:
- Stores any amount of data (petabytes)
- Hierarchical namespace (folders, like a filesystem)
- Cheap (~$0.02/GB/month)
- Integrated with Spark, Databricks, Synapse
- Fine-grained access control

---

## 18. What is Azure Databricks?

Databricks is a managed platform for Apache Spark on Azure. It handles:
- **Cluster management**: Auto-creates and destroys Spark clusters
- **Notebooks**: Write Python/SQL code in a browser
- **Delta Lake**: Built-in support
- **SQL warehouse**: Run SQL queries on big data with a JDBC connector
- **Scheduling**: Run ETL jobs on a schedule

The main benefit: You don't have to manage Spark infrastructure yourself.

---

## Summary: The Big Picture

```
                    CURRENT                         FUTURE (100 GB)
                    ───────                         ───────────────
Question:           Same                            Same
Intent extraction:  Gemini                          Gemini
Schema validation:  Python                          Python
Query execution:    MySQL (local)                   Databricks SQL (cloud)
Data storage:       MySQL tables                    Delta Lake + Parquet
Data processing:    None needed (ETL done)          Spark (distributed ETL)
Response generation:Gemini                          Gemini
UI:                 Streamlit (local)               Streamlit (cloud-hosted)
```

The architecture is designed to scale. When data grows, you change the **infrastructure layer** (storage, compute), not the **application logic** (intents, prompts, analytics functions).
