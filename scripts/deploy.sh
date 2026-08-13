#!/usr/bin/env bash
# Deploy STAR to Cloud Run. Runnable from anywhere — cd's to the repo root
# itself so `--source .` always means this repo, not the caller's cwd.
set -euo pipefail
cd "$(dirname "$0")/.."

PROJECT="${PROJECT:-star-research-dept}"
REGION=us-central1
SERVICE=star

# Read the two config values out of .env when they are not already exported.
#
# The documented invocation used to be
#   FIREBASE_API_KEY=$(grep '^FIREBASE_API_KEY=' .env | cut -d= -f2-) bash scripts/deploy.sh
# which put a secret on a command line — into shell history, into `ps` for
# every user on the box — to hand it to a script sitting in the same directory
# as the file it came from. It also carried GOOGLE_OAUTH_CLIENT_ID nowhere, so
# the ordinary way to run the deploy was the way that triggers the warning
# below and strips account linking off the live service. The safe invocation
# and the convenient one now agree: `bash scripts/deploy.sh`.
#
# Values are never echoed, an already-exported value always wins, and a
# missing .env is not an error — CI exports these rather than shipping the
# file, and that has to keep working.
if [[ -f .env ]]; then
  for _var in FIREBASE_API_KEY GOOGLE_OAUTH_CLIENT_ID; do
    if [[ -z "${!_var:-}" ]]; then
      # `read` rather than eval: a .env line is data, and a value containing
      # $(...) or a backtick must reach the deploy as those characters rather
      # than as something this shell ran. Quotes are stripped, nothing else is
      # interpreted, and only the first match counts.
      _val=$(grep -m1 "^${_var}=" .env 2>/dev/null | cut -d= -f2- || true)
      _val="${_val%\"}"; _val="${_val#\"}"
      _val="${_val%\'}"; _val="${_val#\'}"
      [[ -n "$_val" ]] && export "${_var}=${_val}"
    fi
  done
  unset _var _val
fi

# GOOGLE_OAUTH_CLIENT_ID is optional at boot and the app degrades honestly
# without it: /config.js serves "", the card renders linking as unavailable and
# says why, and every other path works. It is NOT optional here in the same way,
# because --set-env-vars REPLACES the service's whole variable set. Deploying
# without it silently REMOVES it from a service that had it, and the only symptom
# is that linking quietly stops being offered — on a surface nobody checks after
# a deploy, because the room still builds and the rail still fills.
#
# So: warn loudly, do not fail. Failing would block a deploy for a feature the
# design says is allowed to be absent.
if [[ -z "${GOOGLE_OAUTH_CLIENT_ID:-}" ]]; then
  echo "WARNING: GOOGLE_OAUTH_CLIENT_ID is not set." >&2
  echo "         Google account linking will be UNAVAILABLE on the deployed service," >&2
  echo "         and if the running service currently has it, this deploy REMOVES it." >&2
  echo "         Export it (it lives in .env) if that is not what you want." >&2
  echo >&2
fi

# --max-instances=1 AND --min-instances=1 are both load-bearing, not tuning —
# neither alone is enough. `_runs` and the abuse guards in star/guards.py
# (_ip_limiter, _daily_cap) are per-process module-level state.
#
# --max-instances=1 keeps a live build's SSE stream and its in-memory room
# read on the same instance; a second instance breaks runs in flight.
#
# --min-instances=1 keeps that one instance warm. Without it, Cloud Run
# scales to zero when idle and the next request cold-starts a fresh process
# with _ip_limiter and _daily_cap back at zero — so the "100 builds/day" cap
# is actually "100 builds per instance lifetime," and instance lifetime has
# no lower bound under min-instances=0. An attacker sends 100 builds, waits
# out the idle window, and repeats; every redeploy or instance recycle also
# resets both counters for free. min-instances=1 removes cold-start latency
# from a live demo too, but that is the bonus, not the reason.
#
# If this ever needs to scale past one instance, both flags AND the abuse
# guards need to move together to a shared store (Firestore/Redis) in the
# same change — see star/guards.py's module docstring and
# docs/INFRASTRUCTURE.md.
#
# --no-cpu-throttling is the third load-bearing flag, and the least obvious.
# By default Cloud Run allocates CPU only while a request is being processed.
# The build itself is NOT a request: star/server.py's create_room returns
# immediately and _execute runs as a detached asyncio task. The only thing
# holding a request open during a build is the client's EventSource.
#
# So without this flag, a user who closes the tab mid-build ends the SSE
# request, CPU throttles to near zero, and the pipeline stalls partway. The
# run never reaches a terminal status, which means _evict_old_runs can never
# reclaim it (it does not touch "running" entries), its daily-cap slot stays
# spent, and its Firestore document is stranded at status "running" — which
# the room view then reports to its owner as a run that never finished.
# Every one of those consequences is invisible in a local test, because
# nothing throttles a laptop.
#
# --timeout must exceed STAR_RUN_TIMEOUT_SECONDS (600), because the SSE
# stream is itself a request and stays open for the whole build.
gcloud run deploy "$SERVICE" \
  --source . \
  --project "$PROJECT" \
  --region "$REGION" \
  --allow-unauthenticated \
  --max-instances=1 \
  --min-instances=1 \
  --cpu=1 \
  --no-cpu-throttling \
  --memory=2Gi \
  --timeout=900 \
  --set-env-vars="GOOGLE_CLOUD_PROJECT=$PROJECT,FIREBASE_PROJECT_ID=$PROJECT,GOOGLE_GENAI_USE_VERTEXAI=FALSE,FIREBASE_API_KEY=${FIREBASE_API_KEY:?set FIREBASE_API_KEY in the environment before deploying}${GOOGLE_OAUTH_CLIENT_ID:+,GOOGLE_OAUTH_CLIENT_ID=$GOOGLE_OAUTH_CLIENT_ID}" \
  --set-secrets="GOOGLE_API_KEY=star-google-api-key:latest,PARALLEL_API_KEY=star-parallel-api-key:latest"

gcloud run services describe "$SERVICE" --project "$PROJECT" --region "$REGION" \
  --format='value(status.url)'
