FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    podman \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Set work directory
WORKDIR /app

# Copy dependency files first (for caching)
COPY pyproject.toml .

# Install python dependencies via UV
RUN uv pip install --system --no-cache -r pyproject.toml || true

# Copy the rest of the code
COPY . .

# Default command
CMD ["uv", "run", "worker/main.py"]