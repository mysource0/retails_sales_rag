# Scalability Architecture — 100 GB Data

## Overview

This document proposes how the Retail Insights Assistant architecture would evolve to handle approximately 100 GB of retail sales data, using Azure cloud services.

**Important**: This is a design document only. The current application runs on a local MySQL database with ~128K rows. This proposal describes the **future architecture** needed when data volume grows by 1000x.

---

## Current vs. Future Scale

| Metric | Current (Local) | Future (100 GB) |
|---|---|---|
| Data Size | ~30 MB | ~100 GB |
| Rows | ~128,000 | ~500M+ |
| Storage | MySQL (local) | Azure Data Lake + Delta Lake |
| Processing | Single-thread SQL | Distributed (Apache Spark) |
| Query Engine | MySQL | Databricks SQL / Azure Synapse |
| Infrastructure | Laptop | Azure Cloud |

---

## Proposed Architecture

```
Large raw files (CSV, JSON, API feeds)
        ↓
Azure Data Lake Storage Gen2 (ADLS Gen2)
        ↓
Azure Databricks / Apache Spark
        ↓
Cleaning + Deduplication + Transformation
        ↓
Delta Lake (Parquet-based storage)
        ↓
Partitioned analytical tables
        ↓
Databricks SQL / Azure Synapse Analytics
        ↓
Analytics query (aggregated results)
        ↓
Small result set (KB, not GB)
        ↓
Gemini API
        ↓
Business-friendly answer
        ↓
Streamlit / Web UI
```

The core principle remains the same:
- **Never send 100 GB of raw data to the LLM.**
- Always aggregate first, then explain.

---

## 1. Data Ingestion — Azure Data Lake Storage Gen2

### What is ADLS Gen2?
Azure Data Lake Storage Gen2 is Microsoft's cloud storage optimized for big data analytics. It combines:
- **Blob storage** (cheap, scalable, durable)
- **Hierarchical namespace** (folder structure, like a filesystem)
- **Fine-grained access control** (per-file permissions)

### Why ADLS Gen2?
- Can store petabytes of data cost-effectively
- Native integration with Spark, Databricks, and Synapse
- Supports structured, semi-structured, and unstructured data
- 99.999999999% (11 nines) durability

### Ingestion Design
```
Raw Zone:           /raw/sales/2022/04/sales_april_2022.csv
                    /raw/sales/2022/05/sales_may_2022.csv
                    
Processed Zone:     /processed/retail_analytics/year=2022/month=4/
                    /processed/retail_analytics/year=2022/month=5/
                    
Curated Zone:       /curated/aggregates/daily_sales.parquet
                    /curated/aggregates/category_summary.parquet
```

Raw files land in the **raw zone**, are processed by Spark, and the clean output goes to the **processed zone** in Parquet/Delta format.

---

## 2. Distributed Processing — Azure Databricks + Apache Spark

### What is Apache Spark?
Apache Spark is a distributed data processing engine. Instead of processing 100 GB on one machine, Spark splits the work across many machines (a "cluster") that work in parallel.

### What is Azure Databricks?
Azure Databricks is a managed Spark platform on Azure. It handles:
- Cluster provisioning (auto-scaling)
- Job scheduling
- Notebook interface for development
- Delta Lake integration

### Processing Pipeline
```python
# Conceptual Spark ETL pipeline

# 1. Read raw data
raw_df = spark.read.csv("adls://raw/sales/", header=True)

# 2. Schema enforcement
from pyspark.sql.types import StructType, StructField, StringType, DecimalType
schema = StructType([
    StructField("order_id", StringType()),
    StructField("order_date", StringType()),
    StructField("amount", StringType()),
    # ... other fields
])

# 3. Data quality validation
clean_df = (raw_df
    .filter(col("order_id").isNotNull())
    .filter(col("order_date").isNotNull())
    .withColumn("sales_amount", 
        when(col("amount") == "", None)
        .otherwise(col("amount").cast(DecimalType(12, 2)))
    )
)

# 4. Deduplication
deduped_df = clean_df.dropDuplicates(["order_id", "sku"])

# 5. Add derived columns
enriched_df = (deduped_df
    .withColumn("order_year", year(col("order_date")))
    .withColumn("order_month", month(col("order_date")))
    .withColumn("order_quarter", quarter(col("order_date")))
)

# 6. Write to Delta Lake, partitioned by year and month
enriched_df.write \
    .format("delta") \
    .partitionBy("order_year", "order_month") \
    .mode("overwrite") \
    .save("adls://processed/retail_analytics/")
```

### Why Spark?
- Processes 100 GB in minutes (distributed across cluster)
- Handles schema enforcement, deduplication, type conversion
- Native integration with Delta Lake and ADLS
- Cost-effective (clusters auto-scale, shut down when idle)

---

## 3. Storage Design — Parquet + Delta Lake

### What is Parquet?
Parquet is a **columnar** file format designed for analytics:
- Stores data by column, not by row
- When you query `SUM(sales_amount)`, only the `sales_amount` column is read (not all 20+ columns)
- Compresses data ~5-10x compared to CSV
- 100 GB CSV → ~15-20 GB Parquet

### What is Delta Lake?
Delta Lake adds ACID transactions and versioning on top of Parquet:
- **Time travel**: Query data as it was at any point in the past
- **Schema enforcement**: Rejects data that doesn't match the schema
- **Merge (upsert)**: Efficiently update existing records
- **Audit history**: Track every change

### Why not one giant CSV?

| Feature | CSV | Parquet/Delta |
|---|---|---|
| Read 1 column from 100 GB | Reads entire 100 GB | Reads only that column (~5 GB) |
| Compression | None | 5-10x |
| Schema | None (just strings) | Enforced types |
| Partitioning | Manual file splitting | Built-in |
| Concurrent access | File locks / corruption | ACID transactions |
| Query performance | Full scan always | Predicate pushdown, partition pruning |

### Partitioning Strategy
```
/processed/retail_analytics/
    ├── order_year=2022/
    │   ├── order_month=3/
    │   │   ├── part-00000.parquet
    │   │   └── part-00001.parquet
    │   ├── order_month=4/
    │   │   ├── part-00000.parquet
    │   │   └── ...
    │   └── order_month=5/
    └── order_year=2023/
        ├── order_month=1/
        └── ...
```

When a query filters by `WHERE order_year = 2022 AND order_month = 4`, the engine reads ONLY the `order_year=2022/order_month=4/` folder. This is called **partition pruning**.

---

## 4. Query Engine — Databricks SQL / Azure Synapse

### How queries work at scale

The analytics assistant's SQL doesn't change much. The difference is WHERE it runs:

**Current (local):**
```sql
-- Runs on local MySQL, single thread
SELECT category, SUM(sales_amount) AS sales
FROM retail_analytics
GROUP BY category
ORDER BY sales DESC
```

**At 100 GB (Databricks SQL):**
```sql
-- Same SQL, but runs on a distributed cluster
-- Databricks automatically uses partition pruning, 
-- column pruning, and parallel aggregation
SELECT category, SUM(sales_amount) AS sales
FROM delta.`adls://processed/retail_analytics/`
GROUP BY category
ORDER BY sales DESC
```

### Key Optimization Techniques

1. **Predicate Pushdown**: Filter conditions are pushed down to the storage layer, so irrelevant data is never read into memory.

2. **Partition Pruning**: Only partitions matching the WHERE clause are scanned. `WHERE order_month = 4` reads only the April folder.

3. **Column Pruning**: Parquet/Delta only reads the columns mentioned in the query. `SELECT category, SUM(sales_amount)` reads only those two columns, not all 20+.

4. **Aggregate Pushdown**: The aggregation (SUM, COUNT) happens in parallel across the cluster, then results are combined.

5. **Materialized Aggregates / Caching**: For frequently asked questions (e.g., "total sales by category"), pre-compute and cache the results in a summary table:
```sql
-- Pre-computed summary table, refreshed daily
CREATE TABLE category_summary AS
SELECT category, 
       SUM(sales_amount) AS sales,
       COUNT(DISTINCT order_id) AS orders,
       SUM(qty) AS units
FROM retail_analytics
GROUP BY category;
```

### Query result size
Even with 100 GB of raw data, the RESULT of an aggregation query is tiny:
- "Sales by category" → 9 rows
- "Sales by state" → ~30 rows
- "Monthly trend" → 12 rows per year

This small result set is what gets sent to Gemini — never the raw data.

---

## 5. Full Proposed Cloud Stack

| Component | Service | Purpose |
|---|---|---|
| Raw Storage | Azure Data Lake Storage Gen2 | Store raw CSV/JSON files |
| Processing | Azure Databricks + Apache Spark | ETL: clean, transform, partition |
| Analytical Storage | Delta Lake on ADLS Gen2 | Columnar, partitioned, versioned |
| Query Engine | Databricks SQL or Azure Synapse | Fast SQL on large datasets |
| LLM | Gemini API | NLU + response generation |
| Application | Streamlit (Azure App Service) | Web UI |
| Orchestration | Azure Data Factory | Schedule ETL pipelines |
| Monitoring | Azure Monitor | Track performance, errors |

---

## 6. What Changes vs. What Stays the Same

### Stays the same:
- User experience (chat interface)
- Structured intent extraction (Gemini → JSON)
- Pre-approved analytics functions (no arbitrary SQL)
- Response generation (data → Gemini → English)
- Security model (read-only, allowlisted operations)

### Changes:
- **Storage**: MySQL → ADLS Gen2 + Delta Lake
- **Query engine**: Local MySQL → Databricks SQL / Synapse
- **ETL**: Simple view → Spark pipeline
- **Database connection**: `mysql.connector` → Databricks SQL connector or Synapse ODBC
- **Infrastructure**: Laptop → Azure Cloud
- **Cost model**: Free → pay-per-use cloud compute

### Conceptual code change:
```python
# Current (database.py)
import mysql.connector
conn = mysql.connector.connect(host="localhost", ...)

# Future (would change to)
from databricks import sql as databricks_sql
conn = databricks_sql.connect(
    server_hostname="<workspace>.azuredatabricks.net",
    http_path="/sql/1.0/warehouses/<warehouse_id>",
    access_token="<token>"
)
```

The `analytics.py` functions and SQL queries remain almost identical.

---

## 7. Cost Considerations

| Resource | Estimated Monthly Cost |
|---|---|
| ADLS Gen2 (100 GB) | ~$2 |
| Databricks (auto-scaling, on-demand) | ~$50-200 (usage dependent) |
| Synapse Serverless | ~$5/TB queried |
| Gemini API | ~$5-20 (depending on usage) |
| App Service (Streamlit) | ~$15-50 |
| **Total** | **~$80-290/month** |

The biggest cost driver is the Databricks/Synapse compute. Using auto-scaling and serverless options keeps costs low during off-peak hours.

---

## Summary

The same architectural pattern — **structured intent → controlled analytics → exact results → LLM explanation** — scales from 128K rows on a laptop to 500M+ rows on Azure. The key differences are:

1. **Storage**: MySQL → ADLS Gen2 + Delta Lake (columnar, partitioned)
2. **Processing**: Single-thread → Spark (distributed, parallel)
3. **Query**: Local MySQL → Databricks SQL (optimized for big data)
4. **Never send raw data to the LLM** — always aggregate first.
