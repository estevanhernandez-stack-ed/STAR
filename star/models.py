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
    """A real-world claim extracted from a scene."""

    text: str
    claim_type: str = Field(description="object | language | timing | geography | technology | behavior")
    verdict: Verdict | None = None
    note: str | None = None
    citations: list[Citation] = []
