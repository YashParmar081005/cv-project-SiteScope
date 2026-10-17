# SiteScope API + static frontend. Build from the project root:
#   docker compose build      (or: docker build -f backend/Dockerfile .)
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PROJECT_ROOT=/app

WORKDIR /app/backend
COPY backend/requirements.txt .
RUN pip install -r requirements.txt

COPY backend/app ./app
COPY backend/configs ./configs
# labelled reference photos: shown as the nearest neighbours of each analysed photo
COPY reference_photos /app/reference_photos
COPY frontend/index.html /app/frontend/index.html
COPY frontend/css /app/frontend/css
COPY frontend/js /app/frontend/js

RUN useradd --create-home --uid 1000 app && mkdir -p /app/data && chown -R app /app
USER app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
