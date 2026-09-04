FROM python:3.11-slim

LABEL maintainer="Razorpay AI Buildathon 2026 — Track 01"
LABEL description="Small-Merchant AI Readiness Agent — Backend"

WORKDIR /app

# System deps for lxml, numpy, sentence-transformers, and psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libffi-dev \
    libssl-dev \
    libpq-dev \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (layer-cache optimization)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# Create required data directories
RUN mkdir -p data/merchant_fixtures results

# Pre-download the sentence-transformers model at build time
# so the container doesn't need internet access at startup
RUN python3 -c "\
from sentence_transformers import SentenceTransformer; \
SentenceTransformer('all-MiniLM-L6-v2'); \
print('Model cached successfully')" || echo "Model pre-download skipped (no internet)"

# Non-root user for security
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Health check — start-period gives time for migrations + model load
HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Use 2 workers for production; set UVICORN_WORKERS env to override
CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers ${UVICORN_WORKERS:-2}"]
