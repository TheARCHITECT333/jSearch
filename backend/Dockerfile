# Backend image: Python + FastAPI + Playwright + Chromium.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

COPY requirements.txt .
# libatomic1: Playwright's bundled Node needs it, and -slim doesn't ship it.
RUN apt-get update && apt-get install -y --no-install-recommends libatomic1 \
    && rm -rf /var/lib/apt/lists/* \
    && pip install -r requirements.txt \
    && playwright install --with-deps chromium

COPY app ./app
COPY migrations ./migrations
COPY alembic.ini .
COPY tests ./tests
COPY pytest.ini .

EXPOSE 8000

# Schema migrations run automatically on startup (app/db.py).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
