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


def csv_filename(room_title: str, created_at: str) -> str:
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
    return f"{stem}-sweep-{day}.csv" if stem else f"sweep-{day}.csv"
