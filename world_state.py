from __future__ import annotations

from typing import Any

from models_phase2 import StateChange, WorldMap


class WorldStateManager:
    def __init__(self, world_map: WorldMap, starting_room: str) -> None:
        self._world_map = world_map
        self._player_room: str = starting_room

        self._npc_locations: dict[str, str] = {}
        self._evidence_exists: dict[str, bool] = {}
        self._evidence_locations: dict[str, str] = {}
        self._item_states: dict[str, dict[str, Any]] = {}
        self._known_to_player: set[str] = set()
        self._room_states: dict[str, dict[str, Any]] = {}

        for room_name, room in world_map.rooms.items():
            for npc in room.npc_names:
                self._npc_locations[npc] = room_name
            for ev_id in room.evidence_ids:
                self._evidence_exists[ev_id] = True
                self._evidence_locations[ev_id] = room_name
            for item in room.item_names:
                self._item_states[item] = {"location": room_name, "state": "normal"}
            self._room_states[room_name] = {"accessible": True}

    # ── properties ────────────────────────────────────────────────────────

    @property
    def player_room(self) -> str:
        return self._player_room

    # ── public API ────────────────────────────────────────────────────────

    def apply_effects(self, effects: list[StateChange]) -> None:
        for change in effects:
            self._apply_one(change)

    def move_player(self, destination: str) -> bool:
        room = self._world_map.rooms.get(self._player_room)
        if room is None:
            return False
        target = self._resolve_room_name(destination)
        if target is None:
            return False
        if target not in room.adjacent_rooms:
            return False
        room_state = self._room_states.get(target, {})
        if not room_state.get("accessible", True):
            return False
        self._player_room = target
        return True

    def get_room_view(self, room_name: str | None = None) -> dict[str, Any]:
        name = room_name or self._player_room
        room = self._world_map.rooms.get(name)
        if room is None:
            return {}

        present_npcs = [n for n, loc in self._npc_locations.items() if loc == name]
        present_evidence = [
            ev for ev in room.evidence_ids
            if self._evidence_exists.get(ev, False)
            and self._evidence_locations.get(ev) == name
        ]
        present_items = [
            item for item, state in self._item_states.items()
            if state.get("location") == name
        ]
        exits = [
            nb for nb in room.adjacent_rooms
            if self._room_states.get(nb, {}).get("accessible", True)
        ]
        return {
            "room": name,
            "description": room.description,
            "npcs": present_npcs,
            "evidence": present_evidence,
            "items": present_items,
            "exits": exits,
        }

    def evidence_exists(self, evidence_id: str) -> bool:
        return self._evidence_exists.get(evidence_id, False)

    def evidence_location(self, evidence_id: str) -> str | None:
        return self._evidence_locations.get(evidence_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "player_room": self._player_room,
            "npc_locations": self._npc_locations,
            "evidence_exists": self._evidence_exists,
            "evidence_locations": self._evidence_locations,
            "item_states": self._item_states,
            "known_to_player": list(self._known_to_player),
            "room_states": self._room_states,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], world_map: WorldMap) -> WorldStateManager:
        first_room = next(iter(world_map.rooms))
        obj = cls.__new__(cls)
        obj._world_map = world_map
        obj._player_room = data["player_room"]
        obj._npc_locations = data["npc_locations"]
        obj._evidence_exists = data["evidence_exists"]
        obj._evidence_locations = data["evidence_locations"]
        obj._item_states = data["item_states"]
        obj._known_to_player = set(data.get("known_to_player", []))
        obj._room_states = data.get("room_states", {r: {"accessible": True} for r in world_map.rooms})
        return obj

    # ── internal ──────────────────────────────────────────────────────────

    def _apply_one(self, change: StateChange) -> None:
        entity = change.entity
        attr = change.attribute
        new_val = change.new_value

        if attr == "known_to_player":
            if new_val:
                self._known_to_player.add(entity)
            else:
                self._known_to_player.discard(entity)
            return

        if attr == "exists":
            self._evidence_exists[entity] = bool(new_val)
            return

        if attr == "location":
            if entity in self._npc_locations:
                self._npc_locations[entity] = str(new_val)
            elif entity in self._evidence_exists:
                self._evidence_locations[entity] = str(new_val)
            elif entity in self._item_states:
                self._item_states[entity]["location"] = str(new_val)
            elif entity == "player":
                resolved = self._resolve_room_name(str(new_val))
                if resolved:
                    self._player_room = resolved
            return

        if attr == "accessible":
            target = self._resolve_room_name(entity)
            if target:
                self._room_states.setdefault(target, {})["accessible"] = bool(new_val)
            return

        if attr == "state":
            if entity in self._item_states:
                self._item_states[entity]["state"] = str(new_val)
            else:
                target = self._resolve_room_name(entity)
                if target:
                    self._room_states.setdefault(target, {})["state"] = str(new_val)
            return

    def _resolve_room_name(self, name: str) -> str | None:
        if name in self._world_map.rooms:
            return name
        name_lower = name.lower()
        for room_name in self._world_map.rooms:
            if room_name.lower() == name_lower:
                return room_name
        return None
