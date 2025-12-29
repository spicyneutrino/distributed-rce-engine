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

# Copy and install dependencies
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-cache

# Copy the rest of the code
COPY . .

# Default command
CMD ["uv", "run", "worker/main.py"]