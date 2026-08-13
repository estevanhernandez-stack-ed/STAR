"""A filed sweep as a spreadsheet, without becoming a program.

WHY A ROW PER SOURCE. A claim with three citations is three rows sharing a
claim, not one row with three urls crammed into a cell. A writer opening this
wants to filter on a domain, sort by verdict, and count how much of a draft
rests on one site — none of which a packed cell allows. A claim with NO source
still gets a row, because a claim nobody could answer is exactly the row a
reader is looking for.

FORMULA INJECTION IS THE REAL RISK HERE, and it is not hypothetical. Every cell
in this file is either a writer's own scene text or an excerpt from the open
web, and both flow into a spreadsheet that will happily execute a cell opening
`=`, `+`, `-`, `@`, or a tab or carriage return. Excel and Sheets have both
shipped remote-data-exfiltration through exactly this. A leading apostrophe
neutralises it and survives a round trip, which is what item 4 needs.

WHAT THIS FILE DOES NOT DO. It never re-verifies, never re-orders a claim
against its verdict, and never drops a claim it cannot make sense of. The
export is a view of a filed sweep; a sweep is the record.
"""

import csv
import io

# What a spreadsheet treats as the start of a formula, plus the two whitespace
# characters that let an attacker push a formula past a naive prefix check.
_DANGEROUS = ("=", "+", "-", "@", "\t", "\r")

COLUMNS = (
    "scenes",
    "claim",
    "claim_type",
    "verdict",
    "note",
    "source_title",
    "source_url",
    "source_excerpt",
    "swept_at",
    "sweep_id",
)


def safe_cell(value: object) -> str:
    """One cell, as text a spreadsheet will not run.

    Prefixed with an apostrophe rather than escaped or stripped: stripping
    would edit a writer's own line, and this file is read beside the draft it
    came from. The apostrophe is the convention every spreadsheet understands
    as "this is text", and `star/exports.py`'s importer knows to take it off
    again, so a value survives the round trip unchanged.
    """
    text = "" if value is None else str(value)
    return f"'{text}" if text.startswith(_DANGEROUS) else text


def sweep_rows(document: dict) -> list[dict]:
    """A filed sweep, flattened. Pure.

    One row per claim per source; one row for a claim with none. `scenes` is a
    space-separated list rather than a comma one, because the file is
    comma-delimited and a reader should not have to think about which commas
    are data.
    """
    document = document or {}
    swept_at = str(document.get("created_at") or "")
    sweep_id = str(document.get("sweep_id") or "")
    rows: list[dict] = []

    for claim in document.get("claims") or []:
        claim = claim or {}
        base = {
            "scenes": " ".join(str(s) for s in (claim.get("scenes") or [])),
            "claim": claim.get("text") or "",
            "claim_type": claim.get("claim_type") or "",
            "verdict": claim.get("verdict") or "",
            "note": claim.get("note") or "",
            "swept_at": swept_at,
            "sweep_id": sweep_id,
        }
        citations = claim.get("citations") or []
        if not citations:
            rows.append({**base, "source_title": "", "source_url": "", "source_excerpt": ""})
            continue
        for citation in citations:
            citation = citation or {}
            rows.append(
                {
                    **base,
                    "source_title": citation.get("title") or "",
                    "source_url": citation.get("url") or "",
                    "source_excerpt": citation.get("excerpt") or "",
                }
            )
    return rows


def sweep_to_csv(document: dict) -> str:
    """A filed sweep as CSV text.

    `csv.writer` does the quoting and the embedded newlines, because a claim is
    an exact quotation from a draft and will contain commas, quotes and line
    breaks — and hand-rolled quoting is how one of them ends up shifting every
    column after it.

    `\\r\\n` line endings: RFC 4180 says so and Excel on Windows is the reader
    this is most likely to meet.
    """
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=COLUMNS, lineterminator="\r\n")
    writer.writeheader()
    for row in sweep_rows(document):
        writer.writerow({key: safe_cell(row.get(key)) for key in COLUMNS})
    return buffer.getvalue()


def unsafe_cell(value: object) -> str:
    """The inverse of `safe_cell`, for a file coming back in.

    One leading apostrophe comes off, and only one. A writer whose line
    genuinely begins with an apostrophe — `'61 Impala` is the obvious one in a
    period script — must not have it eaten on every round trip, so this removes
    the prefix only where the character after it is one this file would have
    escaped.
    """
    text = "" if value is None else str(value)
    if text.startswith("'") and text[1:2].startswith(_DANGEROUS):
        return text[1:]
    return text


# What an import is allowed to bring back. Deliberately short: a writer's
# decisions, and nothing the department said.
WRITER_COLUMNS = ("writer_note", "dismissed")

# What it may never bring back, named individually so the refusal can say which
# one was attempted rather than "some column".
DEPARTMENT_COLUMNS = ("verdict", "note", "source_title", "source_url", "source_excerpt")

_TRUE = {"1", "true", "yes", "y", "x", "dismissed"}


def read_annotations(text: str) -> tuple[dict[str, dict], list[str]]:
    """A returned CSV, reduced to the writer's own marks. Pure.

    Returns `{claim_text: {writer_note, dismissed}}` and a list of complaints.

    IT NEVER CARRIES A VERDICT, A SOURCE OR AN EXCERPT BACK IN, and that is the
    whole shape of this feature rather than a validation nicety. Those are the
    department's, hydrated out of a ledger, and the one thing that must stay
    impossible is a room reading as better-sourced than its research made it. A
    row that edited one is refused BY NAME so a writer knows which column was
    dropped rather than wondering why their change did nothing.

    Rows are matched on claim text, not row order: a spreadsheet gets sorted,
    and a writer who sorted by verdict before annotating would otherwise have
    their notes land on the wrong claims.

    A row matching nothing is reported rather than dropped. Silence here would
    let a writer annotate twenty claims, import, and find nineteen — with no
    way to learn which.
    """
    complaints: list[str] = []
    annotations: dict[str, dict] = {}

    try:
        rows = list(csv.DictReader(io.StringIO(text or "")))
    except csv.Error as exc:  # pragma: no cover - csv rarely raises on read
        return {}, [f"That file could not be read as CSV: {exc}"]

    if not rows:
        return {}, ["That file has no rows under its header."]

    header = set(rows[0].keys())
    if "claim" not in header:
        return {}, [
            (
                "That file has no `claim` column, so there is no way to tell "
                "which claim a row belongs to. Export a sweep and annotate "
                "that file."
            )
        ]

    for number, row in enumerate(rows, start=2):
        claim = unsafe_cell(row.get("claim")).strip()
        if not claim:
            complaints.append(f"Row {number} names no claim and was skipped.")
            continue

        edited = [
            column
            for column in DEPARTMENT_COLUMNS
            if column in row and unsafe_cell(row.get(column)).strip()
        ]
        note = unsafe_cell(row.get("writer_note")).strip()
        dismissed = unsafe_cell(row.get("dismissed")).strip().casefold() in _TRUE

        if not note and not dismissed:
            continue

        # Present and non-empty is not the same as CHANGED — an unmodified
        # export carries every one of these — so the refusal fires only when a
        # row also brings something of the writer's. The department's columns
        # are then ignored rather than the row being thrown away, and the
        # sentence names them.
        if edited:
            complaints.append(
                f"Row {number} carries {', '.join(edited)}, which the department "
                "writes and an import never changes. The note was kept; those "
                "columns were ignored."
            )

        existing = annotations.setdefault(claim, {"writer_note": "", "dismissed": False})
        if note and note not in existing["writer_note"]:
            # A claim is several rows when it has several sources, and a writer
            # may have annotated more than one of them. Joined rather than
            # last-wins, because a note they typed is a note they meant.
            existing["writer_note"] = f"{existing['writer_note']} {note}".strip()
        existing["dismissed"] = existing["dismissed"] or dismissed

    return annotations, complaints


def apply_annotations(document: dict, annotations: dict[str, dict]) -> tuple[dict, list[str]]:
    """A filed sweep with the writer's marks on it. Pure.

    Returns the new document and the claim texts that matched nothing.

    Verdicts, notes and citations are copied through untouched. The only fields
    this writes are `writer_note` and `dismissed`, which exist nowhere in what
    the department produced and cannot be mistaken for it.
    """
    document = dict(document or {})
    wanted = dict(annotations or {})
    claims = []

    for claim in document.get("claims") or []:
        claim = dict(claim or {})
        mark = wanted.pop(str(claim.get("text") or "").strip(), None)
        if mark:
            claim["writer_note"] = mark.get("writer_note") or ""
            claim["dismissed"] = bool(mark.get("dismissed"))
        claims.append(claim)

    document["claims"] = claims
    return document, sorted(wanted)


# A ROOM's own research, which is a different question from a sweep's answers.
# A sweep says what a draft claimed and how it held up; this says what the
# department found, which is the thing a writer actually paid for and the thing
# they want when somebody asks "where is your research".
ROOM_COLUMNS = (
    "drawer",
    "fact",
    "source_title",
    "source_url",
    "source_excerpt",
    "retrieved_at",
    "requisition",
    "room",
    "era",
    "run_id",
)


def room_rows(result: dict, run_id: str = "") -> list[dict]:
    """A room's findings, flattened. One row per finding per source. Pure.

    Same shape as `sweep_rows` and for the same reason: a writer wants to
    filter on a domain and count how much of a room rests on one site, and a
    cell holding three urls allows neither. A finding with no source still gets
    a row, because a fact nobody could cite is exactly the row worth finding.

    `retrieved_at` is the finding's own where it has one and the room's
    otherwise — the rule web/clip.js applies to the RET stamp. A finding
    requisitioned after the build was retrieved when it was asked for, and
    stamping the room's date on it would be a fabricated provenance claim in a
    column somebody will sort by.

    `requisition` carries the question a writer asked to put the finding there,
    empty for everything the build filed. It is how a reader tells research
    that was commissioned from research that was planned.
    """
    result = result or {}
    profile = result.get("story_profile") or {}
    room = profile.get("title") or "Untitled room"
    era = profile.get("era") or ""
    built = str(result.get("created_at") or "")
    rows: list[dict] = []

    for drawer, doc in (result.get("categories") or {}).items():
        for finding in (doc or {}).get("findings") or []:
            finding = finding or {}
            base = {
                "drawer": drawer,
                "fact": finding.get("fact") or "",
                "retrieved_at": str(finding.get("retrieved_at") or "").strip() or built,
                "requisition": finding.get("requisition") or "",
                "room": room,
                "era": era,
                "run_id": run_id,
            }
            citations = finding.get("citations") or []
            if not citations:
                rows.append(
                    {**base, "source_title": "", "source_url": "", "source_excerpt": ""}
                )
                continue
            for citation in citations:
                citation = citation or {}
                rows.append(
                    {
                        **base,
                        "source_title": citation.get("title") or "",
                        "source_url": citation.get("url") or "",
                        "source_excerpt": citation.get("excerpt") or "",
                    }
                )
    return rows


def room_to_csv(result: dict, run_id: str = "") -> str:
    """A room's research as CSV text.

    Every cell goes through `safe_cell` for the reason the sweep's do: a
    finding is a sentence a model wrote from pages off the open web, and an
    excerpt is those pages verbatim. Both land in a program that will run a
    cell opening `=`.
    """
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=ROOM_COLUMNS, lineterminator="\r\n")
    writer.writeheader()
    for row in room_rows(result, run_id):
        writer.writerow({key: safe_cell(row.get(key)) for key in ROOM_COLUMNS})
    return buffer.getvalue()


def chain_to_csv(rooms) -> str:
    """A whole story's research as one CSV. Pure.

    `rooms` is an iterable of `(run_id, result)`, nearest first — the order a
    check reads them in, so the room a writer opened is at the top of the file.

    THE `room` COLUMN IS WHAT MAKES THIS SAFE TO OFFER. Merging two rooms into
    one file is only useful if a reader can still tell them apart, and the whole
    reason `room_to_csv` stays narrow is that a writer's own research should not
    become indistinguishable from the room it follows. Every row already carries
    `room`, `era` and `run_id`, so this widens the reach without spending that:
    sort by `room` and the single-room file is back.

    Nothing is deduplicated across rooms. Two rooms citing one page is a fact
    about the research — it says a source is doing double duty — and collapsing
    the second row would hide it.
    """
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=ROOM_COLUMNS, lineterminator="\r\n")
    writer.writeheader()
    for run_id, result in rooms or ():
        for row in room_rows(result, run_id):
            writer.writerow({key: safe_cell(row.get(key)) for key in ROOM_COLUMNS})
    return buffer.getvalue()


def csv_filename(room_title: str, created_at: str, kind: str = "sweep") -> str:
    """A filename a writer can find again in a downloads folder.

    Built from the room and the date rather than the sweep id, because a reader
    looking for last Tuesday's sweep of the Doctor Who room is not looking for
    `sw_9f2c1a`. Reduced to characters every filesystem accepts.
    """
    stem = "".join(
        char if char.isalnum() or char in " -_" else " " for char in str(room_title or "")
    )
    stem = "-".join(stem.split()).strip("-").lower()
    day = str(created_at or "")[:10] or "undated"
    # No stem means no room title, and `sweep-sweep-undated.csv` is what a
    # default stem of "sweep" produces. The word appears once.
    return f"{stem}-{kind}-{day}.csv" if stem else f"{kind}-{day}.csv"
