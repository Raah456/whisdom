"""
Properties the payoff engine must hold.

These are not checks that the advice is CORRECT — only a player can say that.
They check the engine is doing what it claims: reasoning from frame data and
game state rather than returning constants. The old engine failed most of these.

    python3 tests/test_payoffs.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from whisdom.core.options import expected_values
from whisdom.games.brawlhalla import payoffs as P

TEND = {"deep_dair": 0.5, "ledge_sair": 0.3, "wait": 0.2}


def _best(weapon, mine, theirs, atk="Sword"):
    rows = P.model().matrix(dict(defender_weapon=weapon, attacker_weapon=atk,
                                 defender_damage=mine, attacker_damage=theirs))
    return expected_values(rows, TEND)


def check(name, ok, detail=""):
    print("   %-52s %s%s" % (name, "ok" if ok else "FAIL", "  " + detail if detail else ""))
    return 0 if ok else 1


def run():
    fails = 0

    # 1. a faster move must be more likely to land first
    fails += check("faster startup wins more exchanges",
                   P.p_first(5, 15) > P.p_first(11, 15) > P.p_first(16, 15))

    # 2. the engine must not give every weapon the same answer
    picks = {w: _best(w, 0.5, 0.5)[0][0] for w in P.weapons()}
    fails += check("advice differs across weapons", len(set(picks.values())) > 1,
                   "%d distinct" % len(set(picks.values())))

    # 3. and the scores themselves must differ, not just the ranking
    evs = {w: round(_best(w, 0.5, 0.5)[0][1], 3) for w in P.weapons()}
    fails += check("scores differ across weapons", len(set(evs.values())) > 3,
                   "%d distinct values" % len(set(evs.values())))

    # 4. game state must change the answer for most weapons
    flips = 0
    for w in P.weapons():
        got = {_best(w, me, them)[0][0] for me in (0.1, 0.9) for them in (0.1, 0.9)}
        if len(got) > 1:
            flips += 1
    fails += check("damage state changes the answer", flips >= 8, "%d of 14 weapons" % flips)

    # 5. being hit must cost more at high damage; landing one must be worth more
    fails += check("hit cost rises with own damage", P.hit_cost(0.9) > P.hit_cost(0.1))
    fails += check("hit value rises with their damage", P.hit_value(0.9) > P.hit_value(0.1))

    # 6. risk aversion: at kill percent against a fresh opponent, contesting
    #    must not be preferred over simply surviving
    ev = _best("Sword", 0.95, 0.05)
    risky = [o for o, _v, _r in ev].index("Air attack (contest)")
    safe = [o for o, _v, _r in ev].index("Double jump")
    fails += check("at kill percent, survival beats contesting", safe < risky)

    # 7. moves whose frame data did not resolve must be flagged, not presented
    #    as fact (Lance recovery reads 0 frames of startup, which is impossible)
    lance = P.stats("Lance", "recovery")
    fails += check("unresolved frame data is flagged", lance["known"] is False)
    rows = P.matrix("Lance", "Sword", defender_damage=0.5)
    rec = [r for r in rows if r["key"] == "recovery"][0]
    fails += check("low confidence propagates to the cell", rec["confidence"] < 1.0,
                   "confidence %.1f" % rec["confidence"])
    sword = [r for r in P.matrix("Sword", "Sword", defender_damage=0.5)
             if r["key"] == "recovery"][0]
    fails += check("verified weapons keep full confidence", sword["confidence"] == 1.0)

    # 8. every reason must cite real frames, so advice is auditable
    bare = [c["why"] for r in P.matrix("Sword", "Sword", 0.5) for c in r["cells"].values()
            if "f" not in c["why"] and c["why"] != "-"]
    fails += check("reasons cite frame numbers", not bare)

    print("payoffs: %d check(s) failed" % fails)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(run())
