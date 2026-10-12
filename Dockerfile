# Relief Desk API. Build from the repo root so data/ and bench/results
# resolve the same way they do locally (parents[4] of app/tools/*.py is /srv).
# Cloud Run injects PORT and the secret env vars. This image is the recipe.
# It is not a running service, and it does not contain a key or a project id.
FROM python:3.12-slim

WORKDIR /srv

COPY services/api/requirements.txt /srv/services/api/requirements.txt
RUN pip install --no-cache-dir -r /srv/services/api/requirements.txt

COPY services/api /srv/services/api
COPY data /srv/data
COPY bench/results /srv/bench/results

WORKDIR /srv/services/api
ENV PYTHONPATH=/srv/services/api \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEMO_MODE=true \
    AI_MODE=auto \
    GEMINI_ENABLED=true \
    PORT=8080

EXPOSE 8080
# exec so Cloud Run's SIGTERM reaches uvicorn. ${PORT} is set by Cloud Run.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
