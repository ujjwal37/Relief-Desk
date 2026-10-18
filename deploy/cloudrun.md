# Deploy recipe (not a deployment)

This file is not a record of a deployment. There is no live Cloud Run URL, no Firebase Hosting site, and no Secret Manager binding. Nothing in this repository was deployed by the agent that wrote the recipe. A human supplies the GCP project and the secret values, then runs the commands below.

The API that the tests run is a local process. `StorageService` in `services/api/app/tools/storage.py` keeps reports, requests, resources, matches, and the audit log in process memory. A new Cloud Run instance reloads the synthetic seeds and drops anything submitted to the previous instance. `_init_firestore` opens a client only when `FIRESTORE_EMULATOR_HOST` accepts a TCP connection and `google.cloud.firestore` imports. Nothing in that file reads or writes through the client after that. `google-cloud-firestore` is not pinned in `services/api/requirements.txt`. Treat Firestore as unused for this prototype.

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
  aiplatform.googleapis.com \
  firebase.googleapis.com \
  firebasehosting.googleapis.com
```

Add Firebase to the same GCP project if it is not already a Firebase project:

```bash
npx firebase-tools projects:addfirebase "$PROJECT_ID"
```

## 1. Secret Manager

The process reads environment variables. It does not call the Secret Manager API. Mount the secrets as env vars. Values stay in your shell and in Secret Manager. They do not go in git, in `deploy/cloudrun.env.yaml`, or in the image.

The mounts:

| Env var | Secret id | Why |
|---|---|---|
| `GEMINI_API_KEY` | `gemini-api-key` | Intake, dedupe judge, embeddings, explainer. `replace-me` keeps the deterministic fallback. |
| `JWT_SECRET` | `jwt-secret` | Signs coordinator JWTs, including one-click `POST /api/auth/demo-login`. There is no source default. If this secret is missing, demo login returns 503. Mount it before deploying the revision that removed the default. Use a new random value. Do not reuse `relief-desk-coordinator-secret-2026` (it is in git history). |
| `COORDINATOR_PASSWORD` | `coordinator-password` | Optional. Only `POST /api/auth/login` reads it. The judge button calls `/api/auth/demo-login` and does not need this secret. |
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
# Optional. Skip this if judges only use the one-click button.
# create_secret coordinator-password
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

# Grant Vertex AI user role so Cloud Run can call Gemini via ADC without an API key:
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${RUNTIME_SA}" \
  --role="roles/aiplatform.user"

# If you created coordinator-password, grant the same role on that secret too:
# gcloud secrets add-iam-policy-binding coordinator-password \
#   --member="serviceAccount:${RUNTIME_SA}" \
#   --role="roles/secretmanager.secretAccessor"
```

### Vertex AI with AI Studio Fallback
When `GEMINI_BACKEND: "auto"` and `VERTEX_PROJECT: "relief-desk"` (configured in `deploy/cloudrun.env.yaml`) are set, the API builds `genai.Client(vertexai=True, project=VERTEX_PROJECT, location=VERTEX_LOCATION)` using Application Default Credentials (ADC) provided by the Cloud Run runtime service account (`$RUNTIME_SA`). `VERTEX_LOCATION` defaults to `global` because Vertex in `asia-south1` returns 417 for these models (Cloud Run and Secret Manager remain in `asia-south1`). Granting `roles/aiplatform.user` enables first-party Vertex AI Gemini calls without needing an API key. If Vertex AI credentials or permissions fail, the API automatically falls back to AI Studio using `GEMINI_API_KEY` from Secret Manager, logging a single warning without exposing keys.


## 2. API container

The root `Dockerfile` copies `services/api`, `data`, and `bench/results`, listens on `0.0.0.0:$PORT`, and defaults `PORT` to 8080. Cloud Run sets `PORT`. `DEMO_MODE=true` and `DEMO_SEED=small` keep the current two-case demo. Local check, still with a placeholder key:

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

`requirements.txt` pins `PyJWT` because `app/api/auth.py` imports it at startup.

### Deploy from source

`--source .` uses the root `Dockerfile` (Cloud Build does not use buildpacks when that file is present). `.gcloudignore` keeps `node_modules`, `.env`, and `dist` out of the upload. `.dockerignore` does the same for a local `docker build`.

`--max-instances 1` keeps a single in-memory store. Two instances would each hold a different queue. `--no-cpu-throttling` leaves CPU on after the HTTP response so the intake pipeline thread and the simulated team-movement thread keep running. `--timeout 300` matches the Server-Sent Events stream (`GET /api/events`): the handler sends `Cache-Control: no-cache, no-transform`, `X-Accel-Buffering: no`, and `Content-Encoding: identity`, and a heartbeat goes out every 15 seconds. A shorter timeout closes the socket; the desk and the status page reconnect with backoff and poll every 5 seconds while the stream is down. `--min-instances 0` scales to zero when idle (the queue is then gone and the next start reloads seeds).

```bash
gcloud run deploy "$SERVICE" \
  --source . \
  --region "$REGION" \
  --platform managed \
  --allow-unauthenticated \
  --port 8080 \
  --memory 1Gi \
  --cpu 1 \
  --timeout 300 \
  --concurrency 80 \
  --min-instances 0 \
  --max-instances 1 \
  --no-cpu-throttling \
  --env-vars-file deploy/cloudrun.env.yaml \
  --set-secrets GEMINI_API_KEY=gemini-api-key:latest,JWT_SECRET=jwt-secret:latest,GOOGLE_MAPS_API_KEY=google-maps-api-key:latest
```

`DEMO_MODE=true` and `GEMINI_ENABLED=true` are in `deploy/cloudrun.env.yaml`. `GEMINI_ENABLED=false` is the kill-switch. `AI_MODE=auto` calls Gemini only when the mounted key is real. `SUPPORTED_LANGS` is `en`, `hi`, `hinglish`, and `ml` (Malayalam), matching the PWA. If the deploy rejects the empty `FIRESTORE_EMULATOR_HOST` or `FIREBASE_AUTH_EMULATOR_HOST` lines, delete them. The code default then probes `127.0.0.1:8080` for a fraction of a second and still keeps cases in memory.

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
  --timeout 300 \
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
curl -sS "${CLOUD_RUN_URL}/api/health"
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

`/healthz` is rewritten because the PWA calls `/healthz` (see `apps/web/proxy.conf.js` and `libs/shared` `api-client.service.ts`). `/api/**` does not include `/healthz`.

Deploy Hosting only after the Cloud Run service exists in the same project. Do not run `firebase init`; it will offer to replace `firebase.json`.

```bash
npm ci
npx ng build web
test -f dist/web/browser/index.html

npx firebase-tools deploy --only hosting --project "$PROJECT_ID"
```

The CLI prints `Hosting URL: https://PROJECT_ID.web.app` (and usually `https://PROJECT_ID.firebaseapp.com`). That Hosting URL is the single public URL.

Maps key referrers, if you mounted a real browser key: `https://PROJECT_ID.web.app/*` and `https://PROJECT_ID.firebaseapp.com/*`, plus localhost. Until `GOOGLE_MAPS_API_KEY` is a real key, the map stays the built-in SVG.

Judges sign in with **Enter as demo coordinator** on `/coordinator/login`. That calls `POST /api/auth/demo-login`. The handler checks `DEMO_MODE` (set in `deploy/cloudrun.env.yaml`) and returns a JWT signed with `JWT_SECRET`. It does not read a password. Before this revision is deployed, Secret Manager secret **`jwt-secret`** must be mounted as `JWT_SECRET` (already on the `--set-secrets` line). There is no code default. If the running service was still on the old source default, add a new version of `jwt-secret` with a new random value and redeploy. Do not reuse `relief-desk-coordinator-secret-2026`.

The email/password form calls `POST /api/auth/login` and succeeds only when `COORDINATOR_PASSWORD` matches. That variable is optional for the demo. To enable the form, create secret id **`coordinator-password`** and add `COORDINATOR_PASSWORD=coordinator-password:latest` to `--set-secrets`. Leave it unset and the form stays closed. The one-click button still works.

`ENV=production` refuses the old bearer `demo-coordinator-token`. `python scripts/seed.py` is local only. Leave `FIREBASE_AUTH_EMULATOR_HOST` empty on Cloud Run.

Smoke from a network that is not your laptop:

```bash
curl -sS "https://${PROJECT_ID}.web.app/api/health"
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

Pub/Sub, BigQuery, Gemini Live, and Search grounding are not part of the service. Photo observations are: the API checks a PNG, JPEG, or WebP in memory and does not store the image. `requirements.txt` pins Pillow for that check, and the image install picks it up with the other dependencies. Firestore rules are not applied, because this process does not store cases in Firestore. The PWA languages are English, Hindi, Hinglish, and Malayalam. The model call timeout in `deploy/cloudrun.env.yaml` is 20 seconds, matching `GEMINI_TIMEOUT_S` in `services/api/app/config.py`.
