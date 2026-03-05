# =============================================================================
# LocalTaskClaw — multi-stage build (frontend + core)
# =============================================================================

# Stage 1: Build React frontend
FROM node:20-alpine AS frontend
WORKDIR /src
COPY frontend/ ./frontend/
WORKDIR /src/frontend
RUN npm ci --silent
RUN npm run build
# vite outDir: '../admin' → output at /src/admin/

# Stage 2: Python core + built admin SPA
FROM python:3.12-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl git bash \
    && rm -rf /var/lib/apt/lists/*

COPY core/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY core/ ./core/
COPY scripts/ ./scripts/
COPY tests/ ./tests/
COPY --from=frontend /src/admin ./admin/

WORKDIR /app/core
CMD ["python", "main.py"]
