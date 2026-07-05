# Base image for a scenario backend (API + Celery worker + beat all share it).
FROM python:3.11-slim

WORKDIR /app

# ffmpeg = RTSP decode (CV layers); curl = healthchecks.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg curl \
 && rm -rf /var/lib/apt/lists/*

# Install deps first (layer-cached) then the package.
COPY pyproject.toml ./
COPY edge ./edge
COPY example ./example
COPY migrations ./migrations
COPY alembic.ini ./
RUN pip install --no-cache-dir -e ".[messaging,tasks,reports,system,storage]"

EXPOSE 8000

# Overridden by compose for the worker/beat services.
CMD ["uvicorn", "example.main:app", "--host", "0.0.0.0", "--port", "8000"]
