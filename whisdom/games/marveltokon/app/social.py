"""
Community feed — other players' combos, cited.

A post is added by its URL (X / Twitter for now). We ask X's own oEmbed endpoint for
it — the documented, unauthenticated way to republish a public post with attribution:
    https://publish.twitter.com/oembed?url=<post>&omit_script=true&dnt=true
It returns the author's name and profile URL, the post text as HTML, and an embed block
that X's widget script turns into the real post (with its video) inside the app. That
is what "watching" is: X's own embed, in our frame, with the author's name and link on
it. No scraping, no login, no copies of their media on disk.

The text is parsed for fighting-game notation (numpad + L/M/H/U, j., 236…) into steps
the app understands, with a confidence figure. Above the threshold the post can become
a tech — a drill in Training — carrying the source: author, handle, URL, when fetched.

Discovery (finding posts without pasting links) has no stable, free, sanctioned path
today: the X API is paid, the web UI forbids scraping. The app can embed an X *list*
timeline (official widget) so a curated list of lab players scrolls inside the app;
posts still get added by link. `pull()` below tries X's syndication endpoint for a
handful of accounts — undocumented, may break, best effort, every failure recorded.

Storage: data/app/community/posts.json (gitignored — it is other people's text).
"""
import json
import os
import re
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.normpath(os.path.join(HERE, "..", "data"))
COMM = os.path.join(DATA, "app", "community")
POSTS = os.path.join(COMM, "posts.json")
UA = "Whisdom/0.5 (+local coach app; fetches one post at a time by its URL)"

# ---------------------------------------------------------------- notation parser

def _token_re(btn):
    return re.compile(
        r"(?<![A-Za-z0-9])"
        r"(?P<pre>(?:j\.|dl\.|c\.|dc\.|cl\.|f\.|st\.|cr\.|dj\.|sj\.)*)"
        r"(?P<motion>[1-9]{1,6})?"
        r"(?P<btn>" + btn + r")"
        r"(?P<plus>(?:\+" + btn + r")*)"
        r"(?P<hold>\[\]|\(hold\))?"
        r"(?![A-Za-z0-9])", re.I)


TOKEN = _token_re(r"(?:QS|QA|[LMHU]{1,3}|[AT])")          # the app's notation: L M H U (a run like MM = pressed twice), A assist, T tag
TOKEN_LETTERS = _token_re(r"(?:QS|QA|[ABCD]{1,3}|T)")       # the game's trial letters: A B C D
WORD = re.compile(r"(?<![A-Za-z])(jump|jc|sj|dj|land|dash|delay|walk|whiff|hold|charge|tag|assist|super|ultimate|dhc|tac|ult)(?![A-Za-z])", re.I)
SEP = re.compile(r"\s*(?:>|→|->|,|xx|~|then|into|\||;)\s*", re.I)
LETTERS = {"A": "L", "B": "M", "C": "H", "D": "U"}


def _letters_mode(text):
    """The game's own trial letters: A/B/C/D for L/M/H/U. Only if B/C/D show up as buttons
    and none of L/M/H/U do — otherwise A means assist."""
    has_letters = re.search(r"(?<![A-Za-z])[1-9]?[BCD](?![A-Za-z])", text) is not None
    has_lmhu = re.search(r"(?<![A-Za-z])[1-9]?j?\.?[LMHU](?![A-Za-z])", text) is not None
    return has_letters and not has_lmhu


def parse_combo(text):
    """Text → {steps, confidence, raw_tokens, recognised}. Steps are in the app's wiki notation
    (2M, 236H, j.5H, 5A, jump…). confidence = recognised tokens / candidate tokens."""
    t = (text or "").replace("→", ">")
    letters = _letters_mode(t)
    # split on separators and whitespace to count candidates; a candidate is any run of [A-Za-z0-9.+\[\]]
    candidates = [c for c in re.split(r"[\s>,~|;→]+", t) if re.search(r"[A-Za-z0-9]", c)]
    steps, recognised = [], 0
    for cand in candidates:
        cand_clean = cand.strip("()[]{}.:!?\"'")
        rx = TOKEN_LETTERS if letters else TOKEN
        m = rx.fullmatch(cand_clean) or rx.fullmatch(cand_clean.upper())
        if m:
            pre = (m.group("pre") or "").lower().replace("cl.", "").replace("st.", "5").replace("cr.", "2").replace("c.", "").replace("f.", "6")
            pre = pre.replace("dj.", "j.").replace("sj.", "j.")
            motion = m.group("motion") or ""
            btn = m.group("btn").upper()
            plus = (m.group("plus") or "").upper()
            if letters and all(ch in LETTERS for ch in btn):
                btn = "".join(LETTERS[ch] for ch in btn)
                plus = "".join("+" + LETTERS.get(p, p) for p in plus.split("+") if p)
            if pre.endswith("5") and motion:
                pre = pre[:-1]
            if pre == "2" and motion:
                pre = ""
            if not motion and pre in ("", "j.", "dl.", "dc.", "j.dl."):
                motion = "5"
            # a run like MM / HH / UU is the button pressed again: one step per press
            presses = [btn] if len(btn) < 2 or btn in ("QS", "QA") else list(btn)
            for k, b in enumerate(presses):
                step = f"{pre}{motion if k == 0 else '5'}{b}{plus if k == len(presses) - 1 else ''}"
                if k > 0 and pre.startswith("j."):
                    step = "j.5" + b
                step = re.sub(r"^(j\.)5(?=[0-9])", r"\1", step)
                steps.append(step)
            recognised += 1
            continue
        w = WORD.fullmatch(cand_clean)
        if w:
            word = w.group(1).lower()
            steps.append({"jc": "jump", "sj": "jump", "dj": "jump", "ult": "ultimate"}.get(word, word))
            recognised += 1
            continue
    conf = (recognised / len(candidates)) if candidates else 0.0
    return {"steps": steps, "confidence": round(conf, 2), "candidates": len(candidates), "recognised": recognised, "letters": letters}


def combo_lines(text):
    """Posts often carry one combo per line plus commentary. Return the best-parsing line(s):
    every line whose own confidence ≥ .5 and ≥ 3 steps, best first."""
    out = []
    for ln in re.split(r"[\r\n]+", text or ""):
        p = parse_combo(ln)
        if len(p["steps"]) >= 3 and p["confidence"] >= 0.5:
            out.append({"line": ln.strip(), **p})
    out.sort(key=lambda x: (-x["confidence"], -len(x["steps"])))
    return out


# ---------------------------------------------------------------- oEmbed

def _norm_url(url):
    u = url.strip()
    u = re.sub(r"^https?://(www\.)?(x\.com|mobile\.twitter\.com)/", "https://twitter.com/", u)
    u = u.split("?")[0]
    return u


def _html_text(html):
    """The blockquote's <p> text, tags stripped, entities decoded, <br> → newline."""
    import html as _h
    m = re.search(r"<p[^>]*>(.*?)</p>", html or "", re.S)
    body = m.group(1) if m else (html or "")
    body = re.sub(r"<br\s*/?>", "\n", body)
    body = re.sub(r"<[^>]+>", "", body)
    return _h.unescape(body).strip()


def oembed(url, timeout=12):
    """Ask X for the embed of one public post. Returns the record or {'error': …}."""
    u = _norm_url(url)
    if not re.match(r"https://twitter\.com/[^/]+/status/\d+", u):
        return {"error": "not a post URL (expected x.com/<user>/status/<id>)", "url": url}
    q = urllib.parse.urlencode({"url": u, "omit_script": "true", "dnt": "true", "hide_thread": "true", "align": "center", "maxwidth": "550"})
    req = urllib.request.Request("https://publish.twitter.com/oembed?" + q, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read().decode("utf-8"))
    except Exception as e:  # network, 404 (deleted / private), rate limit
        return {"error": "%s: %s" % (type(e).__name__, str(e)[:160]), "url": u}
    handle = ""
    m = re.match(r"https?://(?:www\.)?twitter\.com/([^/?#]+)", d.get("author_url", ""))
    if m:
        handle = m.group(1)
    text = _html_text(d.get("html", ""))
    return {
        "id": "x-" + u.rsplit("/", 1)[-1],
        "url": u, "platform": "x",
        "author": d.get("author_name", ""), "handle": handle, "author_url": d.get("author_url", ""),
        "text": text, "html": d.get("html", ""),
        "combos": combo_lines(text),
        "fetched": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
    }


# ---------------------------------------------------------------- store

def load():
    if not os.path.exists(POSTS):
        return {"posts": [], "config": {"list_url": "", "accounts": []}}
    try:
        d = json.load(open(POSTS, encoding="utf-8"))
    except ValueError:
        d = {"posts": []}
    d.setdefault("posts", [])
    d.setdefault("config", {"list_url": "", "accounts": []})
    return d


def save(d):
    os.makedirs(COMM, exist_ok=True)
    tmp = POSTS + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=1, ensure_ascii=False)
    os.replace(tmp, POSTS)


def add(url, note=""):
    d = load()
    rec = oembed(url)
    if "error" in rec:
        return rec
    rec["note"] = note[:500]
    rec["added"] = rec["fetched"]
    d["posts"] = [p for p in d["posts"] if p.get("id") != rec["id"]] + [rec]
    save(d)
    return rec


def remove(pid):
    d = load()
    n = len(d["posts"])
    d["posts"] = [p for p in d["posts"] if p.get("id") != pid]
    save(d)
    return n - len(d["posts"])


def pull(accounts, per=20, timeout=12):
    """Best effort: X's syndication endpoint for an account's recent posts (the thing the
    official embedded-timeline widget reads). Undocumented; may 403 or change. Each post that
    parses to a combo is added like a pasted link would be. Returns {added, errors}."""
    added, errors = [], []
    for acct in accounts:
        acct = acct.strip().lstrip("@")
        if not acct:
            continue
        url = "https://syndication.twitter.com/srv/timeline-profile/screen-name/%s" % urllib.parse.quote(acct)
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                page = r.read().decode("utf-8", "replace")
        except Exception as e:
            errors.append("%s: %s" % (acct, str(e)[:120]))
            continue
        ids = re.findall(r'"id_str":"(\d{10,})"', page)
        seen = set()
        for pid in ids:
            if pid in seen:
                continue
            seen.add(pid)
            if len(seen) > per:
                break
            rec = oembed("https://twitter.com/%s/status/%s" % (acct, pid))
            if "error" in rec:
                errors.append("%s/%s: %s" % (acct, pid, rec["error"]))
                continue
            if rec["combos"]:
                d = load()
                if not any(p.get("id") == rec["id"] for p in d["posts"]):
                    rec["added"] = rec["fetched"]
                    rec["note"] = "pulled from @%s" % acct
                    d["posts"].append(rec)
                    save(d)
                    added.append(rec["id"])
    return {"added": added, "errors": errors}


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "parse":
        print(json.dumps(parse_combo(" ".join(sys.argv[2:])), indent=1))
    elif len(sys.argv) > 1:
        print(json.dumps(add(sys.argv[1]), indent=1, ensure_ascii=False)[:2000])
    else:
        print(__doc__)
