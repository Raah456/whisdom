"""
Whisdom for Tōkon — the local app.

Stdlib only, binds to 127.0.0.1. Serves ui/ and a thin JSON API over the
tables in ../data. Anything long-running (footage extraction) stays in the CLI.

    python -m whisdom.games.marveltokon.app.server        # opens the browser
    python -m whisdom.games.marveltokon.app.server --port 8765 --no-open

API
    GET  /api/roster                teams, codes, slot roles
    GET  /api/character/<name>      game-knowledge card: systems, fastest, longest reach, most punishable
    GET  /api/profile               the saved profile (or {} when none)
    POST /api/profile               save the profile (JSON body)
    GET  /api/community/<name>      community notes for a character from the tokon.gg snapshot (or {status:"none"})
    POST /api/community/refresh     fetch tokon.gg on this machine in a background thread; GET /api/community/status to watch
    GET  /api/progress              Whisdom level: xp, level, progress into the next level
    POST /api/progress              record an event {event, ref} — awards xp once per (event, ref) where it should
    GET  /api/moves/<name>          the character's command list (game names, inputs, images) joined to wiki rows
    GET  /api/matchup?them=&move=&you=   the punish answer: their move, your candidates, reach verdicts
    GET  /moves/<CODE>/<file>.jpg   per-move screenshot from the game's command list
    GET  /api/replays               captures with a *-segments.json in data/replays
    GET  /api/videos                capture files the runner can see (repo root *.mp4, the drive) + analysed flag
    POST /api/replay/run            {video} → run the pipeline in a background thread (see runner.py)
    GET  /api/jobs                  runner status per video
    GET  /api/replay/<video>        segments (with who was on point), openings, Punish! reads, findings
    GET  /api/sources               every source + which tools this machine has (ffmpeg / tesseract / whisper)
    GET  /api/source/<id>           one source: meta, on-screen text blocks, transcript, combos, job state
    GET  /api/quotes?fighter=&k=    transcript lines mentioning a fighter / keywords, with creator + timestamp
    POST /api/sources/upload        raw video body + X-Filename → data/app/sources/video/
    POST /api/sources/add           {path?, title, creator, url, fighter, type, process?} → meta (and start the pipeline)
    POST /api/sources/meta          {id, title?, creator?, url?, fighter?}
    POST /api/sources/process       {id} → frames → ocr → combos in a thread
    POST /api/sources/transcript    {id, text} — pasted transcript (YouTube panel / srt / vtt)
    POST /api/sources/to_tech       {id, steps, t, line?, title?, char?} → a tech cited to the creator at that timestamp
    GET  /api/coach/<video>         the cached coach record {have_key, model, rec:{last, thread, dry, calls}}
    POST /api/coach                 {video, reply?, force?} → build the prompt from findings + takes + team + concepts, call Claude (or dry-run without a key), cache
    GET  /api/grade_tags            the tag vocabulary for takes
    POST /api/grades/send           {video} → ops/takes/<video>_<date>.md (app's read vs Raah's, per finding) + an INBOX line
    GET  /api/grades                every grade given so far
    POST /api/grade                 {id, verdict: right|wrong|actually, note} -> data/app/grades.json
    GET  /api/routes/<name>         the game's own Trial routes for a character, steps in wiki notation with pictures and frame data
    GET  /api/drills                drill log (reps landed/dropped per route)
    POST /api/drill                 {char, route, ok: true|false} → data/app/drills.json, XP drill_logged
    GET  /api/concepts              game-agnostic concepts (ours) + which fighters the game's descriptions tag for each
    GET  /api/tech                  tech library: every data/app/tech/*.json (yours and imported)
    POST /api/tech                  create/update a tech {id?, title, char, steps[], concepts[], notes, clip}; author = profile username
    POST /api/tech/import           {tech: {...}} → saved as imported (keeps original author)
    POST /api/tech/delete           {id}
    GET  /tech/<id>.json            the file itself, for sending to someone
    GET  /api/knowledge             the game's Battle Guide topics (125) + our number hooks for a few of them
    GET  /api/secrets               {anthropic_api_key: bool} — never returns the key itself
    POST /api/secrets               {anthropic_api_key: "..."} saved to data/app/secrets.json (gitignored); empty string removes it
    GET  /api/social/posts          the community feed: posts added by URL (X oEmbed), each with author, text, parsed combos
    POST /api/social/add            {url, note} → fetch X's oEmbed for the post, parse its notation, store it
    POST /api/social/remove         {id}
    POST /api/social/config         {list_url, accounts} — the X list to embed, accounts for the best-effort pull
    POST /api/social/pull           {accounts?, per?} → try X's syndication endpoint for recent posts (undocumented; may fail)
    POST /api/tech/clip             raw video body, headers X-Tech-Id + X-Filename → data/app/tech/clips/<id>.<ext>, served at /tech/clips/
    POST /api/social/parse          {text} → {steps, confidence}
    POST /api/social/to_tech        {id, steps?, title?, char?} → a tech in the Imported shelf with the source on it
    POST /api/admin/note            {screen, context, text, errors} → ops/INBOX.md + data/app/admin/notes.jsonl (Admin panel)
    GET  /api/admin/notes           the last 50 notes
    GET  /api/audio                 the BGM library: data/app/audio/*.{m4a,mp3,ogg,wav,flac}, cover art = same stem .png/.jpg, names in tracks.json
    POST /api/audio/upload          raw file body + X-Filename [+ X-Stem for art] → data/app/audio/; tags and embedded cover read with ffprobe/ffmpeg when present
    POST /api/audio/meta            {id, name, artist, album} → tracks.json
    POST /api/audio/remove          {id} → files moved to data/app/audio/_removed/
    GET  /audio/<file>              music loops (data/app/audio, gitignored)
    GET  /clips/<file>.mp4          footage clips (data/app/clips, gitignored)
    GET  /hero/<CODE>.<ext>         full-size still of a character, if one has been added to data/app/hero/
    GET  /hero_wide/<CODE>.<ext>    the game's wide banner art (cyan silhouette, colour band), data/app/hero_wide/
    GET  /api/art                   per code: hero still, wide banner, command-list frames on disk
    GET  /portraits/<CODE>.webp     character portrait
    GET  /moveart/<file>            command-list art

Profile lives in ../data/app/profile.json. It carries the language settings
(glyph set, notation, bindings, spoken language) and the handles. Bindings are a
property of THIS player's controller, never of the game — see ops/CONTEXT.md.
"""
import argparse
import sys
import json
import mimetypes
import os
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, unquote, parse_qs

HERE = os.path.dirname(os.path.abspath(__file__))
UI = os.path.join(HERE, "ui")
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import community as C
import social as SOC
import coach as COACH
import sources as SRCS  # noqa: E402  — sibling module; works both as a package and as a script
import runner as RUN
import doctor as DOC  # noqa: E402
DATA = os.path.normpath(os.path.join(HERE, "..", "data"))
APPDATA = os.path.join(DATA, "app")
PROFILE = os.path.join(APPDATA, "profile.json")
PROGRESS = os.path.join(APPDATA, "progress.json")
SECRETS = os.path.join(APPDATA, "secrets.json")
GRADES = os.path.join(APPDATA, "grades.json")
DRILLS = os.path.join(APPDATA, "drills.json")
TECH = os.path.join(APPDATA, "tech")
ROOT = os.path.normpath(os.path.join(HERE, "..", "..", "..", ".."))       # the repo
INBOX = os.path.join(ROOT, "ops", "INBOX.md")                             # Raah's notes from inside the app → the sessions' inbox
ADMIN_LOG = os.path.join(APPDATA, "admin", "notes.jsonl")
REPLAYS = os.path.join(DATA, "replays")

# Whisdom level: rewards using the app and touching every feature. Points per
# event; "once" events pay a single time per ref (a character, a mode, a day).
XP = {
    "language_set": (30, "once"),
    "team_saved": (25, "daily"),
    "card_viewed": (3, "once"),      # ref = character name
    "menu_open": (5, "daily"),
    "mode_open": (15, "once"),       # ref = mode name — first visit to each mode
    "replay_dropped": (40, "always"),
    "drill_logged": (10, "always"),
    "claim_graded": (8, "once"),         # ref = finding id
    "matchup_answered": (4, "always"),
    "concept_read": (6, "once"),         # ref = topic id
    "tech_written": (25, "once"),        # ref = tech id
    "tech_imported": (10, "once"),
    "coach_read": (0, "once"),      # deliberately nothing — reading the coach is not a chore to reward
}
LEVEL_STEP = 100  # xp per level, flat for now


def _load(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as f:
        return json.load(f)


class Tables:
    """Loaded once. Everything the character card needs."""

    def __init__(self):
        self.roster = json.load(open(os.path.join(APPDATA, "roster.json"), encoding="utf-8"))
        self.moveart = json.load(open(os.path.join(APPDATA, "moveart.json"), encoding="utf-8"))
        self.dust = _load("dustloop_movedata.json")
        self.damage = _load("dustloop_damage.json")
        self.reach = _load("reach.json")
        self.punish = _load("punish_data.json")
        self.behav = _load("behav.json")
        self.mech = _load("mechanics.json")
        self.names = _load("movenames.json")
        self.code_of = {v: k for k, v in self.roster["charname"].items()}
        vp = os.path.join(DATA, "verified.json")
        self.verified = json.load(open(vp, encoding="utf-8")) if os.path.exists(vp) else {}
        mp = os.path.join(APPDATA, "moves.json")
        self.cmd = json.load(open(mp, encoding="utf-8")) if os.path.exists(mp) else {}
        self.reach_ix = {}
        for r in self.reach:
            if r.get("reach"):
                self.reach_ix[(r["char"], r["dl"])] = r["reach"]

    # ---- command list ↔ wiki input join -------------------------------------
    _MOTIONS = ("632146", "41236", "63214", "236", "214", "623", "421", "22")

    def _entry_inputs(self, key):
        """Expand a command-list key like '236L / M / H (Air OK)' or 'U / 2U / 3U / 6U'
        into the wiki inputs it covers. [model] — a text rule, not a table."""
        import re as _re
        k = key.split("(")[0].strip().replace(" + ", "+").replace(" +", "+").replace("+ ", "+")
        outs = set()
        for alt in k.split("/"):
            alt = alt.strip()
            m = _re.match(r"^(\d*)\s*([LMHUA](?:\+[LMHUA])?|QS|QA|T|QD)?", alt)
            if not m or not m.group(2):
                continue
            pre, btn = m.group(1), m.group(2)
            if not pre and outs:
                # 'M / H' alternatives inherit the previous prefix
                last = sorted(outs)[-1]
                pre = _re.match(r"^\d*", last).group(0)
            if btn in ("QS", "QA", "T", "QD"):
                continue
            outs.add((pre or "5") + btn if btn in ("L", "M", "H", "U") else (pre + btn if pre else btn))
        return outs

    def command_list(self, name):
        code = self.code_of.get(name)
        c = self.cmd.get(code) or {}
        rows = {r["input"]: r for r in (self.dust.get(name) or [])}
        out = []
        for e in c.get("moves", []):
            ins = self._entry_inputs(e.get("key", ""))
            matched = [i for i in ins if i in rows] + [i for i in ins if "j." + i in rows]
            out.append({**e, "inputs": sorted(ins), "wiki": matched})
        return {"name": name, "code": code, "info": c.get("info"), "moves": out}

    def image_for(self, name, inp):
        """The command-list screenshot for a wiki input, if the join finds one."""
        base = inp.replace("j.", "").replace("dc.", "")
        for e in self.command_list(name)["moves"]:
            if e.get("image") and (base in e["inputs"] or inp in e["inputs"]):
                return e["image"], e["title"]
        # strength-agnostic wiki inputs like 236X
        if base.endswith("X"):
            for e in self.command_list(name)["moves"]:
                if e.get("image") and any(i[:-1] == base[:-1] for i in e["inputs"]):
                    return e["image"], e["title"]
        return None, None

    # ---- routes: the game's own Trial combos, in wiki notation ----------------
    @staticmethod
    def _step_wiki(p):
        """Trial notation (A/B/C/D/E letters, ~EX, ULT~Finish, jump) → wiki input + label."""
        s = p
        if s == "jump":
            return {"input": "jump", "label": "Jump", "kind": "move"}
        label = None
        if "ULT~Finish" in s:
            s = s.replace(" ULT~Finish", ""); label = "Ultimate" if "632146" in s else "Super"
        elif " ULT" in s:
            s = s.replace(" ULT", ""); label = ("Ultimate" if "632146" in s else "Super") + " (start)"
        if "~EX" in s:
            s = s.replace("~EX", ""); label = "EX"
        if "~" in s or s.startswith("shot "):      # follow-ups like 5D~N, 5A~ir5DEX, shot Spear_AirA: keep raw, letters translated
            head, _, tail = s.partition("~")
            head = head.replace("E", "M+H").replace("A", "L").replace("B", "M").replace("C", "H").replace("D", "U") if not head.startswith("shot") else head
            return {"input": head + ("~" + tail if tail else ""), "label": "follow-up", "kind": "raw"}
        w = s.replace("E", "M+H")
        w = w.replace("A", "L").replace("B", "M").replace("C", "H").replace("D", "U")
        return {"input": w, "label": label, "kind": "attack"}

    def routes(self, name):
        code = self.code_of.get(name)
        v = self.verified.get(code) or {}
        rows = {r["input"]: r for r in (self.dust.get(name) or [])}
        out = []
        for i, c in enumerate(v.get("combos") or []):
            steps = []
            for p in c["p"]:
                st = self._step_wiki(p)
                inp = st["input"]
                r = rows.get(inp) or rows.get(inp.replace("j.", ""))
                img, title = (self.image_for(name, inp) if st["kind"] == "attack" else (None, None))
                nm = (self.names.get(name, {}).get(inp) or [title])[0] if (self.names.get(name, {}).get(inp) or title) else None
                st.update({"raw": p, "startup": self._num(r["startup"]) if r else None, "onBlock": self._num(r["onBlock"]) if r else None,
                           "image": img, "name": nm})
                steps.append(st)
            cost = 100 if any("632146" in p for p in c["p"]) else (50 if any("E" in p.split("~")[0] for p in c["p"]) else 0)
            out.append({"id": "%s:%d" % (code, i), "steps": steps, "damage": c.get("dmg"), "cost": cost, "n": len(steps)})
        cancels = {}
        for k, vs in (v.get("cancels") or {}).items():
            cancels[self._step_wiki(k)["input"]] = [self._step_wiki(x)["input"] for x in vs]
        return {"name": name, "code": code, "routes": out, "cancels": cancels,
                "source": "TrialMissionData_<C>.uasset — the game's own Trial mode routes, known to connect [fact]; damage where the trial states a requirement"}

    def matchup(self, them, move, you):
        prow = next((r for r in (self.punish.get(them) or []) if r[0] == move), None)
        if not prow or prow[2] is None:
            return {"error": "no on-block value for that move"}
        adv = -prow[2]
        their_reach = self.reach_ix.get((them, move))
        img, title = self.image_for(them, move)
        cands = []
        for r in (self.punish.get(you) or []):
            inp, su, ob, dmg, guard, typ = r[0], r[1], r[2], r[3], r[4], r[5]
            if typ == "assist" or su is None or su > adv:
                continue
            if inp.startswith("j.") or ".j." in inp:
                continue
            reach = self.reach_ix.get((you, inp))
            verdict = None
            if their_reach is not None and reach is not None:
                gap = their_reach - reach
                verdict = "reaches" if gap <= 0 else ("close" if gap <= 60 else "may not reach")
            cost = 150 if typ == "tokon" else (100 if "632146" in inp else (50 if typ == "super" else 0))
            yimg, yname = self.image_for(you, inp)
            cands.append({"input": inp, "startup": su, "onBlock": ob, "damage": dmg, "guard": guard, "type": typ,
                          "reach": reach, "verdict": verdict, "cost": cost, "spare": adv - su,
                          "name": (self.names.get(you, {}).get(inp) or [yname])[0] if (self.names.get(you, {}).get(inp) or yname) else None,
                          "image": yimg, "throw": guard in ("T", "W")})
        cands.sort(key=lambda c: (-(c["damage"] or 0), c["startup"]))
        return {"them": them, "move": move, "you": you, "onBlock": prow[2], "adv": adv,
                "their": {"reach": their_reach, "image": img, "title": title or (self.names.get(them, {}).get(move) or [None])[0],
                          "startup": prow[1], "guard": prow[4], "type": prow[5]},
                "candidates": cands,
                "sources": {"onBlock": "dustloop_movedata [fact]", "reach": "collision files, hitbox tip to body edge [fact]",
                            "verdict": "gap heuristic — assumes the gap after blocking equals their reach [model]"}}

    @staticmethod
    def _num(s):
        try:
            return int(str(s).strip())
        except (TypeError, ValueError):
            return None

    def card(self, name):
        rows = self.dust.get(name) or []
        normals = [r for r in rows if r.get("type") == "normal" and self._num(r.get("startup")) is not None]
        fastest = min(normals, key=lambda r: self._num(r["startup"])) if normals else None

        reaches = [r for r in self.reach if r.get("char") == name and r.get("reach")]
        longest = max(reaches, key=lambda r: r["reach"]) if reaches else None

        # normals, specials and unique attacks only — a whiffed Ultimate is not a habit anyone drills
        blockable = [r for r in rows if self._num(r.get("onBlock")) is not None
                     and r.get("type") in ("normal", "s", "q") and not str(r.get("input", "")).startswith("dc.")]
        worst = min(blockable, key=lambda r: self._num(r["onBlock"])) if blockable else None

        systems = self.behav.get(name) or {}
        own = systems.get("own") or []
        # group the game's own state names by their leading token so a reader
        # sees "Portal ×24" rather than twenty-four identifiers
        # split the identifiers into words and count the words that carry meaning
        import re as _re
        noise = {"rsn", "nml", "atk", "tmp", "init", "special", "skill", "set", "start", "end", "ex", "2nd", "3rd",
                 "air", "player", "shot", "x", "y", "add", "del", "flex", "chain", "begin", "all", "delete", "fast",
                 "for", "limited", "attack", "hit", "stack0", "stack1", "replacement", "change", "adjustment",
                 "temporary", "stop", "assemble", "u", "cmn", "act", "lv1", "lv2", "lv3", "loop", "in", "out",
                 "on", "off", "up", "down", "front", "back", "ground", "land", "landing", "to", "a", "b", "c", "d"}
        groups = {}
        for s in own:
            words = {w.lower() for w in _re.findall(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[0-9]+|[A-Z]+", s.replace("_", " "))}
            for w in words:
                if w in noise or len(w) < 3 or w.isdigit():
                    continue
                groups[w] = groups.get(w, 0) + 1
        top = [(k.capitalize(), n) for k, n in sorted(groups.items(), key=lambda kv: -kv[1])[:6]]

        excels = {}
        try:
            excels = _concepts()["fighters"].get(name, {})
        except Exception:  # noqa
            pass
        return {
            "name": name,
            "code": self.code_of.get(name),
            "excels": excels,
            "team": next((t["name"] for t in self.roster["teams"] if name in t["chars"]), None),
            "moves": {"wiki": len(rows), "named": len(self.names.get(name) or {})},
            "fastest": {"input": fastest["input"], "startup": self._num(fastest["startup"]),
                        "name": (self.names.get(name, {}).get(fastest["input"]) or [None])[0]} if fastest else None,
            "longest": {"input": longest["dl"], "reach": longest["reach"],
                        "name": (self.names.get(name, {}).get(longest["dl"]) or [None])[0]} if longest else None,
            "worst_on_block": {"input": worst["input"], "onBlock": self._num(worst["onBlock"]),
                               "name": (self.names.get(name, {}).get(worst["input"]) or [None])[0]} if worst else None,
            "resources": self.mech.get(name) or [],
            "info": (self.cmd.get(self.code_of.get(name, ""), {}) or {}).get("info"),
            "systems": [{"key": k, "states": n} for k, n in top],
            "system_count": len(own),
            "sources": {
                "fastest": "dustloop_movedata (wiki, hand-measured) [fact]",
                "longest": "reach.json — hitbox tip to body edge, engine units, from collision files [fact]",
                "worst_on_block": "dustloop_movedata onBlock [fact]; game-verified for Magik normals",
                "systems": "behav.json — the character's own BBScript state names [fact: names] [guess: what they do]",
            },
        }


T = None


def _tech_list():
    out = []
    if os.path.isdir(TECH):
        for f in sorted(os.listdir(TECH)):
            if f.endswith(".json"):
                try:
                    out.append(json.load(open(os.path.join(TECH, f), encoding="utf-8")))
                except ValueError:
                    pass
    out.sort(key=lambda x: x.get("updated", ""), reverse=True)
    return out


AUDIO_EXT = (".m4a", ".mp3", ".ogg", ".wav", ".flac", ".aac")
ART_EXT = (".png", ".jpg", ".jpeg", ".webp")


def _audio_tracks():
    """Every track in data/app/audio: one entry per stem, the formats it comes in, cover art if a
    picture with the same stem sits beside it, name / artist / album from tracks.json (written by the
    BGM screen, or by hand). Drop files in and they appear; nothing to restart."""
    adir = os.path.join(APPDATA, "audio")
    tracks = {}
    if os.path.isdir(adir):
        for fn in sorted(os.listdir(adir)):
            stem, ext = os.path.splitext(fn)
            if ext.lower() in AUDIO_EXT:
                t = tracks.setdefault(stem, {"id": stem, "name": stem.replace("_", " ").replace("-", " ").title(), "files": [], "art": None, "artist": "", "album": ""})
                t["files"].append(fn)
        for fn in os.listdir(adir):
            stem, ext = os.path.splitext(fn)
            if ext.lower() in ART_EXT and stem in tracks:
                tracks[stem]["art"] = "/audio/" + fn
    meta = os.path.join(adir, "tracks.json")
    if os.path.exists(meta):
        try:
            for k, v in json.load(open(meta, encoding="utf-8")).items():
                if k in tracks and isinstance(v, dict):
                    tracks[k].update({kk: vv for kk, vv in v.items() if kk in ("name", "artist", "album", "seconds", "source")})
        except Exception:
            pass
    return list(tracks.values())


def _audio_meta_write(stem, **kw):
    adir = os.path.join(APPDATA, "audio")
    os.makedirs(adir, exist_ok=True)
    meta = os.path.join(adir, "tracks.json")
    d = {}
    if os.path.exists(meta):
        try:
            d = json.load(open(meta, encoding="utf-8"))
        except Exception:
            d = {}
    d.setdefault(stem, {})
    d[stem].update({k: v for k, v in kw.items() if v is not None})
    with open(meta + ".tmp", "w", encoding="utf-8") as f:
        json.dump(d, f, indent=1, ensure_ascii=False)
    os.replace(meta + ".tmp", meta)


SRC_JOBS = {}


def _source_job(sid):
    """frames → ocr → combos for one source, in a thread; progress in SRC_JOBS[sid]."""
    j = SRC_JOBS[sid] = {"step": "frames", "started": __import__("datetime").datetime.now().isoformat(timespec="seconds"), "done": False, "error": None, "log": []}
    why = DOC.gate("source_frames")
    if why:
        j["error"] = why
        j["step"] = "cannot run here"
        j["done"] = True
        return
    if DOC.gate("source_ocr"):
        j["log"].append("frames only — " + DOC.gate("source_ocr"))
    try:
        m = SRCS.meta_read(sid)
        if m and m.get("video"):
            total = m.get("duration") or 0
            start = 0.0
            while start < total:
                r = SRCS.frames(sid, start=start, dur=min(120.0, total - start))
                j["log"].append("frames to %.0fs" % (start + 120))
                start += 120.0
            j["step"] = "ocr"
            if SRCS.have("tesseract"):
                while True:
                    r = SRCS.ocr(sid, max_frames=40)
                    j["log"].append("ocr %d/%d, kept %d" % (r.get("read", 0), r.get("bands", 0), r.get("kept", 0)))
                    if r.get("read_now", 0) == 0:
                        break
            else:
                j["log"].append("no tesseract on this machine — on-screen text not read")
        j["step"] = "combos"
        SRCS.combos(sid)
        j["step"] = "done"; j["done"] = True
    except Exception as e:
        j["error"] = "%s: %s" % (type(e).__name__, str(e)[:200]); j["done"] = True


def _tech_save(tech):
    import datetime, re as _re, uuid
    os.makedirs(TECH, exist_ok=True)
    tid = tech.get("id") or ("tech-" + uuid.uuid4().hex[:8])
    tid = _re.sub(r"[^A-Za-z0-9_-]+", "-", tid)[:48]
    tech["id"] = tid
    tech["updated"] = datetime.datetime.now().isoformat(timespec="seconds")
    tech.setdefault("created", tech["updated"])
    tech["steps"] = [str(x).strip() for x in (tech.get("steps") or []) if str(x).strip()][:60]
    tech["concepts"] = [str(x) for x in (tech.get("concepts") or [])][:8]
    for k in ("title", "char", "notes", "author", "clip", "origin"):
        tech[k] = str(tech.get(k) or "")[:2000 if k == "notes" else 200]
    cc = tech.get("clip_credit")
    if isinstance(cc, dict) and (cc.get("who") or cc.get("url")):
        tech["clip_credit"] = {"who": str(cc.get("who") or "")[:80].lstrip("@"), "url": str(cc.get("url") or "")[:300]}
    else:
        tech.pop("clip_credit", None)
    src = tech.get("source")
    if isinstance(src, dict):
        tech["source"] = {k: str(src.get(k) or "")[:300] for k in ("platform", "url", "author", "handle", "author_url", "fetched", "line")}
    else:
        tech.pop("source", None)
    tmp = os.path.join(TECH, tid + ".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(tech, f, indent=1, ensure_ascii=False)
    os.replace(tmp, os.path.join(TECH, tid + ".json"))
    return tech


def _concepts():
    """Our concept list, joined to the game's Battle Guide topics and to the fighters whose
    own in-game description matches each concept's tag rules ([model] — keyword rules over the
    game's text; the sentence that matched is returned as the receipt)."""
    cp = os.path.join(APPDATA, "concepts.json")
    if not os.path.exists(cp):
        return {"concepts": [], "fighters": {}}
    c = json.load(open(cp, encoding="utf-8"))
    kn = {}
    kp = os.path.join(APPDATA, "knowledge.json")
    if os.path.exists(kp):
        for tpc in json.load(open(kp, encoding="utf-8")).get("topics", []):
            kn[tpc["id"]] = {"id": tpc["id"], "title": tpc["title"], "category": tpc["category"], "tutorial": bool(tpc.get("tutorial"))}
    # fighters → tags with the matching sentence
    fighters = {}
    for code, v in (T.cmd or {}).items():
        info = (v.get("info") or "")
        if not info or not v.get("name") or v["name"].startswith("Unreleased"):
            continue
        sents = [x.strip() for x in info.replace("^n;", " ").split(". ") if x.strip()]
        tags = {}
        unless = c.get("tag_unless", {})
        for tag, words in c["tag_rules"].items():
            for sen in sents:
                low = sen.lower()
                if any(w in low for w in words) and not any(w in low for w in unless.get(tag, [])):
                    tags[tag] = sen if sen.endswith(".") else sen + "."
                    break
        fighters[v["name"]] = tags
    out = []
    for k in c["concepts"]:
        k = dict(k)
        k["topics"] = [kn[t] for t in k.get("game_topics", []) if t in kn]
        k["fighters"] = sorted({n for n, tg in fighters.items() if "all" in k["tags"] or any(t in tg for t in k["tags"])}) if "all" not in k["tags"] else []
        out.append(k)
    return {"about": c["about"], "concepts": out, "fighters": fighters, "tag_names": c["tag_names"]}


# ---- knowledge -----------------------------------------------------------
def _knowledge():
    kp = os.path.join(APPDATA, "knowledge.json")
    if not os.path.exists(kp):
        return {"topics": [], "source": None}
    k = json.load(open(kp, encoding="utf-8"))
    prof = {}
    if os.path.exists(PROFILE):
        prof = json.load(open(PROFILE, encoding="utf-8"))
    you = (prof.get("team") or ["Magik"])[0]
    hooks = {}
    # Punishes: your fastest buttons, and the verified fact behind the number
    rows = [r for r in (T.punish.get(you) or []) if r[1] is not None and r[5] != "assist" and not r[0].startswith("j.")]
    rows.sort(key=lambda r: r[1])
    hooks["Punish"] = {"title": "Your fastest answers as %s" % you,
                       "lines": ["%s — %d frames%s" % (r[0], r[1], (" · " + (T.names.get(you, {}).get(r[0]) or [""])[0]) if T.names.get(you, {}).get(r[0]) else "") for r in rows[:5]],
                       "fact": "The overlay's Recovery field IS frame advantage, in frames — verified on Mgk.mp4: 5L −3, 5M −7, 5LL −9, all exact against the wiki.",
                       "link": "matchup"}
    # Fuzzy guard: overheads the opponents you actually face throw, with startup — slow ones are what fuzzy guard beats
    try:
        rp = _replay("LongBatch1") or {}
    except Exception:
        rp = {}
    opps = [n for n, c in (rp.get("opponents") or [])][:6]
    ov = []
    for n in opps:
        for r in (T.punish.get(n) or []):
            if r[4] and "O" in r[4] and r[1] is not None and r[5] != "assist":
                ov.append((r[1], n, r[0]))
    ov.sort(reverse=True)
    hooks["FuzzyGuard"] = {"title": "Slow overheads from the fighters you face",
                           "lines": ["%s %s — %d frames startup" % (n, i, s) for s, n, i in ov[:8]] or ["no overhead rows found for your opponents"],
                           "fact": "Guard property 'O' = overhead, from the wiki guard table (dustloop_guard.json). Startup from movedata.",
                           "link": None}
    # Meaty / okizeme: what the capture shows
    hooks["Kasane"] = {"title": "In your capture",
                       "lines": ["%d moments where one side was free ≥12 frames and started no new attack" % (rp.get("openings") or 0),
                                 "some of those are knockdowns (okizeme moments), some are whiffs — the reader cannot tell them apart yet"],
                       "fact": "Openings are read from the latched Recovery value [fact]; their kind is unresolved [open].", "link": "replay"}
    hooks["AtkParameter"] = {"title": "Where the numbers in this app come from",
                             "lines": ["937 rows read from the game's own scripts (startup 79% exact vs the wiki)", "975 wiki rows, hand-measured by players", "Frame advantage verified against the game on three Magik normals"],
                             "fact": "Two independent methods agreeing is the currency.", "link": None}
    for tpc in k["topics"]:
        if tpc["id"] in hooks:
            tpc["hook"] = hooks[tpc["id"]]
    return k


# ---- replay dataset --------------------------------------------------------
def _replays_list():
    out = []
    if not os.path.isdir(REPLAYS):
        return out
    for f in sorted(os.listdir(REPLAYS)):
        if f.endswith("-segments.json"):
            v = f[:-len("-segments.json")]
            try:
                meta = json.load(open(os.path.join(REPLAYS, f), encoding="utf-8"))
            except ValueError:
                continue
            segs = meta.get("segments") or []
            out.append({"video": v, "segments": len(segs), "overlay_seconds": round(sum(b - a for a, b in segs), 1),
                        "scanned_seconds": (meta.get("scored") or [[0]])[-1][0] if meta.get("scored") else None,
                        "has_openings": os.path.exists(os.path.join(REPLAYS, v + "-openings.json")),
                        "has_punishes": os.path.exists(os.path.join(REPLAYS, v + "-punishes.json"))})
    return out


def _starters(video):
    """What this player opens combos with, and what each opener is worth.

    From the panel only — see extract/moves.py for the two fields and why the
    other two are unusable. Nothing is guessed down to one name: a starter the
    reading cannot separate (5L and j.L share both a startup and a damage
    figure) is printed as the pair, and more than three candidates is reported
    as not identified rather than as a list.
    """
    sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "extract")))
    try:
        import moves as MV
    except Exception as e:
        return {"error": "%s: %s" % (type(e).__name__, e)}
    rep = _replay(video)
    you = (rep or {}).get("you")
    try:
        rows = MV.starters(video)
    except Exception as e:
        return {"error": "%s: %s" % (type(e).__name__, e)}
    s_you = MV.summarise(rows, you)
    return {"video": video, "you": you, **s_you,
            "rows": [r for r in rows if not you or r["character"] == you][:120],
            "label": "[fact] on the panel readings; [model] on the name — a startup and an unscaled damage figure "
                     "matched against the character's move table",
            "known_gap": "the panel cannot tell a jump from a stance, so a ground move and its air version "
                         "with the same startup and damage stay a pair until the input gutter is read (T-012)"}


def _habits(min_windows=3):
    """What each opponent character does, from every capture on file.

    Nothing here needs move naming. Three things are already measured per segment:
    who was on the opposing side, the windows where THEY were free and threw no new
    attack, and every combo with its damage. Put together they answer the two
    questions that actually change how you play a matchup — how often they give you
    a free moment, and what it costs when they get in.

    "What followed a free window" is [model], not [fact]: it asks whether a hit
    landed on their side within 2 s of the window ending. A hit landing is a fact;
    calling it "they pressed" is an inference, and the app says so.

    Nothing is claimed for a character with fewer than `min_windows` windows —
    that threshold is the difference between a habit and a coincidence.
    """
    AFTER = 2.0
    out = {}
    for meta in _replays_list():
        video = meta["video"]
        rep = _replay(video)
        if not rep or not rep.get("usable"):
            continue
        you = rep.get("you")
        # A CAPTURE THAT CANNOT NAME THE PLAYER CANNOT NAME THE OPPONENT EITHER.
        # Mgk.mp4 has no readable plates, so `you` falls back to the profile's point
        # slot ("Captain America") and every combo in it would be filed under the
        # wrong opponent. Skip those captures rather than poison the habit rows.
        if not you or "fell back" in (rep.get("you_why") or ""):
            continue
        segs = {s["i"]: s for s in rep["segments"]}
        cpath = os.path.join(REPLAYS, video + "-combos.json")
        cdata = json.load(open(cpath, encoding="utf-8")) if os.path.exists(cpath) else {}
        combos = cdata.get("combos") or []
        by_side = {}
        for c in combos:
            by_side.setdefault((c["segment"], c["side"]), []).append(c)
        for f in rep["findings"]:
            if f["kind"] != "opening" or f.get("whose") != "them":
                continue
            name = f.get("free_name")
            # "L"/"R" is the side letter standing in for an unread plate, not a fighter.
            if not name or name == you or name in ("L", "R", "?"):
                continue
            r = out.setdefault(name, {"name": name, "captures": set(), "segments": set(),
                                      "windows": [], "pressed": 0, "punished_you": 0,
                                      "their_combos": [], "receipts": []})
            r["captures"].add(video)
            r["segments"].add((video, f["segment"]))
            r["windows"].append(f["frames"])
            hits = [c for c in by_side.get((f["segment"], f["free"]), [])
                    if f["t"] <= c["t0"] <= f["t"] + AFTER]
            if hits:
                r["pressed"] += 1
                if len(r["receipts"]) < 6:
                    r["receipts"].append("%s: %d frames free at %.1fs, then a hit landed %.1fs later for %s"
                                         % (video, f["frames"], f["t"], hits[0]["t0"] - f["t"],
                                            "{:,}".format(hits[0]["damage"])))
            elif len(r["receipts"]) < 6:
                r["receipts"].append("%s: %d frames free at %.1fs, nothing landed in the next %.0fs"
                                     % (video, f["frames"], f["t"], AFTER))
        for c in combos:
            nm = c.get("character")
            if not nm or nm == you or nm == "?":
                continue
            out.setdefault(nm, {"name": nm, "captures": set(), "segments": set(), "windows": [],
                                "pressed": 0, "punished_you": 0, "their_combos": [], "receipts": []})
            out[nm]["their_combos"].append(c)
        for pz in (cdata.get("punishes") or []):
            nm = pz.get("character")
            if nm and nm != you and nm in out:
                out[nm]["punished_you"] += 1
    rows = []
    import statistics
    for name, r in out.items():
        w = sorted(r["windows"])
        tc = r["their_combos"]
        row = {"name": name, "captures": sorted(r["captures"]), "segments": len(r["segments"]),
               "windows": len(w), "enough": len(w) >= min_windows,
               "median_frames": (int(statistics.median(w)) if w else None),
               "longest": (w[-1] if w else None),
               "pressed": r["pressed"],
               "pressed_share": (round(r["pressed"] / len(w), 2) if w else None),
               "their_combos": len(tc),
               "their_median_damage": (int(statistics.median([c["damage"] for c in tc])) if tc else None),
               "their_biggest": (max([c["damage"] for c in tc]) if tc else None),
               "punished_you": r["punished_you"],
               "receipts": r["receipts"]}
        if w:
            # WHOSE MOMENT IS IT. A window with whose == "them" is a moment where THEY were
            # free and you could not act, and they threw no new attack. From your side that
            # is a moment you gave away; from theirs it is one they did not take. Say it
            # that way round — the first draft read "gave you 8 free moments", which is the
            # opposite of what the window measures.
            row["line"] = ("You gave %s %d moment%s where they were free and you could not act, "
                           "across %d segment%s (median %d frames, longest %d). A hit landed on "
                           "their side within 2 s of %d of them."
                           % (name, len(w), "" if len(w) == 1 else "s", row["segments"],
                              "" if row["segments"] == 1 else "s", row["median_frames"], row["longest"], r["pressed"]))
        if tc:
            row["cost"] = ("When %s got in: %d combos, typical %s, biggest %s%s."
                           % (name, len(tc), "{:,}".format(row["their_median_damage"]),
                              "{:,}".format(row["their_biggest"]),
                              "" if not r["punished_you"] else ", and the game called Punish! on them %d time%s"
                              % (r["punished_you"], "" if r["punished_you"] == 1 else "s")))
        rows.append(row)
    rows.sort(key=lambda r: (-r["windows"], -(r["their_combos"] or 0)))
    return {"opponents": rows, "min_windows": min_windows,
            "label": "counts are [fact]; \"they pressed\" is [model] — a hit landing within 2 s of the window is the measurement, calling it a decision is the inference",
            "thin": [r["name"] for r in rows if not r["enough"]]}


def _captures():
    """Every analysed capture, as comparable RATES. [fact] on the numbers.

    Captures are not the same length — LongBatch1 is 17.1 minutes of read
    playback and Vid1 is 1.8 — so a raw count comparison says nothing. Everything
    that can be a rate is one, the minutes are shown beside every row, and any
    row under five minutes is flagged `thin` rather than quietly averaged in.
    """
    import datetime
    rows = []
    mt = {}
    try:
        for v in RUN.videos():
            try:
                mt[v["video"]] = os.path.getmtime(v["path"])
            except OSError:
                pass
    except Exception:
        pass
    grades = _grades_read()
    for meta in _replays_list():
        video = meta["video"]
        rep = _replay(video)
        if not rep or not rep.get("usable"):
            continue
        mins = (rep["live_seconds"] or 0) / 60.0
        if mins <= 0:
            continue
        c = rep.get("conversion") or {}
        mine = [g for fid, g in grades.items() if fid.startswith(video + ":")]
        tags = {}
        for g in mine:
            for t in (g.get("tags") or []):
                tags[t] = tags.get(t, 0) + 1
        row = {
            "video": video, "you": rep.get("you"), "segments": rep["usable"],
            "minutes": round(mins, 1), "thin": mins < 5,
            "when": (datetime.datetime.fromtimestamp(mt[video]).date().isoformat() if video in mt else None),
            "opponents": rep.get("opponents") or [],
            "openings": rep["openings"], "openings_per_min": round(rep["openings"] / mins, 1),
            "free_seconds": round(rep["free_frames"] / 59.94, 1),
            "free_share": round(rep["free_frames"] / 59.94 / (rep["live_seconds"] or 1), 3),
            "combos": c.get("yours"), "combos_per_min": (round(c["yours"] / mins, 1) if c.get("yours") else None),
            "median_damage": c.get("median_damage"), "biggest": c.get("biggest"),
            "one_hit_share": c.get("one_hit_share"),
            "punishes": c.get("punishes_yours"),
            "punishes_per_min": (round(c["punishes_yours"] / mins, 2) if c.get("punishes_yours") else None),
            "punish_median_damage": c.get("punish_median_damage"),
            "punish_one_hit": c.get("punish_one_hit"),
            "takes": len(mine), "tags": sorted(tags.items(), key=lambda kv: -kv[1]),
        }
        rows.append(row)
    rows.sort(key=lambda r: (mt.get(r["video"], 0), r["video"]))
    # A TREND NEEDS TWO CAPTURES THAT CAN CARRY ONE. A 0.5-minute training clip
    # with four openings reads as "7.4 openings a minute" and would swamp any
    # comparison; so would a capture with no combos in it at all. Deltas are
    # computed only between captures with at least five minutes of read playback
    # AND damage numbers, and when there are fewer than two of those the screen
    # says so instead of drawing a line through one point.
    good = [r for r in rows if not r["thin"] and r.get("combos")]
    keys = ("openings_per_min", "free_share", "median_damage", "one_hit_share",
            "punish_median_damage", "combos_per_min")
    if len(good) > 1:
        base = good[0]
        for r in good[1:]:
            r["delta"] = {k: (None if base.get(k) in (None, 0) or r.get(k) is None
                              else round((r[k] - base[k]) / abs(base[k]), 3)) for k in keys}
        compare = "%s → %s, ordered by each file's date on disk" % (good[0]["video"], good[-1]["video"])
        need = None
    else:
        compare = None
        need = ("%d capture%s deep enough to compare. A trend needs two with at least five minutes "
                "of read playback each — record a session, drop it in, and this screen starts "
                "answering \"is it working\"." % (len(good), "" if len(good) == 1 else "s"))
    return {"captures": rows, "comparable": [r["video"] for r in good],
            "note": ("Rates, not counts — the captures are different lengths. A row under five "
                     "minutes of read playback is marked thin and is left out of the comparison."),
            "dates_are": "the capture file's date on disk — when it was copied here, not when it was played",
            "compare": compare, "need": need}


def _conversion(all_combos, punish_combos, you_name, segs):
    """How much a punish is worth, against how much any combo is worth. [fact] on the
    numbers, and n is small — say so wherever this is shown."""
    import statistics
    if not all_combos:
        return None
    mine = [c for c in all_combos if you_name and c.get("character") == you_name] or all_combos
    # only YOUR punishes count toward your conversion - two of LongBatch1's ten captions are
    # the opponent punishing you, and folding those in made the number say the opposite thing.
    got = [p for p in punish_combos if p.get("damage") and (not you_name or p.get("character") == you_name)]
    out = {"combos": len(all_combos), "yours": len(mine),
           "median_damage": int(statistics.median([c["damage"] for c in mine])),
           "one_hit_share": round(sum(1 for c in mine if c["hits"] <= 1) / len(mine), 3),
           "biggest": max(c["damage"] for c in mine),
           "punishes": len(punish_combos), "punishes_yours": len(got)}
    if got:
        out["punish_median_damage"] = int(statistics.median([p["damage"] for p in got]))
        out["punish_one_hit"] = sum(1 for p in got if p["hits"] <= 1)
        out["receipt"] = ("%d combos cut from the panel; a punish is worth %s here against %s for any "
                          "combo, and %d of %d of YOUR punishes stopped at one hit. n=%d — a direction, not a rate."
                          % (len(mine), "{:,}".format(out["punish_median_damage"]),
                             "{:,}".format(out["median_damage"]), out["punish_one_hit"], len(got), len(got)))
    return out


def _replay(video):
    segf = os.path.join(REPLAYS, video + "-segments.json")
    if not os.path.exists(segf):
        return None
    meta = json.load(open(segf, encoding="utf-8"))
    segs = []
    for i, (a, b) in enumerate(meta.get("segments") or []):
        rec = {"i": i, "start": a, "end": b, "active_seconds": None, "characters": None, "usable": None, "moves": None}
        pf = os.path.join(REPLAYS, "%s-%02d.json" % (video, i))
        if os.path.exists(pf):
            try:
                r = json.load(open(pf, encoding="utf-8"))
                rec["active_seconds"] = r.get("active_seconds")
                ch = r.get("characters") or {}
                rec["characters"] = {"L": ch.get("L"), "R": ch.get("R"), "seen": ch.get("_seen")}
                rec["usable"] = (r.get("active_seconds") or 0) >= 15
                mv = r.get("moves") or {}
                rec["moves"] = (len(mv.get("L") or []) + len(mv.get("R") or [])) if isinstance(mv, dict) else None
            except ValueError:
                pass
        segs.append(rec)
    def _load(suffix):
        p = os.path.join(REPLAYS, video + suffix)
        return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else []
    # events (clustered windows) if the newer pipeline has run, else raw windows
    openings = _load("-events.json") or _load("-openings.json")
    punishes = _load("-punishes.json")
    by_i = {s["i"]: s for s in segs}
    prof = {}
    if os.path.exists(PROFILE):
        try:
            prof = json.load(open(PROFILE, encoding="utf-8"))
        except ValueError:
            prof = {}
    # WHO IS THE PLAYER IN THIS CAPTURE? Not the profile's point fighter - that is today's team,
    # and it read "Captain America" while every segment of LongBatch1 has Magik in it. The capture
    # answers for itself: the player is on screen in nearly every segment, opponents come and go.
    # [model], with the count as the receipt; the profile only breaks a tie.
    appear = {}
    for sg in segs:
        if not sg.get("usable"):
            continue
        for nm in {v for k, v in (sg.get("characters") or {}).items() if k in ("L", "R") and v}:
            appear[nm] = appear.get(nm, 0) + 1
    n_seg = max(1, len([x for x in segs if x.get("usable")]))
    ranked = sorted(appear.items(), key=lambda kv: -kv[1])
    you_name, you_why = None, "not determined"
    if ranked and ranked[0][1] >= 0.6 * n_seg and (len(ranked) == 1 or ranked[0][1] > ranked[1][1]):
        you_name = ranked[0][0]
        you_why = "on screen in %d of %d segments; the next most frequent is %s at %d" % (
            ranked[0][1], n_seg, ranked[1][0] if len(ranked) > 1 else "-", ranked[1][1] if len(ranked) > 1 else 0)
    elif (prof.get("team") or []):
        you_name = prof["team"][0]
        you_why = "no fighter is in most segments — fell back to your profile's point fighter"
    # Raah's own lag tags, carried forward to the rest of the segment. HIS judgement, not ours:
    # two panel discriminators were tested against these tags and both failed (see find_openings.py).
    g_all = _grades_read()
    lag_segs = {}
    for fid, g in g_all.items():
        if fid.startswith(video + ":open:") and "lag" in (g.get("tags") or []):
            try:
                lag_segs[int(fid.split(":")[2])] = lag_segs.get(int(fid.split(":")[2]), 0) + 1
            except (ValueError, IndexError):
                pass
    # WHAT HE PRESSED IN THAT WINDOW. The opening finder can only say "no NEW attack
    # started" — blocking, dashing and repeating a move all read the same to it, and it
    # says so. The input gutter's frame-count column, read every sample and never used
    # until now, counts the inputs entered. It cannot say WHICH input (the direction
    # rosette is unread and the button glyphs are unlocated), so this separates "did
    # nothing" from "did something the panel does not count" and stops there.
    ins = {}
    ipath = os.path.join(REPLAYS, video + "-inputs.json")
    if os.path.exists(ipath):
        try:
            ins = {int(k): v for k, v in json.load(open(ipath, encoding="utf-8")).items()}
        except (ValueError, TypeError):
            ins = {}
    # findings: what the pipeline can say today, each with its receipt and label
    findings = []
    for o in sorted(openings, key=lambda o: -o["frames"]):
        s = by_i.get(o["segment"], {})
        ch = (s.get("characters") or {})
        free_name = ch.get(o["free"]) or o["free"]; stuck_name = ch.get(o["stuck"]) or o["stuck"]
        anchor = o.get("anchor", o["end"])           # the id never moves when clustering changes
        seen = ((s.get("characters") or {}).get("_seen") or {}).get(o["free"]) or {}
        mirror = free_name and free_name == stuck_name
        if you_name and free_name == you_name and not mirror:
            who, whose = "You", "you"
        elif you_name and free_name == you_name and mirror:
            who, whose = "You (%s side)" % o["free"], "you"
        elif you_name and free_name != you_name:
            who, whose = "%s (them)" % free_name, "them"
        else:
            who, whose = "%s (%s side)" % (free_name, o["free"]), "unknown"
        f = {"id": "%s:open:%d:%.1f" % (video, o["segment"], anchor), "kind": "opening", "label": "fact",
             "title": "%s — %d frames free, no new attack" % (who, o["frames"]),
             "whose": whose, "segment": o["segment"], "t": anchor, "frames": o["frames"],
             "free": o["free"], "stuck": o["stuck"], "free_name": free_name, "stuck_name": stuck_name,
             "windows": o.get("windows", 1), "span": o.get("span"),
             "members": ["%s:open:%d:%.1f" % (video, o["segment"], m) for m in (o.get("members") or [])],
             "receipt": "Recovery latched %+d on the %s side at %.1f s; the %s side was stuck %.2f s%s"
                        % (o["frames"], o["free"], anchor, o["stuck"], o["frames"] / 59.94,
                           (" · %d windows inside %.1f s read as one moment" % (o["windows"], o.get("span") or 0)) if o.get("windows", 1) > 1 else ""),
             "open": "the panel says no NEW attack started — blocking, dashing and repeating a move all read the same. Whether this was a mistake is yours to say."}
        if len(seen) > 1:
            f["note"] = "a tag happened in this segment (%s seen on this side) — the fighter free here may not be the one on the plate" % ", ".join(seen)
        rows = (ins.get(o["segment"]) or {}).get(o["free"]) or []
        pressed = [x for x in rows if o["start"] - 0.2 <= x["t"] <= o["end"] + 0.2]
        if ins:
            f["inputs"] = len(pressed)
            f["inputs_held"] = [x["held"] for x in pressed][:8]
            who_p = "you" if whose == "you" else ("they" if whose == "them" else "that side")
            f["receipt"] += (" · %s entered nothing in that window" % who_p
                             if not pressed else
                             " · %s entered %d input%s in that window (held %s frames)"
                             % (who_p, len(pressed), "" if len(pressed) == 1 else "s",
                                ", ".join(("99+" if x.get("capped") else str(x["held"])) for x in pressed[:6])))
            if not pressed:
                f["open"] = ("the panel says no NEW attack started, and the input log says %s entered "
                             "nothing at all — this one is not blocking or dashing." % who_p)
            elif max((x["held"] for x in pressed), default=0) >= 20:
                top = max(pressed, key=lambda x: x["held"])
                f["open"] = ("the panel says no NEW attack started, but %s held an input for %s frames "
                             "here — the panel cannot see blocking or walking, and that is what a long "
                             "hold looks like. Yours to call."
                             % (who_p, "99 or more" if top.get("capped") else str(top["held"])))
        if lag_segs.get(o["segment"]):
            f["player_note"] = "you called %d window%s in this segment lag" % (lag_segs[o["segment"]], "" if lag_segs[o["segment"]] == 1 else "s")
        findings.append(f)
    # what each punish was WORTH — extract/combos.py cuts the panel's Combo field into
    # individual combos (Combo == Damage marks a first hit; see that file) and joins the
    # caption to the combo whose first hit it followed.
    cdata = _load("-combos.json") or {}
    conv = {(x["seg"], round(x["caption_t"], 1)): x for x in (cdata.get("punishes") or [])}
    allc = cdata.get("combos") or []
    for p in punishes:
        s = by_i.get(p["seg"], {}); ch = (s.get("characters") or {})
        nm = ch.get(p["side"])
        mirror = nm and nm == ch.get("L") and nm == ch.get("R")
        if you_name and nm == you_name:
            who, whose = ("You (%s side)" % p["side"]) if mirror else "You", "you"
        elif you_name and nm:
            who, whose = "%s (them)" % nm, "them"
        else:
            who, whose = "%s side (%s)" % (p["side"], nm or "?"), "unknown"
        c = conv.get((p["seg"], round(p["t"], 1)))
        f = {"id": "%s:punish:%d:%.1f" % (video, p["seg"], p["t"]), "kind": "punish", "label": "fact",
             "title": "%s — the game called Punish!" % who, "whose": whose,
             "segment": p["seg"], "t": p["t"], "side": p["side"],
             "receipt": "caption template distance %.3f at x=%d; right-side templates only — left count is a lower bound" % (p["d"], p["x"]),
             "open": "the caption sits on the punisher's side — settled by the player's own takes on ten of them (2026-08-25); left-side captions are still not read"}
        if c and c.get("damage"):
            f["damage"], f["hits"] = c["damage"], c["hits"]
            f["title"] = "%s — Punish! into %s damage over %d hit%s" % (
                who, "{:,}".format(c["damage"]), c["hits"], "" if c["hits"] == 1 else "s")
            f["receipt"] += " · " + c["receipt"]
            if c["hits"] <= 1:
                f["open"] = ("it stopped at one hit. That can be the right call — no meter, wrong range, "
                             "their assist was out — so this is the number, not a verdict.")
        findings.append(f)
    usable = [s for s in segs if s["usable"]]
    live = sum((s["active_seconds"] or 0) for s in usable)
    # OPPONENTS ARE THE OTHER SIDE, not "anyone who is not Magik". The player's own
    # second fighter tagging in on his side was listed as an opponent (Match1:
    # Deadpool, 2026-09-02). Find the side the player's fighter appears on most;
    # opponents are the names on the other side — a mirror Magik there included.
    opp = {}
    sides = {"L": 0, "R": 0}
    for s in usable:
        ch = s.get("characters") or {}
        for side in ("L", "R"):
            if ch.get(side) == you_name:
                sides[side] += 1
    you_side = "L" if sides["L"] > sides["R"] else ("R" if sides["R"] > sides["L"] else None)
    for s in usable:
        ch = s.get("characters") or {}
        for side in ("L", "R"):
            n = ch.get(side)
            if not n:
                continue
            if you_side is not None:
                if side != you_side:
                    opp[n] = opp.get(n, 0) + 1
            elif n != you_name:
                opp[n] = opp.get(n, 0) + 1
    return {"video": video, "segments": segs, "usable": len(usable), "live_seconds": round(live, 1),
            "moves": sum((s["moves"] or 0) for s in usable),
            "openings": len(openings), "free_frames": sum(o["frames"] for o in openings),
            "windows": sum(o.get("windows", 1) for o in openings),
            "you": you_name, "you_why": you_why,
            "punishes": len(punishes), "opponents": sorted(opp.items(), key=lambda kv: -kv[1]),
            "conversion": _conversion(allc, [conv[k] for k in conv], you_name, segs),
            "findings": findings,
            "locked": [{"title": "Move-level findings", "why": "needs move naming — T-020. 'You blocked −13 five times' lives here once the action widget reads."},
                       {"title": "Habits and bread-and-butters", "why": "same dependency: which move was thrown"},
                       ]}


GRADE_TAGS = {
    "real": "real opening — I should have pressed",
    "lag": "lag / rollback — the counter stalled, nobody could act",
    "defend": "I was defending on purpose — blocking, waiting, baiting",
    "spacing": "out of range — nothing would have reached",
    "misread": "the app misread the panel",
    "unsure": "not sure what this was",
}


def fmt_t(t):
    t = float(t or 0)
    return "%d:%02d" % (int(t // 60), int(round(t % 60)))


def _re_sub_id(fid):
    import re as _re
    return _re.sub(r"[^A-Za-z0-9_.-]+", "_", fid)


def _grades_read():
    if os.path.exists(GRADES):
        return json.load(open(GRADES, encoding="utf-8"))
    return {}


def _grades_write(g):
    tmp = GRADES + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(g, f, indent=1, ensure_ascii=False)
    os.replace(tmp, GRADES)


def _progress_read():
    if os.path.exists(PROGRESS):
        with open(PROGRESS, encoding="utf-8") as f:
            return json.load(f)
    return {"xp": 0, "seen": {}, "log": []}


def _progress_write(p):
    tmp = PROGRESS + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(p, f, indent=1, ensure_ascii=False)
    os.replace(tmp, PROGRESS)


def _progress_view(p):
    xp = int(p.get("xp", 0))
    level = 1 + xp // LEVEL_STEP
    return {"xp": xp, "level": level, "into": xp % LEVEL_STEP, "next": LEVEL_STEP, "events": len(p.get("log", []))}


def _progress_award(event, ref):
    import datetime
    if event not in XP:
        return None
    pts, rule = XP[event]
    p = _progress_read()
    key = event + ":" + (str(ref) if ref else "")
    if rule == "daily":
        key += ":" + datetime.date.today().isoformat()
    seen = p.setdefault("seen", {})
    if rule in ("once", "daily") and key in seen:
        return _progress_view(p)
    seen[key] = True
    p["xp"] = int(p.get("xp", 0)) + pts
    p.setdefault("log", []).append({"t": datetime.datetime.now().isoformat(timespec="seconds"), "event": event, "ref": ref, "xp": pts})
    p["log"] = p["log"][-500:]
    _progress_write(p)
    return _progress_view(p)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _send(self, code, body, ctype="application/json"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _file(self, root, rel):
        rel = unquote(rel).lstrip("/")
        path = os.path.normpath(os.path.join(root, rel))
        if not path.startswith(root) or not os.path.isfile(path):
            return self._send(404, {"error": "not found"})
        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        if path.endswith(".webp"):
            ctype = "image/webp"
        with open(path, "rb") as f:
            self._send(200, f.read(), ctype)

    def do_GET(self):
        u = urlparse(self.path)
        p = u.path
        if p == "/" or p == "/index.html":
            return self._file(UI, "index.html")
        if p.startswith("/ui/"):
            return self._file(UI, p[4:])
        if p.startswith("/portraits/"):
            return self._file(os.path.join(APPDATA, "portraits"), p[len("/portraits/"):])
        if p.startswith("/moveart/"):
            return self._file(os.path.join(APPDATA, "moveart"), p[len("/moveart/"):])
        if p.startswith("/moves/"):
            return self._file(os.path.join(APPDATA, "moves"), p[len("/moves/"):])
        if p.startswith("/api/moves/"):
            name = unquote(p[len("/api/moves/"):])
            if name not in T.code_of:
                return self._send(404, {"error": "unknown character"})
            cl = T.command_list(name)
            # the punishable list: every wiki row with a negative on-block, with its picture where the join finds one
            pun = []
            for r in (T.punish.get(name) or []):
                if r[2] is not None and r[2] < 0 and r[5] != "assist":
                    img, title = T.image_for(name, r[0])
                    pun.append({"input": r[0], "startup": r[1], "onBlock": r[2], "damage": r[3], "guard": r[4], "type": r[5],
                                "image": img, "title": title or (T.names.get(name, {}).get(r[0]) or [None])[0],
                                "reach": T.reach_ix.get((name, r[0]))})
            pun.sort(key=lambda x: x["onBlock"])
            cl["punishable"] = pun
            cl["rows"] = [{"input": r[0], "startup": r[1], "onBlock": r[2], "damage": r[3], "type": r[5],
                           "image": T.image_for(name, r[0])[0], "name": (T.names.get(name, {}).get(r[0]) or [T.image_for(name, r[0])[1]])[0]}
                          for r in (T.punish.get(name) or []) if r[5] != "assist"]
            return self._send(200, cl)
        if p == "/api/matchup":
            qs = parse_qs(u.query)   # module-level import; a local one here made every
                                     # LATER use of parse_qs in do_GET an UnboundLocalError
                                     # (that is what broke /api/quotes — found by tests/smoke.py)
            them, move, you = (qs.get("them") or [""])[0], (qs.get("move") or [""])[0], (qs.get("you") or [""])[0]
            if them not in T.code_of or you not in T.code_of:
                return self._send(404, {"error": "unknown character"})
            return self._send(200, T.matchup(them, move, you))
        if p.startswith("/audio/"):
            return self._file(os.path.join(APPDATA, "audio"), p[len("/audio/"):])
        if p.startswith("/clips/"):
            return self._file(os.path.join(APPDATA, "clips"), p[len("/clips/"):])
        if p.startswith("/hero/"):
            return self._file(os.path.join(APPDATA, "hero"), p[len("/hero/"):])
        if p.startswith("/sources/"):
            return self._file(SRCS.SRC, p[len("/sources/"):])
        if p == "/api/sources":
            return self._send(200, {"sources": SRCS.list_sources(), "tools": {"ffmpeg": SRCS.have("ffmpeg"), "tesseract": SRCS.have("tesseract"), "whisper": SRCS.have("whisper") or SRCS.have("whisper-cpp") or SRCS.have("whisper-cli")}, "jobs": SRC_JOBS})
        if p.startswith("/api/source/"):
            sid = unquote(p[len("/api/source/"):])
            m = SRCS.status(sid)
            if "error" in m:
                return self._send(404, m)
            d = SRCS.src_dir(sid)
            for name in ("text", "transcript", "combos"):
                fp = os.path.join(d, name + ".json")
                m[name] = json.load(open(fp, encoding="utf-8")) if os.path.exists(fp) else None
            if m.get("text"):
                m["text"] = {"kept": m["text"]["kept"], "read": len(m["text"]["read"])}
            m["job"] = SRC_JOBS.get(sid)
            return self._send(200, m)
        if p.startswith("/api/quotes"):
            q = parse_qs(u.query)
            return self._send(200, SRCS.quotes(fighter=(q.get("fighter") or [None])[0], keywords=(q.get("k") or [""])[0].split(",") if q.get("k") else None, limit=int((q.get("n") or ["12"])[0])))
        if p.startswith("/hero_wide/"):
            return self._file(os.path.join(APPDATA, "hero_wide"), p[len("/hero_wide/"):])
        if p == "/api/art":
            # what art exists on disk, per fighter code: the full-body still, the wide banner, and a few
            # command-list frames — the UI fills empty panes with these instead of leaving them blank
            out = {}
            hero_dir, wide_dir, mv_dir = (os.path.join(APPDATA, d) for d in ("hero", "hero_wide", "moves"))
            for code in T.roster["charname"]:
                e = {"hero": None, "wide": None, "frames": []}
                for ext in ("png", "jpg", "webp"):
                    if os.path.isfile(os.path.join(hero_dir, code + "." + ext)):
                        e["hero"] = "/hero/%s.%s" % (code, ext); break
                for ext in ("png", "jpg", "webp"):
                    if os.path.isfile(os.path.join(wide_dir, code + "." + ext)):
                        e["wide"] = "/hero_wide/%s.%s" % (code, ext); break
                d = os.path.join(mv_dir, code)
                if os.path.isdir(d):
                    fr = sorted(x for x in os.listdir(d) if x.lower().endswith((".jpg", ".png", ".webp")))
                    e["frames"] = ["/moves/%s/%s" % (code, x) for x in fr]
                out[code] = e
            return self._send(200, out)
        if p == "/api/health":
            # cheap and dependency-free: the readiness probe for tests/smoke.py and
            # for the desktop launcher, which needs to know the port answered.
            return self._send(200, {"ok": True, "app": "whisdom-tokon",
                                    "captures": [c["video"] for c in _replays_list()],
                                    "data": os.path.isdir(APPDATA)})
        if p == "/api/doctor":
            return self._send(200, DOC.check())
        if p.startswith("/api/starters/"):
            return self._send(200, _starters(unquote(p[len("/api/starters/"):])))
        if p == "/api/habits":
            return self._send(200, _habits())
        if p == "/api/captures":
            return self._send(200, _captures())
        if p == "/api/progress":
            return self._send(200, _progress_view(_progress_read()))
        if p == "/api/tech":
            return self._send(200, _tech_list())
        if p.startswith("/tech/"):
            return self._file(TECH, p[len("/tech/"):])
        if p == "/api/concepts":
            return self._send(200, _concepts())
        if p == "/api/knowledge":
            return self._send(200, _knowledge())
        if p == "/api/replays":
            return self._send(200, _replays_list())
        if p == "/api/videos":
            return self._send(200, RUN.videos())
        if p == "/api/jobs":
            return self._send(200, RUN._read())
        if p.startswith("/api/replay/"):
            r = _replay(unquote(p[len("/api/replay/"):]))
            return self._send(200 if r else 404, r or {"error": "no such capture"})
        if p == "/api/grades":
            return self._send(200, _grades_read())
        if p.startswith("/api/routes/"):
            name = unquote(p[len("/api/routes/"):])
            if name not in T.code_of:
                return self._send(404, {"error": "unknown character"})
            return self._send(200, T.routes(name))
        if p == "/api/drills":
            return self._send(200, json.load(open(DRILLS, encoding="utf-8")) if os.path.exists(DRILLS) else {})
        if p == "/api/social/posts":
            d = SOC.load()
            return self._send(200, {"posts": list(reversed(d["posts"])), "config": d["config"]})
        if p.startswith("/api/coach/"):
            video = unquote(p[len("/api/coach/"):])
            rec = COACH.load(video)
            sec = {}
            if os.path.exists(SECRETS):
                try:
                    sec = json.load(open(SECRETS, encoding="utf-8"))
                except ValueError:
                    pass
            return self._send(200, {"video": video, "have_key": bool(sec.get("anthropic_api_key")), "model": sec.get("coach_model") or COACH.DEFAULT_MODEL, "rec": rec})
        if p == "/api/grade_tags":
            return self._send(200, GRADE_TAGS)
        if p == "/api/admin/notes":
            out = []
            if os.path.exists(ADMIN_LOG):
                with open(ADMIN_LOG, encoding="utf-8") as f:
                    for ln in f:
                        try:
                            out.append(json.loads(ln))
                        except ValueError:
                            pass
            return self._send(200, out[-50:])
        if p == "/api/audio":
            return self._send(200, {"tracks": _audio_tracks()})
        if p == "/api/secrets":
            sec = {}
            if os.path.exists(SECRETS):
                with open(SECRETS, encoding="utf-8") as f:
                    sec = json.load(f)
            out = {k: bool(v) for k, v in sec.items()}
            out["coach_model_value"] = sec.get("coach_model", "")     # the model id is not a secret; the key never leaves
            return self._send(200, out)
        if p == "/api/roster":
            return self._send(200, T.roster)
        if p.startswith("/api/character/"):
            name = unquote(p[len("/api/character/"):])
            if name not in T.code_of:
                return self._send(404, {"error": "unknown character", "name": name})
            return self._send(200, T.card(name))
        if p == "/api/community/status":
            st = {}
            if os.path.exists(C.STATUS):
                st = json.load(open(C.STATUS, encoding="utf-8"))
            snap = C.load()
            st["have_snapshot"] = bool(snap); st["fetched"] = snap.get("fetched") if snap else None
            st["errors"] = (snap or {}).get("errors", {})
            return self._send(200, st)
        if p.startswith("/api/community/"):
            name = unquote(p[len("/api/community/"):])
            snap = C.load()
            if not snap or name not in snap.get("characters", {}):
                return self._send(200, {"name": name, "status": "none",
                                        "note": "No community snapshot yet. Options → Community → Refresh fetches tokon.gg from this Mac."})
            c = dict(snap["characters"][name]); c["status"] = "ok"; c["source"] = snap["source"]
            return self._send(200, c)
        if p == "/api/profile":
            if os.path.exists(PROFILE):
                return self._file(APPDATA, "profile.json")
            return self._send(200, {})
        return self._send(404, {"error": "not found"})

    def do_HEAD(self):
        # used by the UI to probe for an optional hero still without downloading it
        u = urlparse(self.path)
        if u.path.startswith("/hero/") or u.path.startswith("/clips/"):
            sub = "hero" if u.path.startswith("/hero/") else "clips"
            path = os.path.normpath(os.path.join(APPDATA, sub, unquote(u.path.split("/", 2)[2])))
            self.send_response(200 if os.path.isfile(path) else 404)
            self.end_headers()
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        u = urlparse(self.path)
        n = int(self.headers.get("Content-Length") or 0)
        if u.path == "/api/audio/upload":
            # raw file body: a track (mp3 / m4a / ogg / wav / flac) or cover art (png / jpg) for an existing stem.
            # headers: X-Filename (the original name), optional X-Stem (attach art to this track)
            import re as _re
            fn = self.headers.get("X-Filename") or "track.mp3"
            base, ext = os.path.splitext(fn)
            ext = ext.lower()
            stem = _re.sub(r"[^A-Za-z0-9]+", "_", (self.headers.get("X-Stem") or _re.sub(r"^\d+[\s._-]*", "", base))).strip("_").lower()[:60] or "track"
            if ext not in AUDIO_EXT + ART_EXT or not stem:
                self.rfile.read(n)
                return self._send(400, {"error": "audio (mp3 / m4a / ogg / wav / flac) or a png / jpg cover"})
            if n > 400 * 1024 * 1024:
                self.rfile.read(n)
                return self._send(413, {"error": "file over 400 MB"})
            adir = os.path.join(APPDATA, "audio")
            os.makedirs(adir, exist_ok=True)
            out = os.path.join(adir, stem + ext)
            with open(out + ".tmp", "wb") as f:
                left = n
                while left > 0:
                    chunk = self.rfile.read(min(left, 1 << 20))
                    if not chunk:
                        break
                    f.write(chunk)
                    left -= len(chunk)
            os.replace(out + ".tmp", out)
            if ext in AUDIO_EXT:
                # a readable name from the file name; the tags inside the file are read if ffprobe is around
                name = _re.sub(r"^\d+[\s._-]*", "", base).replace("_", " ").strip() or stem
                artist = album = ""
                try:
                    import subprocess
                    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format_tags=title,artist,album", "-of", "json", out], capture_output=True, text=True, timeout=20)
                    tags = {k.lower(): v for k, v in (json.loads(r.stdout).get("format", {}).get("tags") or {}).items()}
                    name = tags.get("title") or name
                    artist, album = tags.get("artist", ""), tags.get("album", "")
                    if not any(os.path.exists(os.path.join(adir, stem + e)) for e in ART_EXT):
                        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", out, "-an", "-frames:v", "1", "-vf", "scale=600:600", "-q:v", "4", os.path.join(adir, stem + ".jpg")], capture_output=True, timeout=30)
                        if os.path.exists(os.path.join(adir, stem + ".jpg")) and os.path.getsize(os.path.join(adir, stem + ".jpg")) == 0:
                            os.remove(os.path.join(adir, stem + ".jpg"))
                except Exception:
                    pass
                _audio_meta_write(stem, name=name, artist=artist, album=album)
            return self._send(200, {"ok": True, "id": stem, "file": stem + ext, "tracks": _audio_tracks()})
        if u.path == "/api/sources/upload":
            # raw video body → data/app/sources/video/<name>; then POST /api/sources/add with the path
            import re as _re
            fn = self.headers.get("X-Filename") or "video.mp4"
            base, ext = os.path.splitext(fn)
            if ext.lower() not in (".mp4", ".mov", ".m4v", ".webm", ".mkv"):
                self.rfile.read(n)
                return self._send(400, {"error": "a video file (mp4 / mov / webm / mkv)"})
            if n > 3 * 1024 ** 3:
                self.rfile.read(n)
                return self._send(413, {"error": "over 3 GB"})
            vdir = os.path.join(SRCS.SRC, "video")
            os.makedirs(vdir, exist_ok=True)
            safe = _re.sub(r"[^A-Za-z0-9._-]+", "_", base)[:80] + ext.lower()
            out = os.path.join(vdir, safe)
            with open(out + ".tmp", "wb") as f:
                left = n
                while left > 0:
                    chunk = self.rfile.read(min(left, 1 << 20))
                    if not chunk:
                        break
                    f.write(chunk)
                    left -= len(chunk)
            os.replace(out + ".tmp", out)
            return self._send(200, {"ok": True, "path": out, "bytes": n})
        if u.path == "/api/tech/clip":
            # raw video body for a tech's clip: headers X-Tech-Id and X-Filename; saved under data/app/tech/clips/
            import re as _re
            tid = _re.sub(r"[^A-Za-z0-9_-]+", "-", self.headers.get("X-Tech-Id") or "")[:48]
            fn = self.headers.get("X-Filename") or "clip.mp4"
            ext = os.path.splitext(fn)[1].lower()
            if not tid or ext not in (".mp4", ".mov", ".webm", ".m4v"):
                self.rfile.read(n)
                return self._send(400, {"error": "need X-Tech-Id and an .mp4 / .mov / .webm file"})
            if n > 400 * 1024 * 1024:
                self.rfile.read(n)
                return self._send(413, {"error": "clip over 400 MB"})
            cdir = os.path.join(TECH, "clips")
            os.makedirs(cdir, exist_ok=True)
            out = os.path.join(cdir, tid + ext)
            with open(out + ".tmp", "wb") as f:
                left = n
                while left > 0:
                    chunk = self.rfile.read(min(left, 1 << 20))
                    if not chunk:
                        break
                    f.write(chunk)
                    left -= len(chunk)
            os.replace(out + ".tmp", out)
            return self._send(200, {"ok": True, "clip": "/tech/clips/" + tid + ext, "bytes": n})
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return self._send(400, {"error": "bad json"})
        if u.path == "/api/progress":
            v = _progress_award(body.get("event"), body.get("ref"))
            return self._send(200, v or {"error": "unknown event"})
        if u.path == "/api/community/refresh":
            names = [n for tm in T.roster["teams"] for n in tm["chars"]]
            th = threading.Thread(target=C.run, args=(names, lambda *a: None), daemon=True)
            th.start()
            return self._send(200, {"ok": True, "note": "fetching in the background; poll /api/community/status"})
        if u.path == "/api/replay/run":
            v = body.get("video")
            if not v:
                return self._send(400, {"error": "video required"})
            ok = RUN.start(v)
            if ok:
                _progress_award("replay_dropped", v)
            return self._send(200, {"ok": ok, "note": "started" if ok else "already running"})
        if u.path == "/api/tech":
            prof = json.load(open(PROFILE, encoding="utf-8")) if os.path.exists(PROFILE) else {}
            body["author"] = body.get("author") or ((prof.get("profile") or {}).get("user") or "me")
            body.setdefault("origin", "mine")
            tech = _tech_save(body)
            _progress_award("tech_written", tech["id"])
            return self._send(200, tech)
        if u.path == "/api/tech/import":
            tech = body.get("tech") or {}
            if not tech.get("title") or not tech.get("steps"):
                return self._send(400, {"error": "a tech needs a title and steps"})
            tech["origin"] = "imported"
            tech["id"] = "imp-" + (tech.get("id") or "x")
            tech = _tech_save(tech)
            _progress_award("tech_imported", tech["id"])
            return self._send(200, tech)
        if u.path == "/api/tech/delete":
            tid = str(body.get("id") or "")
            path = os.path.normpath(os.path.join(TECH, tid + ".json"))
            if tid and path.startswith(TECH) and os.path.exists(path):
                os.remove(path)
                return self._send(200, {"ok": True})
            return self._send(404, {"error": "no such tech"})
        if u.path == "/api/drill":
            import datetime
            d = json.load(open(DRILLS, encoding="utf-8")) if os.path.exists(DRILLS) else {}
            rid = body.get("route")
            if not rid:
                return self._send(400, {"error": "route required"})
            e = d.setdefault(rid, {"char": body.get("char"), "landed": 0, "dropped": 0, "log": []})
            e["landed" if body.get("ok") else "dropped"] += 1
            e["log"].append({"t": datetime.datetime.now().isoformat(timespec="seconds"), "ok": bool(body.get("ok"))}); e["log"] = e["log"][-200:]
            tmp = DRILLS + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(d, f, indent=1)
            os.replace(tmp, DRILLS)
            _progress_award("drill_logged", None)
            return self._send(200, e)
        if u.path == "/api/audio/meta":
            stem = str(body.get("id") or "")
            if not stem or stem not in {t["id"] for t in _audio_tracks()}:
                return self._send(404, {"error": "no such track"})
            _audio_meta_write(stem, name=(body.get("name") or None), artist=body.get("artist"), album=body.get("album"))
            return self._send(200, {"tracks": _audio_tracks()})
        if u.path == "/api/audio/remove":
            stem = str(body.get("id") or "")
            adir = os.path.join(APPDATA, "audio")
            gone = []
            for fn in os.listdir(adir) if os.path.isdir(adir) else []:
                b, e = os.path.splitext(fn)
                if b == stem and e.lower() in AUDIO_EXT + ART_EXT:
                    os.makedirs(os.path.join(adir, "_removed"), exist_ok=True)
                    os.replace(os.path.join(adir, fn), os.path.join(adir, "_removed", fn))
                    gone.append(fn)
            return self._send(200, {"removed": gone, "tracks": _audio_tracks()})
        if u.path == "/api/social/add":
            rec = SOC.add(body.get("url") or "", body.get("note") or "")
            return self._send(200 if "error" not in rec else 400, rec)
        if u.path == "/api/social/remove":
            return self._send(200, {"removed": SOC.remove(body.get("id") or "")})
        if u.path == "/api/social/config":
            d = SOC.load()
            cfg = d["config"]
            if "list_url" in body:
                cfg["list_url"] = str(body["list_url"] or "")[:300]
            if "accounts" in body:
                cfg["accounts"] = [str(a).strip().lstrip("@")[:50] for a in (body["accounts"] or []) if str(a).strip()][:30]
            SOC.save(d)
            return self._send(200, cfg)
        if u.path == "/api/social/pull":
            d = SOC.load()
            accts = body.get("accounts") or d["config"].get("accounts") or []
            if not accts:
                return self._send(400, {"error": "no accounts configured (Options → Community)"})
            return self._send(200, SOC.pull(accts, per=int(body.get("per") or 20)))
        if u.path == "/api/social/parse":
            return self._send(200, SOC.parse_combo(body.get("text") or ""))
        if u.path == "/api/social/to_tech":
            # a post's parsed combo becomes a tech in the Imported shelf, with the source on it
            d = SOC.load()
            post = next((x for x in d["posts"] if x.get("id") == body.get("id")), None)
            if not post:
                return self._send(404, {"error": "post not found"})
            steps = body.get("steps") or (post["combos"][0]["steps"] if post.get("combos") else [])
            if not steps:
                return self._send(400, {"error": "no steps parsed from this post"})
            # which fighter? the first roster name in the post, unless the caller says
            char = body.get("char") or ""
            if not char:
                low = post["text"].lower()
                for nm in T.roster["charname"].values():
                    if nm.lower() in low:
                        char = nm
                        break
            tech = {"title": (body.get("title") or (post["text"].split("\n")[0][:60] or "Combo by @" + post["handle"])),
                    "char": char, "steps": steps, "concepts": body.get("concepts") or [],
                    "notes": (body.get("notes") or "") + ("\n\n" if body.get("notes") else "") + "From the post:\n" + post["text"][:900],
                    "author": ("@" + post["handle"]) if post.get("handle") else post.get("author", ""), "origin": "imported", "clip": post["url"],
                    "clip_credit": {"who": post.get("handle") or post.get("author", ""), "url": post["url"]},
                    "source": {"platform": "x", "url": post["url"], "author": post.get("author", ""), "handle": post.get("handle", ""),
                               "author_url": post.get("author_url", ""), "fetched": post.get("fetched", ""), "line": (post["combos"][0]["line"] if post.get("combos") else "")}}
            tech = _tech_save(tech)
            _progress_award("tech_imported", tech["id"])
            return self._send(200, tech)
        if u.path == "/api/admin/note":
            # a note written inside the app, with where it was written: appended to ops/INBOX.md (read by every
            # session first) and to data/app/admin/notes.jsonl. The errors the UI saw since the last note ride along.
            import datetime
            text = (body.get("text") or "").strip()[:2000]
            if not text and not body.get("errors"):
                return self._send(400, {"error": "empty"})
            now = datetime.datetime.now().isoformat(timespec="seconds")
            rec = {"t": now, "screen": body.get("screen"), "context": body.get("context") or {}, "text": text,
                   "errors": (body.get("errors") or [])[:20], "build": body.get("build")}
            os.makedirs(os.path.dirname(ADMIN_LOG), exist_ok=True)
            with open(ADMIN_LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            ctx = " · ".join("%s=%s" % (k, v) for k, v in rec["context"].items() if v)
            line = "- **%s** · `%s`%s — %s" % (now.replace("T", " "), rec["screen"] or "?", (" · " + ctx) if ctx else "", text or "(errors only)")
            if rec["errors"]:
                line += "\n  - errors: " + "; ".join(str(e)[:160] for e in rec["errors"])
            try:
                os.makedirs(os.path.dirname(INBOX), exist_ok=True)
                new_file = not os.path.exists(INBOX)
                with open(INBOX, "a", encoding="utf-8") as f:
                    if new_file:
                        f.write("# Inbox — notes Raah wrote inside the app\n\n*Newest at the bottom. A session reads this first, acts, and moves each line to DISPATCH or LOG with what was done.*\n\n")
                    f.write(line + "\n")
            except OSError as e:
                return self._send(200, {"ok": True, "inbox": False, "error": str(e)})
            return self._send(200, {"ok": True, "inbox": True})
        if u.path == "/api/grade":
            # a take per finding: free text (the player's read), tags (what it really was), the player's own gap.
            # `verdict` is derived from the tags so older code and the coach's accuracy count keep working.
            import datetime
            g = _grades_read()
            fid = body.get("id")
            if not fid:
                return self._send(400, {"error": "id required"})
            tags = [str(t) for t in (body.get("tags") or []) if str(t) in GRADE_TAGS][:6]
            take = (body.get("take") or body.get("note") or "")[:2000]
            gap = (body.get("gap") or "")[:500]
            verdict = body.get("verdict")
            if verdict not in ("right", "wrong", "actually"):
                verdict = "right" if "real" in tags else ("wrong" if ("lag" in tags or "misread" in tags) else ("actually" if (tags or take) else None))
            if not verdict and not take and not tags:
                return self._send(400, {"error": "say something — a take, a tag, or a gap"})
            prev = g.get(fid) or {}
            g[fid] = {"verdict": verdict or prev.get("verdict") or "actually", "take": take, "note": take, "tags": tags, "gap": gap,
                      "t": datetime.datetime.now().isoformat(timespec="seconds")}
            _grades_write(g)
            _progress_award("claim_graded", fid)
            return self._send(200, {"ok": True, "count": len(g), "grade": g[fid]})
        if u.path == "/api/sources/add":
            m = SRCS.add(body.get("path") or None, creator=body.get("creator", ""), url=body.get("url", ""), title=body.get("title", ""),
                         fighter=body.get("fighter", ""), kind=body.get("type", "guide"), sid=body.get("id") or None)
            if body.get("process") and m.get("video") and not (SRC_JOBS.get(m["id"]) and not SRC_JOBS[m["id"]]["done"]):
                threading.Thread(target=_source_job, args=(m["id"],), daemon=True).start()
            return self._send(200, m)
        if u.path == "/api/sources/meta":
            m = SRCS.meta_read(body.get("id") or "")
            if not m:
                return self._send(404, {"error": "no such source"})
            for k in ("title", "creator", "url", "fighter", "type"):
                if k in body:
                    m[k] = str(body[k] or "")[:300]
            SRCS.meta_write(m["id"], m)
            return self._send(200, m)
        if u.path == "/api/sources/process":
            sid = body.get("id") or ""
            if not SRCS.meta_read(sid):
                return self._send(404, {"error": "no such source"})
            if SRC_JOBS.get(sid) and not SRC_JOBS[sid]["done"]:
                return self._send(200, {"ok": True, "note": "already running"})
            threading.Thread(target=_source_job, args=(sid,), daemon=True).start()
            return self._send(200, {"ok": True})
        if u.path == "/api/sources/transcript":
            sid = body.get("id") or ""
            if not SRCS.meta_read(sid):
                return self._send(404, {"error": "no such source"})
            tmp = os.path.join(SRCS.src_dir(sid), "transcript_pasted.txt")
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(body.get("text") or "")
            r = SRCS.transcript_import(sid, tmp)
            SRCS.combos(sid)
            return self._send(200, r)
        if u.path == "/api/sources/to_tech":
            # a combo read off a source becomes a tech, cited to the creator + timestamp
            sid = body.get("id") or ""
            m = SRCS.meta_read(sid)
            if not m:
                return self._send(404, {"error": "no such source"})
            steps = body.get("steps") or []
            if not steps:
                return self._send(400, {"error": "no steps"})
            t = float(body.get("t") or 0)
            url = m.get("url") or ""
            if url and "youtube" in url and t:
                url = url + ("&" if "?" in url else "?") + "t=%ds" % int(t)
            mm, ss = divmod(int(t), 60)
            who = m.get("creator") or m.get("title") or sid
            tech = {"title": body.get("title") or ("%s · %d:%02d" % (m.get("title") or sid, mm, ss))[:80], "char": body.get("char") or m.get("fighter") or "",
                    "steps": steps, "concepts": body.get("concepts") or [], "origin": "imported", "author": who, "clip": url,
                    "notes": (body.get("notes") or "") + ("\n\n" if body.get("notes") else "") + "From %s at %d:%02d%s" % (m.get("title") or sid, mm, ss, (": “" + body["line"] + "”") if body.get("line") else ""),
                    "source": {"platform": "youtube" if "youtube" in (m.get("url") or "") else "video", "url": url, "author": who, "handle": "", "author_url": "", "fetched": m.get("added", ""), "line": body.get("line") or ""},
                    "clip_credit": {"who": who, "url": url}}
            tech = _tech_save(tech)
            _progress_award("tech_imported", tech["id"])
            return self._send(200, tech)
        if u.path == "/api/coach":
            # {video, reply?, force?} → the coach's take (cached per capture; a reply grows the thread)
            # The coach is under active tuning; reload it per call so a fix lands on
            # the next Ask instead of the next relaunch (it holds no state).
            import importlib
            importlib.reload(COACH)
            video = body.get("video") or ""
            rep = _replay(video)
            if not rep:
                return self._send(404, {"error": "no such capture"})
            prof = json.load(open(PROFILE, encoding="utf-8")) if os.path.exists(PROFILE) else {}
            concepts = _concepts().get("concepts", [])
            you = ((prof.get("team") or ["Magik"])[0])
            quotes = SRCS.quotes(fighter=you, keywords=["portal", "assist", "neutral", "pressure", "punish", "combo", "corner", "meter", "gauge"], limit=10)
            scombos = []
            for sm in SRCS.list_sources():
                if sm.get("fighter") and sm["fighter"] != you:
                    continue
                cp = os.path.join(SRCS.src_dir(sm["id"]), "combos.json")
                if os.path.exists(cp):
                    for c in json.load(open(cp, encoding="utf-8"))[:4]:
                        scombos.append({**c, "creator": sm.get("creator") or sm.get("title")})
            rec = COACH.run(video, rep, _grades_read(), prof, concepts, reply=(body.get("reply") or "").strip() or None, force=bool(body.get("force")), quotes=quotes, source_combos=scombos,
                              habits=[h for h in _habits()["opponents"]
                                      if h["name"] in {n for n, _ in (rep.get("opponents") or [])}],
                              starters=_starters(video))
            if rec.get("last") and not body.get("reply"):
                _progress_award("coach_read", video)
            return self._send(200, rec)
        if u.path == "/api/grades/send":
            # bundle every take on a capture into one markdown file the sessions read: the app's read next to
            # the player's, per finding, plus the tag counts. Also a line in ops/INBOX.md.
            import datetime
            video = body.get("video") or ""
            rep = _replay(video)
            if not rep:
                return self._send(404, {"error": "no such capture"})
            g = _grades_read()
            rows = [(f, g[f["id"]]) for f in rep.get("findings", []) if f["id"] in g]
            if not rows:
                return self._send(400, {"error": "no takes on this capture yet"})
            now = datetime.datetime.now()
            counts = {}
            for _, gg in rows:
                for t in gg.get("tags") or []:
                    counts[t] = counts.get(t, 0) + 1
            lines = ["# Takes — %s · %s" % (video, now.strftime("%Y-%m-%d %H:%M")), "",
                     "*%d of %d findings have a take. Tags: %s.*" % (len(rows), len(rep.get("findings", [])), ", ".join("%s ×%d" % (GRADE_TAGS[k], v) for k, v in sorted(counts.items(), key=lambda kv: -kv[1])) or "none"), "",
                     "Read this as: the app's read of the moment, then Raah's. Where they differ, Raah is the one who was there.", ""]
            for i, (f, gg) in enumerate(rows, 1):
                lines.append("## %d · %s" % (i, f["title"]))
                lines.append("- id `%s` · seg %s · %s · clip `/clips/%s.mp4`" % (f["id"], f.get("segment"), fmt_t(f.get("t", 0)), _re_sub_id(f["id"])))
                lines.append("- **App:** %s%s" % (f.get("receipt", ""), (" · open: " + f["open"]) if f.get("open") else ""))
                lines.append("- **Raah:** %s" % (gg.get("take") or "(no words)"))
                if gg.get("tags"):
                    lines.append("- tags: " + ", ".join(GRADE_TAGS.get(t, t) for t in gg["tags"]))
                if gg.get("gap"):
                    lines.append("- **his gap:** " + gg["gap"])
                lines.append("")
            out_dir = os.path.join(ROOT, "ops", "takes")
            os.makedirs(out_dir, exist_ok=True)
            out = os.path.join(out_dir, "%s_%s.md" % (video, now.strftime("%Y-%m-%d_%H%M")))
            with open(out, "w", encoding="utf-8") as fh:
                fh.write("\n".join(lines))
            try:
                with open(INBOX, "a", encoding="utf-8") as fh:
                    if os.path.getsize(INBOX) == 0:
                        fh.write("# Inbox — notes Raah wrote inside the app\n\n")
                    fh.write("- **%s** · `s-replay` · takes sent — %d findings on %s → `ops/takes/%s` (%s)\n" % (now.isoformat(timespec="seconds").replace("T", " "), len(rows), video, os.path.basename(out), ", ".join("%s ×%d" % (k, v) for k, v in counts.items()) or "no tags"))
            except OSError:
                pass
            return self._send(200, {"ok": True, "file": os.path.relpath(out, ROOT), "count": len(rows)})
        if u.path == "/api/secrets":
            sec = {}
            if os.path.exists(SECRETS):
                with open(SECRETS, encoding="utf-8") as f:
                    sec = json.load(f)
            for k, v in body.items():
                # A key pasted into the model box asks the API for a model named
                # sk-ant-... and 404s. The model field simply refuses keys.
                if k == "coach_model" and str(v).strip().startswith("sk-ant-"):
                    return self._send(400, {"error": "that is the API key — the model box wants a model id like claude-sonnet-4-5, or blank for the default"})
                if v:
                    sec[k] = str(v)
                else:
                    sec.pop(k, None)
            os.makedirs(APPDATA, exist_ok=True)
            tmp = SECRETS + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(sec, f, indent=1)
            os.replace(tmp, SECRETS)
            try:
                os.chmod(SECRETS, 0o600)
            except OSError:
                pass
            out = {k: bool(v) for k, v in sec.items()}
            out["coach_model_value"] = sec.get("coach_model", "")     # the model id is not a secret; the key never leaves
            return self._send(200, out)
        if u.path != "/api/profile":
            return self._send(404, {"error": "not found"})
        os.makedirs(APPDATA, exist_ok=True)
        tmp = PROFILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(body, f, indent=1, ensure_ascii=False)
        os.replace(tmp, PROFILE)
        return self._send(200, {"ok": True})


def main():
    global T
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-open", action="store_true")
    a = ap.parse_args()
    T = Tables()
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    url = "http://127.0.0.1:%d/" % a.port
    print("Whisdom for Tōkon —", url)
    if not a.no_open:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
