from __future__ import annotations

from pathlib import Path
from random import Random

from llm_interface import LLMBackend
from models import CaseBible, Character, EvidenceItem, RedHerring, TimelineEvent


class CaseBibleGenerator:
    def __init__(self, llm: LLMBackend, seed: int = 11) -> None:
        self.llm = llm
        self.rng = Random(seed)
        self.setting_file = Path(__file__).with_name("setting.txt")

    def generate(self) -> CaseBible:
        setting = self.setting_file.read_text(encoding="utf-8").strip()

        victim = Character(
            name="Professor Adrian Wren",
            role="victim",
            description="A celebrated criminologist who planned to expose fraud at the retreat.",
            relationship_to_victim="self",
            means="n/a",
            motive="n/a",
            opportunity="n/a",
            alibi="n/a",
        )

        suspects = [
            Character(
                name="Evelyn Cross",
                role="suspect",
                description="The retreat director whose finances depend on the professor's endorsement.",
                relationship_to_victim="host and recent professional rival",
                means="Access to the estate's service corridors and maintenance keys.",
                motive="Feared exposure of embezzlement tied to retreat funds.",
                opportunity="Met the victim shortly before the lights failed.",
                alibi="Claims she was greeting donors in the west salon at 9:05 PM.",
            ),
            Character(
                name="Miles Dorian",
                role="suspect",
                description="A bestselling true-crime author accused by the victim of plagiarism.",
                relationship_to_victim="public adversary",
                means="Handled rare toxins during research for a previous book.",
                motive="Wanted to stop the victim from ruining his reputation at the keynote.",
                opportunity="Was seen near the library corridor ten minutes before the death.",
                alibi="Says he was recording notes alone in the observatory at 9:10 PM.",
            ),
            Character(
                name="Nora Bell",
                role="suspect",
                description="The victim's graduate assistant who depended on him for recommendation letters.",
                relationship_to_victim="assistant with growing resentment",
                means="Organized the victim's tea service and handled his schedule.",
                motive="Learned that the victim intended to sabotage her fellowship application.",
                opportunity="Delivered the victim's tea before the lecture.",
                alibi="States she stayed in the archive room cataloging papers at 9:00 PM.",
            ),
            Character(
                name="Julian Pike",
                role="culprit",
                description="The estate's head of security and the victim's former research subject.",
                relationship_to_victim="past subject with a hidden grudge",
                means="Controlled camera outages and had access to the antique display weapons.",
                motive="The victim was about to reveal Julian had fabricated data in a famous cold case study.",
                opportunity="Used a staged security sweep to move unseen through the east stair.",
                alibi="Claims he was resetting a generator fault in the basement at 9:12 PM.",
            ),
        ]

        culprit = suspects[-1]
        motive = culprit.motive
        method = (
            "Julian disabled the east corridor camera, lured the victim to the map room, "
            "then used a puncture device coated with fast-acting digitalis to mimic a sudden collapse."
        )

        timeline = [
            TimelineEvent(
                event_id="T1",
                time_marker="8:15 PM",
                summary="Guests arrive for the retreat gala while snow closes the access road.",
                participants=["Evelyn Cross", "Miles Dorian", "Nora Bell", "Julian Pike", victim.name],
                location="Grand foyer",
                public=True,
            ),
            TimelineEvent(
                event_id="T2",
                time_marker="8:40 PM",
                summary="The victim privately tells Nora that a public accusation will be made tonight.",
                participants=[victim.name, "Nora Bell"],
                location="Archive room",
                public=False,
            ),
            TimelineEvent(
                event_id="T3",
                time_marker="8:55 PM",
                summary="Julian initiates a fake maintenance alert and quietly disables the east corridor camera.",
                participants=["Julian Pike"],
                location="Security office",
                public=False,
            ),
            TimelineEvent(
                event_id="T4",
                time_marker="9:00 PM",
                summary="Nora delivers tea to the victim, unaware Julian has already tampered with the route.",
                participants=[victim.name, "Nora Bell"],
                location="Lecture antechamber",
                public=False,
            ),
            TimelineEvent(
                event_id="T5",
                time_marker="9:08 PM",
                summary="Julian messages the victim about an urgent discovery in the map room.",
                participants=[victim.name, "Julian Pike"],
                location="East corridor",
                public=False,
            ),
            TimelineEvent(
                event_id="T6",
                time_marker="9:12 PM",
                summary="The victim is killed in the map room with a poisoned puncture wound.",
                participants=[victim.name, "Julian Pike"],
                location="Map room",
                public=False,
            ),
            TimelineEvent(
                event_id="T7",
                time_marker="9:15 PM",
                summary="Julian triggers a brief power fluctuation to scramble witness recollection and coverage.",
                participants=["Julian Pike"],
                location="Basement control panel",
                public=False,
            ),
            TimelineEvent(
                event_id="T8",
                time_marker="9:20 PM",
                summary="The body is discovered and the estate is locked down.",
                participants=["Evelyn Cross", "Miles Dorian", "Nora Bell", "Julian Pike"],
                location="Map room",
                public=True,
            ),
        ]

        evidence_items = [
            EvidenceItem(
                evidence_id="E1",
                name="Cracked teacup",
                description="A teacup bearing Nora's fingerprints but no poison residue.",
                location_found="Lecture antechamber",
                implicated_person="Nora Bell",
                reliability=0.75,
                planted=False,
            ),
            EvidenceItem(
                evidence_id="E2",
                name="Deleted security segment",
                description="A seven-minute gap in east corridor footage manually triggered from the security desk.",
                location_found="Security office",
                implicated_person="Julian Pike",
                reliability=0.98,
                planted=False,
            ),
            EvidenceItem(
                evidence_id="E3",
                name="Digitalis trace",
                description="A toxicology trace on the victim's collar consistent with digitalis delivery by puncture.",
                location_found="Victim's clothing",
                implicated_person="Julian Pike",
                reliability=0.94,
                planted=False,
            ),
            EvidenceItem(
                evidence_id="E4",
                name="Missing display spike",
                description="A display label from an antique navigation spike case now missing one item.",
                location_found="Map room display",
                implicated_person="Julian Pike",
                reliability=0.88,
                planted=False,
            ),
            EvidenceItem(
                evidence_id="E5",
                name="Burned ledger scrap",
                description="A scrap from the retreat accounts suggesting Evelyn hid expenses.",
                location_found="Fireplace grate",
                implicated_person="Evelyn Cross",
                reliability=0.67,
                planted=False,
            ),
            EvidenceItem(
                evidence_id="E6",
                name="Unsigned apology draft",
                description="A draft apology in Miles's notebook after the victim threatened exposure.",
                location_found="Observatory desk",
                implicated_person="Miles Dorian",
                reliability=0.71,
                planted=False,
            ),
            EvidenceItem(
                evidence_id="E7",
                name="Basement boot print",
                description="Wet tread marks matching Julian's boots lead from the control panel toward the east stair.",
                location_found="Basement corridor",
                implicated_person="Julian Pike",
                reliability=0.91,
                planted=False,
            ),
            EvidenceItem(
                evidence_id="E8",
                name="Phone message extract",
                description="A recovered message summoning the victim to the map room from Julian's device.",
                location_found="Victim's phone",
                implicated_person="Julian Pike",
                reliability=0.97,
                planted=False,
            ),
            EvidenceItem(
                evidence_id="E9",
                name="Cut generator wire",
                description="A deliberately nicked wire that caused the brief outage used to support Julian's alibi.",
                location_found="Generator housing",
                implicated_person="Julian Pike",
                reliability=0.89,
                planted=False,
            ),
        ]

        red_herrings = [
            RedHerring(
                herring_id="RH1",
                suspect_name="Nora Bell",
                misleading_evidence_ids=["E1"],
                explanation="Nora appears suspicious because she served the victim's tea, but the poison was not ingested.",
            ),
            RedHerring(
                herring_id="RH2",
                suspect_name="Evelyn Cross",
                misleading_evidence_ids=["E5"],
                explanation="Evelyn hid financial fraud, giving her motive to lie, but that misconduct is separate from the murder.",
            ),
        ]

        culprit_evidence_chain = ["E2", "E8", "E3", "E4", "E7", "E9"]

        return CaseBible(
            setting=setting,
            victim=victim,
            culprit=culprit,
            suspects=suspects,
            motive=motive,
            method=method,
            true_timeline=timeline,
            evidence_items=evidence_items,
            red_herrings=red_herrings,
            culprit_evidence_chain=culprit_evidence_chain,
        )
