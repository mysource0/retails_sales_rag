"""
app.py — Streamlit UI for Retail Insights Assistant

WHY THIS EXISTS:
    This is the user-facing entry point.  It provides:
    1. A chat interface for natural-language business questions
    2. Sidebar KPI metrics and example questions
    3. Charts for visual analytics
    4. An executive summary feature

HOW STREAMLIT WORKS:
    Streamlit re-runs this entire script top-to-bottom every time the
    user interacts with the page (clicks a button, submits a message).
    State is preserved between re-runs using st.session_state, which
    acts like a global dictionary that persists across re-runs.

ARCHITECTURE FLOW:
    User question
      → Gemini extracts structured intent
        → Analytics layer executes approved SQL
          → MySQL returns exact results
            → Gemini explains results in English
              → Streamlit displays the response
"""

import logging
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from database import DatabaseConnection
from analytics import AnalyticsService
from gemini import GeminiService
from schemas import AnalyticsIntent, IntentValidationError
from config import DATASET_DATE_MIN, DATASET_DATE_MAX

# ---------------------------------------------------------------------------
# Logging (debug info goes to console, not to the user)
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Page configuration — must be the first Streamlit command
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Retail Insights Assistant",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ---------------------------------------------------------------------------
# Custom CSS for a clean, professional look
# ---------------------------------------------------------------------------
st.markdown("""
<style>
    /* Main header styling */
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        color: #1a1a2e;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1.1rem;
        color: #6c757d;
        margin-bottom: 1.5rem;
    }

    /* Metric cards */
    [data-testid="stMetric"] {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1rem;
        border-radius: 0.75rem;
        color: white;
    }
    [data-testid="stMetric"] label {
        color: rgba(255, 255, 255, 0.85) !important;
    }
    [data-testid="stMetric"] [data-testid="stMetricValue"] {
        color: white !important;
        font-size: 1.3rem !important;
    }

    /* Chat message styling */
    .stChatMessage {
        border-radius: 0.75rem;
    }

    /* Sidebar styling */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #f8f9fa 0%, #e9ecef 100%);
    }

    /* Dataframe styling */
    .dataframe {
        font-size: 0.85rem;
    }

    /* Status badges */
    .status-badge {
        display: inline-block;
        padding: 0.25rem 0.75rem;
        border-radius: 1rem;
        font-size: 0.8rem;
        font-weight: 600;
    }
    .status-connected {
        background: #d4edda;
        color: #155724;
    }
    .status-error {
        background: #f8d7da;
        color: #721c24;
    }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Session state initialisation
# ---------------------------------------------------------------------------
def init_session_state():
    """Initialise all session-state keys on first run."""
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "db" not in st.session_state:
        st.session_state.db = None
    if "analytics" not in st.session_state:
        st.session_state.analytics = None
    if "gemini" not in st.session_state:
        st.session_state.gemini = None
    if "db_connected" not in st.session_state:
        st.session_state.db_connected = False
    if "overall_metrics" not in st.session_state:
        st.session_state.overall_metrics = None

init_session_state()


# ---------------------------------------------------------------------------
# Service initialisation (with caching)
# ---------------------------------------------------------------------------
@st.cache_resource(show_spinner=False)
def get_database():
    """Create a single DatabaseConnection (cached across reruns)."""
    return DatabaseConnection()

@st.cache_resource(show_spinner=False)
def get_analytics(_db):
    """Create AnalyticsService (cached)."""
    return AnalyticsService(_db)

@st.cache_resource(show_spinner=False)
def get_gemini():
    """Create GeminiService (cached)."""
    return GeminiService()


def initialise_services():
    """Connect to MySQL and Gemini.  Show errors in sidebar if something fails."""
    try:
        db = get_database()
        if db.test_connection():
            st.session_state.db = db
            st.session_state.analytics = get_analytics(db)
            st.session_state.db_connected = True
        else:
            st.session_state.db_connected = False
            st.sidebar.error("❌ Cannot connect to MySQL. Check your .env file.")
            return
    except Exception as e:
        st.session_state.db_connected = False
        st.sidebar.error(f"❌ Database error: {e}")
        return

    try:
        st.session_state.gemini = get_gemini()
    except Exception as e:
        st.sidebar.error(f"❌ Gemini API error: {e}")


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
def render_sidebar():
    """Render KPI metrics, connection status, and example questions."""
    with st.sidebar:
        st.markdown("### 🔌 Connection Status")
        if st.session_state.db_connected:
            st.markdown(
                '<span class="status-badge status-connected">✅ MySQL Connected</span>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<span class="status-badge status-error">❌ MySQL Disconnected</span>',
                unsafe_allow_html=True,
            )
            return

        st.divider()

        # KPI Metrics
        st.markdown("### 📈 Key Metrics")
        try:
            if st.session_state.overall_metrics is None:
                st.session_state.overall_metrics = (
                    st.session_state.analytics.get_overall_metrics()
                )

            metrics = st.session_state.overall_metrics
            if not metrics.empty:
                row = metrics.iloc[0]

                col1, col2 = st.columns(2)
                with col1:
                    st.metric(
                        "Total Orders",
                        f"{int(row['total_orders']):,}",
                    )
                with col2:
                    st.metric(
                        "Total Units",
                        f"{int(row['total_units']):,}",
                    )

                st.metric(
                    "Total Sales",
                    f"₹{row['total_sales']:,.2f}",
                )
                st.metric(
                    "Avg Line Value",
                    f"₹{row['avg_line_value']:,.2f}",
                )

                st.caption(
                    f"📅 Data: {row['date_min']} to {row['date_max']}"
                )
        except Exception as e:
            st.warning(f"Could not load metrics: {e}")

        st.divider()

        # Example Questions
        st.markdown("### 💡 Example Questions")
        example_questions = [
            "What were the total sales?",
            "Which category had the highest sales?",
            "Which state had the highest sales?",
            "What were monthly sales?",
            "Which fulfilment method had the highest sales?",
            "How many orders were cancelled?",
            "What percentage of orders were B2B?",
            "Give me an executive summary.",
            "Compare sales between April and May.",
            "Which quarter had the highest sales?",
        ]
        for q in example_questions:
            if st.button(q, key=f"example_{q}", use_container_width=True):
                # Inject the example question into session state
                st.session_state.pending_question = q
                st.rerun()

        st.divider()
        st.caption(
            "Built with Python · MySQL · Gemini API · Streamlit"
        )


# ---------------------------------------------------------------------------
# Chart generation
# ---------------------------------------------------------------------------
def create_chart(data: pd.DataFrame, intent: dict) -> go.Figure | None:
    """
    Create a Plotly chart from analytical results.
    Returns None if a chart doesn't make sense for this data.
    """
    if data is None or data.empty:
        return None

    dimension = intent.get("dimension")
    metric = intent.get("metric", "sales")
    intent_type = intent.get("intent", "")

    # Skip charts for single-value aggregations
    if intent_type == "aggregation" and dimension is None:
        return None

    # Need a dimension column and metric column
    if "dimension_value" not in data.columns or "metric_value" not in data.columns:
        # Check for trend data
        if "order_month" in data.columns and "sales" in data.columns:
            fig = px.bar(
                data,
                x="order_month",
                y="sales",
                title=f"Monthly {metric.title()}",
                labels={"order_month": "Month", "sales": "Sales (₹)"},
                color_discrete_sequence=["#667eea"],
            )
            fig.update_layout(
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
            )
            return fig
        if "order_quarter" in data.columns and "sales" in data.columns:
            fig = px.bar(
                data,
                x="order_quarter",
                y="sales",
                title=f"Quarterly {metric.title()}",
                labels={"order_quarter": "Quarter", "sales": "Sales (₹)"},
                color_discrete_sequence=["#764ba2"],
            )
            fig.update_layout(
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
            )
            return fig
        return None

    # Bar chart for rankings / breakdowns
    if len(data) <= 20:
        fig = px.bar(
            data,
            x="dimension_value",
            y="metric_value",
            title=f"{metric.title()} by {dimension.replace('_', ' ').title() if dimension else 'Dimension'}",
            labels={
                "dimension_value": dimension.replace("_", " ").title() if dimension else "Dimension",
                "metric_value": metric.title(),
            },
            color="metric_value",
            color_continuous_scale="Viridis",
        )
    else:
        # Horizontal bar for many categories
        fig = px.bar(
            data.head(15),
            y="dimension_value",
            x="metric_value",
            orientation="h",
            title=f"Top 15 — {metric.title()} by {dimension.replace('_', ' ').title() if dimension else 'Dimension'}",
            color="metric_value",
            color_continuous_scale="Viridis",
        )

    fig.update_layout(
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
    )
    return fig


# ---------------------------------------------------------------------------
# Process a user question
# ---------------------------------------------------------------------------
def process_question(question: str) -> tuple[str, pd.DataFrame | None, dict | None]:
    """
    Full pipeline:
      question → Gemini intent → analytics → Gemini response

    Returns:
        (response_text, data_df_or_None, intent_dict_or_None)
    """
    analytics: AnalyticsService = st.session_state.analytics
    gemini: GeminiService = st.session_state.gemini

    if not analytics or not gemini:
        return "⚠️ Services not initialised. Check MySQL and Gemini connections.", None, None

    # --- Step 1: Extract intent ---
    try:
        conversation_history = [
            {"role": m["role"], "content": m["content"]}
            for m in st.session_state.messages[-6:]
        ]
        intent = gemini.extract_intent(question, conversation_history)
    except IntentValidationError as e:
        return (
            f"⚠️ I understand your question, but it falls outside the available data:\n\n{e}",
            None,
            None,
        )
    except Exception as e:
        return f"⚠️ Error understanding your question: {e}", None, None

    # --- Step 2: Handle non-analytical intents ---
    if intent.intent == "clarification":
        return intent.clarification_message or "Could you please clarify your question?", None, None

    if intent.intent == "out_of_scope":
        msg = intent.limitation_message or (
            "This question involves predictions or causation that the current "
            "dataset cannot support. The dataset provides descriptive analytics "
            f"covering {DATASET_DATE_MIN} through {DATASET_DATE_MAX}."
        )
        return f"ℹ️ {msg}", None, None

    if intent.intent == "data_limitation":
        msg = intent.limitation_message or (
            f"The requested data is not available. The dataset covers "
            f"{DATASET_DATE_MIN} through {DATASET_DATE_MAX} only."
        )
        return f"ℹ️ {msg}", None, None

    if intent.intent == "general_chat":
        msg = intent.clarification_message or (
            "Hello! I'm your Retail Insights Assistant. "
            "Ask me business questions about the retail sales dataset, such as:\n\n"
            "• What were the total sales?\n"
            "• Which category had the highest sales?\n"
            "• Give me an executive summary."
        )
        return msg, None, None

    # --- Step 3: Execute analytics ---
    try:
        result = analytics.dispatch(intent)
    except Exception as e:
        return f"⚠️ Error querying the database: {e}", None, None

    # --- Step 4: Generate response ---
    try:
        # Special handling for executive summary
        if result.get("is_executive_summary"):
            response_text = gemini.generate_executive_summary(result["data"])
            # Return a combined DF for display
            overall = result["data"].get("overall")
            return response_text, overall, intent.to_dict()

        response_text = gemini.generate_response(
            question=question,
            data_results=result,
            query_description=result.get("query_description", ""),
        )
        data_df = result.get("data")
        return response_text, data_df, intent.to_dict()

    except Exception as e:
        return f"⚠️ Error generating response: {e}", None, intent.to_dict()


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------
def main():
    # Header
    st.markdown('<div class="main-header">📊 Retail Insights Assistant</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sub-header">Ask business questions about your retail sales data.</div>',
        unsafe_allow_html=True,
    )

    # Initialise services
    initialise_services()

    # Sidebar
    render_sidebar()

    # Gate: don't show chat if not connected
    if not st.session_state.db_connected:
        st.warning(
            "⚠️ Cannot connect to MySQL. Please check:\n"
            "1. MySQL is running\n"
            "2. `.env` file has correct credentials\n"
            "3. Database `retails_sales` exists with `retail_analytics` view"
        )
        st.stop()

    # --- Chat history ---
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

            # Show data table if present
            if message.get("data") is not None:
                with st.expander("📋 View Data", expanded=False):
                    st.dataframe(message["data"], use_container_width=True)

            # Show chart if present
            if message.get("chart") is not None:
                st.plotly_chart(message["chart"], use_container_width=True)

    # --- Handle pending question (from sidebar example buttons) ---
    pending = st.session_state.pop("pending_question", None)

    # --- Chat input ---
    user_input = st.chat_input("Ask a business question...")

    # Use pending question if no direct input
    question = pending or user_input

    if question:
        # Display user message
        with st.chat_message("user"):
            st.markdown(question)
        st.session_state.messages.append({"role": "user", "content": question})

        # Process and display assistant response
        with st.chat_message("assistant"):
            with st.spinner("🔍 Analyzing your question..."):
                response_text, data_df, intent_dict = process_question(question)

            st.markdown(response_text)

            # Show data table
            chart = None
            if data_df is not None and isinstance(data_df, pd.DataFrame) and not data_df.empty:
                with st.expander("📋 View Data", expanded=False):
                    st.dataframe(data_df, use_container_width=True)

                # Try to create a chart
                if intent_dict:
                    chart = create_chart(data_df, intent_dict)
                    if chart:
                        st.plotly_chart(chart, use_container_width=True)

        # Save to history
        st.session_state.messages.append({
            "role": "assistant",
            "content": response_text,
            "data": data_df if data_df is not None and isinstance(data_df, pd.DataFrame) and not data_df.empty else None,
            "chart": chart,
        })


if __name__ == "__main__":
    main()
