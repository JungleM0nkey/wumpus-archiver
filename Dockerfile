# =============================================================================
# Wumpus Archiver — Multi-stage Docker build
# Stage 1: Build SvelteKit portal (Node.js)
# Stage 2: Python runtime with pre-built portal
# =============================================================================

# ---------------------------------------------------------------------------
# Stage 1 — Build the SvelteKit portal
# ---------------------------------------------------------------------------
FROM node:22-slim AS portal-build

WORKDIR /build/portal

# Install dependencies first (layer caching)
COPY portal/package.json portal/package-lock.json* ./
RUN npm ci --ignore-scripts

# Copy portal source and build
COPY portal/ ./
RUN npm run build

# ---------------------------------------------------------------------------
# Stage 2 — Python runtime
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

LABEL org.opencontainers.image.title="Wumpus Archiver" \
      org.opencontainers.image.description="Discord server archival system with web exploration portal" \
      org.opencontainers.image.source="https://github.com/JungleM0nkey/wumpus-archiver" \
      org.opencontainers.image.licenses="MIT"

# System deps for aiosqlite and general health
RUN apt-get update && \
    apt-get install -y --no-install-recommends tini && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies (layer caching — pyproject.toml changes rarely)
COPY pyproject.toml LICENSE README.md ./
COPY src/ ./src/
RUN pip install --no-cache-dir -e .

# Copy pre-built portal from Stage 1
COPY --from=portal-build /build/portal/build/ ./portal/build/

# Create data directory for SQLite DB and attachments
RUN mkdir -p /data/attachments

# Default environment for container operation
ENV API_HOST=0.0.0.0 \
    API_PORT=8000 \
    DATABASE_URL=sqlite+aiosqlite:////data/archive.db \
    ATTACHMENTS_PATH=/data/attachments \
    LOG_LEVEL=INFO

EXPOSE 8000 9100

VOLUME ["/data"]

# Use tini as init to handle signals properly
ENTRYPOINT ["tini", "--", "wumpus-archiver"]

# Default command: serve the portal
# Override with: docker run <image> mcp /data/archive.db --http --host 0.0.0.0
CMD ["serve", "/data/archive.db", "--host", "0.0.0.0", "--port", "8000", "-a", "/data/attachments"]
