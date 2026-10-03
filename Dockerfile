# ============================================================
# Dockerfile — Retail Insights Assistant (Streamlit App)
#
# Multi-stage build for a slim, production-ready container.
# The app connects to an external MySQL server (not bundled).
#
# Build:  docker build -t retail-insights-assistant .
# Run:    docker run --env-file .env -p 8501:8501 retail-insights-assistant
# ============================================================

# ---------- Stage 1: Builder ----------
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build dependencies only (keeps final image small)
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---------- Stage 2: Runtime ----------
FROM python:3.11-slim AS runtime

# Metadata
LABEL maintainer="mysource0"
LABEL description="Retail Insights Assistant — GenAI analytics chatbot"
LABEL version="1.0"

# Create non-root user for security
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser

WORKDIR /app

# Copy installed packages from builder stage
COPY --from=builder /install /usr/local

# Copy application source code
COPY app.py .
COPY database.py .
COPY analytics.py .
COPY gemini.py .
COPY prompts.py .
COPY schemas.py .
COPY config.py .

# Streamlit configuration — disable telemetry, set server options
RUN mkdir -p /app/.streamlit
RUN echo '\
[server]\n\
port = 8501\n\
address = "0.0.0.0"\n\
headless = true\n\
enableCORS = false\n\
enableXsrfProtection = false\n\
\n\
[browser]\n\
gatherUsageStats = false\n\
\n\
[theme]\n\
primaryColor = "#667eea"\n\
' > /app/.streamlit/config.toml

# Switch to non-root user
RUN chown -R appuser:appuser /app
USER appuser

# Expose Streamlit port
EXPOSE 8501

# Health check — verify Streamlit is responding
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')" || exit 1

# Run the Streamlit app
ENTRYPOINT ["streamlit", "run", "app.py"]
