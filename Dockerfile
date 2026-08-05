# Harmoniq Backend — Multi-stage Dockerfile
# Stage 1: Build dependencies
# Stage 2: Runtime (slim)

# ---------------------------------------------------------------------------
# Build stage
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS builder

WORKDIR /build

# Install system deps for building Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files first for layer caching
COPY backend/pyproject.toml backend/setup.cfg* backend/setup.py* /build/
COPY backend/app/__init__.py /build/app/__init__.py

# Install Python dependencies
RUN pip install --no-cache-dir --prefix=/install \
    -e ".[dev]" 2>/dev/null || \
    pip install --no-cache-dir --prefix=/install \
    setuptools wheel && \
    pip install --no-cache-dir --prefix=/install \
    fastapi uvicorn httpx pydantic python-dotenv \
    redis celery[redis] prometheus-client tenacity circuitbreaker

# ---------------------------------------------------------------------------
# Runtime stage
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

# Install runtime system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsndfile1 \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages
COPY --from=builder /install /usr/local

# Create non-root user
RUN groupadd -r harmoniq && useradd -r -g harmoniq -d /app harmoniq

WORKDIR /app

# Copy application code
COPY backend/app/ /app/app/
COPY backend/scripts/ /app/scripts/
COPY backend/models/ /app/models/ 2>/dev/null || true

# Ensure data directories exist
RUN mkdir -p /app/data/jobs /app/data/cache && chown -R harmoniq:harmoniq /app

USER harmoniq

# Environment defaults
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV REDIS_URL=redis://redis:6379/0
ENV CELERY_BROKER_URL=redis://redis:6379/1
ENV CELERY_RESULT_BACKEND=redis://redis:6379/2

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
