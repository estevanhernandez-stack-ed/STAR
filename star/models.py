"""Typed data passed between STAR agents."""

from enum import Enum

from pydantic import BaseModel, Field


class Category(str, Enum):
    """The four research categories (from the Writer Studio architecture)."""

    SETTING = "setting"
    OBJECTS_PROPS = "objects_props"
    LOGISTICS = "logistics"
    FORCES_CONFLICTS = "forces_conflicts"


class StoryProfile(BaseModel):
    """What the IntakeAgent extracts from a treatment."""

    title: str = Field(description="Working title, or a short label if none given")
    logline: str = Field(description="One-sentence summary of the story")
    era: str = Field(description="Time period, e.g. '1960-1962' or 'present day'")
    locations: list[str] = Field(description="Primary settings, most specific first")
    genre: str = Field(description="Primary genre")
    key_entities: list[str] = Field(
        description="People, professions, organizations, technologies, or activities "
        "central to the story that require factual grounding"
    )


class ResearchQuestion(BaseModel):
    """A single answerable research question."""

    category: Category
    question: str = Field(description="A specific, factual, answerable question")
    why: str = Field(description="What scene-writing need this answers")


class ResearchPlan(BaseModel):
    """What the PlannerAgent produces: the fan-out work order."""

    questions: list[ResearchQuestion] = Field(
        description="8-20 questions total, spread across all four categories"
    )


class Citation(BaseModel):
    url: str
    title: str
    excerpt: str


class Finding(BaseModel):
    """One researched fact with its receipts."""

    fact: str
    citations: list[Citation] = []
    unverified_urls: list[str] = Field(
        default=[],
        description="URLs the researcher cited that never appeared in a search "
        "result. Rendered as a warning, never as a source.",
    )


class ResearchDoc(BaseModel):
    """A finished, cited research document for one category."""

    category: Category
    markdown: str = Field(description="Raw researcher output, preserved verbatim")
    findings: list[Finding] = []
    field_notes: str = Field(
        default="",
        description="Lines that did not parse as findings, kept rather than dropped",
    )
    parse_rate: float = Field(
        default=0.0, description="Parsed findings over bullet lines seen, 0.0-1.0"
    )
    unverified_count: int = Field(
        default=0, description="Total cited URLs absent from the source ledger"
    )


class Verdict(str, Enum):
    """Script-check outcomes (Pipeline B, week 3)."""

    CONFIRMED = "confirmed"
    ANACHRONISM = "anachronism"
    UNVERIFIABLE = "unverifiable"


class Claim(BaseModel):
    """A real-world claim extracted from a scene, before anyone has checked it."""

    text: str
    claim_type: str = Field(description="object | language | timing | geography | technology | behavior")
    verdict: Verdict | None = None
    note: str | None = None
    citations: list[Citation] = []


class ClaimSet(BaseModel):
    """The claim_extractor's `output_schema`: everything one scene asserts.

    An empty list is a legitimate answer. A scene of pure interior dialogue
    makes no claim about the world, and the check says so rather than
    inventing one to avoid returning nothing.
    """

    claims: list[Claim]


class ClaimResult(BaseModel):
    """One claim after the verifier and `star/verdicts.py` are done with it.

    `verdict` is required here where `Claim.verdict` is optional, because a
    claim before verification and a claim after it are two states, not one
    type with a hole in it. Anything holding a ClaimResult can render a
    verdict without asking whether there is one.

    `citations` and `citation_sources` are parallel lists: index i of the
    second says whether the room's own files or a fresh search produced
    index i of the first. Two lists rather than a field on Citation, because
    Citation is Pipeline A's type and provenance is Pipeline B's question.
    """

    text: str = Field(description="The claim's exact substring of the scene")
    claim_type: str
    verdict: Verdict
    note: str = ""
    citations: list[Citation] = []
    citation_sources: list[str] = Field(
        default=[], description='"room" | "search", parallel to citations'
    )
    unsourced_urls: list[str] = Field(
        default=[],
        description="Cited URLs in neither ledger. Stamped, never rendered as "
        "a source — the same posture Finding.unverified_urls takes.",
    )
    reason: str = Field(
        default="",
        description='"" | "budget" | "unreached". Why a verdict is thin, when '
        "the reason is the department's rather than the world's.",
    )


class ScriptCheckResult(BaseModel):
    """One filed check: a scene, its claims, and what the check cost.

    `cover_note` is the department's own line about the check, and it is the
    one field here no model touches and `star/verdicts.py` never sets — the
    server computes it from what it handed the pipeline. Two results are
    legitimately thin and would otherwise reach a reader as an empty screen:
    a scene that asserts nothing about the world, and a room that filed no
    sources of its own. Both are answers, and an answer that arrives as a
    blank panel reads as a failure. The line lives on the payload rather than
    in the browser because the MCP door has no renderer between this object
    and its reader.
    """

    scene_id: str
    created_at: str
    claims: list[ClaimResult]
    parse_rate: float = 0.0
    unsourced_count: int = 0
    field_notes: str = ""
    search_count: int = 0
    budget_exhausted: bool = False
    cover_note: str = Field(
        default="",
        description="One plain line about what this check had to work with. "
        "Empty when the claims speak for themselves.",
    )
