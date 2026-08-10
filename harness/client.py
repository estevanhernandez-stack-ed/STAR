"""A minimal MCP client, built on the standard library and nothing else.

`urllib.request`, `json`, and `time`. No new dependency in `pyproject.toml`, no
third-party client, and nothing on screen that a Google-track submission has to
apologise for — `docs/HANDOFF.md:44` bars third-party logos and brands from the
video, and the MCP shot is this file in a terminal.

It is a client rather than a curl script because the point of the harness is to
find out what a *driven model* trips on. That needs three things a shell loop
does not give you: `tools/list` in a shape a model can be handed, a tool call
that comes back as text a model can read, and a record of every exchange
complete enough to audit afterwards. So every request and response is kept
(`exchanges`), with wall-clock time and the response's byte count, because
`spec.md > Open issues` #5 asks how big a room is over this door and the only
honest way to answer is to measure it.

Two rules this file will not bend:

  · The bearer token never appears in anything this module returns. It goes
    into one header and nowhere else; `redact` rewrites the secret half out of
    any string on the way to a transcript, and the recorded headers carry the
    redacted form rather than the real one.
  · A refusal is recorded, never raised. 401, 403, 405 and 400 all carry a
    JSON-RPC error body on this server, and that body is the thing being
    audited. Letting `urllib` raise on them would throw away the evidence.
"""

import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

# `star_<12 hex>.<32 hex>`, and only the second half is a credential. The id is
# kept on purpose: a transcript that says which token was in play is useful,
# and star/tokens.py already treats the id as an identifier that appears in
# paths and logs.
_TOKEN = re.compile(r"(star_[0-9a-f]{12})\.[0-9a-f]{32}")

# Long enough for `check_scene`, which is synchronous by design
# (spec.md's Decision 5) and runs under a 180s server-side ceiling. A client
# timeout under that would report a client failure for a server-side timeout
# and the transcript would blame the wrong side.
DEFAULT_TIMEOUT_SECONDS = 200


def redact(text: str) -> str:
    """Any bearer token in this string, with its secret half removed."""
    return _TOKEN.sub(r"\1.<redacted>", text)


@dataclass
class Exchange:
    """One request and what came back, kept for the transcript.

    `response_bytes` is the length of the body as it arrived on the wire, not
    the length of anything re-serialised afterwards. That is the number
    `spec.md > Open issues` #5 is about.
    """

    label: str
    request: dict | None
    status: int
    response: object
    response_bytes: int
    elapsed_ms: int
    body_text: str = ""
    note: str = ""


@dataclass
class McpClient:
    """One connection's worth of MCP, against one bearer token.

    Stateless on the wire — this server issues no session id and requires none
    — so the only state here is the negotiated protocol version and the record
    of what has been sent.
    """

    base_url: str
    token: str
    client_name: str = "star-persona-harness"
    client_version: str = "1.0"
    timeout: int = DEFAULT_TIMEOUT_SECONDS
    exchanges: list[Exchange] = field(default_factory=list)
    protocol_version: str | None = None
    _next_id: int = 1

    @property
    def endpoint(self) -> str:
        return f"{self.base_url.rstrip('/')}/mcp"

    def _headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {self.token}",
        }
        # Not sent on `initialize`, and that is the spec's own sequence rather
        # than an omission: the revision has not been agreed yet at that point.
        # star/mcp/protocol.py reads an absent header as 2025-03-26, which it
        # supports, so the handshake goes through and every later call carries
        # the version the server actually named.
        if self.protocol_version:
            headers["MCP-Protocol-Version"] = self.protocol_version
        return headers

    def _post(self, label: str, payload: dict) -> Exchange:
        """Send one JSON-RPC message and record everything about the answer."""
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.endpoint, data=data, headers=self._headers(), method="POST"
        )
        started = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                status = response.status
                raw = response.read()
        except urllib.error.HTTPError as refused:
            # The refusals are the evidence. 401, 403, 405 and 400 all carry a
            # JSON-RPC error object on this server, and it is the sentence in
            # that object the audit is about.
            status = refused.code
            raw = refused.read()
        elapsed_ms = int((time.monotonic() - started) * 1000)

        body_text = raw.decode("utf-8", "replace")
        if not raw:
            # A 202 with no body, which is what a POSTed notification gets.
            parsed: object = None
        else:
            try:
                parsed = json.loads(body_text)
            except json.JSONDecodeError:
                parsed = None

        exchange = Exchange(
            label=label,
            request=payload,
            status=status,
            response=parsed,
            response_bytes=len(raw),
            elapsed_ms=elapsed_ms,
            body_text=body_text,
        )
        self.exchanges.append(exchange)
        return exchange

    def _request(self, label: str, method: str, params: dict | None = None) -> Exchange:
        payload = {"jsonrpc": "2.0", "id": self._next_id, "method": method}
        if params is not None:
            payload["params"] = params
        self._next_id += 1
        return self._post(label, payload)

    def initialize(self) -> Exchange:
        """The handshake, then the notification that closes it.

        `notifications/initialized` carries no id, so it is a notification and
        the transport spec's answer to it is 202 with no body. Sending it is
        not decoration: a server that answered it with a result would be
        answering a message that has nothing to answer to, and the harness is
        here to check conformance as well as prose.
        """
        exchange = self._request(
            "initialize",
            "initialize",
            {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": self.client_name, "version": self.client_version},
            },
        )
        result = (exchange.response or {}).get("result") if exchange.response else None
        if isinstance(result, dict):
            version = result.get("protocolVersion")
            if isinstance(version, str):
                self.protocol_version = version
        self._post(
            "notifications/initialized",
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
        )
        return exchange

    def list_tools(self) -> list[dict]:
        exchange = self._request("tools/list", "tools/list")
        result = (exchange.response or {}).get("result") or {}
        return list(result.get("tools") or [])

    def call_tool(self, name: str, arguments: dict) -> Exchange:
        """One `tools/call`. The answer is returned whole, refusals included."""
        return self._request(
            f"tools/call {name}", "tools/call", {"name": name, "arguments": arguments}
        )

    def instructions(self) -> str:
        for exchange in self.exchanges:
            if exchange.label != "initialize":
                continue
            result = (exchange.response or {}).get("result") or {}
            return str(result.get("instructions") or "")
        return ""


def was_refused(exchange: Exchange) -> bool:
    """Did the department decline this call rather than carry it out?

    True for a `CallToolResult` carrying `isError`, for a JSON-RPC error
    object, and for any HTTP status that never produced either. It is what the
    runner's spend guard turns on: a refused call never reached a pipeline, so
    it bought no searches and must not cost a persona its allowance.

    One case this reads as a refusal after money was already spent: a
    `check_scene` that outruns the server's 180s ceiling comes back as a
    refusal having spent whatever it searched first. The turn cap is the
    backstop there, and a check that slow is itself worth seeing in a
    transcript.
    """
    payload = exchange.response
    if not isinstance(payload, dict):
        return True
    result = payload.get("result")
    if isinstance(result, dict):
        return bool(result.get("isError"))
    return True


def tool_text(exchange: Exchange) -> str:
    """What a calling model reads back, whichever way the call went.

    Three shapes arrive here and all three have to become text, because a model
    driving this loop has nowhere else to look:

      · A `CallToolResult`, success or `isError`, whose content is text parts.
      · A JSON-RPC error object, which is a client-level failure the server
        deliberately keeps separate from a tool-level one.
      · Neither, when the transport itself refused before any of that.

    The third case is the one worth being careful with. A 401 or a 403 is not
    a tool result and pretending it is would hide which layer said no, so it is
    labelled by status rather than flattened into the other two.
    """
    payload = exchange.response
    if isinstance(payload, dict):
        result = payload.get("result")
        if isinstance(result, dict):
            parts = [
                str(item.get("text") or "")
                for item in result.get("content") or []
                if isinstance(item, dict)
            ]
            text = "\n".join(part for part in parts if part)
            if result.get("isError"):
                return f"The call was refused. {text}".strip()
            return text or json.dumps(result, ensure_ascii=False)
        error = payload.get("error")
        if isinstance(error, dict):
            return (
                f"The server rejected the request itself (JSON-RPC error "
                f"{error.get('code')}): {error.get('message')}"
            )
    return (
        f"HTTP {exchange.status} with no readable JSON-RPC body: "
        f"{exchange.body_text[:400] or '(empty body)'}"
    )
