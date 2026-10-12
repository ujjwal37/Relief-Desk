# Deploy recipe (not a deployment)

This file is not a record of a deployment. There is no live Cloud Run URL, no Firebase Hosting site, and no Secret Manager binding. Nothing in this repository was deployed by the agent that wrote the recipe. A human supplies the GCP project and the secret values, then runs the commands below.

The API that the tests run is a local process. `StorageService` in `services/api/app/tools/storage.py` keeps reports, requests, resources, matches, and the audit log in process memory. A new Cloud Run instance reloads the synthetic seeds and drops anything submitted to the previous instance. `_init_firestore` opens a client only when `FIRESTORE_EMULATOR_HOST` accepts a TCP connection. Nothing in that file reads or writes through the client after that. Treat Firestore as unused for this prototype.

One public URL is the Firebase Hosting site. The PWA and `/api/**` share that origin. The Cloud Run service URL is only for a direct health check while you are debugging.

Region for every command: `asia-south1`. Service name: `relief-desk-api`. Build from the repository root so the root `Dockerfile` is the build context. Do not pass `--source services/api`.

A person still approves every dispatch. `--allow-unauthenticated` only lets the public report form call the API. It does not dispatch.

## 0. What you fill in

```bash
export PROJECT_ID=your-project-id
export REGION=asia-south1
export SERVICE=relief-desk-api
gcloud config set project "$PROJECT_ID"
```

Replace `your-project-id` in this shell and in `deploy/cloudrun.env.yaml` (`GCP_PROJECT_ID`, `API_CORS_ORIGINS`, `GCS_BUCKET_MEDIA`). Do not commit those edits if they contain a real project you do not want in git. `.firebaserc` stays `your-project-id`; pass `--project` instead of running `firebase use` in a way that you then commit.

Billing must be enabled (Blaze). Firebase Hosting can rewrite to Cloud Run only on Blaze.

```bash
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  secretmanager.googleapis.com \
  firebase.googleapis.com \
  firebasehosting.googleapis.com
```

Add Firebase to the same GCP project if it is not already a Firebase project:

```bash
npx firebase-tools projects:addfirebase "$PROJECT_ID"
```

## 1. Secret Manager

The process reads environment variables. It does not call the Secret Manager API. Mount the secrets as env vars. Values stay in your shell and in Secret Manager. They do not go in git, in `deploy/cloudrun.env.yaml`, or in the image.

The three mounts:

| Env var | Secret id | Why |
|---|---|---|
| `GEMINI_API_KEY` | `gemini-api-key` | Intake, dedupe judge, embeddings, explainer. `replace-me` keeps the deterministic fallback. |
| `JWT_SECRET` | `jwt-secret` | Signs coordinator JWTs (`POST /api/auth/login`) and team tokens. The source default is a demo constant. Mount a new value before the site is public. |
| `GOOGLE_MAPS_API_KEY` | `google-maps-api-key` | Returned to the browser by `GET /api/config/maps`. Restrict it to the Hosting origins. `replace-me` keeps the SVG map. |

`SALT_PHONE_HASH` is a placeholder (`replace-me`) in the env file. To use a private salt, delete that line from `deploy/cloudrun.env.yaml` and add `SALT_PHONE_HASH=salt-phone-hash:latest` to `--set-secrets`.

Create each secret in `asia-south1`. `read -rs` keeps the value out of the command line.

```bash
create_secret() {
  local name="$1"
  local value
  read -rs -p "$name: " value
  echo
  printf '%s' "$value" | gcloud secrets create "$name" \
    --data-file=- \
    --replication-policy=user-managed \
    --locations="$REGION"
  unset value
}

create_secret gemini-api-key
create_secret jwt-secret
create_secret google-maps-api-key
```

If a secret already exists, add a version instead of `secrets create`:

```bash
printf '%s' "$GEMINI_API_KEY" | gcloud secrets versions add gemini-api-key --data-file=-
```

Grant the Cloud Run runtime service account accessor on those secrets only:

```bash
PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
RUNTIME_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

for SECRET in gemini-api-key jwt-secret google-maps-api-key; do
  gcloud secrets add-iam-policy-binding "$SECRET" \
    --member="serviceAccount:${RUNTIME_SA}" \
    --role="roles/secretmanager.secretAccessor"
done
```

## 2. API container

The root `Dockerfile` copies `services/api`, `data`, and `bench/results`, listens on `0.0.0.0:$PORT`, and defaults `PORT` to 8080. Cloud Run sets `PORT`. Local check, still with a placeholder key:

```bash
docker build -t relief-desk-api .
docker run --rm -p 8080:8080 \
  -e PORT=8080 \
  -e GEMINI_API_KEY=replace-me \
  -e DEMO_MODE=true \
  -e GEMINI_ENABLED=true \
  relief-desk-api
```

`curl -sS localhost:8080/healthz` should return `"status":"ok"`. With `GEMINI_API_KEY=replace-me` the process stays on the deterministic fallback.

### Deploy from source

`--source .` uses the root `Dockerfile` (Cloud Build does not use buildpacks when that file is present). `.gcloudignore` keeps `node_modules`, `.env`, and `dist` out of the upload.

`--max-instances 1` keeps a single in-memory store. Two instances would each hold a different queue. `--no-cpu-throttling` leaves CPU on after the HTTP response so the intake pipeline thread and the demo mover keep running. `--min-instances 0` scales to zero when idle (the queue is then gone and the next start reloads seeds).

```bash
gcloud run deploy "$SERVICE" \
  --source . \
  --region "$REGION" \
  --platform managed \
  --allow-unauthenticated \
  --port 8080 \
  --memory 1Gi \
  --cpu 1 \
  --timeout 60 \
  --concurrency 80 \
  --min-instances 0 \
  --max-instances 1 \
  --no-cpu-throttling \
  --env-vars-file deploy/cloudrun.env.yaml \
  --set-secrets GEMINI_API_KEY=gemini-api-key:latest,JWT_SECRET=jwt-secret:latest,GOOGLE_MAPS_API_KEY=google-maps-api-key:latest
```

`DEMO_MODE=true` and `GEMINI_ENABLED=true` are in `deploy/cloudrun.env.yaml`. `GEMINI_ENABLED=false` is the kill-switch. `AI_MODE=auto` calls Gemini only when the mounted key is real. If the deploy rejects the empty `FIRESTORE_EMULATOR_HOST` or `FIREBASE_AUTH_EMULATOR_HOST` lines, delete them. The code default then probes `127.0.0.1:8080` for a fraction of a second and still keeps cases in memory. `requirements.txt` pins `PyJWT` because `app/api/auth.py` imports it at startup.

For the evaluation window (18 Oct through 6 Nov), keep one instance warm so the synthetic queue survives idle time:

```bash
gcloud run services update "$SERVICE" \
  --region "$REGION" \
  --min-instances 1 \
  --max-instances 1
```

That instance is billed while it is up. Set `--min-instances 0` again when the window ends.

If the first `--source` deploy stops on IAM, the Cloud Build service account needs to build and deploy. On current projects that account is the default compute service account (`$RUNTIME_SA` above). Grant `roles/cloudbuild.builds.builder`, `roles/artifactregistry.writer`, `roles/run.admin`, `roles/iam.serviceAccountUser`, and `roles/logging.logWriter`, then rerun the deploy command. The error text names the member if it is not `$RUNTIME_SA`.

### Build and push yourself

Same image, your own tag. Run this from the repo root.

```bash
gcloud artifacts repositories create relief-desk \
  --repository-format=docker \
  --location="$REGION" \
  --description="Relief Desk API"

IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/relief-desk/api:latest"
gcloud builds submit --tag "$IMAGE"

gcloud run deploy "$SERVICE" \
  --image "$IMAGE" \
  --region "$REGION" \
  --platform managed \
  --allow-unauthenticated \
  --port 8080 \
  --memory 1Gi \
  --cpu 1 \
  --timeout 60 \
  --concurrency 80 \
  --min-instances 0 \
  --max-instances 1 \
  --no-cpu-throttling \
  --env-vars-file deploy/cloudrun.env.yaml \
  --set-secrets GEMINI_API_KEY=gemini-api-key:latest,JWT_SECRET=jwt-secret:latest,GOOGLE_MAPS_API_KEY=google-maps-api-key:latest
```

`gcloud artifacts repositories create` fails if `relief-desk` already exists. Skip that command and build the image.

Direct health check (this URL is not the submission URL):

```bash
CLOUD_RUN_URL="$(gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.url)')"
curl -sS "${CLOUD_RUN_URL}/healthz"
```

## 3. Firebase Hosting

`firebase.json` at the repo root is what the CLI reads. `public` is `dist/web/browser`, which is the Angular application-builder output (`outputPath.base` `dist/web`, `outputPath.browser` `browser` in `angular.json`).

Exact rewrites, in order. Existing files are served first. `/api/**` and `/healthz` go to Cloud Run. Everything else falls through to the Angular app.

```json
{
  "source": "/api/**",
  "run": {
    "serviceId": "relief-desk-api",
    "region": "asia-south1"
  }
}
```

```json
{
  "source": "/healthz",
  "run": {
    "serviceId": "relief-desk-api",
    "region": "asia-south1"
  }
}
```

```json
{
  "source": "**",
  "destination": "/index.html"
}
```

`/healthz` is rewritten because the PWA calls `/healthz` (see `apps/web/proxy.conf.json` and `libs/shared` `api-client.service.ts`). `/api/**` does not include `/healthz`.

Deploy Hosting only after the Cloud Run service exists in the same project. Do not run `firebase init`; it will offer to replace `firebase.json`.

```bash
npm ci
npx ng build web
test -f dist/web/browser/index.html

npx firebase-tools deploy --only hosting --project "$PROJECT_ID"
```

The CLI prints `Hosting URL: https://PROJECT_ID.web.app` (and usually `https://PROJECT_ID.firebaseapp.com`). That Hosting URL is the single public URL.

Maps key referrers, if you mounted a real browser key: `https://PROJECT_ID.web.app/*` and `https://PROJECT_ID.firebaseapp.com/*`, plus localhost. The muted basemap is a Cloud style on `GOOGLE_MAPS_MAP_ID`. `DEMO_MAP_ID` is the id for Google's demo key. A map id ignores a JavaScript styles array.

Coordinator login on the hosted site is the synthetic account already in the README (`demo-coordinator@reliefdesk.internal`). `POST /api/auth/login` checks that password and signs a JWT with `JWT_SECRET`. `python scripts/seed.py` writes the same synthetic credentials locally and, only when `FIREBASE_AUTH_EMULATOR_HOST` is set, also talks to the Auth emulator. Leave that variable empty on Cloud Run.

Smoke from a network that is not your laptop:

```bash
curl -sS "https://${PROJECT_ID}.web.app/healthz"
curl -sS "https://${PROJECT_ID}.web.app/api/scenarios"
```

Open `/` on a phone and `/coordinator/login` on a laptop. Both should be the Hosting origin, with the padlock.

## 4. Record the public URL in the README

After the Hosting deploy succeeds, edit the first line of the README demo header. It is still a placeholder:

```markdown
Live demo: `<URL to add>` | Demo video: `<link to add>` | Coordinator demo login: see Demo section
```

Replace `<URL to add>` with the Hosting URL the CLI printed, for example `https://PROJECT_ID.web.app`. Do not invent the host, and do not paste the `*.run.app` service URL there. The submission URL is the Hosting URL, because that is the one origin for the PWA and `/api/**`.

Then note the same URL in `WORKDONE.md` (new entry, do not edit old ones) and in the slide deck. That remaining work is T-048. Regenerating the QR is T-049.

## Not in this deploy

Pub/Sub, BigQuery, Gemini Live, Search grounding, Malayalam, and photo intake are not part of the service. Firestore rules are not applied, because this process does not store cases in Firestore.
