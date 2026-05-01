from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "phase1"))
from llm_interface import LLMBackend
from models import CaseBible, PlotPlan

from models_phase2 import Room, WorldMap

_PROMPTS = Path(__file__).parent / "prompts"

_COMMON_ADJACENCY: list[tuple[str, str]] = [
    ("study", "library"),
    ("library", "drawing room"),
    ("drawing room", "ballroom"),
    ("ballroom", "dining room"),
    ("dining room", "kitchen"),
    ("conservatory", "drawing room"),
    ("conservatory", "dining room"),
    ("main entrance", "drawing room"),
    ("main entrance", "ballroom"),
    ("main entrance hall", "drawing room"),
    ("main entrance hall", "ballroom"),
    ("guest wing", "main corridor"),
    ("main corridor", "study"),
    ("main corridor", "library"),
    ("main corridor", "guest wing"),
    ("terrace", "ballroom"),
    ("terrace", "drawing room"),
    ("julian's bedroom", "guest wing"),
    ("the study", "the library"),
    ("the library", "drawing room"),
    ("the terrace", "ballroom"),
]


class WorldBuilder:
    def __init__(self, llm: LLMBackend) -> None:
        self._llm = llm

    def build(self, case_bible: CaseBible, plot_plan: PlotPlan) -> WorldMap:
        rooms = self._extract_rooms(plot_plan)
        contents = self._assign_contents(case_bible, rooms)
        adjacency = self._build_adjacency(rooms)

        # Include rooms introduced by adjacency completion (e.g. "Main Corridor"
        # from _llm_connect); otherwise they appear only as exits and the player
        # cannot enter them.
        all_rooms: list[str] = list(rooms)
        for room_name in adjacency.keys():
            if room_name not in all_rooms:
                all_rooms.append(room_name)

        descriptions = self._generate_descriptions(all_rooms, contents, adjacency)

        room_objects: dict[str, Room] = {}
        for room_name in all_rooms:
            c = contents.get(room_name, {})
            room_objects[room_name] = Room(
                name=room_name,
                description=descriptions.get(room_name, "A room in the manor."),
                adjacent_rooms=adjacency.get(room_name, []),
                npc_names=c.get("npcs", []),
                evidence_ids=c.get("evidence_ids", []),
                item_names=c.get("items", []),
            )
        return WorldMap(rooms=room_objects)

    def save(self, world_map: WorldMap, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(world_map.to_dict(), f, ensure_ascii=False, indent=2)

    def load(self, path: str) -> WorldMap:
        with open(path, encoding="utf-8") as f:
            return WorldMap.from_dict(json.load(f))

    # ── internal ───────────────────────────────────────────────────────────

    def _extract_rooms(self, plot_plan: PlotPlan) -> list[str]:
        seen: dict[str, None] = {}
        for step in plot_plan.steps:
            seen[step.location] = None
        return list(seen.keys())

    def _assign_contents(
        self, case_bible: CaseBible, rooms: list[str]
    ) -> dict[str, dict]:
        contents: dict[str, dict] = {r: {"npcs": [], "evidence_ids": [], "items": []} for r in rooms}
        rooms_lower = {r.lower(): r for r in rooms}

        for ev in case_bible.evidence_items:
            target = self._best_room_match(ev.location_found, rooms_lower, rooms)
            contents[target]["evidence_ids"].append(ev.evidence_id)

        npc_names = (
            [case_bible.victim.name, case_bible.culprit.name]
            + [s.name for s in case_bible.suspects]
        )
        for name in dict.fromkeys(npc_names):
            target = self._npc_starting_room(name, case_bible, rooms_lower, rooms)
            if name not in contents[target]["npcs"]:
                contents[target]["npcs"].append(name)

        return contents

    def _npc_starting_room(
        self,
        name: str,
        case_bible: CaseBible,
        rooms_lower: dict[str, str],
        rooms: list[str],
    ) -> str:
        for event in case_bible.true_timeline:
            if name in event.participants:
                match = self._best_room_match(event.location, rooms_lower, rooms)
                return match
        return rooms[0]

    def _best_room_match(
        self, location: str, rooms_lower: dict[str, str], rooms: list[str]
    ) -> str:
        loc_lower = location.lower()
        if loc_lower in rooms_lower:
            return rooms_lower[loc_lower]
        for key, room in rooms_lower.items():
            if key in loc_lower or loc_lower in key:
                return room
        return rooms[0]

    def _build_adjacency(self, rooms: list[str]) -> dict[str, list[str]]:
        adj: dict[str, list[str]] = {r: [] for r in rooms}
        rooms_lower = {r.lower(): r for r in rooms}

        for a_lower, b_lower in _COMMON_ADJACENCY:
            a = rooms_lower.get(a_lower)
            b = rooms_lower.get(b_lower)
            if a and b and a != b:
                if b not in adj[a]:
                    adj[a].append(b)
                if a not in adj[b]:
                    adj[b].append(a)

        if not self._is_connected(adj, rooms):
            adj = self._llm_connect(adj, rooms)

        return adj

    def _is_connected(self, adj: dict[str, list[str]], rooms: list[str]) -> bool:
        if not rooms:
            return True
        visited: set[str] = set()
        stack = [rooms[0]]
        while stack:
            node = stack.pop()
            if node in visited:
                continue
            visited.add(node)
            stack.extend(adj.get(node, []))
        return len(visited) == len(rooms)

    def _llm_connect(
        self, adj: dict[str, list[str]], rooms: list[str]
    ) -> dict[str, list[str]]:
        template = (_PROMPTS / "world_adjacency.txt").read_text(encoding="utf-8")
        adj_repr = json.dumps(adj, ensure_ascii=False)
        prompt = template.replace("{rooms_list}", json.dumps(rooms)).replace(
            "{current_adjacency}", adj_repr
        )
        response = self._llm.generate(prompt, label="world_adjacency") if hasattr(self._llm, "generate") else self._llm.generate(prompt)
        try:
            data = _extract_json(response.text)
            new_rooms: list[str] = data.get("rooms", rooms)
            new_adj_raw: dict[str, list[str]] = data.get("adjacency", adj)
            for r in new_rooms:
                if r not in adj:
                    adj[r] = []
            for room, neighbours in new_adj_raw.items():
                if room not in adj:
                    adj[room] = []
                for nb in neighbours:
                    if nb not in adj[room]:
                        adj[room].append(nb)
                    if room not in adj.get(nb, []):
                        adj.setdefault(nb, []).append(room)
        except Exception:
            self._force_chain(adj, rooms)
        return adj

    def _force_chain(self, adj: dict[str, list[str]], rooms: list[str]) -> None:
        for i in range(len(rooms) - 1):
            a, b = rooms[i], rooms[i + 1]
            if b not in adj[a]:
                adj[a].append(b)
            if a not in adj[b]:
                adj[b].append(a)

    def _generate_descriptions(
        self,
        rooms: list[str],
        contents: dict[str, dict],
        adjacency: dict[str, list[str]],
    ) -> dict[str, str]:
        template = (_PROMPTS / "world_room_desc.txt").read_text(encoding="utf-8")
        descriptions: dict[str, str] = {}
        for room_name in rooms:
            c = contents.get(room_name, {})
            items_str = ", ".join(c.get("items", [])) or "nothing of obvious note"
            adj_str = ", ".join(adjacency.get(room_name, [])) or "none"
            prompt = (
                template.replace("{room_name}", room_name)
                .replace("{items}", items_str)
                .replace("{adjacent_rooms}", adj_str)
            )
            try:
                resp = self._llm.generate(prompt, label=f"room_desc:{room_name}") if hasattr(self._llm, "generate") else self._llm.generate(prompt)
                descriptions[room_name] = resp.text.strip()
            except Exception:
                descriptions[room_name] = f"You are in {room_name}."
        return descriptions


def _extract_json(text: str) -> dict:
    start = text.find("{")
    end = text.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError("No JSON object found")
    return json.loads(text[start:end])
