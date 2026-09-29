"""Brawlhalla adapter."""
import sys
from whisdom.games.base import GameAdapter, PressureConfig, register
from .adapter import load_match, ACTION_MODEL
from .constants import CATEGORIES, INPUT_BITS, FPS, DODGE_DURATION
from .heroes import HEROES, NAMES
from .levels import LEVELS

def _home(*p):
    import os; return os.path.join(os.path.expanduser("~"), *p)

ADAPTER = register(GameAdapter(
    name="brawlhalla",
    display_name="Brawlhalla",
    load_match=load_match,
    action_model=ACTION_MODEL,
    categories=CATEGORIES,
    replay_ext=".replay",
    character_noun="Legend",
    fps=FPS,
    replay_paths={
        "win": [_home("Documents","Brawlhalla","replays"),
                _home("BrawlhallaReplays"),
                _home("Documents","BrawlhallaReplays")],
        "darwin": [_home("Documents","Brawlhalla","replays"),
                   _home("Library","Application Support","Brawlhalla","replays"),
                   _home("Library","Containers","com.blueMammoth.Brawlhalla","Data",
                         "Documents","Brawlhalla","replays"),
                   _home("BrawlhallaReplays")],
        "linux": [_home("Documents","Brawlhalla","replays"),
                  _home("BrawlhallaReplays")],
    },
    replay_help="In Brawlhalla: Account -> Replays -> the blue folder icon.",
    pressure=PressureConfig(
        action="Dodge",
        duration_frames=DODGE_DURATION,
        label="dodge",
        tracked_actions=["Dodge","Light","Heavy","Jump","ThrowPickup",
                         "Left","Right","AimDown","AimUp"]),
))
