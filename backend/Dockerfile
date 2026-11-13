FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ffmpeg \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

# Copy packaging metadata and the package source before the editable install
# so setuptools sees README.md and the app package. `constraints.txt` is the
# committed universal lock (Commit 7); training-only QAT deps stay out.
COPY pyproject.toml README.md constraints.txt ./
COPY app ./app
RUN pip install --no-cache-dir -e ".[dev,db,redis,celery]" -c constraints.txt

COPY . .

RUN mkdir -p /app/data

EXPOSE 8000

# Migrations run as a one-shot pre-deploy step (see docker-compose.yml `migrate`
# and docs/DEPLOYMENT.md); the API container must not race other replicas.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
