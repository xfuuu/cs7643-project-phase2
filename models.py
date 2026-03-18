from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Character:
    name: str
    role: str
    description: str
    relationship_to_victim: str
    means: str
    motive: str
    opportunity: str
    alibi: str


@dataclass
class EvidenceItem:
    evidence_id: str
    name: str
    description: str
    location_found: str
    implicated_person: str
    reliability: float
    planted: bool = False


@dataclass
class TimelineEvent:
    event_id: str
    time_marker: str
    summary: str
    participants: list[str]
    location: str
    public: bool


@dataclass
class RedHerring:
    herring_id: str
    suspect_name: str
    misleading_evidence_ids: list[str]
    explanation: str


@dataclass
class CaseBible:
    setting: str
    victim: Character
    culprit: Character
    suspects: list[Character]
    motive: str
    method: str
    true_timeline: list[TimelineEvent]
    evidence_items: list[EvidenceItem]
    red_herrings: list[RedHerring]
    culprit_evidence_chain: list[str]


@dataclass
class FactTriple:
    subject: str
    relation: str
    object: str
    time: str | None
    source: str
    confidence: float


@dataclass
class PlotStep:
    step_id: int
    phase: str
    kind: str
    title: str
    summary: str
    location: str
    participants: list[str]
    evidence_ids: list[str] = field(default_factory=list)
    reveals: list[str] = field(default_factory=list)
    timeline_ref: str | None = None


@dataclass
class PlotPlan:
    investigator: str
    steps: list[PlotStep]


@dataclass
class ValidationIssue:
    code: str
    message: str
    step_id: int | None = None


@dataclass
class ValidationReport:
    is_valid: bool
    issues: list[ValidationIssue]
    metrics: dict[str, Any]


def to_data(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    if isinstance(value, list):
        return [to_data(item) for item in value]
    if isinstance(value, dict):
        return {key: to_data(item) for key, item in value.items()}
    return value
