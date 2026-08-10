"""Drive one persona at the agent door with Gemini, and write down what happened.

    .venv/Scripts/python.exe -m harness.run writer --token-file <path>

Runtime AI is Google Cloud only, here as everywhere: the loop below is
`google-genai` against the same pinned Gemini model `star/config.py` names for
the pipelines, and there is no second provider anywhere in this directory.

The loop is deliberately the plainest possible one — list the tools, hand them
to the model, execute what it calls, hand the answers back, stop when it stops
calling — because the harness is an instrument and an instrument that is clever
measures itself. Everything interesting is in what the department says back.

Three things this file is strict about:

  · **The turn cap is hard.** A persona that loops is a finding, not a failure,
    and it stops at the cap with the loop recorded rather than running until
    something else stops it.
  · **The spend guard is the harness's, not the department's.** `check_scene`
    and `build_room` cost real money against a cap the live demo shares
    (`spec.md > Open issues` #7). A call over a persona's allowance is never
    sent, and the transcript labels it a harness block so it can never be read
    as something the service said.
  · **The token is never written down.** It goes into one header inside
    `harness/client.py`; every transcript is passed through `redact` on the way
    to disk, so a secret cannot reach a committed file even by accident.
"""

import argparse
import json
import pathlib
import sys
import time
from dataclasses import dataclass, field

from dotenv import load_dotenv
from google import genai
from google.genai import types

from harness import personas
from harness.client import Exchange, McpClient, redact, tool_text, was_refused
from star import config

RUNS_DIR = pathlib.Path(__file__).resolve().parent / "runs"

# How much of one tool response is reproduced in the transcript. Every response
# on this door leads with a plain-language line and puts the JSON after it
# (star/mcp/tools.py's `_payload`), so this keeps all of the prose and cuts the
# data — and the true size is printed next to every cut, because a room payload
# turning out to be enormous is exactly what `spec.md > Open issues` #5 is
# asking about and a transcript that quietly hid it would be useless.
TRANSCRIPT_CHARS = 2000

# The generic tool the `passthrough` wiring hands a persona instead of the real
# schemas. It takes the arguments as a STRING on purpose: a model given a typed
# object schema is fenced into the right shape by the API, and the whole point
# of that persona is to find out what happens when nothing fences it.
PASSTHROUGH = types.FunctionDeclaration(
    name="star_call",
    description=(
        "Send one call to the STAR tool server and return its raw answer. "
        "Nothing checks the arguments before they are sent."
    ),
    parameters_json_schema={
        "type": "object",
        "properties": {
            "tool_name": {
                "type": "string",
                "description": "the name of the tool on the server",
            },
            "arguments_json": {
                "type": "string",
                "description": (
                    "the arguments for that tool, written as a JSON object in "
                    "a string, for example {\"some_argument\": \"a value\"}"
                ),
            },
        },
        "required": ["tool_name", "arguments_json"],
    },
)


@dataclass
class Attempt:
    """One thing the model tried to do, and what came of it."""

    turn: int
    tool: str
    arguments: object
    sent: bool
    answer: str
    exchange: Exchange | None = None
    note: str = ""


@dataclass
class Run:
    persona: personas.Persona
    model: str
    base_url: str
    started_at: str
    handshake: list[Exchange] = field(default_factory=list)
    narration: list[tuple[int, str]] = field(default_factory=list)
    attempts: list[Attempt] = field(default_factory=list)
    final_report: str = ""
    stopped_because: str = ""
    elapsed_seconds: int = 0


# --- Translating the department's tools into something a model can call ------


def declarations(tools: list[dict]) -> list[types.FunctionDeclaration]:
    """`tools/list` as `FunctionDeclaration`s, schema and description intact.

    `parameters_json_schema` takes the tool's `inputSchema` unchanged rather
    than rebuilding it as a `types.Schema`, so the shape a model is held to is
    the one the department published. A rebuild would be a second copy of the
    contract living in the client, which is the drift `star/mcp/tools.py`
    already refuses to allow between a description and a refusal.

    A tool with no arguments is declared with no parameters at all. Sending an
    empty object instead reads to the API as "an object with unknown
    properties", and `list_rooms` genuinely takes nothing.
    """
    declared = []
    for tool in tools:
        schema = tool.get("inputSchema") or {}
        declared.append(
            types.FunctionDeclaration(
                name=tool["name"],
                description=tool.get("description") or "",
                parameters_json_schema=schema if schema.get("properties") else None,
            )
        )
    return declared


def _text_of(content: types.Content | None) -> str:
    """Whatever the model said in words, thoughts left out."""
    if content is None or not content.parts:
        return ""
    said = [
        part.text
        for part in content.parts
        if getattr(part, "text", None) and not getattr(part, "thought", False)
    ]
    return "\n".join(said).strip()


# --- Executing one call the model asked for ----------------------------------


def _resolve(persona: personas.Persona, call) -> tuple[str, object, str]:
    """What tool the model actually asked for, and with what arguments.

    Returns `(tool_name, arguments, refusal)`. `refusal` is non-empty only when
    the harness could not send anything at all, which on the passthrough wiring
    means the model wrote something that was not a JSON object — a real failure
    mode of that integration shape, and one the department never sees.
    """
    arguments = dict(call.args or {})
    if persona.wiring != "passthrough":
        return call.name, arguments, ""
    if call.name != PASSTHROUGH.name:
        return call.name, arguments, ""

    tool = str(arguments.get("tool_name") or "").strip()
    written = arguments.get("arguments_json")
    if written in (None, ""):
        return tool, {}, ""
    try:
        parsed = json.loads(written)
    except (TypeError, json.JSONDecodeError):
        return tool, written, (
            "[harness] Nothing was sent: `arguments_json` was not valid JSON, "
            "so there was no object to put on the wire."
        )
    if not isinstance(parsed, dict):
        return tool, parsed, (
            "[harness] Nothing was sent: `arguments_json` parsed to "
            f"{type(parsed).__name__}, and a tool call's arguments must be a "
            "JSON object."
        )
    return tool, parsed, ""


def execute(
    run: Run, turn: int, client: McpClient, call, spent: dict[str, int]
) -> Attempt:
    """Run one model-requested call through the guard and onto the wire."""
    persona = run.persona
    tool, arguments, refusal = _resolve(persona, call)

    if refusal:
        return Attempt(turn, tool, arguments, False, refusal, note="unsendable")

    allowance = persona.budget.allowance(tool)
    if allowance is not None and spent.get(tool, 0) >= allowance:
        # Never sent, and labelled so it cannot be mistaken for the department
        # refusing. Written in the second person because the model reads it and
        # has to be able to act on it.
        blocked = (
            f"[harness] This call was not sent. `{tool}` spends real money on "
            "live web searches, and this run is allowed "
            f"{allowance} such call{'' if allowance == 1 else 's'}, which it "
            "has already made. This is the harness stopping you, not the "
            "server. Carry on with the calls that cost nothing, or stop and "
            "report."
        )
        return Attempt(turn, tool, arguments, False, blocked, note="budget-blocked")

    exchange = client.call_tool(tool, arguments if isinstance(arguments, dict) else {})
    # Charged after the fact, and only when the department took the call.
    # Charging on the attempt is the obvious way to write this and it is wrong
    # in the case that matters most here: a persona that misnames an argument
    # is refused before the pipeline is reached, spends nothing, and would
    # still have burned the one call it was going to get right on the retry.
    # The first fumbler run did exactly that, and the persona filled the gap by
    # writing verdicts off the research bible instead — which is the unearned
    # confidence this whole project is built to refuse.
    if allowance is not None and not was_refused(exchange):
        spent[tool] = spent.get(tool, 0) + 1
    return Attempt(turn, tool, arguments, True, tool_text(exchange), exchange=exchange)


# --- The loop ----------------------------------------------------------------


def drive(persona: personas.Persona, client: McpClient, model: str, base_url: str) -> Run:
    run = Run(
        persona=persona,
        model=model,
        base_url=base_url,
        started_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    )
    started = time.monotonic()

    handshake = client.initialize()
    run.handshake.append(handshake)
    # The 202 for `notifications/initialized`, recorded because a zero-byte
    # body is a conformance fact and an empty line in a log otherwise.
    run.handshake.append(client.exchanges[-1])
    tools = client.list_tools()
    run.handshake.append(client.exchanges[-1])

    if persona.wiring == "passthrough":
        declared = [PASSTHROUGH]
    else:
        declared = declarations(tools)

    ai = genai.Client()
    # Not named `config`. `star.config` is imported at the top of this module
    # and shadowing it inside the one function that drives the loop is a bug
    # waiting for someone to add a line that needs the other one.
    settings = types.GenerateContentConfig(
        system_instruction=persona.system,
        tools=[types.Tool(function_declarations=declared)],
    )
    contents = [types.Content(role="user", parts=[types.Part(text=persona.opening)])]
    spent: dict[str, int] = {}

    for turn in range(1, persona.max_turns + 1):
        answer = ai.models.generate_content(
            model=model, contents=contents, config=settings
        )
        candidate = answer.candidates[0] if answer.candidates else None
        content = candidate.content if candidate else None
        said = _text_of(content)
        if said:
            run.narration.append((turn, said))
        if content is not None:
            contents.append(content)

        calls = answer.function_calls or []
        if not calls:
            run.final_report = said
            run.stopped_because = "the persona stopped calling tools and reported"
            break

        replies = []
        for call in calls:
            attempt = execute(run, turn, client, call, spent)
            run.attempts.append(attempt)
            replies.append(
                types.Part(
                    function_response=types.FunctionResponse(
                        name=call.name, response={"output": attempt.answer}
                    )
                )
            )
        contents.append(types.Content(role="user", parts=replies))
    else:
        run.stopped_because = (
            f"the turn cap of {persona.max_turns} was reached with the persona "
            "still calling tools"
        )
        run.final_report = run.narration[-1][1] if run.narration else ""

    run.elapsed_seconds = int(time.monotonic() - started)
    return run


# --- The transcript ----------------------------------------------------------


def _clip(text: str) -> str:
    if len(text) <= TRANSCRIPT_CHARS:
        return text
    return (
        text[:TRANSCRIPT_CHARS]
        + f"\n\n[... clipped in this transcript at {TRANSCRIPT_CHARS} characters. "
        f"The full response text was {len(text)} characters.]"
    )


def _fence(text: str) -> str:
    return "```text\n" + _clip(text).rstrip() + "\n```"


def transcript(run: Run) -> str:
    persona = run.persona
    lines = [
        f"# Persona run — {persona.name}",
        "",
        f"- **Persona:** `{persona.slug}` — {persona.posture}",
        f"- **Wiring:** `{persona.wiring}` — "
        + (
            "the real `inputSchema` from `tools/list`, handed to the model as "
            "function declarations."
            if persona.wiring == "declared"
            else "one generic passthrough call; the model writes its own "
            "argument JSON and nothing checks it before it is sent."
        ),
        f"- **Account:** `{persona.account}`",
        f"- **Driven by:** `{run.model}` via `google-genai`. No other provider.",
        (
            f"- **Endpoint:** `{run.base_url}/mcp`, bearer "
            "`star_<token_id>.<redacted>`"
        ),
        f"- **Started:** {run.started_at} · ran {run.elapsed_seconds}s",
        (
            f"- **Turn cap:** {persona.max_turns} · **spend allowance:** "
            f"`build_room` {persona.budget.build_room}, `check_scene` "
            f"{persona.budget.check_scene}"
        ),
        "",
        "## Handshake",
        "",
        "| Call | HTTP | Response bytes | ms |",
        "| --- | --- | --- | --- |",
    ]
    for exchange in run.handshake:
        lines.append(
            f"| `{exchange.label}` | {exchange.status} | "
            f"{exchange.response_bytes:,} | {exchange.elapsed_ms} |"
        )

    initialize = run.handshake[0]
    result = (initialize.response or {}).get("result") or {}
    lines += [
        "",
        (
            f"`protocolVersion` **{result.get('protocolVersion')}**, `serverInfo` "
            f"`{json.dumps(result.get('serverInfo'))}`, `capabilities` "
            f"`{json.dumps(result.get('capabilities'))}`, `instructions` "
            f"{len(str(result.get('instructions') or ''))} characters."
        ),
        "",
        "## The run",
        "",
    ]

    turns = sorted(
        {turn for turn, _ in run.narration} | {item.turn for item in run.attempts}
    )
    for turn in turns:
        lines.append(f"### Turn {turn}")
        lines.append("")
        for narrated, said in run.narration:
            if narrated == turn and said:
                lines += ["> " + said.replace("\n", "\n> "), ""]
        for attempt in run.attempts:
            if attempt.turn != turn:
                continue
            arguments = json.dumps(attempt.arguments, ensure_ascii=False)
            if len(arguments) > 400:
                arguments = arguments[:400] + f"… [{len(arguments)} characters]"
            lines += [
                f"**Called `{attempt.tool}`** with `{arguments}`",
                "",
            ]
            if attempt.exchange is not None:
                lines.append(
                    f"HTTP {attempt.exchange.status} · "
                    f"{attempt.exchange.response_bytes:,} bytes · "
                    f"{attempt.exchange.elapsed_ms} ms"
                )
            else:
                lines.append(f"_Not sent — {attempt.note}._")
            lines += ["", _fence(attempt.answer), ""]

    lines += [
        "## How it ended",
        "",
        f"Stopped because {run.stopped_because}.",
        "",
    ]
    last_said = run.narration[-1][1] if run.narration else ""
    if run.final_report and run.final_report != last_said:
        lines += ["The persona's own closing report:", "", _fence(run.final_report), ""]
    elif run.final_report:
        lines += [
            (
                "Its closing report is the last thing it said above, in turn "
                f"{run.narration[-1][0]}."
            ),
            "",
        ]

    sent = [item for item in run.attempts if item.sent]
    blocked = [item for item in run.attempts if not item.sent]
    spending = ", ".join(
        f"`{tool}` {sum(1 for item in sent if item.tool == tool)}"
        for tool in ("build_room", "check_scene")
    )
    returned = sum(exchange.response_bytes for exchange in run.handshake) + sum(
        item.exchange.response_bytes for item in sent if item.exchange
    )
    lines += [
        "## What this run cost",
        "",
        f"- Model turns: {len(turns)} of a permitted {persona.max_turns}.",
        f"- Tool calls sent: {len(sent)}. Not sent: {len(blocked)}.",
        f"- Spending calls sent: {spending}.",
        f"- Bytes returned by the department across the whole run: {returned:,}.",
        "",
        "| Call | HTTP | Response bytes | ms |",
        "| --- | --- | --- | --- |",
    ]
    for attempt in sent:
        if attempt.exchange is None:
            continue
        lines.append(
            f"| `{attempt.tool}` | {attempt.exchange.status} | "
            f"{attempt.exchange.response_bytes:,} | {attempt.exchange.elapsed_ms} |"
        )
    lines.append("")
    return redact("\n".join(lines))


# --- Entry point -------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("persona", choices=sorted(personas.BY_SLUG))
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--token-file",
        required=True,
        help="a file holding one bearer token. Never passed on the command line.",
    )
    parser.add_argument("--out", default=None, help="where to write the transcript")
    arguments = parser.parse_args(argv)

    # Before anything reads an environment variable. The API key for the model
    # lives in `.env`, and a script in this repo that skips this step has been
    # wrong before — see process-notes.md on the token that resolved perfectly
    # against the wrong Firestore project.
    load_dotenv()

    persona = personas.BY_SLUG[arguments.persona]
    token = pathlib.Path(arguments.token_file).read_text(encoding="utf-8").strip()
    if not token:
        print("The token file is empty.", file=sys.stderr)
        return 2

    client = McpClient(base_url=arguments.base_url, token=token)
    run = drive(persona, client, config.fast_model(), arguments.base_url)

    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    out = pathlib.Path(arguments.out) if arguments.out else RUNS_DIR / f"{persona.slug}.md"
    out.write_text(transcript(run), encoding="utf-8")
    print(f"{persona.slug}: {len(run.attempts)} calls, wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
