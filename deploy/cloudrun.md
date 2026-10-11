# Deploy recipe

This file is not a record of a deployment. The branch has no live Cloud Run URL, no Firebase Hosting site, and no Secret Manager binding. The API that the tests run is a local process.

## What the process actually stores

`StorageService` in `services/api/app/tools/storage.py` keeps reports, requests, resources, matches, and the audit log in process memory. `_init_firestore` opens a client only when `FIRESTORE_EMULATOR_HOST` accepts a TCP connection and `google.cloud.firestore` imports. Nothing in that file reads or writes through the client after that. `google-cloud-firestore` is not pinned in `services/api/requirements.txt`. Treat Firestore as unused for this prototype.

## Container

The root `Dockerfile` copies `services/api`, `data`, and `bench/results` and listens on `$PORT` (8080 locally). Build it from the repo root only if you intend to ship the image. CI for this branch does not build it.

```bash
docker build -t relief-desk-api .
docker run --rm -p 8080:8080 -e GEMINI_API_KEY=replace-me -e DEMO_MODE=true relief-desk-api
```

With `GEMINI_API_KEY=replace-me` the process stays on the deterministic fallback.

## Secret Manager

The app reads `GEMINI_API_KEY` from the environment (`services/api/app/config.py`). It does not call the Secret Manager API. On Cloud Run, mount the secret as that variable. Do not put the value in git.

```bash
# Example only. Not run from this repo.
gcloud run deploy relief-desk-api \
  --source . \
  --region asia-south1 \
  --set-secrets GEMINI_API_KEY=gemini-api-key:latest \
  --set-env-vars GEMINI_MODEL=gemini-3.8-flash,GEMINI_EMBED_MODEL=gemini-embedding-001,GEMINI_EMBED_DIM=768,GEMINI_EMBED_TASK=SEMANTIC_SIMILARITY,AI_MODE=auto,GEMINI_ENABLED=true,DEMO_MODE=true
```

`JWT_SECRET` and `GOOGLE_MAPS_API_KEY` are the other values that must stay out of git. Maps stays on the built-in SVG until `GOOGLE_MAPS_API_KEY` is a real key.

## Not in this deploy

Pub/Sub, BigQuery, Gemini Live, Search grounding, Malayalam, and photo intake are not part of the service.
