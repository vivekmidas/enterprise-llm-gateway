FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:0.8.7 /uv /uvx /usr/local/bin/

# Copy dependency manifests
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv sync --frozen --no-dev

# Copy application
COPY app ./app

# Install spaCy model
RUN /app/.venv/bin/python -m spacy download en_core_web_sm

# Create non-root user
RUN useradd --create-home appuser
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

#CMD ["/app/.venv/bin/uvicorn","app.main:app","--host","0.0.0.0","--port","8000"]
CMD ["/app/.venv/bin/python","-m","uvicorn","app.main:app","--host","0.0.0.0","--port","8000"]