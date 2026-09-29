"""
Turn an analysed match plus a screen recording into annotated clips.

Reads the stored match document (so no re-parsing), cuts a clip around each
key moment, and burns on an overlay showing what was pressed.

Sync model: `offset_ms` is the position in the VIDEO at which match frame 0
occurs.  video_time = (match_time + offset_ms) / 1000
Because KO timestamps are known exactly, the offset can be verified: if the
predicted KO moments land on real KOs in the footage, the sync is right.
"""
import os, json, html, subprocess, shutil

FONT  = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONTB = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

def have_ffmpeg():
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None

def video_duration(path):
    r = subprocess.run(["ffprobe","-v","error","-show_entries","format=duration",
                        "-of","default=nw=1:nk=1", path], capture_output=True, text=True)
    try: return float(r.stdout.strip())
    except Exception: return None

def _esc(t):
    """
    Escape text for ffmpeg drawtext.

    Note what is NOT escaped: `%`. ffmpeg rejects `\\%` with "Stray %" and then
    silently draws nothing at all — the clip encodes fine and the caption just
    vanishes. Every drawtext below sets `expansion=none`, which makes `%` literal
    and needs no escaping. Do not "fix" this by escaping % again.
    """
    return (str(t).replace("\\","\\\\").replace(":","\\:").replace("'","\u2019")
            .replace(",","\\,"))

def _fonts():
    if os.path.exists(FONTB): return FONT, FONTB
    for root in ("/usr/share/fonts","/System/Library/Fonts","C:/Windows/Fonts"):
        for dp,_,fs in os.walk(root):
            for f in fs:
                if f.lower().endswith((".ttf",".ttc")):
                    p=os.path.join(dp,f); return p,p
    return None, None

def _filter(moment, presses, clip_start_frame, pre_frames, fps):
    f_reg, f_bold = _fonts()
    if not f_reg: return None
    f = ["drawbox=x=0:y=0:w=iw:h=64:color=black@0.62:t=fill",
         "drawtext=expansion=none:fontfile=%s:text='%s':x=24:y=13:fontsize=26:fontcolor=white"
         % (f_bold, _esc(moment.get("title") or moment["kind"])),
         "drawtext=expansion=none:fontfile=%s:text='%s':x=24:y=44:fontsize=16:fontcolor=0xB9C0D0"
         % (f_reg, _esc("%s  ·  %.1fs" % (moment.get("who") or "", moment["frame"]/fps)))]
    mt = pre_frames / fps
    f.append("drawbox=x=0:y=ih-6:w=iw:h=6:color=red@0.85:t=fill:enable='between(t,%.2f,%.2f)'" % (mt, mt+0.6))
    f.append("drawtext=expansion=none:fontfile=%s:text='MOMENT':x=(w-tw)/2:y=h-40:fontsize=22:fontcolor=red:"
             "enable='between(t,%.2f,%.2f)'" % (f_bold, mt, mt+0.6))
    for i,(fr, who, act) in enumerate(presses[-40:]):
        rel = (fr - clip_start_frame) / fps
        if rel < 0: continue
        f.append("drawtext=expansion=none:fontfile=%s:text='%s':x=24:y=%d:fontsize=17:fontcolor=0x7DE08A:"
                 "enable='between(t,%.2f,%.2f)'"
                 % (f_reg, _esc("%s  %s" % (who, act)), 84 + (i % 8) * 22, rel, rel + 0.45))
    return ",".join(f)

def make_clips(store, match_id, video, offset_ms=0, outdir=None,
               limit=8, pre_s=4.0, post_s=2.5, annotate=True, min_severity=2,
               max_width=1600):
    if not have_ffmpeg():
        raise SystemExit("ffmpeg and ffprobe are required for clips.")
    doc = store.load(match_id)
    if not doc: raise SystemExit("unknown match: %s" % match_id)
    fps = doc["match"]["fps"] or 60
    names = {p["slot"]: (p.get("display_name") or "slot %d" % p["slot"]) for p in doc["players"]}
    outdir = outdir or os.path.join(os.path.dirname(store.dbpath), "clips_%s" % match_id)
    os.makedirs(outdir, exist_ok=True)

    presses = sorted((e["frame"], names.get(e["slot"], "?"), e["action"])
                     for e in doc["observations"]["inputs"])
    moments = [m for m in doc["analysis"]["moments"] if m["severity"] >= min_severity]
    moments.sort(key=lambda m: (-m["severity"], m["frame"]))
    moments = moments[:limit]
    for m in moments:
        m["who"] = names.get(m.get("slot"), "")

    vdur = video_duration(video)
    made = []
    for i, m in enumerate(moments, 1):
        start_s = (m["frame"] / fps) + offset_ms / 1000.0 - pre_s
        pre = pre_s
        if start_s < 0: pre += start_s; start_s = 0
        dur = pre + post_s
        if vdur is not None and start_s > vdur:
            made.append(dict(moment=m, file=None, error="past the end of the video")); continue
        name = "%02d_%s_%.0fs.mp4" % (i, m["kind"], m["frame"] / fps)
        out = os.path.join(outdir, name)
        win = [p for p in presses if m["frame"] - pre*fps <= p[0] <= m["frame"] + post_s*fps]
        cmd = ["ffmpeg","-y","-hide_banner","-loglevel","error",
               "-ss","%.3f" % start_s, "-t","%.3f" % dur, "-i", video]
        chain = []
        if max_width:
            chain.append("scale='min(%d,iw)':-2" % max_width)
        if annotate:
            vf = _filter(m, win, m["frame"] - pre*fps, pre*fps, fps)
            if vf: chain.append(vf)
        if chain: cmd += ["-vf", ",".join(chain)]
        cmd += ["-c:v","libx264","-preset","veryfast","-crf","23","-c:a","aac",
                "-movflags","+faststart", out]
        r = subprocess.run(cmd, capture_output=True, text=True)
        made.append(dict(moment=m, file=out if r.returncode == 0 else None,
                         error=None if r.returncode == 0 else r.stderr[-300:]))
    _write_index(doc, made, outdir, offset_ms, fps, video)
    return outdir, made

def _write_index(doc, made, outdir, offset_ms, fps, video):
    m = doc["match"]
    cards = ""
    for c in made:
        if not c["file"]: continue
        mo = c["moment"]
        cards += ("<div class='card'><video controls preload='metadata' src='%s'></video>"
                  "<div class='meta'><div class='t'>%s</div><div class='s'>%s · %.1fs · severity %d</div>"
                  "<div class='d'>%s</div></div></div>"
                  % (html.escape(os.path.basename(c["file"])), html.escape(mo.get("title") or ""),
                     html.escape(mo.get("who") or ""), mo["frame"]/fps, mo["severity"],
                     html.escape((mo.get("detail") or "")[:160])))
    kos = ", ".join("%.1fs" % (k["frame"]/fps) for k in doc["observations"]["kos"])
    page = """<!DOCTYPE html><html><head><meta charset='utf-8'><title>Clips</title><style>
body{margin:0;background:#12141a;color:#e8eaf0;font:14px/1.6 ui-sans-serif,system-ui,sans-serif}
.wrap{max-width:1180px;margin:0 auto;padding:26px}h1{font-size:21px;margin:0 0 4px}
.sub{color:#8b93a7;font-size:13px;margin-bottom:18px}
.note{background:#1a1d26;border:1px solid #272b38;border-radius:9px;padding:14px;margin-bottom:18px;color:#a9b1c4;font-size:13px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:16px}
.card{background:#1a1d26;border:1px solid #272b38;border-radius:9px;overflow:hidden}
video{width:100%%;display:block;background:#000}.meta{padding:12px 14px}
.t{font-weight:600;margin-bottom:3px}.s{color:#8b93a7;font-size:12px;margin-bottom:6px}
.d{color:#a9b1c4;font-size:12px}</style></head><body><div class="wrap">
<h1>Clips — %s</h1><div class="sub">%s · offset %+d ms · %s</div>
<div class="note"><b>Verify the sync:</b> known KO times are %s.
Play a KO clip; the red MOMENT marker should land on the actual KO.
If it is consistently early or late, adjust <code>--offset</code> by that amount.</div>
<div class="grid">%s</div></div></body></html>""" % (
        html.escape(m.get("level_name") or "Match"),
        html.escape(m.get("source_file") or ""), offset_ms, html.escape(os.path.basename(video)),
        html.escape(kos or "none"), cards)
    open(os.path.join(outdir, "index.html"), "w").write(page)
