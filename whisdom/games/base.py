"""
The contract every game adapter must satisfy.

whisdom is one platform with one agent; games plug in as adapters. Anything a
game needs to customise is declared here, so `whisdom.agent` never has to know
which game it is looking at.

Adding a game means creating `whisdom/games/<name>/` that exposes a GameAdapter.
Nothing in core/ or agent/ should need to change.
"""
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

@dataclass
class PressureConfig:
    """
    Which action to measure for the 'quality collapses under pressure' analysis.

    In Brawlhalla this is the dodge: it lasts a fixed number of frames, and a
    second press inside that window is provably discarded by the game. Most
    fighters have an equivalent committed defensive option.
    """
    action: str                     # e.g. "Dodge"
    duration_frames: int            # re-press inside this window does nothing
    label: str = "defensive action"
    tracked_actions: List[str] = field(default_factory=list)

@dataclass
class GameAdapter:
    name: str                                   # "brawlhalla"
    display_name: str                           # "Brawlhalla"
    load_match: Callable                        # (path) -> core.Match
    action_model: object                        # core.detect.ActionModel
    categories: Dict[str, List[str]]            # metric groupings
    replay_ext: str = ".replay"
    replay_paths: Dict[str, List[str]] = field(default_factory=dict)   # per sys.platform key
    character_noun: str = "Character"            # "Legend", "Fighter", "Character"
    fps: int = 60
    pressure: Optional[PressureConfig] = None
    replay_help: str = "Check the game's own replay browser for the folder location."

REGISTRY: Dict[str, GameAdapter] = {}

def register(adapter: GameAdapter):
    REGISTRY[adapter.name] = adapter
    return adapter

def get(name: str) -> GameAdapter:
    if name not in REGISTRY:
        _autoload()
    if name not in REGISTRY:
        raise SystemExit("unknown game %r. Available: %s"
                         % (name, ", ".join(sorted(REGISTRY)) or "none"))
    return REGISTRY[name]

def available() -> List[str]:
    _autoload()
    return sorted(REGISTRY)

def _autoload():
    """Import every game subpackage so it can self-register."""
    import pkgutil, importlib, whisdom.games as pkg
    for m in pkgutil.iter_modules(pkg.__path__):
        if m.ispkg:
            try: importlib.import_module("whisdom.games.%s" % m.name)
            except Exception: pass
