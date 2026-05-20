# ========================================
# Enterprise LLM Gateway - Backend Dockerfile
# ========================================

FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uvicorn globally
RUN pip install uvicorn[standard]

# Install uv (fast Python package manager)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

# Copy project files
COPY pyproject.toml ./

COPY app/ ./app/ --exclude=/.git

# Install dependencies
# RUN uv sync --frozen --no-dev
RUN uv sync 

# Download spaCy model (required for Presidio), changed from en_core_web_lg to en_core_web_sm for faster download, need to change back to lg if we want better NER performance
RUN uv run python -m spacy download en_core_web_sm

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

# Run the application
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
