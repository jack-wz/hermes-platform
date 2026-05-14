# ─── Stage 1: Build ───────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# ─── Stage 2: Runtime ──────────────────────────────────────────────
FROM python:3.11-slim AS runtime

# Security: run as non-root
RUN groupadd -r hermes && useradd -r -g hermes -d /app hermes

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /root/.local /home/hermes/.local
ENV PATH=/home/hermes/.local/bin:$PATH

# Copy application code
COPY --chown=hermes:hermes . .

# Create writable directories for logs
RUN mkdir -p logs/coworkers && chown -R hermes:hermes /app

USER hermes

EXPOSE 5002

# Health check: ensure dashboard is responding
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:5002/api/status')" || exit 1

CMD ["python3", "build/workspace/hermes-dashboard.py"]
