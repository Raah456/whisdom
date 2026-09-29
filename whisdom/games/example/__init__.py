"""
A minimal reference adapter.

Not a real game — it exists to prove the platform is genuinely game-agnostic and
to show exactly what a new game must supply. If this stops working, something
game-specific has leaked back into core/ or agent/.

To add a real game, copy this file, implement `load_match`, and delete the rest.
"""
import os, hashlib
from whisdom.core.events import Match, Player, Event
from whisdom.core.detect import ActionModel
from whisdom.games.base import GameAdapter, PressureConfig, register

FPS = 60
# Any vocabulary at all — core never hardcodes action names.
CATEGORIES = {"attack": ["Strike", "Slam"], "movement": ["Left", "Right"],
              "defence": ["Guard"], "mobility": ["Hop"]}
ACTION_MODEL = ActionModel(busy_frames={"Guard": 20, "Strike": 10, "Slam": 16}, default_busy=0)

def load_match(path):
    """A real adapter parses the game's replay format here."""
    mid = "ex_" + hashlib.sha256(open(path, "rb").read()).hexdigest()[:16]
    players = [Player(slot=0, display_name="P1", character="Alpha", character_id=1),
               Player(slot=1, display_name="P2", character="Beta",  character_id=2)]
    events = [Event(frame=f, slot=f % 2, action=a, kind="input")
              for f, a in enumerate(["Left","Strike","Guard","Guard","Right","Slam"] * 40)]
    return Match(match_id=mid, game="example", patch="1.0", fps=FPS,
                 duration_frames=max(e.frame for e in events),
                 players=players, events=events,
                 meta=dict(source_file=os.path.basename(path)))

ADAPTER = register(GameAdapter(
    name="example", display_name="Example Fighter",
    load_match=load_match, action_model=ACTION_MODEL, categories=CATEGORIES,
    replay_ext=".exrep", character_noun="Fighter", fps=FPS,
    replay_paths={"linux": [os.path.expanduser("~/ExampleReplays")],
                  "darwin": [os.path.expanduser("~/ExampleReplays")],
                  "win": [os.path.expanduser("~/ExampleReplays")]},
    pressure=PressureConfig(action="Guard", duration_frames=20, label="guard",
                            tracked_actions=["Guard","Strike","Slam","Hop","Left","Right"]),
))
