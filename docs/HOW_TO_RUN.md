# 🚀 How to Run — Retail Insights Assistant

> **Complete step-by-step guide** to set up and run the Retail Insights Assistant on your local machine.

---

## 📋 Prerequisites

Before you begin, ensure you have the following installed:

| Requirement          | Minimum Version | Check Command              |
|----------------------|-----------------|----------------------------|
| **Python**           | 3.11+           | `python --version`         |
| **pip**              | 23.0+           | `pip --version`            |
| **MySQL Server**     | 8.0+            | `mysql --version`          |
| **Google Gemini API Key** | —          | [Get one here](https://aistudio.google.com/app/apikey) |

---

## 🗂️ Step 1 — Clone / Download the Project

```bash
# If using git:
git clone <repository-url>
cd retail-insights-assistant

# Or download the ZIP and extract it, then navigate into the folder:
cd retail-insights-assistant
```

---

## 🐍 Step 2 — Create a Virtual Environment

A virtual environment isolates the project's dependencies from your system Python.

### Windows (PowerShell)

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### Windows (CMD)

```cmd
python -m venv venv
venv\Scripts\activate.bat
```

### macOS / Linux

```bash
python3 -m venv venv
source venv/bin/activate
```

> **Verify:** After activation, your terminal prompt should show `(venv)` at the beginning.

---

## 📦 Step 3 — Install Dependencies

```bash
pip install -r requirements.txt
```

This installs the following packages:

| Package                  | Purpose                               |
|--------------------------|---------------------------------------|
| `mysql-connector-python` | MySQL database driver                 |
| `python-dotenv`          | Loads `.env` file into environment    |
| `google-genai`           | Google Gemini API client              |
| `streamlit`              | Web UI framework                      |
| `pandas`                 | Data manipulation (DataFrames)        |
| `plotly`                 | Interactive charts                    |

---

## 🗄️ Step 4 — Set Up the MySQL Database

### 4.1 — Start MySQL Server

Make sure your MySQL server is running:

- **Windows**: Open Services (`services.msc`) → find **MySQL80** → Start
- **macOS**: `brew services start mysql`
- **Linux**: `sudo systemctl start mysql`

### 4.2 — Create the Database and Import Data

If you haven't already set up the database, connect to MySQL and run:

```sql
-- Connect to MySQL
mysql -u root -p

-- Create the database
CREATE DATABASE IF NOT EXISTS retails_sales;
USE retails_sales;
```

Then import your data (the `clean_sales` table) and create the analytical view:

```sql
-- Create the analytical view (if not already present)
-- The view must be named: retail_analytics
-- It should expose these columns:
--   order_id, order_date, order_year, order_month, order_quarter,
--   category, sales_amount, qty, order_status, fulfilment,
--   sales_channel, b2b, style, sku, size, ship_state, ship_city,
--   courier_status, ship_service_level, fulfilled_by
```

### 4.3 — Verify the Database

```sql
-- Check the view exists
SELECT TABLE_NAME FROM information_schema.VIEWS 
WHERE TABLE_SCHEMA = 'retails_sales' AND TABLE_NAME = 'retail_analytics';

-- Check row count (should be ~128,969)
SELECT COUNT(*) FROM retail_analytics;

-- Quick data preview
SELECT * FROM retail_analytics LIMIT 5;
```

---

## 🔑 Step 5 — Configure Environment Variables

### 5.1 — Create the `.env` File

```bash
# Copy the template
cp .env.example .env
```

Or on **Windows PowerShell**:

```powershell
Copy-Item .env.example .env
```

### 5.2 — Edit `.env` with Your Values

Open `.env` in any text editor and fill in your credentials:

```env
# MySQL Database Configuration
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=your_mysql_password_here
MYSQL_DATABASE=retails_sales

# Google Gemini API Key
GEMINI_API_KEY=your_gemini_api_key_here
```

### Environment Variables Reference

| Variable         | Required | Description                        | Default     |
|------------------|----------|------------------------------------|-------------|
| `MYSQL_HOST`     | ✅       | MySQL server hostname              | `localhost` |
| `MYSQL_PORT`     | ❌       | MySQL server port                  | `3306`      |
| `MYSQL_USER`     | ✅       | MySQL username                     | —           |
| `MYSQL_PASSWORD` | ✅       | MySQL password                     | —           |
| `MYSQL_DATABASE` | ✅       | Database name                      | —           |
| `GEMINI_API_KEY` | ✅       | Google Gemini API key              | —           |

> ⚠️ **Never commit the `.env` file to version control.** It is already listed in `.gitignore`.

---

## ▶️ Step 6 — Run the Application

```bash
streamlit run app.py
```

The application will start and display:

```
  You can now view your Streamlit app in your browser.

  Local URL: http://localhost:8501
  Network URL: http://<your-ip>:8501
```

**Open your browser** and navigate to: **http://localhost:8501**

### Custom Port (Optional)

```bash
streamlit run app.py --server.port 8080
```

---

## ✅ Step 7 — Verify Everything Works

Once the app is running, check the following:

| Check                      | Expected Result                                        |
|----------------------------|--------------------------------------------------------|
| **Sidebar → Connection**   | ✅ MySQL Connected (green badge)                       |
| **Sidebar → Key Metrics**  | Shows Total Orders, Total Units, Total Sales, Avg Line Value |
| **Sidebar → Example Questions** | 10 clickable example question buttons              |
| **Chat Input**             | Text input at the bottom: "Ask a business question..." |

### Quick Test Questions

Try typing these in the chat:

1. **`What were the total sales?`** → Should return ~₹78,590,043.30
2. **`Which category had the highest sales?`** → Should show "Set" at the top with a bar chart
3. **`Give me an executive summary`** → Should produce a detailed narrative summary

---

## 🧪 Running Tests

```bash
# Run all tests
python -m pytest tests/ -v

# Individual test modules
python -m pytest tests/test_database.py -v        # Database connectivity & safety
python -m pytest tests/test_analytics.py -v       # Analytics calculations
python -m pytest tests/test_question_validation.py -v  # Intent validation (17+ question types)
```

---

## 🔧 Troubleshooting

### ❌ "Cannot connect to MySQL"

| Possible Cause | Solution |
|---|---|
| MySQL server not running | Start MySQL: `services.msc` (Windows) or `sudo systemctl start mysql` (Linux) |
| Wrong credentials in `.env` | Verify `MYSQL_USER` and `MYSQL_PASSWORD` match your MySQL setup |
| Database doesn't exist | Run `CREATE DATABASE retails_sales;` in MySQL |
| View doesn't exist | Create the `retail_analytics` view (see Step 4.2) |
| Port conflict | Check `MYSQL_PORT` in `.env` matches your MySQL config |

### ❌ "Gemini API Error" / 503 UNAVAILABLE

| Possible Cause | Solution |
|---|---|
| Invalid API key | Get a new key from [Google AI Studio](https://aistudio.google.com/app/apikey) |
| 503 High Demand | **Temporary** — the app has built-in retry logic (3 attempts with exponential backoff). Wait a moment and try again. |
| Model deprecated | The app uses `gemini-3.8-flash`. If deprecated, update `model_name` in `config.py`. |
| Network issues | Check your internet connection |

### ❌ "ModuleNotFoundError"

```bash
# Make sure venv is activated, then reinstall:
pip install -r requirements.txt
```

### ❌ Streamlit shows a blank page

- Hard refresh: `Ctrl + Shift + R` (or `Cmd + Shift + R` on Mac)
- Check the terminal for error messages
- Ensure all services (MySQL, internet for Gemini) are accessible

---

## 📁 Project Structure

```
retail-insights-assistant/
│
├── app.py                  # Streamlit UI — main entry point
├── database.py             # MySQL connection pool + safe query execution
├── analytics.py            # Controlled analytics functions (SQL layer)
├── gemini.py               # Gemini API integration (with retry logic)
├── prompts.py              # Prompt engineering layer
├── schemas.py              # Structured intent schema + validation
├── config.py               # Configuration loading from .env
│
├── tests/
│   ├── test_database.py            # Database connectivity + SQL safety tests
│   ├── test_analytics.py           # Analytics function accuracy tests
│   └── test_question_validation.py # Intent validation + 17 question types
│
├── docs/
│   ├── HOW_TO_RUN.md          # ← This file
│   ├── architecture.md        # System architecture documentation
│   ├── scalability_100gb.md   # 100 GB Azure architecture proposal
│   └── learning_notes.md      # Beginner-friendly concept explanations
│
├── screenshots/               # Application screenshots
│
├── .env.example            # Environment variable template
├── .env                    # Your local config (not committed)
├── .gitignore              # Git ignore rules
├── requirements.txt        # Python dependencies
└── README.md               # Project overview & documentation
```

---

## 🔄 Stopping the Application

Press `Ctrl + C` in the terminal where Streamlit is running.

To deactivate the virtual environment:

```bash
deactivate
```

---

## 📌 Quick Reference Card

```bash
# Activate venv
.\venv\Scripts\Activate.ps1          # Windows PowerShell
source venv/bin/activate              # macOS / Linux

# Install dependencies
pip install -r requirements.txt

# Run the app
streamlit run app.py

# Run tests
python -m pytest tests/ -v

# Stop the app
Ctrl + C

# Deactivate venv
deactivate
```

---

## 🏗️ Architecture Overview

```
User Question → Gemini (Intent Extraction) → Validated JSON Intent
    → Analytics Dispatcher → Pre-approved SQL → MySQL
        → Exact Results → Gemini (Response Generation)
            → Business-friendly Answer + Charts → Streamlit UI
```

**Key principle:** Gemini understands questions and explains results — it never touches the database or calculates numbers. MySQL handles all data computation.

---

## 📞 Getting Help

- Check the [README.md](../README.md) for full project documentation
- Check [architecture.md](architecture.md) for system design details
- Check [learning_notes.md](learning_notes.md) for beginner-friendly explanations
- Check [scalability_100gb.md](scalability_100gb.md) for scaling proposals
