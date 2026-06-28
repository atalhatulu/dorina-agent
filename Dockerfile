# ============================================================
# Dorina Agent — Multi-Stage Docker Build
# ============================================================

# ── Build Stage ──────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy only dependency manifests first for layer caching
COPY pyproject.toml setup.py requirements.txt* ./
COPY dorina_agent.egg-info/ ./dorina_agent.egg-info/

# Install dependencies into a local directory
RUN pip install --no-cache-dir --target=/install \
    litellm rich prompt-toolkit pyyaml pydantic-settings python-dotenv

# Copy the rest of the source code
COPY . .

# Install the package itself (also into /install to keep it self-contained)
RUN pip install --no-cache-dir --target=/install -e . 2>/dev/null || true

# ── Runtime Stage ────────────────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

# Install only runtime system dependencies (no build tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r dorina && useradd -r -g dorina -d /app -s /bin/bash dorina

# Copy installed packages from builder stage
COPY --from=builder /install /usr/local/lib/python3.12/site-packages/

# Copy application source code
COPY --from=builder /build /app

# Create data directories with correct ownership
RUN mkdir -p /app/data /app/.backup && \
    chown -R dorina:dorina /app

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python3 -c "import sys; sys.path.insert(0,'.'); from core.config import settings; print('OK')" || exit 1

# Switch to non-root user
USER dorina

ENTRYPOINT ["python3", "main.py"]
CMD ["--help"]
