"""Recover structured findings from researcher prose.

Researchers cannot carry an `output_schema` — ADK forbids tools on schema'd
agents and they need `parallel_search` — so structure is recovered after the
fact. Researchers write one finding per line:

    - <the fact, stated plainly> :: <url>, <url>

Only the URL is trusted. In the `categories` payload this module produces,
title and excerpt are hydrated from the SourceLedger, which holds what the
search API actually returned, so no title or excerpt in a `Citation` is ever
authored by a model. A cited URL missing from the ledger is recorded as
unverified rather than rendered as a source.

That guarantee covers this payload only. `SynthesisAgent` (see
`star/agents/synthesis.py`) reads the raw researcher prose directly and is
instructed to end each section with a numbered source list of its own
(title — URL). Those titles are model-authored prose, not ledger lookups, so
the `research_bible` the user reads is a separate, unverified path.

Nothing is ever discarded: lines that do not parse are kept as field notes and
the raw prose is preserved verbatim.
"""

import re

from star.ledger import LedgerEntry, SourceLedger
from star.models import Category, Citation, Finding, ResearchDoc

_BULLET = re.compile(r"^\s*[-*•]\s+(.*)$")
_URL = re.compile(r"https?://[^\s,)\]}<>\"']+", re.IGNORECASE)
_SEPARATOR = "::"
_TRAILING_PUNCT = ".,;:!?"
_WORD = re.compile(r"[a-z0-9]+")


def parse_finding_line(line: str) -> tuple[str, list[str]] | None:
    """Split one finding line into its fact and its cited URLs.

    Returns None for any line that is not a well-formed finding, including
    bullets that carry no sources, and bullets with more than one `::` — a
    second separator means a real segment of the fact got cut, and failing to
    parse beats silently dropping it (see `parse_findings`'s `parse_rate`).
    """
    match = _BULLET.match(line)
    if not match:
        return None

    body = match.group(1)
    if _SEPARATOR not in body:
        return None
    if body.count(_SEPARATOR) > 1:
        return None

    fact, _, tail = body.partition(_SEPARATOR)
    fact = fact.strip()
    urls = [url.rstrip(".") for url in _URL.findall(tail)]

    if not fact or not urls:
        return None
    return fact, urls


def _strip_trailing_punct(url: str) -> str:
    """Drop sentence-final punctuation the URL regex had no reason to exclude.

    `!` and `?` are legal URL characters (query strings), so the extractor
    keeps them — this only fires as a fallback once the raw candidate has
    already failed to find a ledger match.
    """
    return url.rstrip(_TRAILING_PUNCT)


def _lower_scheme(url: str) -> str:
    """Lowercase just the `scheme://` prefix, leaving host/path case alone."""
    scheme, sep, rest = url.partition("://")
    if not sep:
        return url
    return f"{scheme.lower()}{sep}{rest}"


def _balance_parens(url: str) -> str:
    """Append the `)` the URL regex had to drop to avoid eating real syntax.

    `)` closes parentheticals in prose far more often than it appears inside
    a URL, so the extractor excludes it — which truncates real URLs like a
    Wikipedia disambiguation link. Balancing is only tried, never assumed.
    """
    open_count = url.count("(")
    close_count = url.count(")")
    if open_count > close_count:
        return url + ")" * (open_count - close_count)
    return url


_LADDER = (_strip_trailing_punct, _lower_scheme, _balance_parens)


def _resolve_citation(url: str, ledger: SourceLedger) -> LedgerEntry | None:
    """Recover the ledger entry a mangled citation was meant to point to.

    The ledger is the only oracle: a rewrite is accepted only when it lands on
    a real entry, so this can recover a truncated-but-genuine URL but can
    never manufacture a source for one that was never returned by search.
    """
    entry = ledger.get(url)
    if entry is not None:
        return entry

    seen = {url}
    frontier = [url]
    for _ in range(len(_LADDER)):
        next_frontier: list[str] = []
        for candidate in frontier:
            for transform in _LADDER:
                rewritten = transform(candidate)
                if rewritten == candidate or rewritten in seen:
                    continue
                seen.add(rewritten)
                entry = ledger.get(rewritten)
                if entry is not None:
                    return entry
                next_frontier.append(rewritten)
        frontier = next_frontier

    return None


def _tokenize(text: str) -> set[str]:
    return {tok for tok in _WORD.findall(text.lower()) if len(tok) >= 4}


def _best_excerpt(excerpts: list[str], fact: str) -> str:
    """Pick the excerpt most relevant to this fact, not just the first found.

    The ledger merges a URL's excerpts across every researcher that cited it,
    so index 0 may answer a different researcher's question entirely. Score
    each excerpt by token overlap with the fact and take the best; ties
    (including "nothing overlaps") keep the first, matching prior behavior.
    """
    if not excerpts:
        return ""
    if len(excerpts) == 1:
        return excerpts[0]

    fact_tokens = _tokenize(fact)
    if not fact_tokens:
        return excerpts[0]

    best_excerpt = excerpts[0]
    best_score = -1
    for excerpt in excerpts:
        score = len(fact_tokens & _tokenize(excerpt))
        if score > best_score:
            best_score = score
            best_excerpt = excerpt
    return best_excerpt


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
                entry = _resolve_citation(url, ledger)
                if entry is None:
                    unverified.append(url)
                    continue
                citations.append(
                    Citation(
                        url=entry.url,
                        title=entry.title or entry.url,
                        excerpt=_best_excerpt(entry.excerpts, fact),
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
