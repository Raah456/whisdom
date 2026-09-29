"""
Community notes — snapshot fetcher for tokon.gg.

Runs on the player's own machine only (the server calls it in a thread when the
UI asks for a refresh, or: python3 -m whisdom.games.marveltokon.app.community).
One request per page, two seconds apart, a User-Agent that names this tool.
tokon.gg's robots.txt allows general crawling and blocks AI crawlers by name;
this is neither — it is the player's own client fetching pages he reads anyway.

What it stores, per character, in data/app/community/tokon_gg.json:
    tier          "S" | "A" | "B" | "C" | "D" | None      from the tier-list page, else the character page
    overview      first paragraph under "<Name> Character Overview"
    how_to_play   first paragraph under "How to Play"
    combos        [{"section": "Basic … Combos", "text": "Down M 》M 》H …"}, …]
    url, fetched  the page and the ISO date it was read
Everything is editorial (one author, tokon.gg / DotGG) — the UI says so.

The parser is tolerant: it flattens the page to (kind, text) lines — headings,
paragraphs, list items, table cells — and reads around heading text. It was
written against the page structure read on 2026-08-25 and has NOT been run
against the live site from this environment (no network here). First live run
is the test; failures are reported per character, never silently skipped.
"""
import datetime
import html
import json
import os
import re
import sys
import time
import urllib.request
from html.parser import HTMLParser

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.normpath(os.path.join(HERE, "..", "data", "app", "community"))
OUT = os.path.join(OUT_DIR, "tokon_gg.json")
STATUS = os.path.join(OUT_DIR, "status.json")
UA = "Whisdom/0.1 (personal training tool; one request per page; contact: the player)"
BASE = "https://tokon.gg/"


def slug(name):
    s = name.lower().replace("ō", "o").replace("'", "").replace(".", "")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s


class Flat(HTMLParser):
    """Flatten HTML to a list of (kind, text) where kind ∈ h1..h6, p, li, td, th."""
    KEEP = {"h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "td", "th"}

    def __init__(self):
        super().__init__()
        self.lines, self._stack, self._buf, self._skip = [], [], [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "nav", "footer", "noscript"):
            self._skip += 1
        if tag in self.KEEP:
            self._stack.append(tag); self._buf.append([])
        if tag == "br" and self._buf:
            self._buf[-1].append(" ")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "nav", "footer", "noscript"):
            self._skip = max(0, self._skip - 1)
        if tag in self.KEEP and self._stack and self._stack[-1] == tag:
            self._stack.pop()
            txt = re.sub(r"\s+", " ", "".join(self._buf.pop())).strip()
            if txt:
                self.lines.append((tag, txt))

    def handle_data(self, data):
        if self._skip or not self._buf:
            return
        self._buf[-1].append(html.unescape(data))


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", "replace")


def flatten(page):
    f = Flat(); f.feed(page); return f.lines


TIER_RE = re.compile(r"\b([SABCDEF])[\s-]?Tier\b", re.I)


def parse_tier_list(lines, names):
    """Walk the tier-list page: a heading naming a tier, then the characters under it."""
    tiers, cur = {}, None
    for kind, txt in lines:
        m = TIER_RE.search(txt)
        if kind.startswith("h") and m:
            cur = m.group(1).upper(); continue
        if cur:
            for n in names:
                if n.lower() in txt.lower() and len(txt) < 80:
                    tiers.setdefault(n, cur)
    return tiers


def parse_character(lines, name):
    out = {"tier": None, "overview": None, "how_to_play": None, "combos": []}
    for kind, txt in lines:
        m = TIER_RE.search(txt)
        if m and not out["tier"] and len(txt) < 40:
            out["tier"] = m.group(1).upper()
    section = None
    for kind, txt in lines:
        if kind.startswith("h"):
            section = txt
            continue
        low = (section or "").lower()
        if kind == "p" and "overview" in low and not out["overview"] and len(txt) > 40:
            out["overview"] = txt
        elif kind == "p" and "how to play" in low and not out["how_to_play"] and len(txt) > 40:
            out["how_to_play"] = txt
        elif kind in ("li", "p", "td") and "combo" in low and ("》" in txt or ">" in txt or "→" in txt):
            out["combos"].append({"section": section, "text": txt})
    return out


def run(names, log=print):
    os.makedirs(OUT_DIR, exist_ok=True)
    snap = {"source": "tokon.gg (DotGG) — editorial, one author", "fetched": datetime.datetime.now().isoformat(timespec="seconds"),
            "characters": {}, "errors": {}}
    def status(msg, done, total):
        with open(STATUS, "w", encoding="utf-8") as f:
            json.dump({"msg": msg, "done": done, "total": total, "t": datetime.datetime.now().isoformat(timespec="seconds")}, f)
    total = len(names) + 1
    status("tier list", 0, total)
    tiers = {}
    try:
        tiers = parse_tier_list(flatten(fetch(BASE + "tier-list/")), names)
        log("tier list:", len(tiers), "characters placed")
    except Exception as e:  # noqa
        snap["errors"]["tier-list"] = str(e); log("tier list failed:", e)
    time.sleep(2)
    for i, n in enumerate(names):
        url = BASE + slug(n) + "/"
        status(n, i + 1, total)
        try:
            c = parse_character(flatten(fetch(url)), n)
            c["tier"] = tiers.get(n) or c["tier"]
            c["url"] = url; c["fetched"] = snap["fetched"]
            snap["characters"][n] = c
            log(f"{n}: tier {c['tier']} · overview {'yes' if c['overview'] else 'no'} · {len(c['combos'])} combos")
        except Exception as e:  # noqa
            snap["errors"][n] = str(e); log(f"{n}: FAILED {e}")
        time.sleep(2)
    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(snap, f, indent=1, ensure_ascii=False)
    os.replace(tmp, OUT)
    status("done", total, total)
    return snap


def load():
    if os.path.exists(OUT):
        with open(OUT, encoding="utf-8") as f:
            return json.load(f)
    return None


if __name__ == "__main__":
    roster = json.load(open(os.path.join(HERE, "..", "data", "app", "roster.json"), encoding="utf-8"))
    names = [n for t in roster["teams"] for n in t["chars"]]
    if len(sys.argv) > 1:
        names = sys.argv[1:]
    run(names)
