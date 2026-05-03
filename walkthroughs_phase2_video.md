# Phase II Video Walkthroughs

This document provides the text walkthroughs used in the Phase II final video. User actions are separated from system, world-state, and Drama Manager actions so the interaction flow is explicit.

Source transcripts:

- Normal run: `presentation/logs/normal_terminal_20260502_160833.log`
- Exceptional run: `presentation/logs/presentation_exception_session.log`

## Normal Walkthrough: Planned Story Progression

In the normal walkthrough, the player follows the intended investigation path. The system parses each free-text action, applies the expected world-state changes, advances the PlotPlan cursor, and generates narration. No Drama Manager repair is triggered in this run.

| Step | User action(s) | Drama / system action | Result shown to player |
| --- | --- | --- | --- |
| 1 | `examine the desk` | Treats the action as planned story progress. Applies the desk discovery and advances the current PlotPlan beat. | Next beat: `A Room Disturbed` |
| 2 | `examine EV-01` | Marks the flask clue as discovered and advances the investigation. | Next beat: `The Household Gathers` |
| 3 | `go library`; `go drawing room` | Handles movement directly in `game.py`. Updates the player room; no LLM narration or Drama Manager repair is needed. | Player reaches the Drawing Room; next beat remains `The Household Gathers` |
| 4 | `interview Eleanor Vance about the tragedy` | Treats the interview as the expected constituent action for the current beat. Updates the interaction state and advances the plot. | Next beat: `The Silent Library` |
| 5 | `go library` | Handles room traversal directly. The player reaches the correct location, but the beat does not advance until the required evidence is examined. | Next beat remains `The Silent Library` |
| 6 | `examine EV-06` | Marks the library alibi clue as discovered and advances the planned investigation. | Next beat: `The Weapon in the Ashes` |
| 7 | `go study`; `examine EV-08` | Moves to the Study, applies the weapon discovery, and advances the PlotPlan. | Next beat: `The Heir's Panic` |
| 8 | `go library`; `go drawing room`; `go ballroom`; `interview Julian Thorne about the green silk ribbon` | Handles traversal, then treats Julian's interview as the expected story action. Updates the NPC/evidence interaction state. | Next beat: `The Muddy Terrace` |
| 9 | `go terrace` | Handles traversal to the required room. The room-entry condition auto-advances the story beat. | Next beat: `The Motive of Debt` |
| 10 | `go ballroom`; `go drawing room`; `go main entrance hall`; `go main corridor`; `go guest wing`; `go julian's bedroom`; `examine EV-05` | Moves through the room graph, marks Julian's ledger as discovered, and advances the story. | Next beat: `The Bloodless Wound` |
| 11 | `go guest wing`; `go main corridor`; `go main entrance hall`; `go drawing room`; `go library`; `go study`; `examine EV-08`; `examine EV-01` | Applies the bloodless-wound interpretation and connects it back to the poisoned flask evidence. | Next beat: `The Doctor's Deception` |
| 12 | `go library`; `go drawing room`; `go main entrance hall`; `go main corridor`; `go guest wing`; `interview Dr Percival Vance about the paper hidden in his medical bag` | Treats the interview as the planned interference/deception beat. Applies the new clue and advances the PlotPlan. | Next beat: `The Loyal Wife` |
| 13 | `go main corridor`; `go main entrance hall`; `go drawing room`; `interview Eleanor Vance about her movements during the masquerade` | Updates Eleanor's testimony state and advances to the next evidence location. | Next beat: `The Gardener's Secret` |
| 14 | `go conservatory`; `examine EV-03` | Marks the monkshood glove clue as discovered and advances the investigation. | Next beat: `The Beaded Handbag` |
| 15 | `go drawing room`; `go main entrance hall`; `examine EV-07` | Marks the handbag/petal clue as discovered and advances the chain of evidence. | Next beat: `The Midnight Reckoning` |
| 16 | `go drawing room`; `go library`; `examine EV-04` | Applies the final timeline/evidence connection before the confrontation. | Next beat: `The Final Mask Removed` |
| 17 | `go study`; `examine EV-01` | Applies the final flask clue in the confrontation context and resolves the case. | `The case is closed.` |

## Exceptional Walkthrough: Story Accommodation

In the exceptional walkthrough, the player first performs a normal planned action, then performs an unexpected action that materially changes the Study. This triggers the accommodation path: the system preserves the hidden mystery truth, applies the player's physical effects to the world state, and adapts the future story path.

| Step | User action(s) | Drama / system action | Result shown to player |
| --- | --- | --- | --- |
| 1 | `/hint` | Reports the current planned beat and location. | Current next beat: `The Witness Fails to Appear` in `The Study` |
| 2 | `examine the desk` | Treats the action as planned story progress and advances normally. No repair is needed. | Next beat: `A Room Disturbed` |
| 3 | `attack / break the gas lamp` | Classifies the action as exceptional because it changes the physical conditions needed by the planned investigation path. Applies player-caused effects to the world state. | Narration describes flames starting in the Study and debris partially blocking the doorway. |
| 4 | `System accommodation after the exceptional action` | The causal span is disrupted, so the Drama Manager accommodation path removes or rewrites affected future beats while preserving the hidden mystery truth. | The story continues on an adapted path. |
| 5 | `/hint` | Shows the repaired next beat after accommodation. | New next beat: `The Silent Demise` in `Sir Alistair's Study` |
| 6 | `/quit` | Ends the demonstration run. | Game exits cleanly with `Farewell.` |