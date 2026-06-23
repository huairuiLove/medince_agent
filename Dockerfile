# =============================================================================
# MedSafe Dockerfile — CPU-only, no GPU required
# =============================================================================
# Build:  docker build -t medsafe:latest .
# Run:    docker compose up -d

FROM python:3.11-slim

LABEL org.opencontainers.image.title="MedSafe"
LABEL org.opencontainers.image.description="Multi-Agent Drug Safety Review System"
LABEL org.opencontainers.image.version="2.0.0"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MEDSAFE_LLM__PROVIDER=deepseek \
    MEDSAFE_SERVER__HOST=0.0.0.0 \
    MEDSAFE_SERVER__PORT=8000 \
    MEDSAFE_LOGGING__FORMAT=structured

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY pyproject.toml config.yaml .env.example ./
COPY src/ ./src/
COPY scripts/ ./scripts/
COPY datasets/knowledge/ ./datasets/knowledge/
COPY datasets/case_templates/ ./datasets/case_templates/
COPY datasets/hospital/ ./datasets/hospital/
COPY datasets/departments/ ./datasets/departments/
COPY datasets/agents/ ./datasets/agents/

RUN mkdir -p datasets/cases datasets/processed data/pharmacy data/auth data/hospital data/imaging_cache logs

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

ENTRYPOINT ["python", "-m", "uvicorn", "src.app:app", "--host", "0.0.0.0", "--port", "8000"]
