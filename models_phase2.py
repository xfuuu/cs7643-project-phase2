from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


@dataclass
class Room:
    name: str
    description: str
    adjacent_rooms: list[str]
    npc_names: list[str]
    evidence_ids: list[str]
    item_names: list[str]


@dataclass
class WorldMap:
    rooms: dict[str, Room]

    def to_dict(self) -> dict[str, Any]:
        return {
            "rooms": {
                name: {
                    "name": room.name,
                    "description": room.description,
                    "adjacent_rooms": room.adjacent_rooms,
                    "npc_names": room.npc_names,
                    "evidence_ids": room.evidence_ids,
                    "item_names": room.item_names,
                }
                for name, room in self.rooms.items()
            }
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorldMap:
        rooms = {
            name: Room(
                name=r["name"],
                description=r["description"],
                adjacent_rooms=r["adjacent_rooms"],
                npc_names=r["npc_names"],
                evidence_ids=r["evidence_ids"],
                item_names=r["item_names"],
            )
            for name, r in data["rooms"].items()
        }
        return cls(rooms=rooms)


@dataclass
class StateChange:
    entity: str
    attribute: str
    old_value: Any
    new_value: Any

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity": self.entity,
            "attribute": self.attribute,
            "old_value": self.old_value,
            "new_value": self.new_value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StateChange:
        return cls(
            entity=data["entity"],
            attribute=data["attribute"],
            old_value=data["old_value"],
            new_value=data["new_value"],
        )


@dataclass
class CausalSpan:
    span_id: str
    variable: str
    required_value: Any
    from_step_id: int
    until_step_id: int | None
    evidence_ids: list[str]
    description: str


@dataclass
class ViolatedSpan:
    span: CausalSpan
    triggering_change: StateChange
    description: str


@dataclass
class ActionIntent:
    raw_text: str
    verb: str
    object_: str
    target_location: str | None
    confidence: float
    predicted_effects: list[StateChange] = field(default_factory=list)


class ActionKind(str, Enum):
    CONSTITUENT = "constituent"
    EXCEPTIONAL = "exceptional"
    CONSISTENT = "consistent"


@dataclass
class ActionClassification:
    kind: ActionKind
    triggered_step_id: int | None = None
    violated_spans: list[ViolatedSpan] = field(default_factory=list)
