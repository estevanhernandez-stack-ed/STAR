# STAR infrastructure

Provisioned 2026-08-09. Everything below is live and verified, not aspirational.

## Google Cloud project

| | |
| --- | --- |
| Project ID | `star-research-dept` |
| Project number | `390753828501` |
| Firebase console | https://console.firebase.google.com/project/star-research-dept |

A dedicated project, deliberately. STAR is a publicly-deployed hackathon entry;
putting its Firestore, its anonymous-auth users, and its public Cloud Run
traffic inside `project-626labs` would share a blast radius and a quota with
the 626 dashboard. Teardown after 2026-09-07 is one project deletion.

## Billing — read this before adding another project

Linked to billing account `01CBAA-C1C50E-FB7E78`.

**Not** the usual `01A07D-181DC7-0B4BA0`. That account sits at Google's cap of
5 linked projects, and the first link attempt failed with
`Cloud billing quota exceeded`. `01CBAA` had zero projects linked. If a future
project fails to link billing, that cap is why — check
`gcloud billing projects list --billing-account=<id>` before assuming a
permissions problem.

## Services enabled

- `firestore.googleapis.com` — Native mode database, location `nam5`
- `identitytoolkit.googleapis.com` — Firebase Auth, anonymous provider enabled
- `firebase.googleapis.com`, `firebaserules.googleapis.com`

Cloud Run and Artifact Registry are **not** yet enabled; that belongs to the
deploy task.

## What needed billing and what did not

Worth recording, because the two behave differently and it cost a detour:

- **Firestore Native created fine with no billing.** The free tier covers it.
- **Firebase Auth did not.** `identityPlatform:initializeAuth` returns
  `BILLING_NOT_ENABLED`, and until it is initialized, anonymous sign-in fails
  with `CONFIGURATION_NOT_FOUND` — a confusing error that looks like a
  misconfigured client rather than an uninitialized project.

## Gemini is independent of all of this

`GOOGLE_GENAI_USE_VERTEXAI=FALSE`, so Gemini runs through AI Studio on
`GOOGLE_API_KEY` and does not touch this project. Changing cloud projects does
not disturb the working model path.

## Verified end to end

Anonymous sign-in returns a real uid with `sign_in_provider: anonymous`,
token audience `star-research-dept`, issuer
`https://securetoken.google.com/star-research-dept`.

## The web API key is not a secret

`FIREBASE_API_KEY` identifies the project to the browser and is designed to
ship in client code. Security comes from Auth and Firestore rules, not from
hiding it. Do not treat it like `GOOGLE_API_KEY` or `PARALLEL_API_KEY`, which
are secrets and stay in the gitignored `.env`.

## Firestore security rules: none deployed, and that is correct

Verified empirically 2026-08-09 with a real anonymous ID token against the
Firestore REST API:

| Probe | Result |
| --- | --- |
| `GET /users` (enumerate all users) | 403 `PERMISSION_DENIED` |
| `PATCH /users/{own_uid}/rooms/...` | 403 `PERMISSION_DENIED` |
| `GET /users/{other_uid}/rooms` | 403 `PERMISSION_DENIED` |

**No ruleset is deployed, and with none deployed Firestore denies all
client-side access.** That is the desired posture here: the server owns every
read and write through Application Default Credentials, which bypass rules
entirely, and the browser holds a token that is useful only against STAR's own
API. One security boundary, not two.

**Do not "fix" this by deploying permissive test-mode rules.** A ruleset of the
`allow read, write: if true` shape would hand every browser token direct
read access to every user's rooms and silently void the boundary the server
was built to be. If rules are ever deployed, they must be deny-by-default with
ownership checks, and this probe should be re-run to confirm the posture did
not invert.

## Cloud Run deployment

Deployed 2026-08-09.

| | |
| --- | --- |
| Service URL | `https://star-390753828501.us-central1.run.app` |
| Region | `us-central1` |
| Service name | `star` |
| Revision | `star-00001-6r6` |

Deploy command (also `scripts/deploy.sh`, run from repo root):

```bash
FIREBASE_API_KEY=$(grep '^FIREBASE_API_KEY=' .env | cut -d= -f2-) bash scripts/deploy.sh
```

The script builds from source via Cloud Build (no local Docker needed),
deploys to Cloud Run, and prints the service URL.

### `--max-instances=1` is load-bearing, not tuning

`_runs` is per-process in-memory state: a live build's SSE stream and its
in-memory room read both have to hit the same instance, or the reader gets
"room not found" against an instance that never ran the build. A second
instance silently breaks runs in flight — no error, just a client stuck on a
stream that another instance knows nothing about. The abuse guards in
`star/guards.py` (the 5-per-IP-per-hour and 100-per-day counters) are
in-memory for the same reason, and they become per-instance — and therefore
bypassable by hitting a different instance — the moment instance count rises
above one.

**If this ever needs to scale past one instance, both of these must move
together, in the same change:**

- `_runs` (or whatever replaces it) to a shared store — Firestore or Redis —
  keyed so any instance can serve any in-flight run's SSE stream.
- The abuse-guard counters in `star/guards.py` to that same shared store, or
  the per-IP/per-day limits become per-instance and the real ceiling is
  `limit * instance_count`.

Shipping a `max-instances` bump without both of these is the failure mode
this comment exists to prevent.

### Secrets: where they live

| Env var | Source | Why |
| --- | --- | --- |
| `GOOGLE_API_KEY` | Secret Manager, secret `star-google-api-key`, mounted via `--set-secrets` | Real credential — Gemini via AI Studio |
| `PARALLEL_API_KEY` | Secret Manager, secret `star-parallel-api-key`, mounted via `--set-secrets` | Real credential — Parallel search |
| `FIREBASE_API_KEY` | Plain `--set-env-vars`, read from the caller's shell environment | Public browser-facing project identifier, not a secret — see above |
| `GOOGLE_CLOUD_PROJECT`, `FIREBASE_PROJECT_ID`, `GOOGLE_GENAI_USE_VERTEXAI` | Plain `--set-env-vars`, hardcoded to `star-research-dept` / `FALSE` in the script | Non-sensitive configuration |

The runtime identity (`390753828501-compute@developer.gserviceaccount.com`)
holds `roles/secretmanager.secretAccessor` on both secrets individually
(least privilege — scoped to the two secrets it needs, not project-wide) and
`roles/datastore.user` on the project for Firestore reads/writes through
Application Default Credentials.

Confirmed by inspecting `gcloud run services describe star --format=yaml`:
`GOOGLE_API_KEY` and `PARALLEL_API_KEY` appear only as
`valueFrom.secretKeyRef`, never as plaintext `value`. `FIREBASE_API_KEY`
appears as plaintext `value` by design.

### Verification run 2026-08-09

All six checks passed against the live URL immediately after deploy. Full
verbatim output lives in
`.superpowers/sdd/2026-08-09-cloud-run-deploy-and-hardening/task-4-report.md`.
Summary:

1. `/config.js` serves `projectId` and the public `FIREBASE_API_KEY`; neither
   `GOOGLE_API_KEY` nor `PARALLEL_API_KEY` value appears anywhere in the
   response (checked programmatically against the real secret values, not by
   eye).
2. `/api/rooms` with no token: `401`.
3. `/docs`: `404`.
4. `/`: serves the app's `<!DOCTYPE html>` shell.
5. Anonymous sign-in against Identity Toolkit, then `GET /api/rooms` with
   that token: `200`, `{"rooms":[]}` for a fresh uid.
6. Re-ran the Firestore probe from above against the deployed project with a
   fresh anonymous token: `GET /users`, `PATCH /users/{own_uid}/rooms/...`,
   and `GET /users/{other_uid}/rooms` all still return `403
   PERMISSION_DENIED`. The security boundary did not move — the server, via
   ADC, is still the only path to Firestore.

**Not exercised in this pass:** building an actual research room. Each build
spends real money on live web searches; that first production spend is the
controller's call, not something this deploy step takes on its own.

## Reading the Cloud Run service YAML without being fooled

`gcloud run services describe star --format yaml` contains **two** `maxScale`
keys and **two** `timeoutSeconds` keys, and in both cases the first one you
hit is not the one that governs. This cost a false alarm on 2026-08-09.

| Key | Where | Meaning |
| --- | --- | --- |
| `run.googleapis.com/maxScale: '20'` | service annotations, near the top | a GCP-level hint. **Not** the effective cap. |
| `autoscaling.knative.dev/maxScale: '1'` | revision template annotations | the real instance ceiling. |
| `timeoutSeconds: 240` | nested under `tcpSocket:` | the **startup probe** timeout. |
| `timeoutSeconds: 900` | container spec, top level | the **request** timeout. |

Ask the serving revision instead of grepping the service:

```bash
REV=$(gcloud run services describe star --project star-research-dept   --region us-central1 --format="value(status.latestReadyRevisionName)")
gcloud run revisions describe "$REV" --project star-research-dept   --region us-central1   --format="value(metadata.annotations['autoscaling.knative.dev/maxScale'],spec.timeoutSeconds,spec.containerConcurrency)"
```

Expected: `1	900	80`. If the first value is ever not `1`, stop — `_runs`
is per-process, so live builds break and the in-memory abuse guards silently
become per-instance.
