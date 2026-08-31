# ── Multi-stage Dockerfile for BookTale ──────────────────────────────────────
# Builder stage: install deps + build frontend assets
# Runtime stage: slim image with only runtime deps
#
# Usage:
#   docker build -t booktale .
#   docker run -p 5000:5000 -e SECRET_KEY=... -e DATABASE_URL=... booktale

# ══════════════════════════════════════════════════════════════════════════════
# Stage 1: Builder
# ══════════════════════════════════════════════════════════════════════════════
FROM python:3.14-slim AS builder

# System deps for psycopg2-binary and python-magic
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Install Python deps into a virtualenv
COPY requirements.txt .
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir -r requirements.txt

# Install Node.js for frontend build
RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    rm -rf /var/lib/apt/lists/*

# Build frontend assets
COPY package.json .
RUN npm install --ignore-scripts 2>/dev/null || true
COPY scripts/build_frontend.mjs scripts/
COPY app/static/js/ app/static/js/
COPY app/static/css/ app/static/css/
COPY app/static/dist/ app/static/dist/
RUN node scripts/build_frontend.mjs

# ══════════════════════════════════════════════════════════════════════════════
# Stage 2: Runtime
# ══════════════════════════════════════════════════════════════════════════════
FROM python:3.14-slim AS runtime

# Runtime deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 && \
    rm -rf /var/lib/apt/lists/*

# Copy virtualenv from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Copy application code
COPY . .

# Copy built frontend assets from builder
COPY --from=builder /build/app/static/dist/ app/static/dist/

# Create non-root user
RUN groupadd -r booktale && useradd -r -g booktale booktale && \
    mkdir -p /app/data /app/logs /app/backups /app/uploads && \
    chown -R booktale:booktale /app

# Set environment defaults
ENV STORAGE_BACKEND=db \
    FLASK_HOST=0.0.0.0 \
    FLASK_PORT=5000 \
    FLASK_DEBUG=False \
    PYTHONUNBUFFERED=1

EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/healthz')" || exit 1

USER booktale

# Run with gunicorn in production, Flask dev server in dev
CMD ["sh", "-c", "gunicorn -w 4 -b 0.0.0.0:5000 --timeout 120 web_app:app 2>/dev/null || python web_app.py"]
