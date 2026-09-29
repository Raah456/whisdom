"""
The coach — one Claude call per capture, with receipts.

What goes in: the capture's numbers, its findings (each with its receipt and label), the
player's own takes on those findings (verbatim — where the player and the app disagree, the
player was there), the team, the concept list, and the rules below. What comes out: a short
take where every sentence points at a finding id or is labelled a guess, one question back,
and one drill to go do. Cached to data/app/coach/<video>.json; a reply from the player is
appended and the coach answers again, so the thread grows.

No key → dry run: the exact prompt that would be sent, so it can be read and judged.
stdlib only (urllib). The model id lives in secrets.json as `coach_model` if set.
"""
import json
import os
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.normpath(os.path.join(HERE, "..", "data"))
APPDATA = os.path.join(DATA, "app")
CACHE = os.path.join(APPDATA, "coach")
SECRETS = os.path.join(APPDATA, "secrets.json")
DEFAULT_MODEL = "claude-sonnet-4-5"
API = "https://api.anthropic.com/v1/messages"

SYSTEM = """You are Whisdom, the coach inside a training app for Marvel Tōkon: Fighting Souls (a 4v4 tag fighter: L/M/H/U buttons, assists, Quick Skill, portals for Magik). You coach one player, from their own replay footage, the way a good sparring partner would: specific, short, no hype.

Rules, and they are strict:
1. Every claim you make about what happened must point at a finding id in square brackets, e.g. [LongBatch1:open:13:2231.8]. A sentence with no finding behind it must start with "Guess:". Never invent a moment.
2. The app's findings are measurements of the game's own frame-data panels. They are facts about the panels, not about intent. The player's takes say what the moment meant. Where a take contradicts a finding, believe the take and say so — the player was there and you were not. Windows the player tagged lag or unsure are not evidence of anything.
3. Community material (guides, commentary) may be quoted only with the creator's name and timestamp, e.g. (Marv Media, 10:38). It is what other players say, not a fact about this footage.
4. Say what to do, not what went wrong: one habit to build, tied to a concept from the list and to something they can drill in the app's Training mode (a route from the game's trials, or a tech they wrote). Use the player's own words for what they'd press when they gave them.
5. The frame-data panel exists only in training mode and replay playback. Never tell the player to watch the panel "when you play" — in a live match there is no panel. Advice for live play must rest on what they can see there: spacing, animations, their own habits. Panel-watching belongs in drills.
6. Length: 4 to 7 sentences for the take. Then exactly one question that would change your advice depending on the answer. Then one drill.
7. Output JSON only, no prose around it:
{"take": [{"text": "...", "refs": ["finding id", ...], "label": "fact|model|guess"}, ...],
 "question": "...",
 "drill": {"what": "...", "concept": "<concept id or null>", "where": "training:routes|training:builder|training:pad|matchup|knowledge"},
 "confidence": "low|medium|high",
 "why_confidence": "one line"}"""


def _secrets():
    if os.path.exists(SECRETS):
        try:
            return json.load(open(SECRETS, encoding="utf-8"))
        except ValueError:
            return {}
    return {}


def build_prompt(rep, grades, profile, concepts, thread=None, max_findings=40, quotes=None, source_combos=None, habits=None, starters=None):
    """The user turn: capture → findings with takes → team → concepts → the thread so far."""
    team = (profile.get("team") or [])
    user = (profile.get("profile") or {}).get("user") or "the player"
    # WHO THE PLAYER IS comes from the CAPTURE, not the profile. The profile's point slot read
    # "Captain America" while every segment of LongBatch1 has Magik in it; using it told the coach
    # that all of Raah's own windows belonged to the opponent. rep["you"] is derived in _replay().
    you = rep.get("you") or (team[0] if team else "Magik")
    tagn = {"real": "real opening — should have pressed", "lag": "lag / rollback", "defend": "defending on purpose",
            "spacing": "out of range", "misread": "app misread the panel", "unsure": "not sure"}
    lines = ["CAPTURE %s — %d usable segments, %.1f min of replay playback read, %d openings measured, %d Punish! captions, %s moves segmented [model]." % (
        rep["video"], rep["usable"], rep["live_seconds"] / 60, rep["openings"], rep["punishes"], "{:,}".format(rep["moves"]))]
    lines.append("PLAYER: %s, playing %s in this capture (%s). Their saved team: %s. Opponents here: %s." % (
        user, you, rep.get("you_why") or "from the profile", " / ".join(team) or "?",
        ", ".join("%s ×%d" % (n, c) for n, c in rep.get("opponents", [])) or "?"))
    c = rep.get("conversion") or {}
    if c.get("punish_median_damage"):
        lines.append("WHAT A HIT IS WORTH IN THIS CAPTURE [fact]: %d combos cut from the panel, %d of them %s's. "
                     "Typical combo %s damage, typical punish %s, biggest %s. %d of %d combos stop at one hit; "
                     "%d of %d punishes do. n is small — a direction, never a rate." % (
                         c.get("combos", 0), c.get("yours", 0), you,
                         "{:,}".format(c["median_damage"]), "{:,}".format(c["punish_median_damage"]),
                         "{:,}".format(c.get("biggest", 0)),
                         round(c.get("one_hit_share", 0) * c.get("yours", 0)), c.get("yours", 0),
                         c.get("punish_one_hit", 0), c.get("punishes_yours", 0)))
    if starters and starters.get("starters"):
        lines.append("")
        top = [r for r in starters["starters"][:8]]
        lines.append("WHAT %s OPENS COMBOS WITH [fact on the numbers, model on the name] — %d of %d starters named exactly. "
                     "A name written \"A or B\" is a pair the panel cannot separate (same startup, same damage); do not pick one."
                     % (you, starters.get("resolved_to_one", 0), starters.get("examined", 0)))
        for r in top:
            lines.append("- %s: %d time%s, typical combo %s, best %s"
                         % (r["move"], r["times"], "" if r["times"] == 1 else "s",
                            "{:,}".format(r["median_damage"]), "{:,}".format(r["best"])))
    if habits:
        lines.append("")
        lines.append("WHAT THE OPPONENTS DO [fact on the counts, model on \"they pressed\"] — across every capture on file, not just this one:")
        for hrow in habits[:5]:
            bits = [hrow.get("line"), hrow.get("cost")]
            lines.append("- " + " ".join(b for b in bits if b) + ("" if hrow.get("enough") else " (too few windows to call it a habit — do not)"))
    lines.append("")
    lines.append("FINDINGS (id · what the app measured · [label] · the player's take, if any). The player is the one named %s — on whichever side that fighter appears; in a mirror match the take says which one. A window on the other fighter's side is about the opponent." % you)
    fs = rep.get("findings", [])
    with_takes = [f for f in fs if f["id"] in grades]
    if not with_takes:
        lines.append("NONE of these findings carry the player's take yet. On the one capture the player "
                     "graded by eye, the opening finder was right about half the time — so treat every "
                     "window below as UNCONFIRMED: label sentences resting on them [model] at best, do not "
                     "build a story from more than one unverified window, and keep confidence low.")
    without = [f for f in fs if f["id"] not in grades]
    ordered = (with_takes + without)[:max_findings]
    for f in ordered:
        g = grades.get(f["id"]) or {}
        take = (g.get("take") or g.get("note") or "").strip()
        tags = ", ".join(tagn.get(t, t) for t in (g.get("tags") or []))
        s = "- [%s] %s · %s · [%s]" % (f["id"], f["title"], f.get("receipt", ""), f.get("label", "fact"))
        if f.get("inputs") == 0:
            s += "\n    the input log says nothing was entered in this window at all"
        elif f.get("inputs_held") and max(f["inputs_held"]) >= 20:
            s += "\n    an input was held %d frames here — a long hold is what blocking or walking looks like" % max(f["inputs_held"])
        if take or tags:
            s += "\n    player: %s%s" % (take or "(no words)", (" · tags: " + tags) if tags else "")
            if g.get("gap"):
                s += "\n    player's own gap: " + g["gap"]
        lines.append(s)
    if len(fs) > max_findings:
        lines.append("(%d more findings not shown — smaller windows)" % (len(fs) - max_findings))
    lines.append("")
    lines.append("CONCEPTS you may point at (id: name — one line): " + "; ".join(
        "%s: %s — %s" % (c["id"], c["name"], (c.get("def") or "").split(".")[0]) for c in (concepts or [])[:14]))
    if quotes or source_combos:
        lines.append("")
        lines.append("WHAT OTHER PLAYERS SAY (community — quote with the creator's name and timestamp, never as your own idea):")
        for q in (quotes or [])[:10]:
            mm, ss = divmod(int(q.get("t") or 0), 60)
            lines.append("- %s, \"%s\" @ %d:%02d: %s" % (q.get("creator") or "?", q.get("title") or "", mm, ss, q.get("text", "")))
        for c in (source_combos or [])[:8]:
            mm, ss = divmod(int(c.get("t") or 0), 60)
            lines.append("- combo shown by %s @ %d:%02d: %s" % (c.get("creator") or "?", mm, ss, " > ".join(c.get("steps") or [])))
    if thread:
        lines.append("")
        lines.append("THREAD SO FAR:")
        for t in thread[-6:]:
            lines.append("%s: %s" % ("COACH" if t["role"] == "coach" else "PLAYER", t["text"]))
        lines.append("")
        lines.append("Answer the player's last message, keep the rules, same JSON shape.")
    else:
        lines.append("")
        lines.append("Give your take now. JSON only.")
    return "\n".join(lines)


def call(prompt, key, model=None, timeout=60):
    body = {"model": model or DEFAULT_MODEL, "max_tokens": 4000, "system": SYSTEM,
            "messages": [{"role": "user", "content": prompt}]}
    req = urllib.request.Request(API, data=json.dumps(body).encode("utf-8"), method="POST",
                                 headers={"content-type": "application/json", "x-api-key": key, "anthropic-version": "2023-06-01"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read().decode("utf-8"))
            msg = (err.get("error") or {}).get("message") or str(err)
        except Exception:
            msg = str(e)
        return {"error": "API %s: %s" % (e.code, msg[:300])}
    except Exception as e:
        return {"error": "%s: %s" % (type(e).__name__, str(e)[:200])}
    text = "".join(b.get("text", "") for b in d.get("content", []) if b.get("type") == "text")
    usage = d.get("usage", {})
    parsed = _parse(text)
    return {"raw": text, "parsed": parsed, "model": d.get("model"), "usage": usage, "stop": d.get("stop_reason")}


def _parse(text):
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        if t.startswith("json"):
            t = t[4:]
    try:
        return json.loads(t)
    except ValueError:
        i, j = t.find("{"), t.rfind("}")
        if i >= 0 and j > i:
            try:
                return json.loads(t[i:j + 1])
            except ValueError:
                pass
    return None


def cache_path(video):
    return os.path.join(CACHE, "%s.json" % "".join(c if c.isalnum() or c in "-_." else "_" for c in video))


def load(video):
    p = cache_path(video)
    if os.path.exists(p):
        try:
            return json.load(open(p, encoding="utf-8"))
        except ValueError:
            pass
    return None


def save(video, rec):
    os.makedirs(CACHE, exist_ok=True)
    p = cache_path(video)
    with open(p + ".tmp", "w", encoding="utf-8") as f:
        json.dump(rec, f, indent=1, ensure_ascii=False)
    os.replace(p + ".tmp", p)


def run(video, rep, grades, profile, concepts, reply=None, force=False, quotes=None, source_combos=None, habits=None, starters=None):
    """The whole thing: build, call (or dry-run), cache. `reply` appends the player's message to the
    thread first. Returns the cache record."""
    import datetime
    rec = load(video) or {"video": video, "thread": [], "calls": []}
    if reply:
        rec["thread"].append({"role": "player", "text": reply[:1500], "t": datetime.datetime.now().isoformat(timespec="seconds")})
    elif rec.get("last") and not force:
        return rec
    sec = _secrets()
    key = sec.get("anthropic_api_key")
    # A re-ask with no reply is a FRESH take, not a conversation. Sending the thread
    # ending in the coach's own message plus "answer the player's last message" made
    # the model audit itself instead of coaching (Fable, 2026-09-02: its whole take
    # was corrections of its previous take). Prune trailing coach messages so any
    # thread we send ends with the player; replace the stale take on success.
    thread = list(rec["thread"])
    replace_tail = 0
    while not reply and thread and thread[-1]["role"] == "coach":
        thread.pop(); replace_tail += 1
    prompt = build_prompt(rep, grades, profile, concepts, thread=thread if thread else None, quotes=quotes, source_combos=source_combos, habits=habits, starters=starters)
    if not key:
        rec["dry"] = {"prompt": prompt, "system": SYSTEM, "t": datetime.datetime.now().isoformat(timespec="seconds"),
                      "note": "no API key — this is what would be sent. Options → Coach to add one."}
        save(video, rec)
        return rec
    model = sec.get("coach_model")
    if model and str(model).startswith("sk-ant-"):
        model = None            # a key pasted in the model slot; use the default instead of 404ing
    res = call(prompt, key, model=model)
    entry = {"t": datetime.datetime.now().isoformat(timespec="seconds"), "model": res.get("model") or sec.get("coach_model") or DEFAULT_MODEL,
             "usage": res.get("usage"), "prompt_chars": len(prompt), "error": res.get("error"), "raw": res.get("raw")}
    rec["calls"].append(entry)
    if res.get("error"):
        rec["error"] = res["error"]
        save(video, rec)
        return rec
    rec.pop("error", None)
    rec.pop("dry", None)
    parsed = res.get("parsed") or {"take": [{"text": res.get("raw", ""), "refs": [], "label": "guess"}], "question": "", "drill": None,
                                   "confidence": "low", "why_confidence": "the reply was not valid JSON; shown raw"}
    # every ref must exist; a sentence whose refs do not exist is demoted to guess
    ids = {f["id"] for f in rep.get("findings", [])}
    for s in parsed.get("take") or []:
        refs = [r for r in (s.get("refs") or []) if r in ids]
        bad = [r for r in (s.get("refs") or []) if r not in ids]
        s["refs"] = refs
        if bad or (not refs and s.get("label") != "guess"):
            s["label"] = "guess"
            s["demoted"] = True
    rec["last"] = {"t": entry["t"], "model": entry["model"], "usage": entry["usage"], **parsed}
    coach_text = " ".join(x.get("text", "") for x in (parsed.get("take") or []))
    if parsed.get("question"):
        coach_text += " — " + parsed["question"]
    if replace_tail:
        rec["thread"] = rec["thread"][:-replace_tail]
    rec["thread"].append({"role": "coach", "text": coach_text, "t": entry["t"]})
    save(video, rec)
    return rec


if __name__ == "__main__":
    print(__doc__)
