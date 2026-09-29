# Adding Marvel Tokon: Fighting Souls

Status as of 2026-08-19: **adapter registered, `load_match` unimplemented.**
`whisdom/games/marveltokon/__init__.py` exists, registers cleanly, and appears in
`whisdom games`. It cannot parse anything yet, and nothing in `core/` or `agent/`
was changed to add it.

Read this before implementing, because most of the work is blocked on facts
nobody has established yet — including publicly. Treat every unverified line
below as a claim, not a finding.

---

## The game

Arc System Works, published by Sony Interactive Entertainment. Released
2026-08-06 worldwide (08-07 Japan) on PS5 and Windows, with cross-play. Rollback
netcode; the closed beta had a spectator mode.

It is a **4v4 tag fighter**. A player begins with one fighter plus an assist and
unlocks a lineup of four as the match progresses. Launch roster is 20 fighters in
five teams — Unbreakable X-Men (Storm, Magik, Wolverine, Danger), Amazing
Guardians (Spider-Man, Ms. Marvel, Star-Lord, Peni Parker), Fighting Avengers
(Captain America, Iron Man, Hulk, Black Panther), Knights of Doom (Doctor Doom,
Magneto, Green Goblin, Carnage), Samurai Outriders (Ghost Rider, Blade, Loki,
Deadpool) — with at least four DLC fighters planned.

---

## The one architectural problem: a slot is no longer a character

This is the first thing that genuinely tests the "one agent, many adapters"
claim, and it deserves a decision before any parsing work starts.

`core.events.Player` carries a **single, static** `character`. In Brawlhalla that
is correct: one human, one Legend, for the whole match. In Tokon one human
controls **four** fighters and swaps between them mid-match, so "which character
is slot 0" is a function of frame, not a constant.

The proposed resolution, which requires **no change to `core/` or the schema**:

* **`slot` stays the human player.** Two slots in a 1v1, exactly as now. This is
  the important half: habit profiling, the pressure analysis and the option
  engine all aggregate per-slot, and they are all trying to describe *a person*.
  Splitting one human across four slots would destroy that.
* **`Player.character`** holds the point fighter (or the team name); the full
  four-fighter lineup goes in `Match.meta`.
* **Tag switches are ordinary input events** — action strings are free-form, so
  `TagIn:Storm` costs nothing and keeps the active fighter recoverable at any
  frame by scanning forward from the start.
* **Fighter defeats encode the fighter in the action string** the same way, e.g.
  `action="KO:Storm"`, with `Event.slot` remaining the **victim's human slot**
  per the contract in `core/events.py`.

The alternative — eight slots with `team` set to 0/1 — makes per-fighter KOs fall
out naturally but breaks every per-player analysis in the repo. Not recommended,
but write down whichever is chosen and why.

**Open question this raises:** is a defeated fighter in Tokon equivalent to a
Brawlhalla stock, for the purposes of moment detection? KOs are whisdom's
highest-value moments and the review engine is built around "at the damage you
were actually at". In a tag fighter the analogous pressure point may be the tag
itself, not the KO. That is a product decision, not a parsing one.

---

## What is blocked, in order

1. **Replay files.** They are **not** in the game's install directory — the
   Windows install is UE5 pak containers and Bink video, with no replay data in
   it. They live in the title's save data. Nothing can start until a legitimately
   obtained set of replays exists.
2. **The container format.** Unknown, and undecoded by anyone publicly. The
   critical unknown is whether a saved match is a **full input log** or only a
   **seed plus metadata** — rollback titles sometimes store the latter, which
   would mean the frame-accurate input stream whisdom depends on is not
   recoverable from a replay at all. *Establish this before anything else; it
   determines whether this adapter is possible.*
3. **Frame data.** Nothing extracted. `ACTION_MODEL` is empty and `pressure` is
   `None` until real numbers exist.

## Deliberately empty, not forgotten

Per CONTRIBUTING.md rules 4 and 5, every unknown degrades to silence rather than
to a plausible-looking constant:

| Field | Value | Behaviour |
|---|---|---|
| `ACTION_MODEL` | `busy_frames={}` | `busy()` returns 0; the wasted-input detector never fires |
| `pressure` | `None` | `whisdom pressure` exits with "does not define a pressure action" |
| `replay_paths` | all empty | `whisdom where` reports no candidates instead of a wrong path |
| `replay_ext` | `".replay"` | **placeholder, unverified** |
| `fps` | `60` | **assumed** — ASW house standard, and the patched PC "broken 60fps" issue implies 60 is the target |

`CATEGORIES` is a first cut, written in tag-fighter vocabulary (`TagIn`,
`AssistCall`, `PushBlock`) rather than borrowed from Brawlhalla — partly because
it is more likely right, and partly to keep `games/example/` doing its job as a
leak detector.

## Where the frame data should come from

**Dustloop (`dustloop.com/w/MTFS`) is the right source** and is exactly the kind
of outside-the-system check CONTRIBUTING.md rule 3 asks for — a published,
community-verified table that can contradict us. It blocks automated fetching
(403), so the numbers need to be brought in by hand.

Note the Brawlhalla precedent before leaning on it: 414 signatures shipped with
per-part data and **no summary figures**, because three plausible aggregation
rules disagreed by 5–20× and no published source could settle it. Tokon is a
tag fighter with assists and team supers, so the same "which parts are sequential
vs alternative" problem is likely, and a published total may be measuring
something different from what the adapter needs.

## What was NOT done, and why

A copy of the Windows install was available while this was written. It was
**not** unpacked or reverse-engineered. It showed the fingerprints of a
DRM-stripped build (a Steam emulator config, renamed `steam_api64` and EOS SDK
binaries, a small loader `.exe` in place of the shipping binary) for a paid title
released two weeks earlier. Extracting game content from it would also have run
straight into the repo's own standing rule — decrypted game content is the
publisher's, never committed, never ours.

None of that blocks the work: the replay format is what matters, and it is not in
the install directory anyway.
