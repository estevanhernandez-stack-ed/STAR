# Cloud Run Deploy and Public-Exposure Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Put STAR on a public hosted URL that cannot be turned into someone else's search budget, and that survives the failure modes a laptop never shows.

**Architecture:** All hardening lands **before** the URL is ever public — abuse guards, error-detail stripping, SSE reconnect correctness, memory eviction, and blocking-call removal are code changes verified locally. Only then does the container get built and deployed. Secrets go to Secret Manager, never to `--set-env-vars`.

**Tech Stack:** Python 3.12, FastAPI, Docker, Cloud Run, Artifact Registry, Secret Manager, Firestore.

**Spec:** `docs/superpowers/specs/2026-08-09-star-gui-design.md`
**Infrastructure:** `docs/INFRASTRUCTURE.md` — read it before touching cloud config.

## Global Constraints

Every task's requirements implicitly include this section.

- **Runtime AI is Google Cloud only.** Gemini via `google-adk` / `google-genai`. No other AI provider anywhere. Hackathon disqualification criterion.
- **The Parallel Search API must genuinely execute at runtime** via the `parallel-web` SDK in `star/tools/parallel_search.py`. Do not modify or stub it. Disqualification criterion.
- **All runtime dependencies pinned exactly** in `pyproject.toml`. A container build installs fresh.
- **`star/ledger.py` and `star/findings.py` stay pure** — no I/O, no network, no model calls.
- **`star/store.py` is the only module that touches Firestore.**
- **No secret may reach the browser.** `FIREBASE_API_KEY` is a public project identifier and is safe to serve; `GOOGLE_API_KEY` and `PARALLEL_API_KEY` are secrets.
- **Never commit `.env`.** Never print a secret's value, in a log line, a shell echo, or a report.
- **`web/config.js` must not exist on disk** — it is served from environment values.
- **No build step in `web/`.** Native ES modules only.
- **`# noqa: E402` late imports in `star/server.py` are deliberate**; ruff enforces E402 so they stay meaningful.
- **Commit style:** sentence-case imperative, not Conventional Commits.
- Suite is at 115 passing with 7 pre-existing third-party deprecation warnings. Do not fix those; do not add new ones.
- `ruff check star tests scripts` reports exactly 1 finding, the tracked `BLE001` on `_execute`'s outer handler. **Task 1 is expected to remove it** by adding a `logger.exception` call; after Task 1 the expected count is 0.

## Cloud facts (provisioned and verified)

| | |
| --- | --- |
| Project | `star-research-dept` (number `390753828501`) |
| Firestore | Native, `nam5`, live. **No ruleset deployed, and that is correct** — client access is denied on every path. |
| Runtime identity | `390753828501-compute@developer.gserviceaccount.com` |
| APIs enabled | `run`, `artifactregistry`, `cloudbuild`, `firestore`, `identitytoolkit`, `firebase` |
| Billing | account `01CBAA-C1C50E-FB7E78` |

**Region: `us-central1`.** Firestore is `nam5`, a US multi-region that includes `us-central1`, so this keeps database round trips in-continent.

## The eight hazards this plan closes

Recorded by the Phase 2 whole-branch review. Each maps to a task below.

1. `_runs` is per-process; SSE and live room reads need the same instance → Task 4 (`--max-instances=1`)
2. Run ceiling may exceed Cloud Run's request timeout; SSE replays from cursor 0 on reconnect → Tasks 2 and 4
3. `_runs` is never evicted; long-lived instances grow monotonically → Task 2
4. Service env must carry the Firebase vars; runtime SA needs Firestore → Task 4
5. Do not deploy permissive Firestore rules → Task 4 (a verification step, not a change)
6. `mark_interrupted` raises `NotFound`, now reachable → Task 2
7. Sync-blocking Firestore calls in `list_rooms` / `get_room` → Task 2
8. `/docs`, `/redoc`, `/openapi.json` are public → Task 2

---

### Task 1: Abuse guards and error-detail stripping

Everything that must be true before a stranger can reach this URL. Pure server code, fully testable offline.

**Files:**

- Create: `star/guards.py`
- Create: `tests/test_guards.py`
- Modify: `star/server.py`
- Modify: `star/config.py`
- Modify: `tests/test_server.py`

**Interfaces:**

- Consumes: nothing from later tasks.
- Produces:
  - `RateLimiter(max_per_window: int, window_seconds: int)` with `check(key: str, now: float) -> bool` — True when the call is allowed, False when it should be refused. Pure: the caller passes `now`, so tests never sleep.
  - `DailyCap(max_per_day: int)` with `check(now: float) -> bool` and `count_for(now: float) -> int`
  - `config.max_rooms_per_ip_per_hour() -> int` (default `5`)
  - `config.max_rooms_per_day() -> int` (default `100`)

**Why in-memory is correct here, not a compromise:** Task 4 deploys with `--max-instances=1`, because `_runs` is per-process and live runs already require instance affinity. With exactly one instance, an in-memory counter *is* the global counter. Say so in the module docstring, and say what breaks if someone later raises the instance count — the guards silently become per-instance and the daily cap multiplies.

- [ ] **Step 1: Write the failing tests**

`tests/test_guards.py`:

```python
import pytest

from star.guards import DailyCap, RateLimiter

HOUR = 3600.0


def test_rate_limiter_allows_up_to_the_limit():
    limiter = RateLimiter(max_per_window=3, window_seconds=HOUR)
    assert [limiter.check("1.2.3.4", now=0.0) for _ in range(3)] == [True, True, True]


def test_rate_limiter_refuses_past_the_limit():
    limiter = RateLimiter(max_per_window=2, window_seconds=HOUR)
    limiter.check("1.2.3.4", now=0.0)
    limiter.check("1.2.3.4", now=1.0)

    assert limiter.check("1.2.3.4", now=2.0) is False


def test_rate_limiter_keys_are_independent():
    limiter = RateLimiter(max_per_window=1, window_seconds=HOUR)
    assert limiter.check("1.2.3.4", now=0.0) is True
    assert limiter.check("5.6.7.8", now=0.0) is True
    assert limiter.check("1.2.3.4", now=0.0) is False


def test_rate_limiter_forgets_calls_older_than_the_window():
    limiter = RateLimiter(max_per_window=1, window_seconds=HOUR)
    limiter.check("1.2.3.4", now=0.0)

    assert limiter.check("1.2.3.4", now=HOUR + 1) is True


def test_rate_limiter_does_not_grow_without_bound():
    """An attacker rotating IPs must not be able to exhaust memory."""
    limiter = RateLimiter(max_per_window=1, window_seconds=HOUR)
    for i in range(5000):
        limiter.check(f"10.0.{i // 256}.{i % 256}", now=0.0)

    # Everything is stale an hour later; one call should collect the garbage.
    limiter.check("1.2.3.4", now=HOUR * 2)

    assert len(limiter) <= 2, f"stale keys were never evicted: {len(limiter)}"


def test_daily_cap_allows_up_to_the_limit():
    cap = DailyCap(max_per_day=2)
    assert cap.check(now=0.0) is True
    assert cap.check(now=1.0) is True


def test_daily_cap_refuses_past_the_limit():
    cap = DailyCap(max_per_day=1)
    cap.check(now=0.0)

    assert cap.check(now=1.0) is False


def test_daily_cap_resets_on_a_new_day():
    cap = DailyCap(max_per_day=1)
    cap.check(now=0.0)

    assert cap.check(now=86400.0 + 1) is True


def test_daily_cap_reports_its_current_count():
    cap = DailyCap(max_per_day=10)
    cap.check(now=0.0)
    cap.check(now=1.0)

    assert cap.count_for(now=2.0) == 2
    assert cap.count_for(now=86400.0 + 1) == 0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_guards.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'star.guards'`

- [ ] **Step 3: Write the guards**

`star/guards.py`:

```python
"""Abuse guards for a publicly reachable endpoint.

One room build spends real money — a dozen or more live web searches plus
several Gemini calls. Without a ceiling, a public URL is an open invitation
to spend someone else's budget, and the first sign would be the bill.

Both guards are in-memory, and that is correct rather than a compromise: the
service deploys with `--max-instances=1` because `_runs` is per-process and
live runs already require instance affinity. With one instance an in-memory
counter IS the global counter.

If anyone later raises the instance count, these silently become per-instance:
the per-IP limit multiplies by the instance count and the daily cap stops
being daily-global. Moving to a shared store is the fix, and it has to happen
in the same change as the scale-up, not after.
"""

import time


class RateLimiter:
    """Sliding-window limiter keyed by caller."""

    def __init__(self, max_per_window: int, window_seconds: float) -> None:
        self._max = max_per_window
        self._window = window_seconds
        self._hits: dict[str, list[float]] = {}

    def check(self, key: str, now: float | None = None) -> bool:
        """Record a call and return whether it is allowed."""
        now = time.time() if now is None else now
        cutoff = now - self._window

        # Evict every stale key, not just this one. Otherwise an attacker
        # rotating source addresses grows this dict without bound, which is
        # its own denial of service.
        for existing in list(self._hits):
            fresh = [t for t in self._hits[existing] if t > cutoff]
            if fresh:
                self._hits[existing] = fresh
            else:
                del self._hits[existing]

        hits = self._hits.setdefault(key, [])
        if len(hits) >= self._max:
            return False
        hits.append(now)
        return True

    def __len__(self) -> int:
        return len(self._hits)


class DailyCap:
    """A global kill switch measured in whole UTC days."""

    def __init__(self, max_per_day: int) -> None:
        self._max = max_per_day
        self._day: int | None = None
        self._count = 0

    def _roll(self, now: float) -> None:
        day = int(now // 86400)
        if day != self._day:
            self._day, self._count = day, 0

    def check(self, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        self._roll(now)
        if self._count >= self._max:
            return False
        self._count += 1
        return True

    def count_for(self, now: float | None = None) -> int:
        now = time.time() if now is None else now
        self._roll(now)
        return self._count
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_guards.py -v`
Expected: PASS, 9 tests.

- [ ] **Step 5: Add the config knobs**

In `star/config.py`, beside the other limits:

```python
def max_rooms_per_ip_per_hour() -> int:
    """Per-caller ceiling on a public endpoint that spends money to answer."""
    return int(os.environ.get("STAR_MAX_ROOMS_PER_IP_PER_HOUR", "5"))


def max_rooms_per_day() -> int:
    """Global kill switch. One build is roughly 15 searches; 100 builds a day
    is a generous demo allowance and a cheap disaster ceiling."""
    return int(os.environ.get("STAR_MAX_ROOMS_PER_DAY", "100"))
```

- [ ] **Step 6: Write the failing server tests**

Append to `tests/test_server.py`:

```python
def test_a_caller_past_the_hourly_limit_is_refused():
    client = TestClient(server.app)
    treatment = {"treatment": "x" * 60}

    with (
        mock.patch("star.server.verify_token", return_value="uid-one"),
        mock.patch("star.server._store", mock.Mock()),
        mock.patch("star.server._ip_limiter", server.RateLimiter(max_per_window=1, window_seconds=3600)),
        mock.patch("star.server._daily_cap", server.DailyCap(max_per_day=1000)),
    ):
        first = client.post("/api/rooms", json=treatment, headers=AUTH)
        second = client.post("/api/rooms", json=treatment, headers=AUTH)

    assert first.status_code == 200
    assert second.status_code == 429

    for run_id in (first.json()["run_id"],):
        server._runs.pop(run_id, None)


def test_the_daily_cap_refuses_everyone_once_it_trips():
    client = TestClient(server.app)
    treatment = {"treatment": "x" * 60}

    with (
        mock.patch("star.server.verify_token", return_value="uid-one"),
        mock.patch("star.server._store", mock.Mock()),
        mock.patch("star.server._ip_limiter", server.RateLimiter(max_per_window=99, window_seconds=3600)),
        mock.patch("star.server._daily_cap", server.DailyCap(max_per_day=0)),
    ):
        response = client.post("/api/rooms", json=treatment, headers=AUTH)

    assert response.status_code == 429


def test_a_pipeline_failure_does_not_leak_exception_detail_to_the_client():
    """The message a stranger sees must not describe our internals."""
    server._runs["leaky"] = {
        "events": [], "status": "running", "search_count": 0,
        "ledger": SourceLedger(), "result": None, "uid": "uid-one",
        "session_id": None,
    }

    async def _explode(run_id, treatment):
        raise RuntimeError("psycopg2.OperationalError: password authentication failed for user 'star'")

    with (
        mock.patch("star.server._run_pipeline", _explode),
        mock.patch("star.server._store", mock.Mock()),
    ):
        await_result = server._execute("leaky", "a treatment")
        asyncio.get_event_loop().run_until_complete(await_result) if False else None

    server._runs.pop("leaky", None)
```

**Note on that last test:** the shape above is deliberately awkward because `_execute` is a coroutine. Write it as an `@pytest.mark.asyncio` test that awaits `server._execute(...)` directly, matching the existing async tests in this file, and assert that the pushed `error` event's message contains **neither** `"psycopg2"` nor `"password"` nor `"RuntimeError"`, and that it does contain a generic phrase you choose. Also assert the real detail *was* logged, using `caplog`.

- [ ] **Step 7: Wire the guards and strip the error detail**

In `star/server.py`, with the other late imports:

```python
from star.guards import DailyCap, RateLimiter  # noqa: E402
```

Beside `_store`:

```python
_ip_limiter = RateLimiter(
    max_per_window=config.max_rooms_per_ip_per_hour(), window_seconds=3600
)
_daily_cap = DailyCap(max_per_day=config.max_rooms_per_day())
```

In `create_room`, after `_require_uid` and after the treatment-length checks, add the guards. Take the client address from `request.client.host`, falling back to the first entry of `X-Forwarded-For` when present — Cloud Run sits behind a proxy, so `request.client.host` alone is the load balancer. You will need to add `request: Request` to the signature and `from fastapi import Request` to the import line.

```python
    if not _daily_cap.check():
        raise HTTPException(
            429, "STAR has hit its daily research limit. Try again tomorrow."
        )
    if not _ip_limiter.check(_caller_key(request)):
        raise HTTPException(
            429,
            "That is a lot of rooms in one hour. Give the department a moment "
            "and try again shortly.",
        )
```

Write `_caller_key(request)` as a small helper next to the guards, and comment why `X-Forwarded-For`'s **first** entry is the one that matters behind Cloud Run.

Then replace `_execute`'s client-facing error message. It currently pushes `f"{type(exc).__name__}: {exc}"`, which hands a stranger our stack vocabulary. Log the real thing, tell the client something true and useless to an attacker:

```python
    except Exception:
        logger.exception("Run %s failed", run_id)
        ...
        _push(
            run,
            "error",
            message=(
                "The department hit an unexpected problem and stopped. "
                "The details are in the server log."
            ),
        )
```

Adding `logger.exception` here also exempts the handler from ruff's `BLE001`, so the tracked lint finding disappears. **Remove the now-stale `# noqa` if one is present**, or `RUF100` will flag it.

- [ ] **Step 8: Run the tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: PASS, 127 tests.

Run: `.venv/Scripts/python.exe -m ruff check star tests scripts`
Expected: **0 findings.** The tracked `BLE001` is gone.

- [ ] **Step 9: Commit**

```bash
git add star/guards.py star/config.py star/server.py tests/test_guards.py tests/test_server.py
git commit -m "Guard the public endpoint and stop leaking exception detail"
```

---

### Task 2: Production hardening

Five defects that only matter once the app is reachable over a real network on ephemeral infrastructure.

**Files:**

- Modify: `star/server.py`
- Modify: `star/store.py`
- Modify: `tests/test_server.py`
- Modify: `tests/test_store.py`

**Interfaces:**

- Consumes: nothing from Task 1 beyond the file being shared.
- Produces:
  - `RoomStore.mark_interrupted` returns `bool` — `True` when it marked, `False` when the document was already gone
  - SSE events carry an `id:` line, and `stream_events` honours the `Last-Event-ID` request header
  - `config.max_runs_in_memory() -> int` (default `20`)

- [ ] **Step 1: Stop the SSE stream duplicating everything on reconnect**

Today `stream_events` starts at `cursor = 0` on every connection and emits no `id:`. Over the internet, `EventSource` reconnects routinely — and each reconnect replays the entire event history, so `web/app.js` appends every timeline entry again and double-counts every search.

Assign each event a monotonic index when it is pushed, emit it as the SSE `id:` field, and start the cursor from the `Last-Event-ID` header when the browser supplies one. `EventSource` sends that header automatically on reconnect; no client change is required for correctness, though the client should still tolerate duplicates.

Add `partial` awareness only if it is missing — it should already be in `_TERMINAL_RUN_STATUSES`.

Write the test first: seed a run with several events, request the stream with `Last-Event-ID` set past the first few, and assert only the later events are emitted.

- [ ] **Step 2: Evict completed runs from memory**

`_runs` grows forever, and each entry holds a `SourceLedger` carrying every excerpt from up to 30 searches plus a task reference. Persistence now makes eviction safe: a finished run can be dropped from memory and read back from Firestore.

Add `config.max_runs_in_memory()` (default `20`) and, after a run reaches a terminal status, drop the oldest completed entries beyond that bound. **Never evict a run that is still `running`** — that would orphan a live build and break its SSE stream.

Test: fill `_runs` past the bound with terminal runs, confirm the oldest are gone, the newest survive, and a `running` entry is untouched regardless of age.

- [ ] **Step 3: Make `mark_interrupted` survive a missing document**

`star/store.py`'s `mark_interrupted` calls `.update()`, which raises `google.api_core.exceptions.NotFound` when the document is gone. `get_room` calls it only after a successful read, but Task 1's creation-time write made a delete-between-read-and-update race genuinely reachable, and today it would surface as an unhandled 500 rather than a 404.

Catch `NotFound` specifically — not a broad `except` — and return `False`. Have `get_room` treat `False` as "this room is gone" and 404 rather than reporting a status it could not set. Test both branches; the fake client in `tests/test_store.py` will need to raise `NotFound` for the missing case, which is also worth doing because that fake currently disagrees with real Firestore on exactly this point.

- [ ] **Step 4: Get the remaining Firestore calls off the event loop**

`list_rooms` and `get_room` call the blocking Firestore client directly in async handlers, stalling the single-threaded loop for every other request and SSE stream on the instance. `create_room`'s write already uses `asyncio.to_thread`; do the same for these two.

No new test is required for behaviour that does not change, but confirm the existing endpoint tests still pass — `mock.Mock()` stores work identically through `to_thread`.

- [ ] **Step 5: Close the public API schema**

`/docs`, `/redoc`, and `/openapi.json` are served publicly. They expose no secrets, but they hand an attacker a map. Disable them in the `FastAPI(...)` constructor:

```python
app = FastAPI(
    title="STAR — Story & Treatment Agentic Research",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
```

Test that all three now return 404.

- [ ] **Step 6: Run the full suite and the linter**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: PASS, roughly 136 tests — report the real number.

Run: `.venv/Scripts/python.exe -m ruff check star tests scripts`
Expected: 0 findings.

- [ ] **Step 7: Commit**

```bash
git add star/server.py star/store.py tests/test_server.py tests/test_store.py star/config.py
git commit -m "Harden the service for public ephemeral infrastructure"
```

---

### Task 3: Container

**Files:**

- Create: `Dockerfile`
- Create: `.dockerignore`

**Interfaces:**

- Consumes: the app as hardened by Tasks 1 and 2.
- Produces: an image that starts `uvicorn star.server:app` on `$PORT`.

- [ ] **Step 1: Write `.dockerignore` first**

Before the Dockerfile, so a careless `COPY . .` can never pick up a secret:

```text
.venv/
.env
.mcp.json
.claude/
.superpowers/
.git/
.playwright-mcp/
__pycache__/
*.pyc
*.egg-info/
.pytest_cache/
.ruff_cache/
docs/
tests/
scripts/
star-*.png
```

`.env` is the line that matters. Everything else is size.

- [ ] **Step 2: Write the Dockerfile**

```dockerfile
# Pinned to the interpreter both verified room builds ran on. A floating tag
# would let a base-image bump land between a rehearsal and the real demo.
FROM python:3.12.12-slim

# Cloud Run sends SIGTERM and gives 10s before SIGKILL. Running uvicorn as PID 1
# without an init means it, not the shell, receives that signal.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependency layer first: pyproject alone changes far less often than source,
# so a code edit does not reinstall google-adk.
COPY pyproject.toml README.md ./
COPY star/ ./star/
RUN pip install --no-cache-dir .

COPY web/ ./web/

# Cloud Run supplies PORT and it is not always 8080. Honour it.
ENV PORT=8080
CMD exec uvicorn star.server:app --host 0.0.0.0 --port ${PORT}
```

**Note:** `pip install .` needs `star/` present because `pyproject.toml` lists explicit packages, which is why the source copy precedes the install rather than following it. `README.md` is copied because `pyproject.toml` declares it as the readme and the build fails without it.

- [ ] **Step 3: Build the image**

Run: `docker build -t star-local .`
Expected: build succeeds.

**If `docker` is not installed on this machine**, say so in your report and skip to Step 5 — Task 4 builds with Cloud Build server-side, so a local Docker is a convenience, not a requirement.

- [ ] **Step 4: Run the container locally against real cloud services**

```bash
docker run --rm -p 8080:8080 \
  --env-file .env \
  -e PORT=8080 \
  -v "$HOME/AppData/Roaming/gcloud/application_default_credentials.json:/adc.json:ro" \
  -e GOOGLE_APPLICATION_CREDENTIALS=/adc.json \
  star-local
```

Then in another shell: `curl -s http://localhost:8080/config.js` — expect JavaScript containing the project id, and `curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/api/rooms` — expect `401`.

**Do not build a room from the container.** It costs real searches and Task 4 verifies the deployed service properly.

- [ ] **Step 5: Commit**

```bash
git add Dockerfile .dockerignore
git commit -m "Containerize the service for Cloud Run"
```

---

### Task 4: Deploy and verify

**Files:**

- Create: `scripts/deploy.sh`
- Modify: `docs/INFRASTRUCTURE.md`

**Interfaces:**

- Consumes: the container from Task 3.
- Produces: a live public URL, and a repeatable deploy script.

**This task performs outward-facing, money-spending actions.** Do not run the deploy without the controller's explicit go-ahead in your dispatch. If anything is ambiguous, stop and ask.

- [ ] **Step 1: Put the secrets in Secret Manager**

Never `--set-env-vars` a secret: it lands in the service YAML, visible in the console and in `gcloud run services describe`.

```bash
gcloud services enable secretmanager.googleapis.com --project=star-research-dept

# Values come from .env. Do not echo them.
grep '^GOOGLE_API_KEY=' .env | cut -d= -f2- | tr -d '\r\n' | \
  gcloud secrets create star-google-api-key --data-file=- --project=star-research-dept
grep '^PARALLEL_API_KEY=' .env | cut -d= -f2- | tr -d '\r\n' | \
  gcloud secrets create star-parallel-api-key --data-file=- --project=star-research-dept
```

- [ ] **Step 2: Grant the runtime identity what it needs**

```bash
SA=390753828501-compute@developer.gserviceaccount.com
gcloud projects add-iam-policy-binding star-research-dept \
  --member="serviceAccount:$SA" --role=roles/datastore.user
gcloud secrets add-iam-policy-binding star-google-api-key \
  --member="serviceAccount:$SA" --role=roles/secretmanager.secretAccessor \
  --project=star-research-dept
gcloud secrets add-iam-policy-binding star-parallel-api-key \
  --member="serviceAccount:$SA" --role=roles/secretmanager.secretAccessor \
  --project=star-research-dept
```

`roles/datastore.user` is Firestore read/write. Token verification needs no IAM — it checks Google's public certs.

- [ ] **Step 3: Write the deploy script**

`scripts/deploy.sh`, so this is repeatable rather than a command someone half-remembers:

```bash
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
```

`FIREBASE_API_KEY` is a public browser-facing identifier, so it is a plain env var by design, not a secret. It still must not be hardcoded in the script — read it from the environment so the script carries no project-specific values a fork would inherit.

- [ ] **Step 4: Deploy**

Run: `FIREBASE_API_KEY=$(grep '^FIREBASE_API_KEY=' .env | cut -d= -f2-) bash scripts/deploy.sh`

Expected: a build, then a service URL. First build takes several minutes.

- [ ] **Step 5: Verify the deployed service, in this order**

Substitute the real URL for `$URL`.

1. `curl -s "$URL/config.js"` — JavaScript with the project id, and **no** `GOOGLE_API_KEY` or `PARALLEL_API_KEY` value in the body.
2. `curl -s -o /dev/null -w "%{http_code}" "$URL/api/rooms"` — `401`.
3. `curl -s -o /dev/null -w "%{http_code}" "$URL/docs"` — `404`.
4. `curl -s "$URL/" | head -5` — the app's HTML.
5. Sign in anonymously against Identity Toolkit with the real API key, then `GET $URL/api/rooms` with the token — `200` and an empty room list for a fresh uid.
6. **Confirm the Firestore posture did not change:** re-run the probe from `docs/INFRASTRUCTURE.md` — a client token must still be denied on every direct Firestore path.

**Do not build a room yet.** Report the URL and stop; the controller decides when to spend a live build on the deployed service.

- [ ] **Step 6: Record the deployment**

Add a section to `docs/INFRASTRUCTURE.md`: the service URL, region, the deploy command, why `--max-instances=1` is load-bearing, which secrets live in Secret Manager under which names, and what a future maintainer must change together if they ever scale past one instance.

- [ ] **Step 7: Commit**

```bash
git add scripts/deploy.sh docs/INFRASTRUCTURE.md
git commit -m "Deploy to Cloud Run and record the service"
```

---

## Done when

- A public URL serves the app, rejects unauthenticated API calls, and hides its schema.
- Secrets are in Secret Manager; the service YAML contains no key values.
- A caller past the hourly limit gets 429; the daily cap refuses everyone once tripped.
- A pipeline failure tells the client nothing about our internals, and the real detail is in the log.
- An SSE reconnect resumes rather than replaying.
- Client-side Firestore access is still denied on every path.
- The suite passes and `ruff check star tests scripts` reports 0 findings.

## Not in this phase

- The room UI, the project rail, `CategoryPanel`. Phase 3.
- Vendoring `marked` and DOMPurify. Phase 3.
- Rendering the `categories` payload. Phase 3.
- Script Check. Phase 4.
- A shared-store rate limiter. Required only if the instance count ever rises above one, and it must land in that same change.
