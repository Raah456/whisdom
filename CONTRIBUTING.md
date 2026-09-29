# Working on Whisdom

Most of this file is about verification, because nearly every serious bug in this
project passed its tests first.

---

## Who owns what

The split follows a seam that already exists in the code, so the two sides rarely
touch the same files.

**The model and the game — needs someone who plays well**

* `whisdom/games/brawlhalla/payoffs.py` — the six constants, and the shape of the
  payoff functions. Is contesting really wrong at 100% against a ledge camper?
* `whisdom/games/brawlhalla/` generally — what the game's semantics actually are.
* Which moments matter, what counts as a mistake, whether a verdict is sane.
* Ground truth: annotating matches, training-mode measurements.

**The pipeline — needs someone comfortable in code**

* `whisdom/core/`, `whisdom/agent/`, `whisdom/vision/`, `whisdom/app/`
* Parsing, storage, the CLI, the UI, performance.

**The contract between them: `schema/match.schema.json`.** Versioned, and 4,000+
documents validate against it. Adding a field is cheap; changing the meaning of
one is not — say so in `DECISION_LOG.md` and bump the version.

---

## The verification rules

These are not general good practice. Each one exists because it was violated here
and cost real work.

### 1. Verify the output, not the status code

Captions silently vanished from every clip for days. `_esc` escaped `%` as `\%`,
ffmpeg rejected it with "Stray %", drew nothing — **and exited 0 with a perfectly
valid video.** Nothing failed. It was found by pulling a frame out of the encoded
file and looking at it.

If a component can fail silently, check what it produced. An exit code is not
evidence.

### 2. A green test suite proves behaviour has not *changed*, not that it was ever *right*

The golden-file regression suite passed through three separate wrong models. It
is genuinely useful — it catches accidental changes — but it cannot tell you the
thing it locked in was correct.

### 3. Internal consistency is not validation

The KO block credits the *killer*, not the victim. We read it as the victim. The
result field was *also* read backwards. The two errors were mutually consistent,
so a 19-check audit passed at 99.9% while the headline finding and the win rate
were both inverted.

Only something outside the system can validate a semantic assumption about a
reverse-engineered field. On this project that has always been a person or a
video, never a test.

### 4. When the data might be wrong, say so in the output

Six moves have an impossible 0-frame startup. They are flagged `known=False` and
their cells carry confidence 0.3 rather than being quietly scored. Before that,
Lance topped the rankings on a phantom 0-frame recovery.

Ship the doubt with the number. `DECISION_LOG.md` has the precedent: 414
signatures shipped with per-part data and no summary figures, because three
plausible aggregation rules disagreed by 5–20×.

### 5. Advice that never changes is a bug wearing a disguise

Twice the engine produced confident, specific-looking output that was really a
constant: once because frame data only entered as branch conditions, once because
`wait` and `retreat` cells were still hand-assigned. Both looked fine until
someone asked why every weapon got the same answer.

`tests/test_payoffs.py` and `tests/test_review.py` now assert that advice differs
across weapons and across game states.

---

## The retractions

Three findings were published inside this project and later withdrawn. All three
were caught by the player, not by code.

| Claim | Reality | How it was caught |
|---|---|---|
| "He mains Rupture" | Never played it. A forward-scan returned hero 70 every time | He said so |
| KO victim identity | The block credits the killer. Deaths, win rate and the headline finding were all inverted | He said "he was Diana" |
| Damage curve | Blue portrait background passed the saturation filter and wrapped to *maximum* damage | Looking at the cropped images |

If you find a fourth, add it to the table.

---

## Before you commit

```bash
for t in tests/test_*.py; do echo "== $t"; python3 "$t"; done
```

`test_payoffs` runs anywhere. `test_review` runs its input-classification checks
anywhere and skips the rest. The others need data — see `tests/paths.py`, or set
`WHISDOM_REPLAYS`, `WHISDOM_REPLAY` and `WHISDOM_VIDEO`.

Tests skip when their inputs are missing. **Read the output** — a skip line and a
pass line look similar and mean opposite things.

## Writing in the decision log

Append an entry when you decide something, change a model, or retract a claim.
Say what was believed, what is true, and how you know. Someone reading only this
file should be able to avoid repeating the mistake.

That file is the reason this project can be handed between people at all.

## Never commit

* `tools/dump/` or any `.swz` / `.swf` — decrypted Brawlhalla content. Blue
  Mammoth's, not ours.
* `store/` — personal gameplay data, and hundreds of megabytes.
* Replays and recordings.

`.gitignore` covers these. Check `git status` before your first commit anyway.
