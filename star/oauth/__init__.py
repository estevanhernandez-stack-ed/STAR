"""The OAuth 2.1 authorization server, as protocol and nothing else.

Six modules, no FastAPI, no routes, and no import of star/server.py. Every
function here maps an argument onto a decision or onto a document, which is
what lets the whole authorization surface be tested with no server running, no
client registered, and no network reachable. star/mcp/protocol.py already takes
this shape and for the same reason; `spec-oauth-as.md` is the brief.

  · metadata.py   the two discovery documents, and the WWW-Authenticate
                  challenge that points a client at the first of them
  · pkce.py       S256, and the refusal of everything else
  · codes.py      authorization codes: single-use, 60 seconds, bounded
  · clients.py    registration by both routes, and the SSRF guard that makes
                  one of them safe to offer
  · tokens.py     issuance and rotation on star/tokens.py's existing shape
  · validate.py   the resource-server side: expiry, audience, scope

Nothing in this package imports anything else in it except metadata, pkce, and
star.tokens, so the dependency arrows all point one way. star/tokens.py never
imports back.

This package must be listed in pyproject.toml's `[tool.setuptools] packages`.
That list is explicit rather than `find`, and the comment there records what
happens to a package omitted from it: the local venv keeps working because it
resolves off the source tree, and the deployed image 500s on the first import.
"""
