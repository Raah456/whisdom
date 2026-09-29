"""
Where the tests find their inputs.

The suites need three things that cannot live in the repo: a folder of replays,
one specific verified replay, and the recording paired with it. Replays and
recordings are personal gameplay data and are gitignored.

Every path resolves in this order:

    1. a command-line argument, if the test takes one
    2. an environment variable
    3. tests/fixtures/ inside the repo
    4. skip, with a message saying exactly what to set

Point them at your own data:

    export WHISDOM_REPLAYS=~/BrawlhallaReplays
    export WHISDOM_REPLAY="$WHISDOM_REPLAYS/[10.09] SmallFortressof.replay"
    export WHISDOM_VIDEO=~/recordings/match.mp4

or drop the files into tests/fixtures/ and they will be found automatically.

Note that WHISDOM_REPLAY and WHISDOM_VIDEO must be the SAME match — the vision
and ground-truth suites check them against each other, which is the whole point.
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
FIXTURES = os.path.join(HERE, "fixtures")

# The one match verified against the player and a screen recording.
VERIFIED_REPLAY_NAME = "[10.09] SmallFortressof.replay"


def schema():
    """The match document contract. Always inside the repo."""
    return os.path.join(REPO, "schema", "match.schema.json")


def _first(*candidates):
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return None


def _has_replays(d):
    """A folder counts only if it actually holds replays. tests/fixtures/ exists
    because of its README, and an empty folder reporting '0 documents valid'
    reads far too much like a pass."""
    if not d or not os.path.isdir(d):
        return False
    for _root, _dirs, files in os.walk(d):
        if any(f.endswith(".replay") for f in files):
            return True
    return False


def replays(arg=None):
    """A folder that actually contains replay files."""
    for c in (arg, os.environ.get("WHISDOM_REPLAYS"), FIXTURES):
        if _has_replays(c):
            return c
    return None


def verified_replay(arg=None):
    """The specific replay the ground-truth and vision suites depend on."""
    return _first(arg,
                  os.environ.get("WHISDOM_REPLAY"),
                  os.path.join(FIXTURES, VERIFIED_REPLAY_NAME),
                  os.path.join(os.environ.get("WHISDOM_REPLAYS") or "",
                               VERIFIED_REPLAY_NAME))


def video(arg=None):
    """The recording paired with the verified replay."""
    v = _first(arg, os.environ.get("WHISDOM_VIDEO"))
    if v:
        return v
    if os.path.isdir(FIXTURES):
        for f in sorted(os.listdir(FIXTURES)):
            if f.lower().endswith((".mp4", ".mkv", ".mov")):
                return os.path.join(FIXTURES, f)
    return None


def missing(what, env):
    """
    A skip message that says what to do about it.

    Worth being loud: a skipped test and a passing test look almost identical in
    a terminal, and this project has already shipped a silently broken component
    once because nothing failed.
    """
    return ("SKIPPED — no %s. Set %s, or put the file in tests/fixtures/.\n"
            "         This is a SKIP, not a pass." % (what, env))
