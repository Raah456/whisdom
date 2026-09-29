"""
One command, one watchable artifact.

Takes a replay already in the store plus a recording of the same match, and
produces a page of clips — each death, captioned with what he was at, what he
chose, what it was worth, and what was worth more.

Everything it needs it works out itself: the video/replay offset comes from the
death pattern, the damage from the HUD, the tendencies from the opponent's
presses, the payoffs from frame data. The only inputs are a match id and a file.
"""
import html
import os
import subprocess

from whisdom.agent import clips as C
from whisdom.agent import review as R
from whisdom.agent import vision_link as vl


def _caption(d):
    """One line of verdict, for burning into the clip."""
    dm = ("%.0f%%" % (100 * d["my_damage"])) if d["my_damage"] is not None else "?"
    bits = ["you %s" % dm, d["chose"]]
    if d["my_ev"] is not None:
        bits.append("%+.2f" % d["my_ev"])
    if d["gap"] and d["gap"] > 0.02:
        bits.append("-> %s %+.2f" % (d["best"], d["best_ev"]))
    return "  ".join(bits)


def build(store, match_id, video, outdir=None, pre_s=5.0, post_s=2.0,
          max_width=1280, progress=None):
    say = progress or (lambda *_a: None)
    if not C.have_ffmpeg():
        raise SystemExit("ffmpeg and ffprobe are required.")
    doc = store.load(match_id)
    if not doc:
        raise SystemExit("unknown match: %s" % match_id)

    # 1. damage, if it isn't already attached
    if not doc.get("observations", {}).get("damage"):
        say("reading damage from the recording (about a minute)")
        res = vl.analyse(doc, video, progress=say)
        vl.attach(doc, res, video)
        store.save(doc)
    offset = (doc["match"].get("video_offset_frames") or 0) / float(
        doc["match"].get("fps") or 60)

    # 2. the verdicts
    say("reviewing the deaths")
    rev = R.review_match(doc)
    if not rev or not rev["deaths"]:
        raise SystemExit("nothing to review in this match")

    fps = doc["match"].get("fps") or 60
    outdir = outdir or os.path.join(os.path.dirname(store.dbpath), "demo_%s" % match_id)
    os.makedirs(outdir, exist_ok=True)
    vdur = C.video_duration(video)
    font = None
    for f in C._fonts():
        if os.path.exists(f):
            font = f
            break

    # 3. one clip per death, captioned
    made = []
    for i, d in enumerate(rev["deaths"], 1):
        start = d["seconds"] + offset - pre_s
        pre = pre_s
        if start < 0:
            pre += start
            start = 0
        dur = pre + post_s
        if vdur is not None and start > vdur:
            made.append(dict(d=d, file=None, error="past the end of the recording"))
            continue
        name = "%02d_death_%.0fs.mp4" % (i, d["seconds"])
        out = os.path.join(outdir, name)
        chain = ["scale='min(%d,iw)':-2" % max_width]
        if font:
            txt = C._esc(_caption(d))
            chain.append(
                "drawbox=x=0:y=ih-56:w=iw:h=56:color=black@0.65:t=fill,"
                "drawtext=expansion=none:fontfile=%s:text='%s':x=20:y=h-40:fontsize=22:"
                "fontcolor=white" % (font, txt))
        cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
               "-ss", "%.3f" % start, "-t", "%.3f" % dur, "-i", video,
               "-vf", ",".join(chain),
               "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
               "-c:a", "aac", "-movflags", "+faststart", out]
        r = subprocess.run(cmd, capture_output=True, text=True)
        made.append(dict(d=d, file=out if r.returncode == 0 else None,
                         error=None if r.returncode == 0 else r.stderr[-300:]))
        say("cut clip %d of %d" % (i, len(rev["deaths"])))

    page = _write(doc, rev, made, outdir, offset, video)
    return outdir, made, page, rev


_CSS = """
body{background:#111;color:#eee;font:15px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;
     margin:0;padding:32px;max-width:900px}
h1{font-size:22px;margin:0 0 4px} h2{font-size:16px;font-weight:600;margin:28px 0 8px}
.sub{color:#888;margin-bottom:24px;font-size:13px}
.card{background:#1b1b1b;border:1px solid #2b2b2b;border-radius:10px;padding:16px;margin:16px 0}
video{width:100%;border-radius:6px;background:#000}
.row{display:flex;gap:14px;flex-wrap:wrap;margin-top:10px;font-size:14px}
.k{color:#888} .bad{color:#ff7b6b} .good{color:#7ddc8a} .warn{color:#e8c46a}
.why{color:#aaa;font-size:13px;margin-top:8px;font-style:italic}
.bar{height:6px;background:#2b2b2b;border-radius:3px;overflow:hidden;margin-top:6px}
.bar i{display:block;height:100%;background:#4a90d9}
table{border-collapse:collapse;width:100%;font-size:14px}
td,th{padding:6px 10px;border-bottom:1px solid #262626;text-align:left}
.note{background:#1a1a22;border-left:3px solid #4a5a80;padding:12px 14px;
      border-radius:0 6px 6px 0;color:#aab;font-size:13px;margin:18px 0}
"""


def _write(doc, rev, made, outdir, offset, video):
    m = doc["match"]
    lbl = {k: l for k, l in __import__(
        "whisdom.games.brawlhalla.payoffs", fromlist=["x"]).ATK_OPTIONS}
    cards = []
    for c in made:
        d = c["d"]
        dm = ("%.0f%%" % (100 * d["my_damage"])) if d["my_damage"] is not None else "unknown"
        td = ("%.0f%%" % (100 * d["their_damage"])) if d["their_damage"] is not None else "unknown"
        vid = ('<video controls preload="metadata" src="%s"></video>'
               % html.escape(os.path.basename(c["file"]))) if c["file"] else \
              '<p class="bad">clip failed: %s</p>' % html.escape(c["error"] or "")
        gap = ""
        if d["gap"] and d["gap"] > 0.02:
            gap = ('<span class="k">better</span> <span class="good">%s %+.2f</span> '
                   '<span class="k">(%+.2f)</span>' % (html.escape(d["best"]), d["best_ev"], d["gap"]))
        else:
            gap = '<span class="good">best available option</span>'
        cards.append("""
<div class="card">
  <h2>Death at %.1fs</h2>
  %s
  <div class="row">
    <span><span class="k">you</span> %s</span>
    <span><span class="k">them</span> %s</span>
    <span><span class="k">chose</span> %s <span class="%s">%+.2f</span></span>
    <span>%s</span>
  </div>
  <div class="why">%s</div>
</div>""" % (d["seconds"], vid, dm, td, html.escape(d["chose"]),
             "bad" if (d["my_ev"] or 0) < 0 else "good", d["my_ev"] or 0.0,
             gap, html.escape(d["why_best"])))

    tend = "".join(
        '<tr><td>%s</td><td>%.0f%%</td><td><div class="bar"><i style="width:%.0f%%"></i></div></td></tr>'
        % (html.escape(lbl.get(k, k)), 100 * v, 100 * v)
        for k, v in sorted(rev["tendency"].items(), key=lambda kv: -kv[1]))

    caveats = [
        "Damage is read from the HUD arc as a 0-100%% position on its colour ramp, not an exact percentage.",
        "The replay does not record which weapon was held, so the engine assumes Sword.",
        "Without position data, 'go deep' and 'ground pound' are the same inputs — %.0f%% of the tendency estimate is ambiguous."
        % (100 * rev["tendency_ambiguous"]),
        "The tendency comes from %d presses across %d deaths. That is a demonstration, not a read on how they play."
        % (rev["tendency_n"], len(rev["deaths"])),
    ]

    page = os.path.join(outdir, "index.html")
    with open(page, "w") as f:
        f.write("""<!doctype html><meta charset="utf-8">
<title>%s vs %s</title><style>%s</style>
<h1>%s vs %s</h1>
<div class="sub">%s &middot; %s &middot; recording aligned automatically at %+.2fs</div>
<h2>What %s did when attacking</h2>
<table>%s</table>
<div class="note">%s</div>
%s
""" % (html.escape(rev["player"] or "?"), html.escape(rev["opponent"] or "?"), _CSS,
       html.escape(rev["player"] or "?"), html.escape(rev["opponent"] or "?"),
       html.escape(m.get("level_name") or ""), html.escape("patch " + (m.get("patch") or "?")),
       offset, html.escape(rev["opponent"] or "?"), tend,
       "<br>".join(html.escape(c) for c in caveats),
       "".join(cards)))
    return page
