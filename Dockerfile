# Build from the repo root so app paths resolve data/ and bench/ the same way they do locally.
# Cloud Run sets PORT. This image is the deploy recipe. It is not a running service.
FROM python:3.12-slim

WORKDIR /srv
COPY services/api/requirements.txt /srv/services/api/requirements.txt
RUN pip install --no-cache-dir -r /srv/services/api/requirements.txt

COPY services/api /srv/services/api
COPY data /srv/data
COPY bench/results /srv/bench/results

WORKDIR /srv/services/api
ENV PYTHONPATH=/srv/services/api
ENV DEMO_MODE=true
ENV AI_MODE=auto
ENV GEMINI_ENABLED=true

EXPOSE 8080
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
