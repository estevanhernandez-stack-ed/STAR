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

from star.models import Category

# What a spreadsheet treats as the start of a formula, plus the two whitespace
# characters that let an attacker push a formula past a naive prefix check.
_DANGEROUS = ("=", "+", "-", "@", "\t", "\r")

COLUMNS = (
    # THE SCENE THIS ROW BELONGS TO, first because it is what a reader sorts and
    # filters on. `scenes` beside it is the claim's whole spread, which is a
    # different question — "where else does the draft say this" — and a packed
    # cell reading `13 17 19 20 21 23 24` can answer that one and neither
    # filters nor sorts.
    "scene",
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


def _scene_numbers(claim: dict) -> list[int]:
    """The scenes a claim was placed in, as numbers, deduplicated and ordered.

    Defensive about the type because this reads a STORED document: a sweep
    filed months ago by an older shape of `sweep.attach` is not something an
    export gets to crash on, and a scene number that will not parse is better
    dropped than raised.
    """
    found: list[int] = []
    for value in claim.get("scenes") or []:
        try:
            found.append(int(value))
        except (TypeError, ValueError):
            continue
    return sorted(dict.fromkeys(found))


def sweep_rows(document: dict) -> list[dict]:
    """A filed sweep, flattened into PAGE ORDER. Pure.

    One row per scene per claim per source. A claim the draft makes in three
    scenes is three rows, because the question a writer opens this file to ask
    is "what is wrong on page 14" — and a claim that answers that question only
    from inside a packed `13 17 19` cell does not answer it in a spreadsheet.
    Sorted by scene for the same reason: a script is read in page order and so
    is the report about it.

    `scenes` stays alongside, carrying the claim's whole spread. That is the
    other question — "where else does the draft say this" — and it is the one
    thing the split loses, so it is kept rather than replaced. Space-separated
    rather than comma, because the file is comma-delimited and a reader should
    not have to think about which commas are data.

    A claim the sweep could not place in any scene keeps its row with an empty
    `scene` and sorts to the end. Those are the ones the surface calls "checked
    but could not place", and dropping them here would quietly shrink the file
    against the count printed on the page it came from.

    Several rows for one claim is not new — a claim with three sources was
    always three rows — and `read_annotations` already joins a writer's marks
    across them rather than letting the last row win.
    """
    document = document or {}
    swept_at = str(document.get("created_at") or "")
    sweep_id = str(document.get("sweep_id") or "")
    # (unplaced?, scene, the claim's own order) — sorted at the end. Python's
    # sort is stable, so rows tying on all three stay in citation order.
    ordered: list[tuple[int, int, int, dict]] = []

    for order, claim in enumerate(document.get("claims") or []):
        claim = claim or {}
        numbers = _scene_numbers(claim)
        base = {
            "scenes": " ".join(str(number) for number in numbers),
            "claim": claim.get("text") or "",
            "claim_type": claim.get("claim_type") or "",
            "verdict": claim.get("verdict") or "",
            "note": claim.get("note") or "",
            "swept_at": swept_at,
            "sweep_id": sweep_id,
        }
        sources = [
            {
                "source_title": (citation or {}).get("title") or "",
                "source_url": (citation or {}).get("url") or "",
                "source_excerpt": (citation or {}).get("excerpt") or "",
            }
            for citation in claim.get("citations") or []
        ] or [{"source_title": "", "source_url": "", "source_excerpt": ""}]

        for number in numbers or [0]:
            for source in sources:
                ordered.append(
                    (
                        0 if numbers else 1,
                        number,
                        order,
                        {**base, "scene": str(number) if numbers else "", **source},
                    )
                )

    ordered.sort(key=lambda row: row[:3])
    return [row for *_, row in ordered]


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


def annotation_origin(text: str) -> str:
    """The sweep this file was exported from, or "" if it does not say.

    Every sweep export writes `sweep_id` into every row, and until now nothing
    read it back: the import matched claim text against whatever sweep happened
    to be open on screen. Import a sweep's export into a DIFFERENT sweep and it
    behaves exactly as designed and reads as broken — the claims that sweep
    does not raise come back "named a claim this sweep does not hold", and
    every row carrying the other sweep's sources is reported as though the
    writer had edited a citation.

    Measured on the live service 2026-08-13: a file from one sweep, opened
    against another, produced eight unmatched claims and six edit complaints,
    all of them true statements about the wrong pair of documents and not one
    of them the actual problem. The file knew. Nothing asked it.

    One id, not a set. A file whose rows disagree is not a sweep export, and
    the first row is the one to believe: it is the header's own neighbour and
    the last thing an editing spreadsheet reorders.
    """
    try:
        for row in csv.DictReader(io.StringIO(text or "")):
            return unsafe_cell(row.get("sweep_id")).strip()
    except csv.Error:  # pragma: no cover - csv rarely raises on read
        return ""
    return ""


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

        # WHAT THE ROW SAID THE DEPARTMENT SAID, carried rather than judged.
        # Judging it here is what this function got wrong: presence is not the
        # same as CHANGE, an unmodified export carries every one of these, and
        # this file has no copy of the sweep to compare against — so every
        # ordinary note on an untouched export raised "you tried to edit the
        # verdict". `apply_annotations` holds the sweep and does the comparing.
        sent = [
            (number, column, unsafe_cell(row.get(column)).strip())
            for column in DEPARTMENT_COLUMNS
            if column in row and unsafe_cell(row.get(column)).strip()
        ]
        note = unsafe_cell(row.get("writer_note")).strip()
        dismissed = unsafe_cell(row.get("dismissed")).strip().casefold() in _TRUE

        if not note and not dismissed:
            continue

        existing = annotations.setdefault(
            claim, {"writer_note": "", "dismissed": False, "sent": []}
        )
        existing["sent"].extend(sent)
        if note and note not in existing["writer_note"]:
            # A claim is several rows when it has several sources, and a writer
            # may have annotated more than one of them. Joined rather than
            # last-wins, because a note they typed is a note they meant.
            existing["writer_note"] = f"{existing['writer_note']} {note}".strip()
        existing["dismissed"] = existing["dismissed"] or dismissed

    return annotations, complaints


def _department_values(claim: dict, column: str) -> set[str]:
    """Everything the department actually wrote in one column of one claim.

    A set rather than a value, because a claim is several rows when it has
    several sources and each row carries a different one of them. A returned
    `source_url` is unchanged if it is ANY of the claim's urls — the writer may
    have sorted the file, and asking which row it came back on would make the
    answer depend on the sort.
    """
    if column in ("verdict", "note"):
        return {str(claim.get(column) or "").strip()}
    field = {"source_title": "title", "source_url": "url", "source_excerpt": "excerpt"}[column]
    return {str((citation or {}).get(field) or "").strip() for citation in claim.get("citations") or []}


def apply_annotations(
    document: dict, annotations: dict[str, dict]
) -> tuple[dict, list[str], list[str]]:
    """A filed sweep with the writer's marks on it. Pure.

    Returns the new document, the claim texts that matched nothing, and the
    complaints that could only be raised here.

    Verdicts, notes and citations are copied through untouched. The only fields
    this writes are `writer_note` and `dismissed`, which exist nowhere in what
    the department produced and cannot be mistaken for it.

    THE DEPARTMENT'S COLUMNS ARE JUDGED HERE rather than in `read_annotations`,
    because this is the first place that holds what the department actually
    said. Presence is not change: an unmodified export carries a verdict and a
    source on every row, and complaining about presence meant every ordinary
    note on an untouched file came back with "you tried to edit the verdict" —
    a surface crying wolf on its own happy path. A column is reported only when
    the value that came back is one the sweep never wrote.
    """
    document = dict(document or {})
    wanted = dict(annotations or {})
    complaints: list[str] = []
    claims = []

    for claim in document.get("claims") or []:
        claim = dict(claim or {})
        mark = wanted.pop(str(claim.get("text") or "").strip(), None)
        if mark:
            claim["writer_note"] = mark.get("writer_note") or ""
            claim["dismissed"] = bool(mark.get("dismissed"))
            # Grouped by row so a reader is sent to the line they typed on,
            # and sorted so two runs over one file read the same.
            changed: dict[int, list[str]] = {}
            for number, column, value in mark.get("sent") or []:
                if value not in _department_values(claim, column):
                    changed.setdefault(number, []).append(column)
            for number in sorted(changed):
                names = sorted(dict.fromkeys(changed[number]))
                complaints.append(
                    f"Row {number} changed {', '.join(names)}, which the department "
                    "writes and an import never changes. The note was kept; "
                    f"{'those columns were' if len(names) > 1 else 'that column was'} "
                    "ignored."
                )
        claims.append(claim)

    document["claims"] = claims
    return document, sorted(wanted), complaints


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
    # The room this one follows, by the SENDER'S id. Meaningless on its own in
    # anybody else's account — but when both rooms travel in one chain export,
    # the import remaps it onto the ids it just minted and the story arrives
    # linked. A chain that arrives as two unrelated rooms has lost the thing
    # the chain was built for.
    "continues",
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
                "continues": str(result.get("continues") or ""),
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


# The four drawers a room has. A row naming anything else is filed under the
# drawer it most nearly is, and told about — a room with a fifth drawer renders
# nowhere, and silently dropping the row would lose research the sender paid
# for. Imported from star.models so the names cannot drift from the ones the
# researchers, the bible and web/drawer.js all use.
_DRAWERS = {category.value for category in Category}
_DRAWER_ALIASES = {
    "objects": Category.OBJECTS_PROPS.value,
    "props": Category.OBJECTS_PROPS.value,
    "objects & props": Category.OBJECTS_PROPS.value,
    "objects and props": Category.OBJECTS_PROPS.value,
    "forces": Category.FORCES_CONFLICTS.value,
    "conflicts": Category.FORCES_CONFLICTS.value,
    "forces & conflicts": Category.FORCES_CONFLICTS.value,
    "forces and conflicts": Category.FORCES_CONFLICTS.value,
    "setting & atmosphere": Category.SETTING.value,
    "atmosphere": Category.SETTING.value,
}


def read_room(text: str) -> tuple[list[tuple[str, dict]], list[str]]:
    """A research export, rebuilt into rooms. Pure.

    Returns `[(sender_run_id, result), ...]` in the order the file lists them,
    and a list of complaints.

    THIS IS THE ONLY PATH BY WHICH A ROOM ENTERS AN ACCOUNT WITHOUT BEING
    RESEARCHED BY IT, and everything about the shape it returns follows from
    that. It carries findings, their sources, a title and an era, and nothing
    that would let the room claim work this account did not do: no search
    count, no bible, no field notes, no parse rate. The caller stamps it as
    imported; this function has no way to produce a room that could pass for a
    built one.

    Rows are grouped into rooms by `run_id`, falling back to `room` when a
    hand-built file has no ids in it. Findings are grouped within a room by
    (drawer, fact), so the several rows one finding occupies — one per source —
    come back as one finding with several citations, which is exactly what
    `room_rows` split apart.

    A chain export holds several rooms. All of them come back, in file order,
    and the caller remaps `continues` onto the ids it mints. Row order is never
    read as structure: a spreadsheet gets sorted, and a chain inferred from
    which room happened to be listed first would invert under a sort.
    """
    complaints: list[str] = []

    try:
        rows = list(csv.DictReader(io.StringIO(text or "")))
    except csv.Error as exc:  # pragma: no cover - csv rarely raises on read
        return [], [f"That file could not be read as CSV: {exc}"]

    if not rows:
        return [], ["That file has no rows under its header."]

    header = set(rows[0].keys())
    if "fact" not in header:
        return [], [
            (
                "That file has no `fact` column, so there is nothing in it to "
                "file as research. Export a room's research and bring that "
                "file back — a sweep export is a different file, and it goes "
                "back into the sweep it came from."
            )
        ]

    # Insertion-ordered so the file's own order survives, which is what makes
    # "nearest first" meaningful when the caller relinks a chain.
    rooms: dict[str, dict] = {}
    unknown_drawers: set[str] = set()

    for number, row in enumerate(rows, start=2):
        fact = unsafe_cell(row.get("fact")).strip()
        if not fact:
            complaints.append(f"Row {number} states no fact and was skipped.")
            continue

        title = unsafe_cell(row.get("room")).strip()
        key = unsafe_cell(row.get("run_id")).strip() or title or "room"
        room = rooms.setdefault(
            key,
            {
                "title": title,
                "era": unsafe_cell(row.get("era")).strip(),
                "continues": unsafe_cell(row.get("continues")).strip(),
                "findings": {},
            },
        )
        # First row wins on the room's own fields. They repeat on every row of
        # a room, and a file edited by hand may disagree with itself; taking
        # the first is at least a rule a reader can predict.
        room["title"] = room["title"] or title

        raw = unsafe_cell(row.get("drawer")).strip().casefold()
        drawer = raw if raw in _DRAWERS else _DRAWER_ALIASES.get(raw, "")
        if not drawer:
            if raw:
                unknown_drawers.add(raw)
            drawer = Category.SETTING.value

        finding = room["findings"].setdefault(
            (drawer, fact),
            {
                "fact": fact,
                "citations": [],
                "retrieved_at": unsafe_cell(row.get("retrieved_at")).strip(),
                "requisition": unsafe_cell(row.get("requisition")).strip(),
                "unverified_urls": [],
                "seen": set(),
            },
        )

        url = unsafe_cell(row.get("source_url")).strip()
        if not url:
            continue
        if url in finding["seen"]:
            # The same source twice on one finding. Two rows saying it does not
            # make it two sources, and a room whose source count double-counts
            # is a room overstating its research.
            continue
        finding["seen"].add(url)
        finding["citations"].append(
            {
                "url": url,
                "title": unsafe_cell(row.get("source_title")).strip(),
                "excerpt": unsafe_cell(row.get("source_excerpt")).strip(),
            }
        )

    if unknown_drawers:
        complaints.append(
            f"{len(unknown_drawers)} drawer name"
            f"{'' if len(unknown_drawers) == 1 else 's'} in that file "
            f"({', '.join(sorted(unknown_drawers))}) are not one of the four this "
            "department files under. Those findings were filed under Setting so "
            "nothing was lost; move them once the room is open."
        )

    built: list[tuple[str, dict]] = []
    for key, room in rooms.items():
        categories: dict[str, dict] = {}
        for (drawer, _), finding in room["findings"].items():
            finding.pop("seen", None)
            categories.setdefault(
                drawer,
                {
                    "category": drawer,
                    "markdown": "",
                    "findings": [],
                    "field_notes": "",
                    "parse_rate": 0.0,
                    "unverified_count": 0,
                },
            )["findings"].append(finding)
        if not categories:
            continue
        built.append(
            (
                key,
                {
                    "story_profile": {
                        "title": room["title"] or "Imported research",
                        "era": room["era"],
                    },
                    "categories": categories,
                    "continues": room["continues"],
                    # Counted from what actually arrived rather than carried in
                    # a column. A file can claim any number; this is the number
                    # of distinct pages the findings below actually cite.
                    "source_count": len(
                        {
                            citation["url"]
                            for drawer in categories.values()
                            for finding in drawer["findings"]
                            for citation in finding["citations"]
                        }
                    ),
                },
            )
        )

    if not built:
        complaints.append("Nothing in that file could be filed as a room.")
    return built, complaints


def bible_markdown(result: dict, run_id: str = "") -> str:
    """A room's bible as a file somebody can be handed. Pure.

    The stored bible is already markdown, so this adds a masthead and gets out
    of the way: which room, which era, when it was built, and how many sources
    stand behind it. A document that arrives in somebody's inbox with no idea
    which room it came from is a document they cannot check.

    NOT A CELL IN THE ROOM CSV, and that is the whole reason this is its own
    file. Excel truncates any cell over 32,767 characters and does it on SAVE,
    without saying so — a writer who opened the research export to sort it and
    pressed save would hand on a bible with the end quietly missing. A document
    and a table are also two things a reader reads two ways, and packing one
    into the other serves neither.

    Returns "" when there is no bible, so a caller can refuse rather than send
    an empty file with a masthead on it.
    """
    result = result or {}
    bible = str(result.get("research_bible") or "").strip()
    if not bible:
        return ""

    profile = result.get("story_profile") or {}
    title = str(profile.get("title") or "Untitled room").strip()
    era = str(profile.get("era") or "").strip()
    built = str(result.get("created_at") or "")[:10]
    sources = int(result.get("source_count") or 0)

    head = [f"# {title}"]
    stamp = " · ".join(
        part
        for part in (
            era,
            f"filed {built}" if built else "",
            f"{sources} source{'' if sources == 1 else 's'}" if sources else "",
            f"room {run_id}" if run_id else "",
        )
        if part
    )
    if stamp:
        head.append(f"*{stamp}*")
    # The bible's own heading levels start at `##` in a well-formed room, so the
    # masthead above sits over them rather than beside them. A room whose bible
    # opens on `#` reads as two documents stacked, which is ugly and is not
    # worth rewriting a writer's document to avoid.
    return "\n\n".join([*head, bible]) + "\n"


def csv_filename(
    room_title: str,
    created_at: str,
    kind: str = "sweep",
    ext: str = "csv",
    unique: str = "",
) -> str:
    """A filename a writer can find again in a downloads folder.

    Room and date first, because a reader looking for last Tuesday's sweep of
    the Doctor Who room is not looking for `sw_9f2c1a`. Reduced to characters
    every filesystem accepts.

    `unique` IS THE SWEEP ID, and it is here because the argument above is only
    true until the second sweep of the day. Measured 2026-08-13: three sweeps of
    one room, three downloads all named
    `doctor-who-liverpool-and-hamburg-special-sweep-2026-08-13.csv`, and a
    browser disambiguating them as `(1)` and `(2)` — which orders them by
    download time and says nothing about which sweep is inside. The writer
    imported one into the wrong sweep and got a screen of true, useless
    complaints about it.

    So it goes LAST, after the human part: the name still sorts and reads by
    room and day, and the id is only doing the job the `(1)` was doing badly.
    Two exports of the SAME sweep still collide, which is correct — they are
    the same file.

    Empty for a room export, where the collision does not arise the same way: a
    room exported twice on one day is the same room, and the two files agree.

    `ext` because the bible leaves as markdown and everything else as CSV, and
    two functions doing this would be two answers to what a room is called.
    """
    stem = "".join(
        char if char.isalnum() or char in " -_" else " " for char in str(room_title or "")
    )
    stem = "-".join(stem.split()).strip("-").lower()
    day = str(created_at or "")[:10] or "undated"
    # Same reduction as the stem: this reaches a Content-Disposition header and
    # a filesystem, and an id is only alphanumeric by convention.
    tail = "".join(char for char in str(unique or "") if char.isalnum())[:12]
    parts = [part for part in (stem, kind, day, tail) if part]
    return f"{'-'.join(parts)}.{ext}"
