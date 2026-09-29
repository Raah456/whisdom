# How this project got here

`DECISION_LOG.md` records technical decisions as they were made, in order, with
the retractions. This file is the narrative around them: where the project
started, what it turned into, what was tried and abandoned, and the product
choices that are not visible in the code.

Written for someone joining who was not in the conversations.

---

## 1. It started as a spreadsheet

The original request was frame data for every character in Brawlhalla, as an
Excel workbook. That is genuinely where this began.

The problem surfaced immediately: **no complete, trustworthy source exists.** The
community wikis cover a fraction of the moves, disagree with each other, and go
stale every patch. So the first real decision was to stop copying published
numbers and go to the game's own files instead.

That route required reading the game's own packaged archives. The code that
does it, and everything it produced, is deliberately not in this repository —
see "What is not here" in the README. What survives here is the half that
reads replay files the game writes to your own disk, and the half that measures
gameplay from video you recorded yourself.

**The workbook shipped**, and the frame data in it is validated against an
independent source: startup matched on 13 of 15 sampled moves exactly, recovery
on 28 of 30 within a frame.

## 2. It became an analyser

The question that changed the project: *if we built a tool that took your
gameplay and told you what you did wrong, what else would it need?*

That reframed everything. Frame data stopped being the deliverable and became an
input.

The vision, in the words it was actually described in:

> upload some matches, you build the profile and learn, then you play a match and
> run it against the profile and see how their habits worked against them

and later, more precisely:

> Ultimately games like this have an rps aspect in choices and options. We want
> the detector to compare different options and pick the winning moves to show
> what could have been better.

Everything since has been in service of that second sentence. It is the reason
the option engine exists, and the reason "you dodge a lot" was never considered
a good enough output.

## 3. What the replay file actually contains

Brawlhalla's `.replay` format is undocumented. It was decoded from scratch: zlib
inflate, then an XOR against a 64-byte key, then an MSB-first bitstream. It now
reads every version from 6.06 to 10.09 — 45 patches, 4,055 matches, roughly seven
million button presses.

**The decisive finding was what is NOT in there.** A replay stores *inputs only*.
No positions, no damage, no stocks. The game reproduces a match by replaying the
inputs through its own physics.

That single fact shaped the entire architecture, and produced the biggest
abandoned branch.

## 4. Re-simulation: tried, then ruled out

The obvious response to "no state in the file" is to rebuild the state: implement
Brawlhalla's physics, feed the inputs through it, recover positions.

**Abandoned deliberately.** It requires exact movement constants, exact collision
behaviour, and exact per-patch changes, across 45 versions. Any small error
compounds over three minutes until the simulation and the real match have nothing
to do with each other — and, worse, it would fail *silently*, producing confident
positions that are simply wrong.

Several data-collection tasks existed only to feed that simulator (measuring run
speed, jump arcs, fastfall). They were cancelled when it was.

The state problem was solved differently and much later: **read it off the screen**
(§7).

## 5. Product decisions

These are not in the code, and they are the ones a new person will not be able to
infer.

**Local first.** The tool runs entirely on your machine. No accounts, no upload,
no network. That is why the app is a Python stdlib server rather than Electron or
a web app — the two people working on this are on macOS and Windows, and neither
should need Node or Rust to run it.

**Free tier is the local tool. Paid tier is progression.** The thing worth paying
for is the version that accumulates: your habits tracked over time, your progress
visible, gamified. The free tier is a complete, useful, offline analyser. This
split is decided; the progression data model is not built yet, and nothing
longitudinal exists in the schema.

**Console support: dropped entirely.** PS5 was considered and then removed from
scope, not deferred. Consoles produce no replay files, so console gameplay could
only ever be analysed from video — a strictly weaker product built on a separate
pipeline. Better to do one thing properly.

**Gamification: deferred, not dropped.** Explicitly parked until there is a UI to
hang it on.

**Named FightingWhisdom** — Whis plus wisdom. The Python package is `whisdom`.

**Architecture: one agent, many adapters.** Brawlhalla is the first game, not the
only intended one. `whisdom/core/` holds nothing game-specific;
`whisdom/games/base.py` is the contract a new game implements. This was chosen
before there was any second game, and it is still only proven against one — the
example adapter is a stub.

## 6. What the corpus turned out to be

4,055 matches from one player's account, spanning 45 patches and 2,888 distinct
opponents. Most-played legends, read from the replays: Diana 1,949, Kaya 781.

Two things about it matter:

* **It is one person's data.** Everything the tool "knows" about how anyone plays
  comes from this one account and its opponents.
* **A third of it has no death data.** KO extraction fails on 75% of 6.x matches
  and 21% of 7.x. These are full-length games, not abandons — 176 seconds average
  against 186 for matches that parse. Modern patches are fine, which is why it
  went unnoticed for so long.

## 7. Reading game state off the screen

With re-simulation ruled out, damage came from the HUD instead. Brawlhalla draws
each player's damage as a coloured arc beside their portrait, and the arc is a
fixed-size crescent whose *colour* moves along a ramp: white → pale yellow →
orange → red, resetting to white on death.

Three things make this work better than it sounds:

* **Arc detection is automatic** — the arcs are found as the pixels that change
  over the match *and* go warm, which excludes the timer and stock numerals
  (always white) and moving characters (warm only briefly at any one pixel).
  Position-independent, which mattered: the HUD in the test footage is top-right,
  not where it was assumed to be.
* **The recording aligns itself to the replay.** Each player's deaths form a
  fingerprint in time, and only one alignment fits. The tool derives both the
  time offset and which HUD slot is which player from that alone. This removed
  the one manual step the data-collection instructions used to require.
* **It self-validates.** Damage must collapse to white after a KO, and KO times
  come from the replay. The two sources check each other.

## 8. The option engine

The RPS idea, made concrete. For each death: what was chosen, what it was worth
against how that opponent actually plays, and what would have been worth more.

Two things were needed to make it non-trivial, and both were bugs before they
were features:

* **Payoffs derived from frame data.** The first engine used frame data only as
  branch conditions, so it returned one of three hand-picked constants regardless
  of how much faster a move was — which is why it gave near-identical advice for
  all fourteen weapons.
* **Payoffs conditioned on game state.** Adding what landing a hit is *worth*
  (given their damage) alongside what being hit *costs* (given yours) turned a
  symmetric model into a situational one. Contesting is cheap when you are fresh
  and they are at kill percent, and reckless in reverse. 12 of 14 weapons now
  change their recommendation with the damage situation.

**What the engine deliberately does not use:** per-move damage and knockback. Those
fields are not trustworthy — multi-part moves resolve to their first part only, so
Sword side-light reads 0 damage against a published 15, and 46 of 112 moves carry
zero. The model reasons about timing, which is validated, and takes lethality from
the video damage reading instead.

**Reach is extracted but also not used.** The power table carries per-frame hitbox
geometry, and reach was pulled for all 14 weapons. Wiring it into the engine would
be wrong: reach means nothing without knowing how far apart the players were, and
there is no position data. It ships as reference and as a cheap validation ask.

## 9. What the tool still cannot do

* **Position.** Nothing knows whether you were offstage. It is why "go deep" and
  "ground pound" are the same inputs, and why hitboxes cannot be drawn onto real
  footage — that needs position, camera scale and facing, and Brawlhalla's camera
  pans and zooms continuously.
* **Hurtboxes.** The power table names them only; the shapes are Flash vector data
  inside the SWF.
* **Weapon identity.** Not recorded in the replay. The engine assumes Sword.
* **Whether the advice is good.** No strong player has reviewed it.

## 10. How the work was done, and what it cost

Three findings were published inside this project and later retracted. They are
the most useful thing in this document.

| Claimed | Actually | Caught by |
|---|---|---|
| "He mains Rupture" | Never played it — a forward scan returned hero 70 whenever it could not resolve | The player saying so |
| KO victim identity | The KO block credits the *killer*. Deaths, win rate and the headline finding were all inverted | The player saying "he was Diana" |
| Damage curve | The blue portrait background passed a saturation filter and wrapped to *maximum* damage | Looking at the cropped images instead of the numbers |

Every one was caught from outside the system. None was caught by a test.

The KO case is the instructive one: the KO attribution and the result field were
*both* read backwards, and the two errors agreed with each other, so a 19-check
audit passed at 99.9% while the headline finding was upside down.

Later, the same class of thing kept appearing:

* ffmpeg drew no caption, **exited 0**, and produced a valid video. Clips shipped
  without their annotations and nothing failed.
* The damage extractor passed 5/5 KO detection while measuring the wrong thing
  entirely — a death changes the picture no matter what you measure.
* Seven tests pointed at paths that existed on only one machine. They did not
  error; they *skipped*, and a skip reads like a pass.

`CONTRIBUTING.md` states the resulting rules. The short version: **a green result
is not evidence, internal agreement is not validation, and when a component can
fail silently you must look at what it produced.**

## 11. Collaboration

Two people. One is the product and technical lead; the other is the domain
expert, the source of all the replay data, and much more technical. The workflow
is deliberately asynchronous.

The ownership split follows a seam already present in the code so the two sides
rarely touch the same files: the model and the game semantics
(`games/brawlhalla/`, the six payoff constants) on one side, the pipeline
(`core/`, `agent/`, `vision/`, `app/`) on the other, with
`schema/match.schema.json` as the contract between them.

Work that needs the domain expert was deliberately queued rather than guessed at:
reviewing the advice, annotating matches, and a five-minute training-mode
measurement that would unblock both the 414 signatures and per-move knockback.

## 12. Where it stands

Working and verified: replay parsing across 45 patches, frame-accurate inputs, KO
extraction on 8.x+, legends and stages, damage from video, automatic video/replay
alignment, the option engine, a local app, captioned death clips.

Not yet true: the advice is unreviewed, a third of the corpus has no KOs, per-move
force is unusable, there is no position data, and exactly one match has a paired
recording.

The honest bottleneck is not code. **Everything interesting needs paired video,
and only one exists.** Making recording feel worth doing is a product problem.
