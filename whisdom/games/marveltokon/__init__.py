"""
Marvel Tokon: Fighting Souls adapter — SCAFFOLD. `load_match` is not implemented.

Arc System Works / Sony Interactive Entertainment. Released 2026-08-06 on PS5 and
Windows. A 4v4 tag fighter: each player starts with one fighter plus an assist and
unlocks a lineup of four over the course of a match.

WHAT IS REAL HERE: the adapter registers, and every field below that is filled in
is either public fact or an explicitly-labelled assumption.

WHAT IS NOT: the replay format has not been decoded by anyone, so `load_match`
raises. Frame data has not been extracted, so `ACTION_MODEL` is empty and
`pressure` is None. Both degrade to *silence* rather than to invented numbers —
an empty ActionModel detects no wasted inputs, and `pressure=None` makes
`whisdom pressure` exit with "Marvel Tokon does not define a pressure action".
That is deliberate. See CONTRIBUTING.md rules 4 and 5: ship the doubt, and never
let the engine emit a confident constant.

Read MARVEL_TOKON.md for the design notes and the open questions.
"""
import os

from whisdom.core.events import Match, Player, Event      # noqa: F401  (Match/Player/Event used once load_match is written)
from whisdom.core.detect import ActionModel
from whisdom.games.base import GameAdapter, PressureConfig, register   # noqa: F401  (PressureConfig used once frame data exists)

FPS = 60   # ASSUMED. Arc System Works fighters target 60fps, and the PC launch's
           # widely-reported "broken 60 FPS" issue implies 60 is the intended tick
           # rate. Verify against a decoded replay before trusting any frame math.

# Free-form vocabulary; core hardcodes none. Deliberately tag-fighter-shaped
# rather than borrowed from Brawlhalla, so the example adapter keeps working as a
# leak detector. This is a first cut and will change once inputs are decoded.
CATEGORIES = {
    "attack":    ["Light", "Medium", "Heavy", "Special"],
    "super":     ["Super", "TeamSuper"],
    "assist":    ["AssistCall", "AssistAction"],
    "tag":       ["TagIn", "TagCombo", "ActiveSwitch"],
    "movement":  ["Dash", "AirDash", "Jump", "Walk"],
    "defence":   ["Block", "PushBlock", "Reversal", "ThrowEscape"],
    "throw":     ["Throw"],
}

# UNKNOWN per-move. Empty on purpose: `busy()` returns default_busy=0 for every
# action, so the wasted-input detector stays silent instead of firing on a made-up
# number. Populate from measured frame data, not from a guess.
ACTION_MODEL = ActionModel(busy_frames={}, default_busy=0)


def load_match(path):
    """Parse a Tokon replay into a core.Match. NOT IMPLEMENTED.

    A real implementation must produce frames (never ms), slots (never names),
    free-form action strings, and — per core.events.Event — KO events whose
    `slot` is the VICTIM, normalising whatever the game actually records.

    Blocked on, in order:
      1. Legitimately-obtained Tokon replay files. They are not in the game's
         install directory; they live in the title's save data.
      2. The container format, and whether a saved match is a full input log or
         only a seed plus metadata. Rollback-netcode titles sometimes store the
         latter, which changes what is recoverable at all.
      3. A frame-accurate input decode, and a KO / fighter-defeat decode.

    Raising is the correct behaviour until then: a half-real Match would pass the
    golden-file regression suite and lock in a wrong model (CONTRIBUTING.md #2).
    """
    raise NotImplementedError(
        "Marvel Tokon replay format is not decoded. See "
        "whisdom/games/marveltokon/__init__.py and MARVEL_TOKON.md."
    )


def _home(*p):
    return os.path.join(os.path.expanduser("~"), *p)


ADAPTER = register(GameAdapter(
    name="marveltokon",
    display_name="Marvel Tokon: Fighting Souls",
    load_match=load_match,
    action_model=ACTION_MODEL,
    categories=CATEGORIES,

    # UNKNOWN — placeholder. Do not trust; verify against real save data.
    replay_ext=".replay",

    # UNKNOWN. Left empty rather than guessed: `whisdom where` reports "no
    # candidate folders" instead of confidently pointing at a path that does not
    # exist. The PC build is UE5 (Steam app 3787240); UE5 titles commonly write
    # under %LOCALAPPDATA%\<Project>\Saved\, but that is unverified for Tokon,
    # and PS5 replays may not be file-accessible at all.
    replay_paths={"win": [], "darwin": [], "linux": []},

    replay_help=("Replay location not yet confirmed. Tokon's replays are in the "
                 "title's save data, not the install folder. Check the in-game "
                 "replay browser."),

    character_noun="Fighter",
    fps=FPS,

    # UNKNOWN. The natural candidate is a committed defensive option (push block
    # or a reversal), but its duration is unmeasured. None makes the pressure
    # analysis refuse to run with a clear message, which is correct.
    pressure=None,
))
