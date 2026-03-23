FROM python:3.13-slim

WORKDIR /app

# Install uv for dependency management
RUN pip install uv

# Copy dependency files first (cache layer)
COPY pyproject.toml uv.lock ./

# Install production dependencies only
RUN uv sync --frozen --no-dev --no-install-project

# Copy bot and src code (bot imports from bot.supabase_admin)
COPY bot/ bot/
COPY src/ src/

# Run the bot gateway
CMD ["uv", "run", "python", "-m", "bot.gateway"]
