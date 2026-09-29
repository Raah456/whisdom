"""
Generic option / payoff engine.

A game supplies: option lists for each role, and a payoff function returning
(score, reason) from the defender's perspective. Core computes EV against a
tendency distribution. Nothing game-specific lives here.
"""
class PayoffModel:
    def __init__(self, defender_options, attacker_options, payoff_fn):
        self.d=defender_options; self.a=attacker_options; self.fn=payoff_fn
    def matrix(self, ctx):
        """
        A payoff function returns (score, why) or (score, why, confidence).

        Confidence below 1.0 means the underlying frame data is not trustworthy
        for this cell — the score is still computed, but callers should surface
        the doubt rather than present it as fact.
        """
        rows=[]
        for dk,dlabel in self.d:
            cells={}; worst=1.0
            for ak,alabel in self.a:
                r=self.fn(ctx,dk,ak)
                s,why = r[0], r[1]
                conf = r[2] if len(r)>2 else 1.0
                worst=min(worst,conf)
                cells[ak]=dict(score=s,why=why,label=alabel,confidence=conf)
            rows.append(dict(key=dk,option=dlabel,cells=cells,confidence=worst))
        return rows

def expected_values(rows, tendencies):
    """EV per option against a tendency distribution, best first."""
    out=[]
    for r in rows:
        ev=sum(r["cells"][k]["score"]*p for k,p in tendencies.items() if k in r["cells"])
        out.append((r["option"],ev,r))
    return sorted(out,key=lambda x:-x[1])
