"""The agent door: MCP Streamable HTTP, hand-written against the transport spec.

Three modules, split by what each one is allowed to touch.

  protocol.py  Pure. Envelope, classification, version negotiation, error
               objects. No FastAPI, no store, no network, so the conformance
               surface is testable with nothing running.
  tools.py     What the department tells an agent it can do, and the dispatch
               onto the four callables star/server.py injects.
  router.py    The HTTP edge: bearer auth, Origin, method, status codes.

No dependency is added for any of it. spec.md's Decision 1 gives four reasons
in descending weight; the shortest form is that a tools-only server needs
`initialize`, `notifications/initialized`, `ping`, `tools/list`, `tools/call`,
a 405 on GET, a 202 on notifications, an Origin check, and version
negotiation — and SSE and sessions are both explicitly optional, so that is
the whole surface.

This package is listed by name in pyproject.toml's `[tool.setuptools]
packages`, which is an EXPLICIT list rather than `find`. Dropping that line
keeps a source checkout working and makes the deployed image 500 on import,
because `pip install .` inside the Cloud Build silently omits a package the
list does not name.
"""
