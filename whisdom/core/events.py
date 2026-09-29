"""
Generic match representation. A game adapter's only job is to produce these.

Time is always FRAMES (int). Actors are always `slot` (int, stable within a match).
Action names are free-form strings; core never hardcodes a game's vocabulary.
"""
from dataclasses import dataclass, field
from typing import Optional, List, Dict

@dataclass
class Event:
    """
    A single observed event.

    For `kind="ko"`, `slot` is the VICTIM — the player who died. Some games
    record the killer instead; it is the adapter's job to normalise, so that
    everything downstream can rely on one meaning.
    """
    frame: int
    slot: int              # for kind="ko" this is the VICTIM
    action: str            # e.g. "Dodge", "Light"
    kind: str = "input"    # "input" | "ko" | "custom"
    by: Optional[int] = None   # for kind="ko": the slot credited with the kill

@dataclass
class Player:
    slot: int
    display_name: Optional[str] = None
    identity_id: Optional[str] = None      # deliberately unused for now
    character: Optional[str] = None
    character_id: Optional[int] = None
    team: Optional[int] = None
    is_bot: Optional[bool] = None

@dataclass
class Match:
    match_id: str
    game: str
    patch: Optional[str]
    fps: int
    duration_frames: int
    players: List[Player] = field(default_factory=list)
    events: List[Event] = field(default_factory=list)
    meta: Dict = field(default_factory=dict)

    def inputs(self, slot=None):
        return [e for e in self.events if e.kind=="input" and (slot is None or e.slot==slot)]
    def kos(self):
        return [e for e in self.events if e.kind=="ko"]
