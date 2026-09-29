"""
Report generation. Reads from the store, never re-parses.

Two outputs:
  match_report(match_id) - one match: result, ranked moments, per-player metrics
  profile_report(name)   - across all stored matches: habits, trends, characters
"""
import os, json, html, statistics as st
from collections import Counter, defaultdict

CSS="""
*{box-sizing:border-box}body{margin:0;background:#12141a;color:#e8eaf0;
font:14px/1.6 ui-sans-serif,system-ui,-apple-system,sans-serif}
.wrap{max-width:1080px;margin:0 auto;padding:28px}
h1{font-size:22px;margin:0 0 4px}h2{font-size:15px;margin:26px 0 10px;color:#cbd2e0}
.sub{color:#8b93a7;font-size:13px;margin-bottom:6px}
.panel{background:#1a1d26;border:1px solid #272b38;border-radius:9px;padding:16px;margin-bottom:14px}
table{width:100%;border-collapse:collapse;font-size:13px}
th{text-align:left;color:#8b93a7;font-weight:600;padding:7px 10px;border-bottom:1px solid #272b38}
td{padding:7px 10px;border-bottom:1px solid #1f2330}
tr:last-child td{border-bottom:none}
.num{text-align:right;font-variant-numeric:tabular-nums}
.sev5{color:#ff6b6b;font-weight:600}.sev4{color:#ff9f43}.sev3{color:#ffd24d}
.sev2{color:#9aa4bb}.sev1{color:#6b7385}
.big{font-size:26px;font-weight:600;display:block}
.stat{display:flex;gap:34px;flex-wrap:wrap}.stat div span{color:#8b93a7;font-size:11px}
.win{color:#7de08a}.loss{color:#ff8080}
.note{color:#8b93a7;font-size:12px;margin-top:8px}
.bar{height:6px;background:#252a38;border-radius:3px;overflow:hidden;margin-top:4px}
.bar i{display:block;height:100%;background:#4d7fc9}
"""

def _page(title, body):
    return ("<!DOCTYPE html><html><head><meta charset='utf-8'><title>%s</title>"
            "<style>%s</style></head><body><div class='wrap'>%s</div></body></html>"
            %(html.escape(title), CSS, body))

def _fmt(v, nd=1):
    return "-" if v is None else (("%%.%df"%nd)%v if isinstance(v,float) else str(v))

def _death_context(doc, fps, pressure=None, window_frames=300):
    """
    For each KO, reconstruct what happened in the seconds before it.
    Returns per-death: who died, the input sequence for both players, and
    the dodge-quality figure for the player who died.
    """
    names = {p["slot"]: (p.get("display_name") or "slot %d" % p["slot"]) for p in doc["players"]}
    by_slot = {}
    for e in doc["observations"]["inputs"]:
        by_slot.setdefault(e["slot"], []).append((e["frame"], e["action"]))
    out = []
    for k in sorted(doc["observations"]["kos"], key=lambda x: x["frame"]):
        end = k["frame"]; start = max(0, end - window_frames)
        seqs = {}
        for slot, ev in by_slot.items():
            seqs[slot] = [(f, a) for f, a in ev if start <= f <= end]
        # committed-action quality for the player who died (which action, and how
        # long it lasts, comes from the game adapter)
        dodges, wasted = [], 0
        if pressure:
            dodges = [f for f, a in by_slot.get(k["slot"], [])
                      if a == pressure.action and start <= f <= end]
            wasted = sum(1 for i in range(1, len(dodges))
                         if dodges[i] - dodges[i-1] < pressure.duration_frames)
        out.append(dict(frame=end, slot=k["slot"], who=names.get(k["slot"], "?"),
                        start=start, seqs=seqs, names=names,
                        dodges=len(dodges), wasted=wasted))
    return out

def match_report(store, match_id, out_path, adapter=None):
    noun = adapter.character_noun if adapter else "Character"
    pressure = adapter.pressure if adapter else None
    doc=store.load(match_id)
    if not doc: raise ValueError("unknown match "+match_id)
    m=doc["match"]; fps=m["fps"] or 60
    names={p["slot"]: (p.get("display_name") or "slot %d"%p["slot"]) for p in doc["players"]}
    res=m.get("outcome") or {}
    def outcome(slot):
        # `result` now holds a derived win/loss per slot, not a raw encoding
        v = (res or {}).get(str(slot))
        if v == "win":  return "<span class='win'>WIN</span>"
        if v == "loss": return "<span class='loss'>LOSS</span>"
        return ""
    rows="".join(
        "<tr><td>%s</td><td>%s</td><td>%s</td><td class='num'>%s</td></tr>"%(
            html.escape(names[p["slot"]]), html.escape(str((p.get("character") or p.get("legend") or {}).get("name") or "-")),
            outcome(p["slot"]), _fmt((doc["analysis"]["metrics"] or {}).get(str(p["slot"]),{}).get("apm"),0))
        for p in doc["players"])
    mo=sorted(doc["analysis"]["moments"], key=lambda x:(-x["severity"], x["frame"]))[:18]
    mrows="".join(
        "<tr><td class='num'>%.1fs</td><td class='sev%d'>%s</td><td>%s</td><td>%s</td></tr>"%(
            x["frame"]/fps, x["severity"], html.escape(x["kind"]),
            html.escape(names.get(x["slot"],"-")), html.escape(x.get("title") or ""))
        for x in mo)
    # ---- deaths, the part people actually want ----
    deaths = _death_context(doc, fps, pressure)
    dsec = ""
    if deaths:
        cards = []
        for i, dd in enumerate(deaths, 1):
            seq_rows = ""      # NB: distinct from the player-table `rows` above
            for slot, seq in sorted(dd["seqs"].items()):
                if not seq: continue
                chips = "".join(
                    "<span class='chip %s'>%s<i>%+.1fs</i></span>"
                    % (html.escape(a), html.escape(a), (f - dd["frame"]) / fps)
                    for f, a in seq[-22:])
                seq_rows += ("<tr><td class='nm'>%s</td><td>%s</td></tr>"
                             % (html.escape(dd["names"].get(slot, "?")), chips))
            wq = ""
            if dd["dodges"]:
                pct = 100 * dd["wasted"] / dd["dodges"]
                cls = "bad" if pct > 25 else ("ok" if pct < 15 else "")
                wq = ("<div class='wq %s'>%d of %d %s inputs wasted in this window (%.0f%%)</div>"
                      % (cls, dd["wasted"], dd["dodges"],
                         (pressure.label if pressure else "committed"), pct))
            cards.append(
                "<div class='death'><div class='dh'><b>Death %d</b> — %s at %.1fs</div>"
                "<table class='seq'>%s</table>%s</div>"
                % (i, html.escape(dd["who"]), dd["frame"] / fps, seq_rows, wq))
        dsec = ("<h2>Deaths — the 5 seconds before each</h2><div class='panel'>"
                + "".join(cards) + "</div>")
    warn=doc["provenance"].get("warnings") or []
    body=f"""
<h1>{html.escape(m.get('level_name') or 'Match')}</h1>
<div class="sub">{html.escape(m.get('source_file') or '')} &middot; patch {html.escape(str(m.get('patch')))}
 &middot; {m['duration_frames']/fps:.0f}s &middot; {len(doc['observations']['kos'])} KOs</div>
<div class="panel"><table><tr><th>Player</th><th>{noun}</th><th>Result</th><th class='num'>APM</th></tr>{rows}</table></div>
{dsec}
<h2>Other moments</h2>
<div class="panel"><table><tr><th class='num'>Time</th><th>Kind</th><th>Player</th><th>What</th></tr>{mrows}</table>
{"<div class='note'>" + html.escape("; ".join(warn)) + "</div>" if warn else ""}</div>
<div class="note">Stage name source: {html.escape(str(m.get('level_name_source','levelId')))} &middot;
analyzer {html.escape(doc['analyzer_version'])} &middot; schema {html.escape(doc['schema_version'])}</div>"""
    open(out_path,"w").write(_page("Match report", body))
    return out_path

def profile_report(store, name, out_path, adapter=None):
    noun = adapter.character_noun if adapter else "Character"
    defence_label = (adapter.pressure.label.capitalize()+"s") if (adapter and adapter.pressure) else "Defensive"
    db=store.db
    ids=[r["match_id"] for r in db.execute(
        "SELECT DISTINCT match_id FROM players WHERE display_name=?",(name,))]
    if not ids: raise ValueError("no matches for "+name)
    keys=["apm","attack_pm","movement_pm","defence_pm","mobility_pm","utility_pm","minutes"]
    mine=defaultdict(list); theirs=defaultdict(list)
    legends=Counter(); patches=Counter(); wins=losses=0
    for mid in ids:
        doc=store.load(mid)
        if not doc: continue
        met=doc["analysis"]["metrics"] or {}
        res=doc["match"].get("outcome") or {}
        for p in doc["players"]:
            slot=str(p["slot"]); vals=met.get(slot) or {}
            tgt = mine if p.get("display_name")==name else theirs
            for k in keys:
                if isinstance(vals.get(k),(int,float)): tgt[k].append(vals[k])
            if p.get("display_name")==name:
                lg=(p.get("character") or p.get("legend") or {}).get("name")
                if lg: legends[lg]+=1
                patches[doc["match"].get("patch")]+=1
                v=(res or {}).get(slot)
                if v=="win": wins+=1
                elif v=="loss": losses+=1
    def med(d,k): return st.median(d[k]) if d.get(k) else None
    rows=""
    for k,label in [("apm","Actions / min"),("movement_pm","Movement / min"),
                    ("defence_pm", defence_label+" / min"),("attack_pm","Attacks / min"),
                    ("mobility_pm","Jumps / min"),("utility_pm","Throws / min")]:
        a,b=med(mine,k),med(theirs,k)
        diff = "" if (a is None or not b) else "%+.0f%%"%((a-b)/b*100)
        rows+="<tr><td>%s</td><td class='num'>%s</td><td class='num'>%s</td><td class='num'>%s</td></tr>"%(
            label,_fmt(a),_fmt(b),diff)
    lrows=""
    top=legends.most_common(8); mx=top[0][1] if top else 1
    for lg,n in top:
        lrows+="<tr><td>%s</td><td class='num'>%d</td><td style='width:45%%'><div class='bar'><i style='width:%.0f%%'></i></div></td></tr>"%(
            html.escape(lg), n, 100*n/mx)
    wr = ("%.0f%%"%(100*wins/(wins+losses))) if (wins+losses) else "-"
    body=f"""
<h1>Play profile — {html.escape(name)}</h1>
<div class="sub">{len(ids)} matches across {len(patches)} patch versions</div>
<div class="panel"><div class="stat">
 <div><span class="big">{len(ids)}</span><span>matches</span></div>
 <div><span class="big">{sum(mine['minutes'])/60:.0f}h</span><span>playtime</span></div>
 <div><span class="big">{len(legends)}</span><span>legends</span></div>
 <div><span class="big">{wr}</span><span>win rate ({wins}W / {losses}L known)</span></div>
</div></div>
<h2>Habits vs opponents</h2>
<div class="panel"><table><tr><th>Metric</th><th class='num'>You</th><th class='num'>Opponents</th><th class='num'>Diff</th></tr>{rows}</table>
<div class="note">Medians per match. "Opponents" pools every other player seen, at varying skill.</div></div>
<h2>{noun}s played</h2>
<div class="panel"><table>{lrows}</table></div>
<div class="note">These are input habits. They describe tendencies, not whether individual decisions were correct.</div>"""
    open(out_path,"w").write(_page("Profile", body))
    return out_path
