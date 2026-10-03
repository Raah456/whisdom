# Whisdom

A fighting-game coach that tells you what you actually did, and says "unknown"
when it does not know.

Two games are wired in. **Brawlhalla** reads the `.replay` files the game writes
to your own disk. **Marvel Tokon: Fighting Souls** has no replay file, so it is
read from video you recorded yourself, frame by frame, with computer vision.

---

## The part worth reading

Most fighting-game tooling presents every number with the same confidence,
whether it came from the game, from a measurement, or from a forum post in 2019.
This project treats that as the central problem rather than a footnote.

Every claim carries its source class and the date it was last checked. A
heuristic that cannot be validated returns `None`, not its best guess.

**[DATA_VERIFICATION.md](DATA_VERIFICATION.md) is the clearest example.** A
partner rejected a finding — "he never played Rupture." Rather than patch the
one case, the question became: was this wrong everywhere? The answer is a
measured accuracy table per code path, the exact patch range affected (170 of
4,068 files), three independent validations of the path that was fine, and a
list of conclusions retracted. The bug was found by two methods disagreeing, not
by a test.

The process rules that came out of it are in that file and are now enforced in
code.

---

## What is here

```
schema/             the formal match schema every document validates against
whisdom/core/       events, match model
whisdom/agent/      the coach: reads a parsed match, produces findings
whisdom/vision/     frame extraction and template matching
whisdom/app/        local server and UI
whisdom/games/
  base.py           the adapter interface
  brawlhalla/       replay container, bitstream parser, structural + anchored
                    decode paths, habit metrics
  marveltokon/      video perception — nameplates, HUD, inputs, captions,
                    combo and opening detection, move fingerprinting
tests/
```

4,068 Brawlhalla replays across 44 game versions informed the parser. Input
streams parse on 100% of them.

The Tokon move identifier fingerprints a move from the training-mode panel
alone: across 3,541 measured move instances, 73.7% of observed startup values
land exactly on that character's known table. It reports a pair when two moves
are genuinely indistinguishable, and "not identified" rather than a guess.

---

## What is not here, and why

This repository excludes the layer that unpacks the retail games' own asset
archives, along with everything that layer produced.

That means no archive readers, no script-bytecode decoders, no texture decoding,
no decryption keys, and none of the decoded output — move tables, art, or
otherwise. Third-party wiki data scraped for cross-checking is also excluded,
since it carries its own licence.

Those tools read files that belong to their publishers. Publishing the tools or
their output is a different act from analysing your own replays and your own
recordings, and this repository only does the second.

A consequence: a few Tokon features degrade without the tables they cross-check
against. They fail with an error rather than a wrong answer, which is the rule
the whole project runs on.

---

## Status

Working, incomplete, and honest about which is which. Brawlhalla parsing and
habit analysis are solid. Tokon perception works on recorded footage. The coach
produces findings. Nothing here is packaged for general use.

`PROJECT_HISTORY.md` is the narrative. `DECISION_LOG.md` is every decision with
its date and reasoning. `ARCHITECTURE_DECISIONS.md` covers the adapter design
and why a slot is a human rather than a character.

---

## Running it

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install --upgrade pip      # editable installs need pip >= 21.3
pip install -e .

whisdom --help          # subcommands: ingest, watch, status, report, clips,
                        # damage, review, demo, app, reindex, where
whisdom where           # diagnoses paths and tells you what is missing
```

`whisdom where` is the right first command. With no data it reports what it
looked for and how to point it somewhere real, rather than failing.

Brawlhalla replays come from the game's own replay folder (Account → Replays →
the folder icon). Tokon needs a recording you made yourself.

### Tests

The suites are scripts, not pytest cases — run them directly:

```bash
pip install -e ".[validate]"  # schema validation needs jsonschema
python tests/test_schema.py
```

For `test_vision.py`, install the vision extra so it does not skip because
Pillow is missing:

```bash
pip install -e ".[vision]"
python tests/test_vision.py
```

The vision test also needs ffmpeg on PATH, your recording (`WHISDOM_VIDEO`),
and its verified replay (`WHISDOM_REPLAY`). It still skips if those are missing.

They need gameplay data, which is personal and not in the repo. Without it they
print `SKIPPED — this is a SKIP, not a pass` and exit 0. Point them at your own:

```bash
export WHISDOM_REPLAYS=~/BrawlhallaReplays
```

See `tests/paths.py`. A skip that announces itself as a skip is the same rule as
the rest of the project: never report a result you did not earn.
