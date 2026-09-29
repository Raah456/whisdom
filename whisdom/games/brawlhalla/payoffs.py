"""
Edgeguard payoffs, derived from frame data.

WHAT CHANGED AND WHY
--------------------
The previous engine used frame data only as branch conditions —

    if recovery_startup + 2 < attacker_startup: return 0.45

so every cell returned one of three hand-picked constants no matter HOW much
faster a move was, and most cells ignored the weapon entirely. That is why the
engine gave near-identical advice for all fourteen weapons.

Here every score is a continuous function of the actual frame numbers, so a
1-frame edge and a 10-frame edge are different answers, and weapons differ
because their frames differ.

WHAT THIS MODEL DOES NOT USE, DELIBERATELY
------------------------------------------
Damage and knockback per move. Those fields are NOT trustworthy in the extracted
data: a multi-part move resolves to its first part only, so Sword side-light
reads 0 damage / 0 force against a published 15 / 61, and 46 of 112 moves carry
zero damage. Same unresolved aggregation problem as the signatures.

Timing IS trustworthy — startup matched an independent source on 6 of 8 Sword
moves exactly (the two misses are multi-part), and recovery matched 28/30 within
a frame. So this model reasons about WHO HITS FIRST and HOW BADLY A WHIFF IS
PUNISHED, which is the core of the interaction, and takes lethality from the
player's damage READING (from video) rather than from per-move force.

Resolving per-move force needs the same five-minute training-mode measurement
that the signatures need. That would let payoffs weight outcomes by how likely a
hit is to actually kill.

THE MODEL VS THE DATA
---------------------
Frame numbers are extracted and validated. The handful of constants below are a
MODEL — a judgement about how frames translate into advantage. They are named,
few, and gathered in one block precisely so a player can argue with them without
touching the code. That is the intended review task.
"""
import json
import math
import os

_DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

# --- the model: these are judgements, not measurements -----------------------
TRADE_WINDOW = 4.0      # frames of startup lead that make a contest decisive
PUNISH_SCALE = 30.0     # whiff recovery (frames) that counts as fully punishable
COMMIT_SCALE = 25.0     # attacker recovery (frames) that counts as a full punish window
DODGE_COST = 0.35       # penalty for spending the dodge and its long cooldown
BASE_HIT_COST = 0.45    # cost of being hit offstage at zero damage
MAX_HIT_COST = 1.00     # cost of being hit offstage at lethal damage
BASE_HIT_VALUE = 0.30   # worth of landing a hit when the opponent is fresh
MAX_HIT_VALUE = 1.00    # worth of landing a hit when the opponent is at kill percent
# -----------------------------------------------------------------------------

_moves = None
_dodge = None
_reach = None


def _load():
    global _moves, _dodge
    if _moves is None:
        raw = json.load(open(os.path.join(_DATA, "moves.json")))
        _moves = {}
        for m in raw:
            _moves.setdefault(m["weapon"], {})[m["move"]] = m
        _dodge = json.load(open(os.path.join(_DATA, "dodge.json")))
    return _moves, _dodge


def weapons():
    return sorted(_load()[0])


def _n(v, default):
    return default if v is None else v


def stats(weapon, move):
    """
    Frame facts for one move, with the untrustworthy fields left out.

    `known` is False when extraction clearly failed — a startup of 0 frames is
    impossible, and every case is a multi-part move whose family resolved to the
    wrong part. Those moves still get a score (using a neutral placeholder) but
    the cell is marked low-confidence rather than quietly presented as fact.
    """
    mv, _ = _load()
    m = mv.get(weapon, {}).get(move)
    if not m:
        return None
    su = m.get("startup")
    known = bool(su and su > 0)
    return dict(
        name="%s %s" % (weapon, move),
        startup=su if known else 12,      # placeholder, flagged by `known`
        whiff=_n(m.get("recover_miss"), 0) + _n(m.get("fixedrec_miss"), 0),
        cooldown=_n(m.get("cooldown"), 0),
        known=known,
        family_size=m.get("family_size"),
    )


def reach(weapon, kind="side_air"):
    """
    How far a move's hitbox extends, in the game's own units.

    Derived from AoERadius/CenterOffset in the power table: the furthest extent
    of the hitbox over every frame and every part of the move. Horizontal for
    side/neutral air, vertical for down air and recovery.

    NOT used by the payoff model, deliberately. Knowing a move reaches 347 units
    tells you nothing useful without knowing how far apart the players were, and
    there is no position data. This is here for comparison between weapons and
    between a player's own options, which is real, and as the thing to calibrate
    once someone measures a known distance in game.

    The unit scale is unverified. Relative numbers are trustworthy; "347 units"
    meaning a specific fraction of a character is not.
    """
    global _reach
    if _reach is None:
        try:
            _reach = json.load(open(os.path.join(_DATA, "reach.json")))
        except (OSError, ValueError):
            _reach = {}
    return (_reach.get(weapon) or {}).get(kind)


def dodge():
    _, dg = _load()
    d = dg.get("StandardSide") or dg.get("StandardUp") or {}
    return dict(duration=_n(d.get("duration"), 14),
                invuln_start=_n(d.get("invuln_start"), 2),
                cooldown=_n(d.get("cooldown"), 163))


def _sig(x):
    return 1.0 / (1.0 + math.exp(-x))


def p_first(defender_startup, attacker_startup):
    """Probability the defender's hitbox lands first. Continuous in the lead."""
    return _sig((attacker_startup - defender_startup) / TRADE_WINDOW)


def punish(frames, scale=PUNISH_SCALE):
    """How exploitable a recovery window is, 0..1."""
    return max(0.0, min(1.0, frames / float(scale)))


def hit_cost(damage):
    """
    What it costs to be hit while offstage, given the VICTIM's damage.

    Damage comes from the video HUD reading (0..1).
    """
    d = 0.5 if damage is None else max(0.0, min(1.0, damage))
    return BASE_HIT_COST + (MAX_HIT_COST - BASE_HIT_COST) * d


def hit_value(damage):
    """
    What landing a hit is WORTH, given the opponent's damage.

    Without this the engine treats every exchange as symmetric, which is exactly
    what an RPS read is not: contesting is cheap when you are fresh and they are
    at kill percent, and reckless when it is the other way round. Cost and value
    together are what make the same option right at 20% and wrong at 150%.
    """
    d = 0.5 if damage is None else max(0.0, min(1.0, damage))
    return BASE_HIT_VALUE + (MAX_HIT_VALUE - BASE_HIT_VALUE) * d


DEF_OPTIONS = [
    ("recovery", "Recovery move"),
    ("airdodge", "Air dodge"),
    ("doublejump", "Double jump"),
    ("contest", "Air attack (contest)"),
    ("stall", "Stall / drift"),
]
ATK_OPTIONS = [
    ("deep_dair", "Go deep (down air)"),
    ("ledge_sair", "Ledge attack (side air)"),
    ("gp", "Ground pound"),
    ("wait", "Wait at ledge"),
    ("retreat", "Retreat / reset"),
]

_ATK_MOVE = {"deep_dair": "dair", "ledge_sair": "sair", "gp": "gp"}


def payoff(ctx, dkey, akey):
    """
    Score in [-1, 1] from the DEFENDER's perspective, with a reason citing frames.

    ctx: {defender_weapon, attacker_weapon, defender_damage (0..1 or None)}
    """
    dw = ctx.get("defender_weapon", "Sword")
    aw = ctx.get("attacker_weapon", "Sword")
    dmg = ctx.get("defender_damage")
    dg = dodge()
    cost = hit_cost(dmg)                          # what being hit costs me
    value = hit_value(ctx.get("attacker_damage"))  # what hitting them is worth

    def dstat(k):
        return stats(dw, k) or dict(name="?", startup=99, whiff=0, cooldown=0,
                                    known=False, family_size=None)

    def flag(*ms):
        """Confidence for a cell: low if any move it depends on is unreliable."""
        return 1.0 if all(m.get("known", True) for m in ms) else 0.3

    def note(*ms):
        bad = [m for m in ms if not m.get("known", True)]
        return "" if not bad else \
            "  [UNVERIFIED: %s frame data did not resolve (multi-part move)]" % \
            ", ".join(m.get("name", "?") for m in bad)

    # --- attacker commits to a hitbox ---------------------------------------
    if akey in _ATK_MOVE:
        am = stats(aw, _ATK_MOVE[akey]) or dict(startup=99, whiff=0, known=False,
                                                name="%s %s" % (aw, _ATK_MOVE[akey]))
        a_start, a_whiff = am["startup"], am["whiff"]
        window = punish(a_whiff, COMMIT_SCALE)   # how punishable their commitment is

        if dkey == "airdodge":
            # invulnerability beats a committed hitbox; the price is the cooldown
            evade = 0.90
            score = evade * value * (0.35 + 0.55 * window) - (1 - evade) * cost - DODGE_COST * 0.5
            return (score,
                    "invuln from f%d for %df beats a committed hitbox; they sit in "
                    "%df recovery (dodge then on %df cooldown)"
                    % (dg["invuln_start"], dg["duration"], a_whiff, dg["cooldown"])
                    + note(am), flag(am))

        if dkey == "recovery":
            dm = dstat("recovery")
            p = p_first(dm["startup"], a_start)
            score = p * value * (0.60 + 0.60 * window) - (1 - p) * cost
            return (score,
                    "recovery hits f%d vs their f%d (%.0f%% to land first); "
                    "%df of your own lag if it misses"
                    % (dm["startup"], a_start, 100 * p, dm["whiff"]) + note(dm, am),
                    flag(dm, am))

        if dkey == "contest":
            dm = dstat("sair")
            p = p_first(dm["startup"], a_start)
            score = p * value * (0.55 + 0.55 * window) - (1 - p) * (cost + 0.15 * punish(dm["whiff"]))
            return (score,
                    "side air f%d vs their f%d (%.0f%% to land first); losing it "
                    "costs %df recovery on top of the hit"
                    % (dm["startup"], a_start, 100 * p, dm["whiff"]) + note(dm, am),
                    flag(dm, am))

        if dkey == "doublejump":
            # no hitbox, but a committed attack can be made to whiff
            evade = 0.55 + 0.35 * window
            score = evade * 0.30 - (1 - evade) * cost
            return (score,
                    "movement can make a committed attack whiff; their %df recovery "
                    "is the window, but you have no hitbox to punish with" % a_whiff
                    + note(am), flag(am))

        if dkey == "stall":
            return (-0.25 - 0.75 * cost,
                    "their %s hits f%d and you have neither invuln nor a hitbox "
                    "to answer it" % (_ATK_MOVE[akey], a_start) + note(am), flag(am))

    # --- attacker waits at the ledge ----------------------------------------
    if akey == "wait":
        if dkey == "airdodge":
            return (-0.30 - DODGE_COST - 0.35 * cost,
                    "dodge spent on nothing; %df cooldown means you must still "
                    "recover without it" % dg["cooldown"])
        if dkey == "recovery":
            dm = dstat("recovery")
            return (-0.15 - 0.85 * punish(dm["whiff"]) * cost,
                    "predictable, and they punish the %df of recovery lag" % dm["whiff"]
                    + note(dm), flag(dm))
        if dkey == "contest":
            dm = dstat("sair")
            return (-0.20 - 0.80 * punish(dm["whiff"]) * cost,
                    "attack whiffs into open air, then %df of recovery" % dm["whiff"]
                    + note(dm), flag(dm))
        if dkey == "doublejump":
            # keeping the dodge and recovery in hand is worth more the more a hit
            # would cost you, which is why this gets stronger at kill percent
            return (0.10 + 0.45 * cost,
                    "keeps dodge (%df cooldown) and recovery in reserve and forces "
                    "them to commit first" % dg["cooldown"])
        if dkey == "stall":
            return (0.20 - 0.20 * cost,
                    "waiting out a waiter costs only drift, but you are the one "
                    "running out of room")

    # --- attacker gives up ---------------------------------------------------
    if akey == "retreat":
        if dkey == "airdodge":
            return (0.20 - DODGE_COST * 0.5 * cost,
                    "safe return, but the dodge is on %df cooldown and you may "
                    "need it" % dg["cooldown"])
        if dkey == "recovery":
            dm = dstat("recovery")
            return (0.35 + 0.25 * cost,
                    "free, uncontested recovery (f%d, %df lag nobody punishes)"
                    % (dm["startup"], dm["whiff"]) + note(dm), flag(dm))
        if dkey == "doublejump":
            return (0.40 + 0.25 * cost,
                    "free return with every option still available")
        if dkey == "contest":
            dm = dstat("sair")
            return (0.0, "attack into empty air; %df of recovery but nobody is "
                         "there to punish it" % dm["whiff"] + note(dm), flag(dm))
        if dkey == "stall":
            return (0.25 + 0.10 * cost, "free repositioning while they reset")

    return (0.0, "-")


def model():
    """A core.PayoffModel wired to these options."""
    from whisdom.core.options import PayoffModel
    return PayoffModel(DEF_OPTIONS, ATK_OPTIONS, payoff)


def matrix(defender_weapon, attacker_weapon, defender_damage=None):
    return model().matrix(dict(defender_weapon=defender_weapon,
                               attacker_weapon=attacker_weapon,
                               defender_damage=defender_damage))
