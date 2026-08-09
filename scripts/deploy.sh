#!/usr/bin/env bash
# Deploy STAR to Cloud Run. Run from the repo root.
set -euo pipefail

PROJECT=star-research-dept
REGION=us-central1
SERVICE=star

# --max-instances=1 is load-bearing, not tuning. `_runs` is per-process: a
# live build's SSE stream and its in-memory room read both require the same
# instance. A second instance breaks runs in flight. The abuse guards in
# star/guards.py are in-memory for the same reason and become per-instance
# if this changes.
#
# --timeout must exceed STAR_RUN_TIMEOUT_SECONDS (600), because the SSE
# stream is itself a request and stays open for the whole build.
gcloud run deploy "$SERVICE" \
  --source . \
  --project "$PROJECT" \
  --region "$REGION" \
  --allow-unauthenticated \
  --max-instances=1 \
  --min-instances=0 \
  --cpu=1 \
  --memory=2Gi \
  --timeout=900 \
  --set-env-vars="GOOGLE_CLOUD_PROJECT=$PROJECT,FIREBASE_PROJECT_ID=$PROJECT,GOOGLE_GENAI_USE_VERTEXAI=FALSE,FIREBASE_API_KEY=${FIREBASE_API_KEY:?set FIREBASE_API_KEY in the environment before deploying}" \
  --set-secrets="GOOGLE_API_KEY=star-google-api-key:latest,PARALLEL_API_KEY=star-parallel-api-key:latest"

gcloud run services describe "$SERVICE" --project "$PROJECT" --region "$REGION" \
  --format='value(status.url)'
