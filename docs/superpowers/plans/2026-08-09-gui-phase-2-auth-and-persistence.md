# GUI Phase 2 — Firebase Anonymous Auth and Firestore Persistence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every visitor a silent anonymous identity and persist their rooms to Firestore, so a room survives a refresh and a returning writer finds their work.

**Architecture:** The browser signs in anonymously against Google's Identity Toolkit REST endpoints (no SDK, no CDN) and sends the resulting ID token as a bearer credential to STAR's own API. The server verifies that token, derives a uid, and owns every Firestore read and write. Document shaping is a pure function so it can be tested hard; only a thin adapter touches the network.

**Tech Stack:** Python 3.12, FastAPI, `firebase-admin` 7.5.0, Firestore Native, vanilla ES modules.

**Spec:** `docs/superpowers/specs/2026-08-09-star-gui-design.md`
**Infrastructure:** `docs/INFRASTRUCTURE.md` — read it; the project is already provisioned and verified.

## Global Constraints

Every task's requirements implicitly include this section.

- **Runtime AI is Google Cloud only.** Gemini via `google-adk` / `google-genai`. No other AI APIs, models, or frameworks anywhere in the project.
- **Parallel Search API must be called at runtime** via the official `parallel-web` SDK in `star/tools/parallel_search.py`. Do not modify or stub that file.
- **New code only, authored in-window.** Contest began 2026-07-27. Never copy code from `writer-studio-template` or any pre-existing project.
- **All runtime dependencies are pinned exactly** in `pyproject.toml`. A Cloud Run build installs fresh and would otherwise take whatever shipped that morning. Add `firebase-admin==7.5.0` in the same exact-pin style.
- **No build step in `web/`.** Native ES modules only.
- **Never commit `.env`.** `GOOGLE_API_KEY` and `PARALLEL_API_KEY` are secrets. `FIREBASE_API_KEY` is **not** — it is a public browser-facing project identifier and is safe in client code.
- **Commit style matches the repo:** sentence-case imperative subject lines, not Conventional Commits.
- **`star/ledger.py` and `star/findings.py` are pure** — no I/O, no network, no model calls. Do not import Firestore or auth into either.
- **The four researchers share session state under `ParallelAgent`.** Never introduce a single shared accumulating state key; per-category keys only.
- The suite is at 67 passing with 7 pre-existing third-party deprecation warnings. `ruff check star tests scripts` reports exactly 1 finding, `BLE001` at `star/server.py`, which is deliberate and tracked. Do not fix either; do not add new ones.

## Cloud facts (already provisioned, verified 2026-08-09)

| | |
| --- | --- |
| Project ID | `star-research-dept` |
| Project number | `390753828501` |
| Firestore | Native mode, location `nam5`, live |
| Anonymous auth | enabled and verified end to end |
| Env vars, already in `.env` | `GOOGLE_CLOUD_PROJECT`, `FIREBASE_PROJECT_ID`, `FIREBASE_API_KEY`, `FIREBASE_AUTH_DOMAIN`, `FIREBASE_APP_ID` |

Local credentials come from Application Default Credentials, already present at
`%APPDATA%\gcloud\application_default_credentials.json`. On Cloud Run the
default service account supplies them instead — that difference is exactly why
the deploy task follows this one immediately.

---

### Task 1: Token verification

Splits into a pure header parser and a thin verifier, so the part most likely to be wrong is tested without a network.

**Files:**

- Create: `star/auth.py`
- Create: `tests/test_auth.py`
- Modify: `pyproject.toml` (add `firebase-admin==7.5.0` to `dependencies`)

**Interfaces:**

- Consumes: nothing from earlier tasks.
- Produces:
  - `extract_bearer(header: str | None) -> str | None` — pure
  - `verify_token(header: str | None) -> str | None` — returns a uid, or None for any failure
  - `AuthError` is **not** used; this module never raises on bad input, it returns None. Callers decide the HTTP consequence.

- [ ] **Step 1: Add the dependency**

In `pyproject.toml`, add to `dependencies`, keeping the exact-pin style:

```toml
    "firebase-admin==7.5.0",
```

Run: `.venv/Scripts/python.exe -m pip install -e ".[dev]"`
Expected: `firebase-admin` and its transitive `google-cloud-firestore` install.

- [ ] **Step 2: Write the failing tests**

`tests/test_auth.py`:

```python
from unittest import mock

from star.auth import extract_bearer, verify_token


def test_extract_bearer_pulls_the_token():
    assert extract_bearer("Bearer abc.def.ghi") == "abc.def.ghi"


def test_extract_bearer_is_case_insensitive_on_the_scheme():
    assert extract_bearer("bearer abc.def.ghi") == "abc.def.ghi"


def test_extract_bearer_tolerates_extra_whitespace():
    assert extract_bearer("  Bearer   abc.def.ghi  ") == "abc.def.ghi"


def test_extract_bearer_rejects_a_missing_header():
    assert extract_bearer(None) is None
    assert extract_bearer("") is None


def test_extract_bearer_rejects_the_wrong_scheme():
    assert extract_bearer("Basic abc.def.ghi") is None
    assert extract_bearer("abc.def.ghi") is None


def test_extract_bearer_rejects_an_empty_credential():
    assert extract_bearer("Bearer ") is None
    assert extract_bearer("Bearer") is None


def test_verify_token_returns_the_uid_on_a_good_token():
    with mock.patch("star.auth._verify", return_value={"uid": "abc123"}):
        assert verify_token("Bearer good.token.here") == "abc123"


def test_verify_token_returns_none_when_firebase_rejects_it():
    with mock.patch("star.auth._verify", side_effect=ValueError("bad signature")):
        assert verify_token("Bearer bad.token.here") is None


def test_verify_token_returns_none_without_calling_firebase_on_a_bad_header():
    """A malformed header must not cost a network round trip."""
    with mock.patch("star.auth._verify") as verifier:
        assert verify_token("Basic nope") is None
        verifier.assert_not_called()


def test_verify_token_returns_none_when_the_claim_set_has_no_uid():
    with mock.patch("star.auth._verify", return_value={}):
        assert verify_token("Bearer good.token.here") is None
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_auth.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'star.auth'`

- [ ] **Step 4: Write the implementation**

`star/auth.py`:

```python
"""Firebase ID token verification.

The browser signs in anonymously and sends its ID token as a bearer
credential. This module turns that header into a uid, or into None. It never
raises on bad input: a forged token and a missing header are the same
non-event, and the caller decides the HTTP consequence.

Header parsing is separated from verification so the parsing — the part most
likely to be subtly wrong — is testable without a network.
"""

import os

import firebase_admin
from firebase_admin import auth as firebase_auth
from firebase_admin import credentials

_app: firebase_admin.App | None = None


def _get_app() -> firebase_admin.App:
    """Initialize lazily; Application Default Credentials locally, the
    service account on Cloud Run."""
    global _app
    if _app is None:
        project = os.environ.get("FIREBASE_PROJECT_ID") or os.environ.get(
            "GOOGLE_CLOUD_PROJECT"
        )
        _app = firebase_admin.initialize_app(
            credentials.ApplicationDefault(), {"projectId": project}
        )
    return _app


def _verify(token: str) -> dict:
    """Seam for tests. Real verification hits Google's public certs."""
    return firebase_auth.verify_id_token(token, app=_get_app())


def extract_bearer(header: str | None) -> str | None:
    """Pull the credential out of an Authorization header. Pure."""
    if not header:
        return None
    parts = header.strip().split()
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1]:
        return None
    return parts[1]


def verify_token(header: str | None) -> str | None:
    """Return the caller's uid, or None if the header is absent or invalid."""
    token = extract_bearer(header)
    if token is None:
        return None
    try:
        claims = _verify(token)
    except Exception:
        # Forged, expired, malformed, or the cert fetch failed. All the same
        # answer to the caller: we do not know who this is.
        return None
    uid = claims.get("uid")
    return uid or None
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_auth.py -v`
Expected: PASS, 10 tests.

- [ ] **Step 6: Run the whole suite**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: PASS, 77 tests.

- [ ] **Step 7: Commit**

```bash
git add star/auth.py tests/test_auth.py pyproject.toml
git commit -m "Verify Firebase ID tokens into a uid"
```

---

### Task 2: Room documents and the Firestore adapter

Document shaping is pure and tested hard. Only a thin adapter touches the network, mirroring the ledger/findings split that worked in Phase 1.

**Files:**

- Create: `star/store.py`
- Create: `tests/test_store.py`

**Interfaces:**

- Consumes: nothing from Task 1.
- Produces:
  - `room_to_document(run_id: str, result: dict, status: str, created_at: str) -> dict` — pure
  - `document_to_room(doc: dict) -> dict` — pure
  - `room_summary(doc: dict) -> dict` — pure; the shape the project rail lists
  - `RoomStore` with `save(uid, run_id, document)`, `get(uid, run_id) -> dict | None`, `list_rooms(uid) -> list[dict]`, `mark_interrupted(uid, run_id)`
  - `RoomStore(client=...)` accepts an injected client so tests never touch the network.

**Why a fake client and not the Firestore emulator:** the emulator needs a Java runtime and a second process, which is a moving part this project does not otherwise have twelve days from a deploy. The tradeoff is that a fake proves the adapter's logic, not Firestore's behavior — so Task 5 runs one real round trip against the live database to cover exactly that gap. Do not skip Task 5.

- [ ] **Step 1: Write the failing tests**

`tests/test_store.py`:

```python
from star.store import (
    RoomStore,
    document_to_room,
    room_summary,
    room_to_document,
)

RESULT = {
    "story_profile": {"title": "1962 Memphis", "era": "1960-1962", "genre": "Crime"},
    "research_plan": {"questions": []},
    "research_bible": "# Bible\n\nSome text.",
    "search_count": 14,
    "source_count": 106,
    "categories": {
        "setting": {
            "category": "setting",
            "markdown": "raw",
            "findings": [{"fact": "A fact", "citations": [], "unverified_urls": []}],
            "field_notes": "",
            "parse_rate": 1.0,
            "unverified_count": 0,
        }
    },
}


class _FakeDoc:
    def __init__(self, store, path):
        self._store, self._path = store, path

    def set(self, data):
        self._store.data[self._path] = data

    def update(self, patch):
        self._store.data.setdefault(self._path, {}).update(patch)

    def get(self):
        return _FakeSnapshot(self._store.data.get(self._path))


class _FakeSnapshot:
    def __init__(self, data):
        self._data = data

    @property
    def exists(self):
        return self._data is not None

    def to_dict(self):
        return self._data


class _FakeCollection:
    def __init__(self, store, prefix):
        self._store, self._prefix = store, prefix

    def document(self, doc_id):
        return _FakeDoc(self._store, f"{self._prefix}/{doc_id}")

    def collection(self, name):
        return _FakeCollection(self._store, f"{self._prefix}/{name}")

    def stream(self):
        depth = self._prefix.count("/") + 1
        for path, data in self._store.data.items():
            if path.startswith(self._prefix + "/") and path.count("/") == depth:
                yield _FakeSnapshot(data)


class _FakeClient:
    def __init__(self):
        self.data = {}

    def collection(self, name):
        return _FakeCollection(self, name)


def test_room_to_document_carries_the_fields_the_rail_and_room_need():
    doc = room_to_document("abc123", RESULT, "complete", "2026-08-09T12:00:00Z")

    assert doc["run_id"] == "abc123"
    assert doc["status"] == "complete"
    assert doc["created_at"] == "2026-08-09T12:00:00Z"
    assert doc["title"] == "1962 Memphis"
    assert doc["era"] == "1960-1962"
    assert doc["search_count"] == 14
    assert doc["research_bible"].startswith("# Bible")
    assert doc["categories"]["setting"]["parse_rate"] == 1.0


def test_room_to_document_survives_a_result_with_no_story_profile():
    """A run that errored before intake finished still has to persist."""
    doc = room_to_document("abc123", {"search_count": 0}, "error", "2026-08-09T12:00:00Z")

    assert doc["title"] == "Untitled room"
    assert doc["status"] == "error"
    assert doc["categories"] == {}


def test_document_to_room_round_trips_the_api_payload():
    doc = room_to_document("abc123", RESULT, "complete", "2026-08-09T12:00:00Z")

    room = document_to_room(doc)

    assert room["story_profile"]["title"] == "1962 Memphis"
    assert room["research_bible"].startswith("# Bible")
    assert room["categories"]["setting"]["findings"][0]["fact"] == "A fact"
    assert room["search_count"] == 14


def test_room_summary_is_small_enough_for_a_rail():
    doc = room_to_document("abc123", RESULT, "complete", "2026-08-09T12:00:00Z")

    summary = room_summary(doc)

    assert summary == {
        "run_id": "abc123",
        "title": "1962 Memphis",
        "era": "1960-1962",
        "status": "complete",
        "created_at": "2026-08-09T12:00:00Z",
        "search_count": 14,
    }
    assert "research_bible" not in summary
    assert "categories" not in summary


def test_save_and_get_round_trip_per_user():
    store = RoomStore(client=_FakeClient())
    doc = room_to_document("abc123", RESULT, "complete", "2026-08-09T12:00:00Z")

    store.save("uid-one", "abc123", doc)

    assert store.get("uid-one", "abc123")["title"] == "1962 Memphis"


def test_one_user_cannot_read_another_users_room():
    store = RoomStore(client=_FakeClient())
    doc = room_to_document("abc123", RESULT, "complete", "2026-08-09T12:00:00Z")
    store.save("uid-one", "abc123", doc)

    assert store.get("uid-two", "abc123") is None


def test_get_returns_none_for_an_unknown_room():
    store = RoomStore(client=_FakeClient())
    assert store.get("uid-one", "does-not-exist") is None


def test_list_rooms_returns_summaries_newest_first():
    store = RoomStore(client=_FakeClient())
    store.save("uid-one", "old", room_to_document("old", RESULT, "complete", "2026-08-01T00:00:00Z"))
    store.save("uid-one", "new", room_to_document("new", RESULT, "complete", "2026-08-09T00:00:00Z"))

    rooms = store.list_rooms("uid-one")

    assert [r["run_id"] for r in rooms] == ["new", "old"]
    assert "research_bible" not in rooms[0]


def test_list_rooms_is_empty_for_a_new_user():
    store = RoomStore(client=_FakeClient())
    assert store.list_rooms("nobody") == []


def test_mark_interrupted_moves_a_stuck_run_off_running():
    store = RoomStore(client=_FakeClient())
    store.save("uid-one", "abc123", room_to_document("abc123", RESULT, "running", "2026-08-09T12:00:00Z"))

    store.mark_interrupted("uid-one", "abc123")

    assert store.get("uid-one", "abc123")["status"] == "interrupted"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_store.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'star.store'`

- [ ] **Step 3: Write the implementation**

`star/store.py`:

```python
"""Firestore persistence. The only module in the project that touches it.

Document shaping is pure and lives at the top of this file; the RoomStore
adapter underneath is a thin wrapper over the client so the shaping can be
tested without a network. The server owns all access — the browser never
talks to Firestore directly, which leaves exactly one security boundary to
get right instead of two.

Schema:
    /users/{uid}/rooms/{run_id}
"""

import os

_UNTITLED = "Untitled room"


def room_to_document(run_id: str, result: dict, status: str, created_at: str) -> dict:
    """Shape a finished run into its stored document. Pure."""
    result = result or {}
    profile = result.get("story_profile") or {}
    return {
        "run_id": run_id,
        "status": status,
        "created_at": created_at,
        "title": profile.get("title") or _UNTITLED,
        "era": profile.get("era") or "",
        "genre": profile.get("genre") or "",
        "story_profile": profile,
        "research_plan": result.get("research_plan"),
        "research_bible": result.get("research_bible") or "",
        "search_count": result.get("search_count") or 0,
        "source_count": result.get("source_count") or 0,
        "categories": result.get("categories") or {},
    }


def document_to_room(doc: dict) -> dict:
    """Rebuild the API's room payload from a stored document. Pure."""
    doc = doc or {}
    return {
        "story_profile": doc.get("story_profile") or {},
        "research_plan": doc.get("research_plan"),
        "research_bible": doc.get("research_bible") or "",
        "search_count": doc.get("search_count") or 0,
        "source_count": doc.get("source_count") or 0,
        "categories": doc.get("categories") or {},
    }


def room_summary(doc: dict) -> dict:
    """The small shape the project rail lists. Pure.

    Deliberately excludes the bible and the categories: a rail listing twenty
    rooms should not carry twenty research bibles across the wire.
    """
    doc = doc or {}
    return {
        "run_id": doc.get("run_id"),
        "title": doc.get("title") or _UNTITLED,
        "era": doc.get("era") or "",
        "status": doc.get("status") or "unknown",
        "created_at": doc.get("created_at") or "",
        "search_count": doc.get("search_count") or 0,
    }


class RoomStore:
    """Reads and writes rooms under /users/{uid}/rooms/{run_id}."""

    def __init__(self, client=None) -> None:
        self._client = client

    @property
    def client(self):
        if self._client is None:
            from google.cloud import firestore

            self._client = firestore.Client(
                project=os.environ.get("GOOGLE_CLOUD_PROJECT")
            )
        return self._client

    def _rooms(self, uid: str):
        return self.client.collection("users").document(uid).collection("rooms")

    def save(self, uid: str, run_id: str, document: dict) -> None:
        self._rooms(uid).document(run_id).set(document)

    def get(self, uid: str, run_id: str) -> dict | None:
        snapshot = self._rooms(uid).document(run_id).get()
        return snapshot.to_dict() if snapshot.exists else None

    def list_rooms(self, uid: str) -> list[dict]:
        docs = [s.to_dict() for s in self._rooms(uid).stream() if s.exists]
        docs.sort(key=lambda d: d.get("created_at") or "", reverse=True)
        return [room_summary(d) for d in docs]

    def mark_interrupted(self, uid: str, run_id: str) -> None:
        """A run left 'running' with no live task did not survive a restart."""
        self._rooms(uid).document(run_id).update({"status": "interrupted"})
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_store.py -v`
Expected: PASS, 10 tests.

- [ ] **Step 5: Run the whole suite**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: PASS, 87 tests.

- [ ] **Step 6: Commit**

```bash
git add star/store.py tests/test_store.py
git commit -m "Persist rooms to Firestore under a per-user path"
```

---

### Task 3: Wire auth and persistence into the server

**Files:**

- Modify: `star/server.py`
- Modify: `tests/test_server.py`

**Interfaces:**

- Consumes: `verify_token` from Task 1; `RoomStore`, `room_to_document`, `document_to_room` from Task 2.
- Produces:
  - `GET /api/rooms` → `{"rooms": [<summary>, ...]}` for the authenticated uid
  - `POST /api/rooms` → unchanged shape, now requires auth
  - `GET /api/rooms/{run_id}` → unchanged shape, now scoped to the caller's uid and falling back to Firestore when the run is not in memory
  - `_require_uid(authorization: str | None) -> str` — raises `HTTPException(401)` when the token is absent or invalid

**On degradation:** the spec says auth failure degrades to an ephemeral session rather than killing the app. That degradation lives in the **browser** (Task 4), which keeps working without persistence. The server stays strict: no valid token, no data. A server that guessed at identity would be a security hole wearing a UX costume.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_server.py`:

```python
from unittest import mock

AUTH = {"Authorization": "Bearer good.token.here"}


def test_api_rejects_a_request_with_no_token():
    client = TestClient(server.app)
    assert client.get("/api/rooms").status_code == 401


def test_api_rejects_a_forged_token():
    client = TestClient(server.app)
    with mock.patch("star.server.verify_token", return_value=None):
        assert client.get("/api/rooms", headers=AUTH).status_code == 401


def test_list_rooms_returns_only_the_callers_rooms():
    client = TestClient(server.app)
    fake_store = mock.Mock()
    fake_store.list_rooms.return_value = [{"run_id": "abc", "title": "1962 Memphis"}]

    with (
        mock.patch("star.server.verify_token", return_value="uid-one"),
        mock.patch("star.server._store", fake_store),
    ):
        response = client.get("/api/rooms", headers=AUTH)

    assert response.status_code == 200
    assert response.json()["rooms"][0]["run_id"] == "abc"
    fake_store.list_rooms.assert_called_once_with("uid-one")


def test_get_room_falls_back_to_firestore_when_not_in_memory():
    client = TestClient(server.app)
    fake_store = mock.Mock()
    fake_store.get.return_value = {
        "run_id": "persisted",
        "status": "complete",
        "story_profile": {"title": "1962 Memphis"},
        "research_bible": "# Bible",
        "search_count": 14,
        "categories": {},
    }

    with (
        mock.patch("star.server.verify_token", return_value="uid-one"),
        mock.patch("star.server._store", fake_store),
    ):
        response = client.get("/api/rooms/persisted", headers=AUTH)

    assert response.status_code == 200
    assert response.json()["result"]["story_profile"]["title"] == "1962 Memphis"
    fake_store.get.assert_called_once_with("uid-one", "persisted")


def test_get_room_404s_when_neither_memory_nor_firestore_has_it():
    client = TestClient(server.app)
    fake_store = mock.Mock()
    fake_store.get.return_value = None

    with (
        mock.patch("star.server.verify_token", return_value="uid-one"),
        mock.patch("star.server._store", fake_store),
    ):
        assert client.get("/api/rooms/nope", headers=AUTH).status_code == 404


def test_an_in_memory_run_is_not_readable_by_a_different_uid():
    """Memory must be scoped by uid too, not just Firestore."""
    client = TestClient(server.app)
    server._runs["owned"] = {
        "events": [], "status": "complete", "search_count": 1,
        "ledger": SourceLedger(), "result": {"research_bible": "x"}, "uid": "uid-one",
    }
    fake_store = mock.Mock()
    fake_store.get.return_value = None

    with (
        mock.patch("star.server.verify_token", return_value="uid-two"),
        mock.patch("star.server._store", fake_store),
    ):
        assert client.get("/api/rooms/owned", headers=AUTH).status_code == 404

    del server._runs["owned"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_server.py -v`
Expected: FAIL — `/api/rooms` returns 404 (route does not exist) rather than 401.

- [ ] **Step 3: Add the imports, store, and auth dependency**

In `star/server.py`, with the other late imports:

```python
from star.auth import verify_token  # noqa: E402
from star.store import RoomStore, document_to_room, room_to_document  # noqa: E402
```

Below `_CATEGORY_BY_AUTHOR`:

```python
_store = RoomStore()


def _require_uid(authorization: str | None) -> str:
    """Every /api route is scoped to a caller. No token, no data."""
    uid = verify_token(authorization)
    if uid is None:
        raise HTTPException(401, "Sign-in required.")
    return uid
```

Add `Header` to the FastAPI import line:

```python
from fastapi import FastAPI, Header, HTTPException  # noqa: E402
```

- [ ] **Step 4: Persist on completion and record the owner**

In `create_room`, add `"uid": uid,` to the `_runs[run_id]` dict literal.

In `_execute`, immediately after `run["status"] = "complete"`, add:

```python
        _store.save(
            run["uid"],
            run_id,
            room_to_document(
                run_id, run["result"], "complete", datetime.now(timezone.utc).isoformat()
            ),
        )
```

And in the `except` block, after `run["status"] = "error"`, add:

```python
        try:
            _store.save(
                run["uid"],
                run_id,
                room_to_document(
                    run_id, run.get("result"), "error",
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
        except Exception:
            pass  # a failed run that also fails to persist is still a failed run
```

Add at the top of the standard-library imports:

```python
from datetime import datetime, timezone
```

- [ ] **Step 5: Add the routes**

Change the three endpoint signatures to take auth and rewrite `get_room`:

```python
@app.post("/api/rooms")
async def create_room(req: RoomRequest, authorization: str | None = Header(None)) -> dict:
    uid = _require_uid(authorization)
    treatment = req.treatment.strip()
    if len(treatment) < 40:
        raise HTTPException(400, "Give the research department a bit more to work with.")
    if len(treatment) > config.max_treatment_chars():
        raise HTTPException(
            400,
            f"Treatments are capped at {config.max_treatment_chars()} characters — "
            "send the department a treatment, not the novel.",
        )
    ...
```

Only the first line is new. Every validation line below it is exactly what is already there — reproduced so you can see where `_require_uid` slots in, not so you retype it. The length checks must run **after** the auth check, so an unauthenticated caller learns nothing about the service's limits.

```python
@app.get("/api/rooms")
async def list_rooms(authorization: str | None = Header(None)) -> dict:
    uid = _require_uid(authorization)
    return {"rooms": _store.list_rooms(uid)}


@app.get("/api/rooms/{run_id}")
async def get_room(run_id: str, authorization: str | None = Header(None)) -> dict:
    uid = _require_uid(authorization)

    run = _runs.get(run_id)
    if run is not None and run.get("uid") == uid:
        return {"status": run["status"], "result": run["result"]}

    document = _store.get(uid, run_id)
    if document is None:
        raise HTTPException(404, "Unknown run")

    # Stored as running but absent from memory: the in-flight asyncio task did
    # not survive a restart, and nothing will ever finish it. Say so once
    # rather than letting the UI spin forever.
    if document.get("status") == "running":
        _store.mark_interrupted(uid, run_id)
        document["status"] = "interrupted"

    return {"status": document.get("status", "complete"), "result": document_to_room(document)}
```

Add the covering test to `tests/test_server.py`:

```python
def test_a_run_stored_as_running_but_absent_from_memory_becomes_interrupted():
    """The asyncio task did not survive a restart; the UI must stop spinning."""
    client = TestClient(server.app)
    fake_store = mock.Mock()
    fake_store.get.return_value = {
        "run_id": "stuck", "status": "running", "story_profile": {},
        "research_bible": "", "search_count": 0, "categories": {},
    }

    with (
        mock.patch("star.server.verify_token", return_value="uid-one"),
        mock.patch("star.server._store", fake_store),
    ):
        response = client.get("/api/rooms/stuck", headers=AUTH)

    assert response.json()["status"] == "interrupted"
    fake_store.mark_interrupted.assert_called_once_with("uid-one", "stuck")
```

**Note on the SSE route:** leave `GET /api/rooms/{run_id}/events` without the auth dependency. `EventSource` cannot send an Authorization header, and inventing a token-in-query-string scheme here would put credentials in access logs. The stream carries only progress events — agent names, search objectives, counts — never the research payload, which stays behind the authenticated `GET /api/rooms/{run_id}`. Tightening this belongs with the Cloud Run H3 guards.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_server.py -v`
Expected: PASS.

- [ ] **Step 7: Run the whole suite and the linter**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: PASS, 93 tests.

Run: `.venv/Scripts/python.exe -m ruff check star tests scripts`
Expected: exactly 1 finding, the tracked `BLE001`.

- [ ] **Step 8: Commit**

```bash
git add star/server.py tests/test_server.py
git commit -m "Scope every room to an authenticated uid and persist it"
```

---

### Task 4: Browser anonymous sign-in

No SDK and no CDN: Identity Toolkit's REST endpoints do anonymous sign-in and refresh in about forty lines, which sidesteps vendoring a library the spec defers to Phase 3 anyway.

**Files:**

- Create: `web/auth.js`
- Create: `web/config.js`
- Modify: `web/app.js`
- Modify: `web/index.html`
- Modify: `star/server.py` (serve `web/config.js` with values from the environment)

**Interfaces:**

- Consumes: the API contract from Task 3 — all `/api/*` calls need `Authorization: Bearer <idToken>`.
- Produces:
  - `getIdToken(): Promise<string|null>` — signs in on first call, refreshes when stale, returns null if sign-in fails
  - `authedFetch(url, options): Promise<Response>` — `fetch` with the bearer header attached
  - `isEphemeral(): boolean` — true when sign-in failed and nothing will persist

- [ ] **Step 1: Serve the browser config from the environment**

`web/config.js` must not be a committed file with a baked-in key, because the same file has to work in local dev and on Cloud Run. Add a route to `star/server.py`, **above** the static mount at the bottom of the file:

```python
@app.get("/config.js")
async def browser_config() -> Response:
    """The Firebase web key is a public project identifier, not a secret."""
    payload = {
        "apiKey": os.environ.get("FIREBASE_API_KEY", ""),
        "projectId": os.environ.get("FIREBASE_PROJECT_ID", ""),
    }
    return Response(
        f"export const FIREBASE = {json.dumps(payload)};",
        media_type="application/javascript",
    )
```

Add `Response` to the FastAPI responses import:

```python
from fastapi.responses import Response, StreamingResponse  # noqa: E402
```

Add `import os` to the standard-library imports if it is not already there.

Do **not** create a `web/config.js` file on disk; the route supplies it.

- [ ] **Step 2: Write the auth module**

`web/auth.js`:

```javascript
// Anonymous identity, no SDK.
//
// Identity Toolkit's REST endpoints do anonymous sign-up and token refresh
// directly, which keeps the browser free of a vendored library and of any
// CDN request. The refresh token lives in localStorage so a returning writer
// keeps the same uid and therefore the same rooms.
//
// The Firebase API key here is a public project identifier, not a secret.
// Security comes from the ID token the server verifies.

import { FIREBASE } from "/config.js";

const STORE_KEY = "star_refresh_token";
const SIGNUP = "https://identitytoolkit.googleapis.com/v1/accounts:signUp";
const REFRESH = "https://securetoken.googleapis.com/v1/token";

let idToken = null;
let expiresAt = 0;
let ephemeral = false;

export function isEphemeral() {
  return ephemeral;
}

async function signUpAnonymously() {
  const res = await fetch(`${SIGNUP}?key=${FIREBASE.apiKey}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ returnSecureToken: true }),
  });
  if (!res.ok) throw new Error("anonymous sign-in failed");
  return res.json();
}

async function refresh(refreshToken) {
  const res = await fetch(`${REFRESH}?key=${FIREBASE.apiKey}`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: `grant_type=refresh_token&refresh_token=${encodeURIComponent(refreshToken)}`,
  });
  if (!res.ok) throw new Error("token refresh failed");
  const data = await res.json();
  return { idToken: data.id_token, refreshToken: data.refresh_token, expiresIn: data.expires_in };
}

function remember(token, refreshToken, expiresIn) {
  idToken = token;
  // Refresh a minute early rather than racing the expiry.
  expiresAt = Date.now() + (Number(expiresIn) - 60) * 1000;
  if (refreshToken) localStorage.setItem(STORE_KEY, refreshToken);
}

export async function getIdToken() {
  if (idToken && Date.now() < expiresAt) return idToken;

  try {
    const stored = localStorage.getItem(STORE_KEY);
    if (stored) {
      const r = await refresh(stored);
      remember(r.idToken, r.refreshToken, r.expiresIn);
      return idToken;
    }
  } catch {
    // A stale or revoked refresh token: fall through and start fresh.
    localStorage.removeItem(STORE_KEY);
  }

  try {
    const fresh = await signUpAnonymously();
    remember(fresh.idToken, fresh.refreshToken, fresh.expiresIn);
    ephemeral = false;
    return idToken;
  } catch {
    ephemeral = true;
    return null;
  }
}

export async function authedFetch(url, options = {}) {
  const token = await getIdToken();
  const headers = { ...(options.headers || {}) };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  return fetch(url, { ...options, headers });
}
```

- [ ] **Step 3: Use it in the app and show the degradation banner**

In `web/index.html`, change the app script tag to a module and add a banner element directly after the opening `<body>` tag:

```html
  <div id="ephemeral-banner" class="banner hidden">
    Working without an account. This room will not be saved.
  </div>
```

Change the script tag at the bottom to:

```html
  <script type="module" src="/app.js"></script>
```

In `web/app.js`, add at the top:

```javascript
import { authedFetch, isEphemeral } from "/auth.js";
```

Replace the two `fetch(` calls in `buildRoom` and `showResults` with `authedFetch(`, then add this at the end of `buildRoom`'s successful start, right after `addEntry("done", "Treatment received. The department is assembling.")`:

```javascript
  if (isEphemeral()) $("ephemeral-banner").classList.remove("hidden");
```

In `web/styles.css`, append:

```css
.banner {
  background: #3a2f16;
  color: var(--accent);
  border-bottom: 1px solid var(--panel-edge);
  padding: 0.6rem 1.5rem;
  font-size: 0.9rem;
  text-align: center;
}
```

- [ ] **Step 4: Verify by hand**

Run: `.venv/Scripts/python.exe -m uvicorn star.server:app --port 8000`

Open `http://localhost:8000`, then in the browser devtools console confirm:

- `localStorage.getItem("star_refresh_token")` returns a token after the page loads and a build starts
- the Network tab shows `POST /api/rooms` carrying an `Authorization: Bearer` header
- no request goes to any CDN

Expected: a room builds exactly as before, and reloading the page keeps the same `star_refresh_token`.

- [ ] **Step 5: Commit**

```bash
git add web/auth.js web/app.js web/index.html web/styles.css star/server.py
git commit -m "Sign in anonymously in the browser and send the token"
```

---

### Task 5: Live round trip against real Firestore

Covers exactly what the fake client in Task 2 cannot: that Firestore itself behaves as the adapter assumes.

**Files:**

- Create: `scripts/verify_persistence.py`

**Interfaces:**

- Consumes: `RoomStore`, `room_to_document`, `room_summary` from Task 2; `verify_token` from Task 1.
- Produces: nothing the app imports. This is an operator script.

- [ ] **Step 1: Write the script**

`scripts/verify_persistence.py`:

```python
"""Round-trip a room through the real Firestore database.

The store's unit tests use a fake client, which proves the adapter's logic
and nothing about Firestore. This closes that gap. Writes to a throwaway uid
and deletes it afterwards.

Run from the repo root:
    .venv/Scripts/python.exe scripts/verify_persistence.py
"""

import os
import sys

from dotenv import load_dotenv

load_dotenv()

from star.store import RoomStore, room_summary, room_to_document  # noqa: E402

UID = "verify-throwaway-uid"
RESULT = {
    "story_profile": {"title": "1962 Memphis", "era": "1960-1962", "genre": "Crime"},
    "research_bible": "# Bible\n\nStax operated from a converted theater.",
    "search_count": 14,
    "source_count": 106,
    "categories": {"setting": {"parse_rate": 1.0, "findings": [], "unverified_count": 0}},
}


def main() -> int:
    print("project:", os.environ.get("GOOGLE_CLOUD_PROJECT"))
    store = RoomStore()

    doc = room_to_document("verify-run", RESULT, "complete", "2026-08-09T12:00:00Z")
    store.save(UID, "verify-run", doc)
    print("wrote /users/%s/rooms/verify-run" % UID)

    got = store.get(UID, "verify-run")
    assert got is not None, "read back nothing"
    assert got["title"] == "1962 Memphis", got.get("title")
    assert got["categories"]["setting"]["parse_rate"] == 1.0
    print("read back OK, title =", got["title"])

    rooms = store.list_rooms(UID)
    assert any(r["run_id"] == "verify-run" for r in rooms), rooms
    assert "research_bible" not in rooms[0], "summary leaked the bible"
    print("list_rooms OK,", len(rooms), "room(s), summary shape correct")

    store.mark_interrupted(UID, "verify-run")
    assert store.get(UID, "verify-run")["status"] == "interrupted"
    print("mark_interrupted OK")

    assert store.get("someone-else", "verify-run") is None
    print("cross-user read correctly returns None")

    store.client.collection("users").document(UID).collection("rooms").document(
        "verify-run"
    ).delete()
    print("cleaned up")

    print("\nround trip complete against real Firestore")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run it**

Run: `.venv/Scripts/python.exe scripts/verify_persistence.py`
Expected: every line prints OK and it ends with "round trip complete against real Firestore".

**If it fails with a credentials error**, Application Default Credentials are missing or point at the wrong project. Check `gcloud auth application-default login` and that `GOOGLE_CLOUD_PROJECT=star-research-dept` is set in `.env`. Do not paper over this by falling back to a fake client — the whole point of this task is touching the real database.

- [ ] **Step 3: Run the whole suite and the linter**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: PASS, 93 tests.

Run: `.venv/Scripts/python.exe -m ruff check star tests scripts`
Expected: exactly 1 finding, the tracked `BLE001`.

- [ ] **Step 4: Commit**

```bash
git add scripts/verify_persistence.py
git commit -m "Verify the Firestore round trip against the live database"
```

---

## Done when

- A visitor gets an anonymous uid silently, with no click and no CDN request.
- `POST /api/rooms` and `GET /api/rooms/{id}` reject an absent or forged token with 401.
- One user cannot read another's room, in memory or in Firestore.
- A completed room survives a page reload and appears in `GET /api/rooms`.
- `scripts/verify_persistence.py` passes against the real database.
- 93 tests pass; ruff reports exactly the tracked `BLE001`.

## Not in this phase

- The room UI, the project rail's visual design, and `CategoryPanel`. Phase 3.
- Vendoring `marked` and `DOMPurify`. Phase 3.
- The SSE `seq` field. Phase 3.
- Firestore security rules. The server owns all access and the browser holds no Firestore credentials, so rules are defence in depth rather than the boundary. They belong with the Cloud Run hardening.
- Rate limiting and the daily run cap. Cloud Run H3 guards.
- Script Check. Phase 4.
