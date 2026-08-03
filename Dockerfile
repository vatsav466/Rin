# ══════════════════════════════════════════════════════════════════════════════
# NOVEX — single-container deployment
#
# Stages:
#   1. frontend-build  → compiles React/Vite to /app/dist
#   2. runtime         → Python 3.11 + nginx + supervisord + Redis
#                        serves frontend on :5378, FastAPI on :8002
# ══════════════════════════════════════════════════════════════════════════════

# ── Stage 1: Build React frontend ─────────────────────────────────────────────
FROM node:20-alpine AS frontend-build

WORKDIR /app

# Install deps first (better layer caching — only re-runs when package.json changes)
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --prefer-offline

# Copy source and build
COPY frontend/ .
RUN npm run build

# ── Stage 2: Runtime image ────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

# Prevent interactive prompts
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV MODE=prod

# ── System packages ────────────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    nginx \
    redis-server \
    supervisor \
    # Required by python-ldap
    libldap2-dev \
    libsasl2-dev \
    libssl-dev \
    # Required by pyodbc
    unixodbc-dev \
    # Required by weasyprint (PDF generation)
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    # C build toolchain (required by python-ldap, pyodbc, asyncpg, msgpack)
    build-essential \
    python3-dev \
    # General utilities
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# ── Python virtual environment ─────────────────────────────────────────────────
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# ── Install Python dependencies ────────────────────────────────────────────────
# Copy requirements first for better layer caching
COPY backend/requirements.txt /tmp/requirements.txt
COPY backend/UrdhvaBase /opt/ceg/algo/UrdhvaBase

# Install UrdhvaBase package (local editable install) then project requirements
RUN pip install --upgrade pip setuptools wheel \
    && pip install -e /opt/ceg/algo/UrdhvaBase \
    && pip install -r /tmp/requirements.txt

# ── Copy backend source ────────────────────────────────────────────────────────
COPY backend/api_manager             /opt/ceg/algo/api_manager
COPY backend/api_manager/.alg_env    /opt/ceg/algo/api_manager/.alg_env
COPY backend/authenticator           /opt/ceg/algo/authenticator
COPY backend/orchestrator            /opt/ceg/algo/orchestrator
COPY backend/utilities               /opt/ceg/algo/utilities
COPY backend/cache_gateway           /opt/ceg/algo/cache_gateway
COPY backend/ceg_role_master_api     /opt/ceg/algo/ceg_role_master_api
COPY backend/vendor_ingestion_api    /opt/ceg/algo/vendor_ingestion_api

# ── Copy React build artifacts ─────────────────────────────────────────────────
RUN rm -rf /usr/share/nginx/html/*
COPY --from=frontend-build /app/dist /usr/share/nginx/html

# ── nginx configuration ────────────────────────────────────────────────────────
COPY nginx.conf /etc/nginx/conf.d/default.conf
# Remove the default nginx site config to avoid port conflicts
RUN rm -f /etc/nginx/sites-enabled/default

# ── supervisord configuration ──────────────────────────────────────────────────
COPY supervisord.conf /etc/supervisor/conf.d/novex.conf

# ── Log directories ────────────────────────────────────────────────────────────
RUN mkdir -p /var/log/ceg_sys_logs /var/log/ceg_logs /var/run/redis

# ── Expose ports ───────────────────────────────────────────────────────────────
# 5378 — nginx (frontend + API proxy)
# 8002 — FastAPI direct (for /docs access)
EXPOSE 5378 8002

# ── Healthcheck ────────────────────────────────────────────────────────────────
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:5378/health || exit 1

# ── Entrypoint ─────────────────────────────────────────────────────────────────
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/novex.conf"]
