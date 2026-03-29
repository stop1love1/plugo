FROM python:3.12-slim AS builder

WORKDIR /app

# Install build deps in builder stage
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- Production stage ---
FROM python:3.12-slim

WORKDIR /app

# Install only runtime deps (curl for healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy app
COPY . .

# Create data directory with correct ownership
RUN mkdir -p /app/data && chown -R appuser:appuser /app

# Widget static files are mounted from the widget_dist volume at /app/static_widget

USER appuser

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
