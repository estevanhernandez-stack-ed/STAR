"""What a stranger gets from every /api route, discovered rather than listed.

`docs/smoke-2026-08-12.md` claimed "every new route answers 401 unauthenticated
on the live service", and it was false the day it was written. The suite tested
GETs. Six write routes took a Pydantic body, and FastAPI validates a body
before a handler runs — so an anonymous caller sending `{}` got a 422 naming
the field it was missing, on surfaces that spend a writer's money.

Nothing executed and nothing leaked but the shape of a request body, so the
severity is low. The class is not: it was the third passing test standing over
an unasserted outcome in the same build, and the smoke list confesses the first
two itself.

THE ROUTES ARE WALKED, NEVER LISTED. A list is a thing somebody has to remember
to add to, and the defect this file exists for is precisely a route that nobody
remembered. Every route the app declares is called here, so a new one is
covered by existing.
"""

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from star import server

# The one /api route that cannot read an Authorization header: an EventSource
# sends no custom headers. It is guarded by a per-run capability instead — see
# stream_events' own docstring, and `_require_uid`'s, which used to claim the
# universal this set exists to record.
EXEMPT = {"/api/rooms/{run_id}/events"}

# A body for every route that takes one, so the 422 this file is about cannot
# be what answers. Any route missing from here is called with `{}`, which is
# the anonymous-caller case and the one that used to leak.
BODIES: dict[str, dict] = {
    "/api/rooms": {"treatment": "x" * 400},
    "/api/rooms/{run_id}/sweep": {"scenes": [{"text": "INT. A\n\nOne."}]},
    "/api/rooms/import": {"csv": "fact\nx\n"},
    "/api/rooms/{run_id}/questions": {"question": "q", "category": "setting"},
    "/api/rooms/{run_id}/scenes": {"scene": "INT. A\n\nOne."},
    "/api/rooms/{run_id}/sweeps/{sweep_id}/annotations": {"csv": "claim\nx\n"},
}


def api_routes() -> list[tuple[str, str]]:
    """Every (method, path) under /api the app actually declares."""
    found = []
    for route in server.app.routes:
        if not isinstance(route, APIRoute) or not route.path.startswith("/api"):
            continue
        if route.path in EXEMPT:
            continue
        for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
            found.append((method, route.path))
    return sorted(found)


def a_url(path: str) -> str:
    return (
        path.replace("{run_id}", "some-room")
        .replace("{sweep_id}", "some-sweep")
        .replace("{scene_id}", "some-scene")
        .replace("{token_id}", "some-token")
    )


def test_there_are_routes_to_walk():
    """A guard on the walk itself. If `api_routes` ever returns nothing — a
    renamed prefix, a changed router class — every assertion below would pass
    against an empty list and this file would go quietly green forever."""
    routes = api_routes()
    assert len(routes) > 15, routes
    assert ("POST", "/api/rooms") in routes
    assert ("POST", "/api/rooms/import") in routes


@pytest.mark.parametrize(("method", "path"), api_routes())
def test_no_api_route_answers_a_stranger_with_its_schema(method, path):
    """401, and never 422.

    A 422 to an anonymous caller is a schema oracle: it names the field, its
    type and its location, for a route that would have refused them anyway. The
    fix is that auth is a dependency rather than a line inside the handler —
    FastAPI solves a dependant's dependencies before validating its own body
    params, so a raising one short-circuits. This asserts the outcome rather
    than the arrangement, so a future route that reads a header inside its
    handler fails here rather than shipping.
    """
    response = TestClient(server.app).request(method, a_url(path), json=BODIES.get(path, {}))

    assert response.status_code == 401, (
        f"{method} {path} answered {response.status_code} to a caller with no "
        f"token: {response.text[:200]}"
    )


@pytest.mark.parametrize(("method", "path"), api_routes())
def test_no_api_route_answers_a_stranger_with_a_body_it_cannot_read(method, path):
    """The same routes with a body they could never parse.

    The case above sends a VALID body, which proves auth runs at all. This
    sends a hostile one — an array where an object belongs — which proves auth
    runs FIRST. Both are needed: a route that validated the body and then
    checked auth would pass the first and fail this.
    """
    response = TestClient(server.app).request(method, a_url(path), json=[1, 2, 3])

    assert response.status_code == 401, (
        f"{method} {path} answered {response.status_code} to an anonymous "
        f"caller sending an unparseable body: {response.text[:200]}"
    )


def test_the_stream_is_exempt_because_it_cannot_read_a_header_at_all():
    """Named rather than silently skipped. An EventSource sends no custom
    headers, so this route is guarded by a per-run capability instead — and a
    reader auditing the auth posture should meet that fact here rather than
    conclude the route was forgotten."""
    declared = {route.path for route in server.app.routes if isinstance(route, APIRoute)}

    assert EXEMPT <= declared, "the exemption names a route that exists"
    for path in EXEMPT:
        assert "events" in path
