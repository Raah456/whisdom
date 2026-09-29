"""
Sources — other people's guides and commentary, as words the coach can quote.

A source is a folder under data/app/sources/<id>/ with meta.json (title, creator, url, type,
fighter), and whatever the pipeline pulled out of it:

    frames/     one small jpg every N seconds of a local video (for the text detector)
    text.json   frames that carry on-screen text: OCR words, and any notation the parser reads
    audio.wav   16 kHz mono, for a speech-to-text engine
    transcript.json  [{t, text}] — from whisper if present, or pasted from YouTube's panel
    combos.json      notation found on screen or in the transcript, deduped, each with a timestamp

Everything a source yields is community knowledge: it wears the creator's name and a timestamp
wherever it shows — on a fighter's card, under a concept, in the coach's prompt.

    python3 -m whisdom.games.marveltokon.app.sources add <video> --creator NAME --url URL --title T --fighter Magik
    python3 -m whisdom.games.marveltokon.app.sources frames <id> [--start S --dur D]   # slice-safe
    python3 -m whisdom.games.marveltokon.app.sources ocr <id> [--max N]                  # slice-safe
    python3 -m whisdom.games.marveltokon.app.sources audio <id>
    python3 -m whisdom.games.marveltokon.app.sources transcript <id> <file.txt|.srt|.vtt|.json>
    python3 -m whisdom.games.marveltokon.app.sources combos <id>
    python3 -m whisdom.games.marveltokon.app.sources status <id>

stdlib + ffmpeg; tesseract if present (else frames are kept for a vision call from the app).
"""
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.normpath(os.path.join(HERE, "..", "data"))
SRC = os.path.join(DATA, "app", "sources")
sys.path.insert(0, HERE)
import social  # noqa: E402  — the notation parser

EVERY = 2.0          # seconds between sampled frames
SMALL_W = 640        # detector frame width
FULL_W = 1920        # OCR frame width for kept frames
BAND = 0.45          # captions and combo cards live in the top part of the frame
BAND_W = 1280        # width of the caption band that gets read


def have(cmd):
    return shutil.which(cmd) is not None


def _run(cmd, timeout=600):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def sid_from(title_or_path):
    base = os.path.splitext(os.path.basename(title_or_path))[0]
    return re.sub(r"[^A-Za-z0-9]+", "_", base).strip("_").lower()[:60]


def src_dir(sid):
    return os.path.join(SRC, sid)


def meta_read(sid):
    p = os.path.join(src_dir(sid), "meta.json")
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None


def meta_write(sid, m):
    os.makedirs(src_dir(sid), exist_ok=True)
    p = os.path.join(src_dir(sid), "meta.json")
    with open(p + ".tmp", "w", encoding="utf-8") as f:
        json.dump(m, f, indent=1, ensure_ascii=False)
    os.replace(p + ".tmp", p)


def duration(path):
    r = _run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path])
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def add(video, creator="", url="", title="", fighter="", kind="guide", sid=None):
    """Register a local video (or a transcript-only source when video is None)."""
    sid = sid or sid_from(title or video or "source")
    m = meta_read(sid) or {}
    m.update({"id": sid, "title": title or m.get("title") or (os.path.basename(video) if video else sid),
              "creator": creator or m.get("creator", ""), "url": url or m.get("url", ""),
              "fighter": fighter or m.get("fighter", ""), "type": kind, "video": None,
              "added": m.get("added") or __import__("datetime").datetime.now().isoformat(timespec="seconds")})
    if video:
        m["video"] = os.path.abspath(video)
        m["duration"] = duration(video)
    meta_write(sid, m)
    return m


def frames(sid, start=0.0, dur=None, every=EVERY):
    """Sample small frames for the text detector. Slice-safe: call with --start/--dur repeatedly."""
    m = meta_read(sid)
    if not m or not m.get("video"):
        return {"error": "no video on this source"}
    fdir = os.path.join(src_dir(sid), "frames")
    os.makedirs(fdir, exist_ok=True)
    total = m.get("duration") or duration(m["video"])
    dur = dur if dur is not None else max(0.0, total - start)
    # frame k of this slice sits at start + k*every; name by absolute second so slices never collide
    n0 = int(round(start / every))
    pattern = os.path.join(fdir, "tmp_%05d.jpg")
    bpattern = os.path.join(fdir, "btmp_%05d.jpg")
    r = _run(["ffmpeg", "-v", "error", "-y", "-ss", "%.2f" % start, "-t", "%.2f" % dur, "-i", m["video"],
              "-filter_complex", "[0:v]fps=%g,split=2[a][b];[a]scale=%d:-2[sm];[b]crop=iw:ih*%.2f:0:0,scale=%d:-2[bd]" % (1.0 / every, SMALL_W, BAND, BAND_W),
              "-map", "[sm]", "-q:v", "4", pattern, "-map", "[bd]", "-q:v", "3", bpattern])
    made = 0
    for fn in sorted(os.listdir(fdir)):
        if fn.startswith("tmp_") or fn.startswith("btmp_"):
            band = fn.startswith("b")
            k = int(fn[5:10] if band else fn[4:9])
            t = (n0 + k - 1) * every
            os.replace(os.path.join(fdir, fn), os.path.join(fdir, ("band_%07.1f.jpg" if band else "f_%07.1f.jpg") % t))
            made += 0 if band else 1
    m["frames_done_to"] = max(m.get("frames_done_to", 0.0), start + dur)
    meta_write(sid, m)
    return {"made": made, "done_to": m["frames_done_to"], "total": total, "err": r.stderr[:200]}


def _tess(path, psm=6):
    r = _run(["tesseract", path, "-", "--psm", str(psm), "tsv"], timeout=60)
    words = []
    for ln in r.stdout.splitlines()[1:]:
        p = ln.split("\t")
        if len(p) >= 12 and p[11].strip():
            try:
                conf = float(p[10])
            except ValueError:
                conf = -1
            if conf >= 50:
                words.append({"w": p[11].strip(), "conf": conf, "x": int(p[6]), "y": int(p[7]), "h": int(p[9]), "line": (int(p[2]), int(p[3]), int(p[4]))})
    return words


def _lines(words):
    by = {}
    for w in words:
        by.setdefault(w["line"], []).append(w)
    out = []
    for key, ws in sorted(by.items(), key=lambda kv: min(x["y"] for x in kv[1])):
        ws.sort(key=lambda x: x["x"])
        out.append(" ".join(x["w"] for x in ws))
    return out


def prep_band(path, out):
    """Guide captions are white fill with a coloured outline over busy gameplay. Keep only the near-white,
    low-saturation pixels, draw them black on white, upscale ×2 and thicken a touch — tesseract then reads
    them where the raw frame gave garbage."""
    from PIL import Image, ImageFilter
    import numpy as np
    im = Image.open(path).convert("RGB")
    a = np.asarray(im).astype(int)
    mx = a.max(axis=2); mn = a.min(axis=2)
    white = (mn > 200) & ((mx - mn) < 40)
    img = Image.fromarray(np.where(white, 0, 255).astype("uint8"))
    img = img.resize((img.width * 2, img.height * 2), Image.LANCZOS).filter(ImageFilter.MinFilter(3))
    img.save(out)
    return out


HUD_WORDS = {"magik", "hits", "hit", "good", "great", "perfect", "punish", "leader", "p1", "p2", "damage", "combo", "highest", "counter"}
NOTATION_HINT = re.compile(r"(?<![A-Za-z0-9])(?:j\.)?[1-9]{0,6}[LMHU](?![A-Za-z])|(?<![A-Za-z])(?:236|214|623|22|41236|63214)|>|xx", re.I)


def normalise_notation(line):
    """Common OCR slips inside notation: S→5, Z→2, O→0, l/I→1 before a button; ')' or '}' before '.' → 'j'."""
    t = line
    t = re.sub(r"[)\]}]\.(?=[0-9LMHU])", "j.", t)
    t = re.sub(r"(?<![A-Za-z0-9])S(?=[LMHU](?![A-Za-z]))", "5", t)
    t = re.sub(r"(?<![A-Za-z0-9])Z(?=[0-9]*[LMHU])", "2", t)
    t = re.sub(r"(?<![A-Za-z0-9])[lI](?=[0-9]*[LMHU](?![A-Za-z]))", "1", t)
    t = re.sub(r"(?<=[0-9])O(?=[0-9LMHU])|(?<=[LMHU>])O(?=[0-9])", "0", t)
    t = t.replace("»", ">").replace("→", ">").replace("=>", ">")
    t = re.sub(r"(?<![A-Za-z0-9])j-(?=[0-9LMHU])", "j.", t)
    t = re.sub(r"(?<![A-Za-z0-9])21U(?=[LMHU])", "214", t)      # 214M read as 21UM
    t = re.sub(r"(?<![A-Za-z0-9])62E(?=[LMHU])", "623", t)
    return t


def ocr(sid, max_frames=None):
    """Read every caption band not yet read. Kept when it has ≥ 3 real words (not the HUD's) or a notation
    hint. Consecutive frames with the same text merge into one entry with a start and an end. Slice-safe."""
    m = meta_read(sid)
    if not m:
        return {"error": "no such source"}
    if not have("tesseract"):
        m["ocr"] = "no tesseract on this machine — frames kept for a vision call"
        meta_write(sid, m)
        return {"error": m["ocr"]}
    fdir = os.path.join(src_dir(sid), "frames")
    tp = os.path.join(src_dir(sid), "text.json")
    text = json.load(open(tp, encoding="utf-8")) if os.path.exists(tp) else {"read": [], "kept": []}
    done = set(text["read"])
    todo = [fn for fn in sorted(os.listdir(fdir)) if fn.startswith("band_") and fn not in done]
    if max_frames:
        todo = todo[:max_frames]
    n_kept = 0
    prep = os.path.join(fdir, "_prep.png")
    for fn in todo:
        t = float(fn[5:-4])
        try:
            prep_band(os.path.join(fdir, fn), prep)
            words = _tess(prep, psm=6)
        except Exception as e:
            text["read"].append(fn)
            continue
        lines = [normalise_notation(ln) for ln in _lines(words)]
        lines = [ln for ln in lines if re.search(r"[A-Za-z0-9]{2,}", ln)]
        real = [w for w in re.findall(r"[A-Za-z][A-Za-z'!?.-]{2,}", " ".join(lines)) if w.lower().strip("!?.") not in HUD_WORDS]
        joined = "\n".join(lines)
        hint = bool(NOTATION_HINT.search(joined)) and bool(re.search(r"[0-9][LMHU]|j\.", joined))
        if len(real) >= 3 or hint:
            key = "|".join(lines)
            last = text["kept"][-1] if text["kept"] else None
            if last and last.get("key") == key and t - last["t_end"] <= EVERY * 1.5:
                last["t_end"] = t
            else:
                combos = social.combo_lines(joined)
                text["kept"].append({"t": t, "t_end": t, "frame": fn, "key": key, "lines": lines[:30], "n": len(words),
                                     "notation": hint, "words": len(real),
                                     "combos": [{"steps": c["steps"], "confidence": c["confidence"], "line": c["line"]} for c in combos[:3]]})
                n_kept += 1
        text["read"].append(fn)
        if len(text["read"]) % 15 == 0:      # checkpoint — the device shell kills long calls
            with open(tp + ".tmp", "w", encoding="utf-8") as f:
                json.dump(text, f, indent=1, ensure_ascii=False)
            os.replace(tp + ".tmp", tp)
    with open(tp + ".tmp", "w", encoding="utf-8") as f:
        json.dump(text, f, indent=1, ensure_ascii=False)
    os.replace(tp + ".tmp", tp)
    m["ocr_read"] = len(text["read"]); m["ocr_kept"] = len(text["kept"])
    meta_write(sid, m)
    return {"read_now": len(todo), "kept_now": n_kept, "read": len(text["read"]), "kept": len(text["kept"]), "bands": len([x for x in os.listdir(fdir) if x.startswith("band_")])}


def audio(sid):
    m = meta_read(sid)
    if not m or not m.get("video"):
        return {"error": "no video"}
    out = os.path.join(src_dir(sid), "audio.wav")
    r = _run(["ffmpeg", "-v", "error", "-y", "-i", m["video"], "-vn", "-ac", "1", "-ar", "16000", out])
    m["audio"] = os.path.basename(out) if os.path.exists(out) else None
    meta_write(sid, m)
    return {"audio": m["audio"], "err": r.stderr[:200]}


def _parse_ts(s):
    p = s.strip().replace(",", ".").split(":")
    try:
        p = [float(x) for x in p]
    except ValueError:
        return None
    return sum(v * 60 ** i for i, v in enumerate(reversed(p)))


def transcript_import(sid, path):
    """A transcript file: .srt / .vtt, whisper .json, or YouTube's pasted panel (lines of `m:ss` then text)."""
    raw = open(path, encoding="utf-8", errors="replace").read()
    segs = []
    if path.lower().endswith(".json"):
        d = json.loads(raw)
        for s in d.get("segments", d if isinstance(d, list) else []):
            segs.append({"t": float(s.get("start", s.get("t", 0))), "text": (s.get("text") or "").strip()})
    elif re.search(r"-->", raw):
        for block in re.split(r"\n\s*\n", raw):
            mm = re.search(r"(\d+:\d+(?::\d+)?[.,]?\d*)\s*-->", block)
            if not mm:
                continue
            t = _parse_ts(mm.group(1))
            txt = " ".join(ln for ln in block.splitlines() if "-->" not in ln and not ln.strip().isdigit() and not ln.startswith("WEBVTT")).strip()
            txt = re.sub(r"<[^>]+>", "", txt)
            if txt:
                segs.append({"t": t or 0.0, "text": txt})
    else:
        # YouTube panel: "0:32" on one line, text on the next (or same line)
        lines = [ln.rstrip() for ln in raw.splitlines()]
        i = 0
        while i < len(lines):
            mm = re.match(r"^\s*(\d{1,2}:\d{2}(?::\d{2})?)\s*(.*)$", lines[i])
            if mm:
                t = _parse_ts(mm.group(1)); txt = mm.group(2).strip()
                if not txt and i + 1 < len(lines):
                    i += 1; txt = lines[i].strip()
                if txt:
                    segs.append({"t": t or 0.0, "text": txt})
            i += 1
    tp = os.path.join(src_dir(sid), "transcript.json")
    with open(tp, "w", encoding="utf-8") as f:
        json.dump({"segments": segs, "from": os.path.basename(path)}, f, indent=1, ensure_ascii=False)
    m = meta_read(sid); m["transcript"] = len(segs); meta_write(sid, m)
    return {"segments": len(segs)}


def combos(sid):
    """Every combo the source yields — on-screen notation first, then transcript lines — deduped by steps."""
    d = src_dir(sid)
    m = meta_read(sid)
    out, seen = [], set()
    tp = os.path.join(d, "text.json")
    if os.path.exists(tp):
        for k in json.load(open(tp, encoding="utf-8"))["kept"]:
            # re-parse from the lines every time, so a better parser improves old sources
            for c in social.combo_lines("\n".join(normalise_notation(ln) for ln in k.get("lines") or [])) or k.get("combos") or []:
                key = " ".join(c["steps"])
                if len(c["steps"]) >= 3 and key not in seen:
                    seen.add(key)
                    out.append({"t": k["t"], "t_end": k.get("t_end", k["t"]), "steps": c["steps"], "confidence": c["confidence"], "line": c["line"], "from": "screen", "frame": k["frame"]})
    trp = os.path.join(d, "transcript.json")
    if os.path.exists(trp):
        for s in json.load(open(trp, encoding="utf-8"))["segments"]:
            for c in social.combo_lines(s["text"]):
                key = " ".join(c["steps"])
                if len(c["steps"]) >= 3 and key not in seen:
                    seen.add(key)
                    out.append({"t": s["t"], "steps": c["steps"], "confidence": c["confidence"], "line": c["line"], "from": "speech"})
    out.sort(key=lambda x: x["t"])
    with open(os.path.join(d, "combos.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    m["combos"] = len(out); meta_write(sid, m)
    return {"combos": len(out)}


def status(sid):
    m = meta_read(sid)
    if not m:
        return {"error": "no such source"}
    d = src_dir(sid)
    fdir = os.path.join(d, "frames")
    m = dict(m)
    m["frames"] = len([x for x in os.listdir(fdir) if x.startswith("f_")]) if os.path.isdir(fdir) else 0
    m["has_text"] = os.path.exists(os.path.join(d, "text.json"))
    m["has_transcript"] = os.path.exists(os.path.join(d, "transcript.json"))
    m["has_combos"] = os.path.exists(os.path.join(d, "combos.json"))
    m["tools"] = {"ffmpeg": have("ffmpeg"), "tesseract": have("tesseract"), "whisper": have("whisper") or have("whisper-cpp") or have("whisper-cli")}
    return m


def list_sources():
    out = []
    if os.path.isdir(SRC):
        for sid in sorted(os.listdir(SRC)):
            if os.path.isdir(src_dir(sid)) and os.path.exists(os.path.join(src_dir(sid), "meta.json")):
                out.append(status(sid))
    return out


def quotes(fighter=None, keywords=None, limit=12):
    """Transcript lines that mention a fighter or any keyword — for cards, concepts, the coach.
    Each carries creator, title, url, timestamp."""
    kws = [k.lower() for k in (keywords or []) if k]
    out = []
    for m in list_sources():
        trp = os.path.join(src_dir(m["id"]), "transcript.json")
        if not os.path.exists(trp):
            continue
        if fighter and m.get("fighter") and m["fighter"].lower() != fighter.lower():
            continue
        for s in json.load(open(trp, encoding="utf-8"))["segments"]:
            low = s["text"].lower()
            if (not kws) or any(k in low for k in kws):
                out.append({"t": s["t"], "text": s["text"], "creator": m.get("creator"), "title": m.get("title"), "url": m.get("url"), "source": m["id"], "fighter": m.get("fighter")})
    return out[:limit]


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__); return
    cmd = a[0]
    opt = {a[i]: a[i + 1] for i in range(1, len(a) - 1) if a[i].startswith("--")}
    pos = [x for i, x in enumerate(a[1:], 1) if not x.startswith("--") and not (i > 1 and a[i - 1].startswith("--"))]
    if cmd == "add":
        print(json.dumps(add(pos[0], creator=opt.get("--creator", ""), url=opt.get("--url", ""), title=opt.get("--title", ""), fighter=opt.get("--fighter", ""), kind=opt.get("--type", "guide"), sid=opt.get("--id")), indent=1))
    elif cmd == "frames":
        print(json.dumps(frames(pos[0], start=float(opt.get("--start", 0)), dur=float(opt["--dur"]) if "--dur" in opt else None, every=float(opt.get("--every", EVERY)))))
    elif cmd == "ocr":
        print(json.dumps(ocr(pos[0], max_frames=int(opt["--max"]) if "--max" in opt else None)))
    elif cmd == "audio":
        print(json.dumps(audio(pos[0])))
    elif cmd == "transcript":
        print(json.dumps(transcript_import(pos[0], pos[1])))
    elif cmd == "combos":
        print(json.dumps(combos(pos[0])))
    elif cmd == "status":
        print(json.dumps(status(pos[0]), indent=1))
    elif cmd == "list":
        print(json.dumps(list_sources(), indent=1))
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
