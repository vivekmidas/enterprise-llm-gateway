# Backend

FastAPI + LangGraph service.

## Structure

- `app/` - Main application
  - `core/` - Config, guards
  - `workflows/` - LangGraph definitions
  - `routers/` - API endpoints
  - `agents/` - Reusable agents
  - `db/` - Models & migrations

# Install uv if not installed

curl -LsSf https://astral.sh/uv/install.sh | sh

# Sync dependencies

uv sync

# Activate environment

uv run python --version

# Create virtual environment

python -m venv venv

# Activate it

# Windows:

# venv\Scripts\activate

# Mac/Linux:

source venv/bin/activate

# Install dependencies

pip install -r requirements.txt

# If no requirements.txt exists yet, create one or use pyproject.toml

pip install -e .

source  ./.venv/bin/activate 
