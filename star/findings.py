"""Recover structured findings from researcher prose.

Researchers cannot carry an `output_schema` — ADK forbids tools on schema'd
agents and they need `parallel_search` — so structure is recovered after the
fact. Researchers write one finding per line:

    - <the fact, stated plainly> :: <url>, <url>

Only the URL is trusted. Title and excerpt are hydrated from the SourceLedger,
which holds what the search API actually returned, so no title or excerpt is
ever authored by a model. A cited URL missing from the ledger is recorded as
unverified rather than rendered as a source.

Nothing is ever discarded: lines that do not parse are kept as field notes and
the raw prose is preserved verbatim.
"""

import re

from star.ledger import SourceLedger
from star.models import Category, Citation, Finding, ResearchDoc

_BULLET = re.compile(r"^\s*[-*•]\s+(.*)$")
_URL = re.compile(r"https?://[^\s,;)\]}<>\"']+")
_SEPARATOR = "::"


def parse_finding_line(line: str) -> tuple[str, list[str]] | None:
    """Split one finding line into its fact and its cited URLs.

    Returns None for any line that is not a well-formed finding, including
    bullets that carry no sources.
    """
    match = _BULLET.match(line)
    if not match:
        return None

    body = match.group(1)
    if _SEPARATOR not in body:
        return None

    fact, _, tail = body.partition(_SEPARATOR)
    fact = fact.strip()
    urls = [url.rstrip(".") for url in _URL.findall(tail)]

    if not fact or not urls:
        return None
    return fact, urls


def parse_findings(
    prose: str | None, category: Category, ledger: SourceLedger
) -> ResearchDoc:
    """Join researcher prose to the ledger, producing a cited ResearchDoc.

    `parse_rate` counts parsed findings over bullet lines only. Headers, blank
    lines, and closing uncertainty paragraphs are legitimate prose and must not
    drag the metric down, since it drives the decision to fall back to schema'd
    structurer agents.
    """
    raw = prose or ""
    findings: list[Finding] = []
    notes: list[str] = []
    bullet_lines = 0
    unverified_total = 0

    for line in raw.splitlines():
        if _BULLET.match(line):
            bullet_lines += 1
            parsed = parse_finding_line(line)
            if parsed is None:
                notes.append(line.rstrip())
                continue

            fact, urls = parsed
            citations: list[Citation] = []
            unverified: list[str] = []

            for url in urls:
                entry = ledger.get(url)
                if entry is None:
                    unverified.append(url)
                    continue
                citations.append(
                    Citation(
                        url=entry.url,
                        title=entry.title or entry.url,
                        excerpt=entry.excerpts[0] if entry.excerpts else "",
                    )
                )

            unverified_total += len(unverified)
            findings.append(
                Finding(fact=fact, citations=citations, unverified_urls=unverified)
            )
        elif line.strip():
            notes.append(line.rstrip())

    parse_rate = (len(findings) / bullet_lines) if bullet_lines else 0.0

    return ResearchDoc(
        category=category,
        markdown=raw,
        findings=findings,
        field_notes="\n".join(notes).strip(),
        parse_rate=round(parse_rate, 3),
        unverified_count=unverified_total,
    )
