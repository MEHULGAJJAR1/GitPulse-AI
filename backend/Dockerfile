# Build from the repository root:  docker build -f backend/Dockerfile -t gitpulse-api .
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install -r backend/requirements.txt

# Keep the repository layout: config.py resolves REPO_ROOT relative to its own location.
COPY backend ./backend
COPY data_pipeline ./data_pipeline
COPY ml_analytics ./ml_analytics
COPY dbt ./dbt

RUN useradd --create-home --uid 10001 gitpulse && chown -R gitpulse /app
USER gitpulse
WORKDIR /app/backend
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status==200 else 1)"
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers"]
