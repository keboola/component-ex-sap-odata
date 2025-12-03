FROM python:3.12-slim

ENV PYTHONIOENCODING=utf-8
ENV PYTHONUNBUFFERED=1

WORKDIR /code

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libxml2-dev \
    libxslt-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv for faster package installation
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy project files
COPY pyproject.toml ./
COPY src/ ./src/
COPY component_config/ ./component_config/

# Install dependencies
RUN uv pip install --system --no-cache .

# Set working directory to src
WORKDIR /code/src

CMD ["python", "-u", "component.py"]
