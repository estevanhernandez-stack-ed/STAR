"""Rewrite the bible of a room whose editor stopped partway, from its own findings.

THE DAMAGE. `max_output_tokens` on a thinking model bounds thinking PLUS
output, and thinking runs first, so a room with more research to weigh
deliberated longer, left less budget for the writing, and the bible stopped
mid-document reporting a normal finish. A fix shipped 2026-08-10 set
`thinking_budget=4000`, which is the Gemini 2.5 control that gemini-3.6-flash
ignores entirely, so bibles kept arriving in pieces for another day and a half
while the config said the problem was solved. The real fix — `thinking_level`,
not `thinking_budget` — landed in aa3a6ce on 2026-08-11 21:16. The full replay
is in star/config.py's synthesis_thinking_level.

So this repairs history and is not a workaround for a live defect. Measured
2026-08-12 across the sixteen stored rooms: every short bible was built before
that commit (the last at 12:41 that day) and every room built after it is 4 of
4. If a room built from here on comes back short, this script is the wrong
tool and star/agents/synthesis.py is the right place to look.

RUN 2026-08-12. Seven rooms, ten stored copies (three exist under two accounts
each, so both copies were repaired — one left short would still have been
readable). All ten came back 4 of 4 with a clean STOP, on 2,339-3,451 output
tokens against a 16,000 ceiling; the damage was never the ceiling, it was
thinking eating the budget beneath it. Lenin Shipyard went from 2,618
characters to 12,020. UNDER THE BRIDGE came back SHORTER, 12,714 to 11,286,
and is still the repair: three sections written long became four written
evenly, which is what a bible that reaches its end looks like next to one that
spent its budget before getting there. Zero live searches spent.

WHAT IT COSTS. One model call per room and NO live searches. The findings are
already filed, hydrated and paid for — only the document was missing, which is
the same argument star/server.py's `_salvage` makes for keeping a run that
died before synthesis.

WHAT IT WILL NOT DO. It refuses to write a room that does not come back
complete with a clean STOP: a bible repaired into a different wrong length is
worse than the damage, because the damage is at least legible in
`bible_coverage`. It keeps the old text in `research_bible_previous` rather
than dropping it, that being the only surviving evidence of what the defect
actually produced.

Run from the repo root, dry by default:

    .venv/Scripts/python.exe scripts/resynthesize_bibles.py
    .venv/Scripts/python.exe scripts/resynthesize_bibles.py --only 94a15bbca87e
    .venv/Scripts/python.exe scripts/resynthesize_bibles.py --write
"""

import argparse
import asyncio
import os

from dotenv import load_dotenv

load_dotenv()


from google.adk.runners import InMemoryRunner  # noqa: E402
from google.cloud import firestore  # noqa: E402
from google.genai import types  # noqa: E402

from star import bible  # noqa: E402
from star.agents.synthesis import synthesis_agent  # noqa: E402
from star.models import Category  # noqa: E402
from star.store import document_to_room  # noqa: E402

APP = "star-resynth"


def _safe(text: object) -> str:
    """Windows consoles are cp1252 and these rooms are full of Polish."""
    return str(text).encode("ascii", "replace").decode("ascii")


def findings_prose(drawer: dict | None) -> str:
    """Stored findings, back in the shape the researchers wrote them.

    `- <fact> :: <url>, <url>`, which is the format star/agents/researchers.py
    specifies and star/findings.py parses. Round-tripping through it means the
    editor reads what it read on the first pass rather than a second rendering
    invented here — the point of this script is to change the budget the
    editor had, and nothing else about the call.

    Excerpts are deliberately not reattached: the editor was never shown them.
    It gets facts and urls, and is told to cite only urls that appear in the
    findings, which is exactly what this rebuilds.
    """
    lines = []
    for finding in (drawer or {}).get("findings") or []:
        fact = str((finding or {}).get("fact") or "").strip()
        if not fact:
            continue
        urls = [
            str((citation or {}).get("url") or "").strip()
            for citation in (finding or {}).get("citations") or []
        ]
        urls = [url for url in urls if url]
        lines.append(f"- {fact} :: {', '.join(urls)}" if urls else f"- {fact}")
    return "\n".join(lines)


async def rewrite(room: dict) -> dict:
    """Run the editor over one room's stored findings."""
    state = {
        "story_profile": str(room.get("story_profile") or {}),
        "research_plan": str(room.get("research_plan") or {}),
    }
    categories = room.get("categories") or {}
    for category in Category:
        state[f"findings_{category.value}"] = findings_prose(
            categories.get(category.value)
        )

    runner = InMemoryRunner(agent=synthesis_agent, app_name=APP)
    session = await runner.session_service.create_session(
        app_name=APP, user_id="repair", state=state
    )

    text, reason, tokens = "", "", {}
    message = types.Content(role="user", parts=[types.Part(text="Write the bible.")])
    async for event in runner.run_async(
        user_id="repair", session_id=session.id, new_message=message
    ):
        finished = getattr(event, "finish_reason", None)
        if finished is not None:
            reason = getattr(finished, "name", str(finished))
        usage = getattr(event, "usage_metadata", None)
        if usage is not None:
            tokens = {
                "thinking": getattr(usage, "thoughts_token_count", None) or 0,
                "output": getattr(usage, "candidates_token_count", None) or 0,
            }
        for part in getattr(getattr(event, "content", None), "parts", None) or []:
            if getattr(part, "text", None):
                text += part.text

    return {"text": text.strip(), "reason": reason, "tokens": tokens}


def _targets(client, only: str | None) -> list:
    """Every complete room whose bible is short, one entry per stored copy.

    Per stored copy rather than per run_id: a room linked from an anonymous
    account exists under two user documents, and repairing one would leave the
    other short while both remain readable.
    """
    found = []
    for user in client.collection("users").list_documents():
        for ref in user.collection("rooms").list_documents():
            doc = ref.get().to_dict() or {}
            if doc.get("status") != "complete":
                continue
            if only and ref.id != only:
                continue
            room = document_to_room(doc)
            counts = bible.coverage(room) or {}
            if counts.get("missing") or counts.get("truncated"):
                found.append((ref, doc, room, counts))
    return found


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--write", action="store_true", help="persist changes (default: dry run)"
    )
    parser.add_argument("--only", help="repair a single run_id")
    args = parser.parse_args()

    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project:
        print("GOOGLE_CLOUD_PROJECT is unset — is .env present?")
        return 2

    client = firestore.Client(project=project)
    targets = _targets(client, args.only)
    if not targets:
        print("No short bibles found. Nothing to repair.")
        return 0

    print(f"{'WRITING' if args.write else 'DRY RUN'} - {len(targets)} stored copy(ies)\n")
    failures = 0
    for ref, doc, room, counts in targets:
        title = _safe(doc.get("title"))[:30]
        before = len(room.get("research_bible") or "")
        print(f"{ref.id}  {title:30} was {counts['covered']}/{counts['expected']} "
              f"({before} chars)")

        try:
            written = await rewrite(room)
        except Exception as exc:  # noqa: BLE001
            print(f"    FAILED {type(exc).__name__}: {_safe(exc)[:90]}\n")
            failures += 1
            continue

        after = bible.coverage({**room, "research_bible": written["text"]}) or {}
        whole = (
            after.get("covered") == after.get("expected")
            and written["reason"] == "STOP"
        )
        print(f"    -> {after.get('covered')}/{after.get('expected')} "
              f"({len(written['text'])} chars)  {written['reason']}  "
              f"thinking={written['tokens'].get('thinking')} "
              f"output={written['tokens'].get('output')}  "
              f"{'OK' if whole else 'STILL SHORT'}")

        if not whole:
            print("    not written: a bible repaired into a different wrong "
                  "length is worse than one whose damage is legible\n")
            failures += 1
            continue

        if args.write:
            ref.update({
                "research_bible_previous": room.get("research_bible") or "",
                "research_bible": written["text"],
                "bible_finish_reason": written["reason"],
                "bible_tokens": written["tokens"],
            })
            print("    written\n")
        else:
            print("    (dry run)\n")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
