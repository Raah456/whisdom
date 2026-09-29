# Decision Log

Append newest at the top. One entry per meaningful decision or finding.
Format: **date — who — what changed — why it matters.**

---

## 2026-08-12 — Claude — Repo, and the handoff it has to carry
`fightingwhisdom` is now a git repo: 70 files, 840 KB of history, first commit
tagged v0.10.0. The three superseded prototypes (`analyzer/`, `fightlab_old/`,
`engine/`) are deliberately NOT carried over — `engine/rps.py` is the hand-assigned
payoff model that `whisdom/games/brawlhalla/payoffs.py` replaced, and keeping it
around invites someone to read the wrong one.

**What the repo is really for.** The code is the smaller half of this project. Three
findings were published and retracted here, and every one was caught from outside the
system — twice by the player, once by looking at an image instead of a number. Someone
inheriting the files without that history would re-introduce all three. So
`DECISION_LOG.md`, `CONTRIBUTING.md` and `HANDOFF.md` are committed as first-class,
and `CONTRIBUTING.md` states the rules as consequences rather than advice:

  1. verify the OUTPUT, not the status code (ffmpeg drew nothing and exited 0)
  2. a green suite proves behaviour has not changed, not that it was right
  3. internal consistency is not validation (two inverted readings agreed with
     each other and passed a 19-check audit at 99.9%)
  4. when the data might be wrong, ship the doubt with the number
  5. advice that never changes is a bug wearing a disguise

**Ownership split**, chosen to follow a seam that already exists so the two sides
rarely touch the same files: the partner owns `games/brawlhalla/` and the six payoff
constants — the model and the game semantics; the pipeline (`core/`, `agent/`,
`vision/`, `app/`) is the other side. `schema/match.schema.json` is the contract
between them.

**Two environment limits worth remembering.** Git cannot operate in the working
folder for the same reason SQLite could not: no reliable file locking on that mount.
The repo was built on local disk and shipped as a zip with `.git` intact. Anyone
cloning onto a synced folder will hit this, so it is in the README next to the
`--index` workaround.

**Verified rather than assumed:** cloned the committed tree fresh and ran the suite
from the clone — imports fine, payoffs/review/ground-truth/app all pass. Then created
`store/`, `tools/dump/`, a `.replay` and an `.mp4` and confirmed `git status` ignores
every one, so no game content, personal gameplay data or recordings can leak in.

## 2026-08-11 — Claude — Local app (`whisdom app`)
The free tier, as a real surface. `whisdom app` starts a local server and opens a
browser: match browser with filters, per-player damage curves with KO markers,
and the review panel.

**Why a stdlib server and not Electron or Tauri.** No new toolchain — the agent is
Python and so is the app, so neither Raah on macOS nor his partner on Windows
needs Node or Rust. It binds to 127.0.0.1, has no accounts and makes no network
calls, which IS the free tier rather than a crippled cloud client. The UI reads
match documents through a thin JSON API and never touches the parser, so replacing
the front end later costs nothing.

**The schema is what made this cheap.** A UI reads documents; it does not reach
into parsing internals. That contract existed before the UI did, which is why this
was a day's work rather than a rewrite.

**Two bugs the app surfaced, both real:**
* SQLite connections cannot cross threads and the server handles each request on
  its own thread. Fixed in `Store` with thread-local connections rather than
  worked around in the server — the store was simply wrong for concurrent use.
* The index had no `has_video` or `level_name`. Added, with `ALTER TABLE` on open
  so existing databases widen instead of failing; the index is a cache, so
  `whisdom reindex` repopulates.

**What the app makes impossible to ignore:** 4,055 matches, **zero** with a
recording paired. The empty state is the common case, so it is designed for
rather than hidden — matches without video say what is missing and print the
command that fixes it, and the app says the same on startup.

**The review panel is marked as the unsettled part, in the UI itself.** The frame
data behind it is checked; the way frames become advice is a model no player has
reviewed. The panel says so, with the sample size and the ambiguity share, so
nobody mistakes it for a verdict.

Queries stay at ~4ms across 4,055 matches. `tests/test_app.py` pins the API
contract the JavaScript depends on, including 404s and concurrent access.

## 2026-08-11 — Claude — MVP: one command, one watchable artifact
`whisdom demo <match_id> <recording>` is the first end-to-end deliverable. It reads
damage off the HUD, derives the video/replay offset from the death pattern, reviews
every death against the alternatives, cuts a captioned clip of each, and writes a
page. The only inputs are a match id and a video file.

**Caption bug, which had been silently breaking `clips` as well.** `_esc` escaped
`%` as `\\%`; ffmpeg rejects that with "Stray %" and then draws NOTHING — while
still exiting 0 and producing a perfectly good video. So captions had been silently
vanishing, and nothing failed loudly enough to notice. Fixed by setting
`expansion=none` on every drawtext (making `%` literal) and removing the escape.
Verified by sampling a frame out of the encoded clip and looking at it, which is
the only check that would have caught it — the exit code never complained.

That is the third time on this project that a green result hid a broken one. The
pattern is consistent: **when a component can fail silently, verify its OUTPUT,
not its status.**

Current state of the MVP:

    ingest    4,055 replays parsed across 45 patches
    damage    read from video, self-validating against replay KO times
    review    every death scored against the alternatives at real damage
    demo      captioned clips + tendency table + stated caveats

What it is NOT yet: it works on one recording. Everything downstream of "does the
pipeline work" — whether the advice is any good, whether the tendencies mean
anything — needs footage and a player's judgement.

## 2026-08-11 — Claude — The whole chain, on one real match
`whisdom review <match_id>` joins everything: inputs from the replay, damage from
the video, the opponent's tendencies from their actual presses, payoffs from frame
data. On the verified match it produces, for each death, what he chose, what it
was worth, and what was worth more.

**Two degenerate results were caught before they shipped**, both versions of the
same failure the payoff rewrite was meant to fix — advice that looks specific but
is really a constant:

1. Every death returned "Double jump" because the `wait` and `retreat` cells were
   still hand-assigned constants (+0.35, +0.55) that the rewrite had missed. They
   are now functions of game state like the rest.
2. The opponent's tendency came out 57% "wait at ledge" because a dodge was being
   counted as waiting, and because the sample included windows where the OPPONENT
   died — situations where he was recovering, not attacking. Tendency now counts
   only attack presses, only in windows where the reviewed player died, and
   measures "wait" as the share of exchanges with no attack at all. It moved to
   86% ledge attack, which changed the verdicts.

**What it says about this match.** He died three times at 96-100% damage. Each
time he committed — dodge, then contest, then contest — instead of preserving
options. The worst was at 148s: contesting at 96% while the opponent sat at 20%,
worth -0.38, a gap of +0.53 against simply double jumping. That is the exact trade
the value model was added to catch: contesting is cheap when you are fresh and
they are at kill percent, and reckless in reverse.

**Stated limits.** Weapon is not in the replay, so the engine assumes Sword. No
position data, so "go deep" and "ground pound" both read as Heavy+AimDown — 86% of
this tendency estimate is ambiguous, from 7 presses across 3 deaths. This is a
demonstration on one match, not a finding about how he plays.

`tests/test_review.py` guards both degenerate failures: tendency must not be
dominated by movement inputs, and verdicts must differ between deaths.

## 2026-08-11 — Claude — Payoffs derived from frame data, and conditioned on game state
The option engine gave near-identical advice for all fourteen weapons. Cause: frame
data entered only as branch conditions —

    if recovery_startup + 2 < attacker_startup: return 0.45

so a 1-frame edge and a 10-frame edge produced the same constant, and most cells
never referenced the weapon at all. `whisdom/games/brawlhalla/payoffs.py` replaces
this: every score is now a continuous function of the real frame numbers.

**Data quality finding — force and damage are NOT usable.** Cross-checking
`resolved_moves.json` against the wiki-validated `weapon_normals.csv`:

    startup   6 of 8 Sword moves exact (both misses are multi-part)
    damage    4 vs 14, 0 vs 15, 2 vs 7, 7 vs 15 ...  wrong on most multi-part moves
    force     21 vs 45, 0 vs 61, 75 vs 60 ...        likewise

46 of 112 moves carry zero damage and 49 zero fixed force. This is the SAME
unresolved multi-part aggregation problem as the signatures. So the model uses
timing only (which is validated) and takes lethality from the player's damage
READING off the video instead of from per-move force. Six moves also have an
impossible 0-frame startup; those are flagged `known=False` and their cells carry
confidence 0.3 rather than being presented as fact — the same discipline as
shipping the signatures without summary figures.

**Game state is now what makes the decision.** Adding `hit_value` (what landing a
hit is worth, given THEIR damage) alongside `hit_cost` (what being hit costs,
given MINE) turned a symmetric model into a situational one. Sword vs Sword:

    fresh, they're at kill percent  -> Recovery move  (+0.36)   contest, it's cheap
    at kill percent, they're fresh  -> Double jump    (+0.16)   survive instead
    both fresh                      -> Double jump    (+0.21)
    both at kill percent            -> Recovery move  (+0.21)

12 of 14 weapons change their recommendation with the damage situation. This is
the RPS reasoning the project set out to do, and it only became possible once
damage could be read from video.

**Model vs data, kept separate.** Six named constants at the top of the file are
judgements about how frames become advantage. Everything else is extracted and
validated. The partner's task is now to argue with six numbers, not to author a
model from scratch — a much better use of a session together.

**Still blocked on the same five-minute measurement.** Resolving per-move force
would let payoffs weight outcomes by whether a hit actually kills. The training-
mode check that unblocks the 414 signatures unblocks this too.

`tests/test_payoffs.py` guards the properties the old engine failed: advice
differs across weapons, scores differ, state changes the answer, risk aversion
holds at kill percent, unresolved data stays flagged, and every reason cites real
frames so advice is auditable.

## 2026-08-11 — Claude — Damage read from video; earlier figures RETRACTED
Replays carry no game state and re-simulation was ruled out, but the HUD encodes
damage as a coloured arc beside each portrait. `whisdom/vision/damage.py` reads it.

**First version was wrong, and its numbers should be discarded.** It treated "how
much of the arc is filled" as a signal and took a median hue over all saturated
pixels. Neither holds up:

* The arc is a FIXED-SIZE crescent. It never grows or fills. Only its COLOUR
  changes: white -> pale yellow -> yellow -> orange -> red, resetting to white on
  death. Verified by looking at the crops frame by frame.
* The apparent "fill" was the portrait's dark blue background passing the
  saturation filter. Worse, blue hue (~215 deg) wrapped through the red-is-high
  branch and read as MAXIMUM damage — so the tool reported ~1.0 for a player at
  zero. The retracted numbers ("0.77 0.98 0.98 0.98 before deaths") were partly
  this artifact.

It nevertheless passed 5/5 KO resets, because a KO does change the picture
sharply whatever you measure. **A test that passes does not mean the model is
right — it means the model is right often enough to fool that test.** Same lesson
as the KO-attribution and result-field retractions: internal agreement is not
validation. This one was caught by looking at the images rather than the numbers.

**Corrected model.** Damage is a pure colour reading on the white->red ramp,
saturation carrying the low end where hue is unstable. No normalisation against
the rest of the match, so a player who never passes 40% reads as never passing 40%.

**Auto-detection (`find_arcs`).** Hand-positioned crops break on any resolution or
HUD layout. Arcs are found from the footage: pixels that change over the match AND
go warm — which excludes the timer and stock numerals (always white) and moving
characters (warm only briefly at any one pixel). Confirmed structurally by pairing:
two same-sized elements on the same row. Position-independent, which mattered — the
HUD in this footage is top-right, not bottom-centre. Detection also returns a pixel
MASK, without which orange hair reads as an orange arc.

**Alignment (`align`).** The recording and the replay are independent observations
of one match, so each player's deaths form a fingerprint in time and only one
alignment fits. The tool derives BOTH the video/replay time offset AND which HUD
slot is which player, from the death pattern alone.

Result on the verified match, nothing supplied by hand:

    video starts -1.82s relative to the match
    left  HUD = xugo54          deaths 3/3 confirmed
    right HUD = NotMashmelIow   deaths 2/2 confirmed

All five deaths within +/-0.2s. Corrected damage context: xugo54 was at 0.85-1.00
before each of his deaths and 0.25-0.67 when he scored — same shape as the
retracted figures, but now trustworthy.

**Consequences**
* State reconstruction is partly solved without a physics simulator: damage from
  video, inputs from the replay, KO times joining them. Position still missing.
* Quest S4 no longer needs "note when the match starts" — that was the whole
  manual sync requirement and it is now derived.
* `whisdom damage <match_id> <video>` attaches the track to the match document
  (`observations.damage`, schema addition). ~70s for a 3-minute match.
* `tests/test_vision.py` runs the whole chain end to end; a pass means arc
  detection, colour model, reset detection and alignment were all right at once.

## 2026-08-11 — Claude — Corpus re-ingested; corrected analysis run
4,055 matches re-ingested with fixed semantics, documents now on persistent storage
(SQLite index kept separately on local disk — a new `--index` option, since the docs may
legitimately live on a synced folder that cannot host a database).

**Results with correct semantics:**
- **Win rate 44%** (previously reported 56% — inverted by the misread result field).
- **Dodge finding reversed:** 15.7% wasted before his deaths vs 35.4% before his kills.
  The "mashing under pressure gets you killed" line is **void**.
- **Wasted-dodge habit holds:** 15.1% vs opponents' 11.0% over 768k dodge presses.
  Never depended on KO attribution.
- **Wins vs losses: no meaningful difference** in any habit metric. The only mover is
  wasted-dodge, and it is *higher in wins* (+17.5%).

**The important negative result:** input-level habits do not separate his wins from his
losses. Whatever decides his matches is invisible at this level. That is the strongest
argument yet for the option-comparison engine — reasoning about decisions in context
rather than aggregate behaviour.

## 2026-08-11 — Claude — Semantics fixed and the result field DECODED
Acting on the two corrections above.

**1. KO events normalised to victim semantics** at the adapter boundary. Brawlhalla
credits the killer; `core.Event` now always means the victim, with `by=` carrying the
killer. In a 1v1 the victim is unambiguous; with more players it is left unknown rather
than guessed. Verified against the recording: xugo54 died at 96.4/148.1/189.8. Correct.

**2. Win/loss now DERIVED FROM DEATHS**, not from the misread result field. In a stock
match whoever runs out first loses. Trustworthy, but only available where KO data exists
(~52% of matches).

**3. The result field is now decoded — using the derived outcome as ground truth.**
On 228 matches where both existed, **the winner had the HIGHER raw value 228/228**, in
every patch era (older patches use 2048/4096, newer 1/2). My original reading — lower =
better placement — was exactly backwards. With this as a fallback, outcome coverage is
back to **90%**: 52% verified from deaths, 38% from the decoded field.

**4. `tests/test_ground_truth.py` added.** The one externally verified match is now a
permanent test: legends, all five KO victims and times, the loser, and duration. Both
bugs found today were self-consistent and passed the internal audit at 99.9%; this test
exists because no internal check could have caught them.

**Method worth reusing:** a small amount of externally verified ground truth was enough to
decode a field that had defeated inference entirely. Guessing at the encoding failed twice;
checking it against something known settled it in one pass at 100%.

## 2026-08-11 — CORRECTION #2 — KO entityId is the KILLER; result encoding unknown
The player confirmed he was **Diana** in the verified match. That single fact resolved
the discrepancy the video exposed — and inverted two things.

**1. KO `entityId` = the KILLER, not the victim.**
Ground truth (stock counters + player confirmation): xugo54/Diana died at 96/148/190 and
hit zero. The parser attributed those exact times to the *other* slot. Cross-checks on all
five KOs are consistent. Every "who died" claim in the project was reversed.

**2. Result encoding is NOT "lower = better placement".**
`{'0': 2, '1': 1}` was read as slot 1 winning. Slot 1 is xugo54, who verifiably LOST.
Semantics unknown — note that older patches store values like 2048/4096, so these are
probably not simple ranks at all.

**Consequences — retracted:**
- The pressure finding's direction. 35.8% wasted dodges is before he *scores a kill*, not
  before he dies. The coaching line built on it is void.
- The 56% win rate and every wins-vs-losses habit comparison.

**Consequences — unaffected (verified independent of KO attribution):**
- Wasted-dodge rate 17.3% vs opponents 10.5%.
- All habit metrics: APM, movement, attack mix, dodge rate.
- Replay parsing, sync (-2000ms, five checkpoints), clip generation.
- Legend identification — the parser was RIGHT; my assumption that HUD-left = slot 0 was wrong.

**Why this took a video to find:** both errors were self-consistent. The audit's
"winner isn't the most-KOd" check passed at 99.9% precisely *because* it compared two
fields that were wrong in a compensating way. No internal check could have caught this —
only external ground truth.

**Rule:** semantic assumptions about a reverse-engineered field ("this id means X") are
not verified by internal consistency. They need an external observation.

## 2026-08-11 — Claude — First real video: sync VERIFIED, legend assignment in doubt
Recording supplied (193s, 3440x1392) of `[10.09] SmallFortressof` replay playback.

**Sync is exact and verified five independent ways.** The replay viewer's own clock
reads 00:02 at video t=0 and advances 1:1, giving `offset = -2000 ms`. Every one of
the five known KO times then lands precisely on a stock-counter drop in the footage:

    match 55.9 / 96.4 / 133.2 / 148.1 / 189.8  ->  video 54 / 94 / 131 / 146 / 188

No drift over 190 seconds. **Real annotated clips now generate from one command:**
`whisdom clips <match_id> recording.mp4 --offset -2000`

**KO attribution and results VERIFIED correct.** Reading stock digits before/after each
KO: one player died at 96/148/190 and hit 0 (lost); the other died at 56/133 (won).
That matches slot 0 having exactly 3 KO events and slot 1 having 2, with results
{'0': 2, '1': 1}. Both were previously unverified assumptions.

**BUT: the legend↔player mapping looks swapped.** The HUD portrait for the player who
died three times is unmistakably Diana (green hood, orange braids), and that player is
slot 0 = NotMashmelIow. The parser assigned Diana to xugo54 and Yumiko to NotMashmelIow.

Not yet conclusive: this rests on assuming HUD-left = slot 0, which is unverified.
But the death counts only line up under that assumption, which supports it.

**Most likely cause:** this is a 10.09 file, so legends come from the anchor heuristic,
measured earlier at only **85% accuracy** for non-last players. This may simply be one
of the 15%. There is no structural parse available on 10.09 to cross-check against.

**Resolution:** ask the partner what he actually played in this match. One answer settles
it, and would also tell us whether the anchor method needs revisiting for 10.x.

## 2026-08-11 — Raah + Claude — Named the project; one agent, many adapters
**Domain: fightingwhisdom.** Package and CLI renamed `fightlab` -> **whisdom**.
Restructured so everything nests under one namespace — the old layout exposed
`core`, `games` and `agent` as top-level packages, which would have collided with
other installs the moment anyone ran `pip install`.

**Architecture decision: ONE agent, MANY game adapters** (not one agent per game).
The store, pipeline, watcher, reports, clip pipeline and analyses are identical work
regardless of game; duplicating them per game means fixing every bug N times. What
genuinely differs is replay parsing and frame extraction — that is the adapter.
Brawlhalla's adapter is ~900 lines; everything else is shared.

**Enforced by a `GameAdapter` contract** (`whisdom/games/base.py`): a game declares
its loader, action model, categories, file extension, per-OS replay paths, character
noun, fps, and which committed action to measure under pressure. Games self-register,
so the CLI discovers them; adding a game touches nothing in core/ or agent/.

**Four real leaks were found and fixed** when this was checked rather than assumed:
- `pressure.py` hardcoded "Dodge" and 14 frames — our best analysis would have
  silently measured nothing on any other game
- `paths.py` hardcoded Brawlhalla replay locations
- `report.py` hardcoded "Dodge" in the death-context view
- `ingest_folder` hardcoded the `.replay` extension

**A reference adapter (`whisdom/games/example/`) proves it and guards it.** A fake
game with a different vocabulary (Guard/Strike/Slam), extension, character noun and
pressure action, running the full pipeline. It caught two of the four leaks
immediately. If game-specific terms creep back into core/ or agent/, it breaks.

Also renamed `players[].legend` -> `players[].character` in the schema (now v1.1).
Free to do with one game and no external consumers; a migration later.

## 2026-08-11 — Claude — Signature frame data: partially resolved, deliberately not summarised
Extracted all **414 signatures across 69 legends** (2,294 individual power parts).

**Reliable and shipped:** charge window (median 70f / 1.2s), minimum charge, cooldown,
part count, and every raw per-part field straight from the game data.

**NOT shipped — deliberately:** a single startup / damage / recovery figure per signature.

**Why.** A signature is 2–9 power entries: a charge plus several hit entries. Some are
SEQUENTIAL (multi-hit) and some are ALTERNATIVES (early hit vs late hit vs release). The
data does not mark which. Three aggregation rules were tried:
- first hit  -> Bödvar sword nSig reads **1** damage (real ≈25)
- biggest    -> discards genuine multi-hit damage
- sum all    -> Diana pistol nSig reads **135** damage (real ≈25–30)

**And there is no validation source.** Weapon normals could be checked against community
frame data (87–93% agreement). The wiki does **not** publish signature frame data — legend
pages carry only descriptions and images. So no aggregation rule can be tested.

**Decision:** ship the per-part ground truth and mark the summary as unresolved, rather
than publish confident numbers that are wrong by 5–20x. Same principle as the Rupture
retraction: an unverifiable derivation must not be presented as a fact.

**To finish:** a player confirming real damage for ~6 signatures from training mode would
identify the correct rule immediately. That is now the cheapest path.

## 2026-08-07 — Claude — First real coaching finding: dodge quality collapses under pressure
Enabled by the KO fix earlier today. Across 5,167 deaths and 5,722 kills:

**35.8% of his dodge inputs are wasted in the 5s before he dies, vs 15.6% before he kills**
(baseline 17.3%). A wasted dodge is one pressed while a 14-frame dodge is still active —
provably discarded by the game.

The important part is that quantity and quality DIVERGE: dodge count rises 50% while the
wasted rate more than doubles, and **total input volume is unchanged (+2%)**. That is
mashing, not defending.

**Replicates independently in all five patch eras** (d = +0.26 to +0.67), including 10.x
where frame data matches the replays. Not a pooled artifact.

**Null results (recorded so nobody re-tests them):**
- No tilt within a match — waste rate before death #1/#2/#3 is 22.5/24.0/23.7%.
- No over-extension — only 1.1% of his kills are followed by his own death within 5s
  (median gap 37s). This is a genuine strength.

**Project-wide methodological limit discovered:** frame-derived metrics use 10.09 game
data, but 96% of the corpus is older replays. 6.x shows half the waste rate of later
eras, which is more likely a mechanics/data change than behaviour. Within-replay
comparisons stay valid (the error cancels); **absolute cross-era comparisons do not**.
Only the current patch's game files are extractable, so this is permanent for history.

**REFRAMED by the opponent comparison (same day):** running the identical test on 2,888
opponents gives a ratio of **2.22x** vs his **2.30x** — statistically the same. Dodge
quality collapsing under pressure is UNIVERSAL, not a personal flaw.

What IS personal is the absolute level: he wastes ~2x as many dodges as opponents in both
conditions (35.8% vs 18.8% under pressure; 15.6% vs 8.5% otherwise).

Correct framing: *"your dodge discipline is roughly half as good as your opponents' at all
times, and pressure degrades everyone equally — so the gap is widest when it costs a stock."*
A mechanical habit, not a mentality problem. Fixing it helps in neutral too.

**Lesson:** a finding about one player is not a finding until compared against a
population. "He mashes under pressure" would have been true, useless, and misleading.

**Open question only the player can answer:** is the mashing deliberate input buffering,
or genuine panic? The coaching advice differs completely.

## 2026-08-07 — Claude — KO extraction solved on ALL patches (last format gap closed)
The KO block position was never the problem. It is exactly derivable:

    ...last input block... | bool(0) terminator | state(N bits) | faces

so `faces = last_block_end + 1 + state_bits`. My formula had been right all along.

**The actual bug: the game writes KOs in DESCENDING timestamp order.** Every validator
I wrote required ascending, so each one silently rejected a perfectly valid block and
reported "no KOs". That single assumption blocked this for days and sent me hunting for
a block I had already found several times.

Fixed in `anchors._try_faces`: accept either direction, verify monotonicity, sort on the
way out. Position is now derived rather than scanned.

**Validated against structural truth (8.07+): 47/54 exact, 0 wrong, 7 none (87%).**
**Recovered on patches that previously had none:** 9.01 14/14, 9.12 6/6, 10.00 5/5,
10.01 88/92, 10.06 6/6, **10.09 7/7**.

Corpus-wide KO coverage: **59%** of sampled matches (was ~43%, and 0% on 9.01+).

Ground-truth file now reads completely:
`NotMashmelIow (Yumiko) vs xugo54 (Diana), 190s, KOs at 56/96/133/148/190s, xugo54 wins.`

**Lesson:** when a derivation is provably correct but "fails", suspect the validator
before the derivation. I re-derived the position three times without once checking
whether my acceptance criteria were sound.

## 2026-08-07 — Claude — Last-entity legend recovered (Rupture case closed)
Ground-truth replay supplied by the partner ([10.09] SmallFortressof, where he is the
LAST entity — precisely the broken case).

**Fix:** anchor the last entity on the RESULTS BLOCK instead of scanning forward.
The layout is fixed downstream of the player data:

    ...last PlayerData... | bool(0) | checksum(32) | state(4) | results

so the entity ends at `results_bit - tail`, and the hero entry sits
`2 + 128*heroCount` bits before that. Implemented as `anchors.last_entity_hero()`.

**Validation** against the structural parser on the 8.07+ generation (same format family
as 9.x/10.x): **30 correct, 0 wrong, 25 declined** of 55. It answers or abstains; it does
not guess. The ground-truth file now reads `xugo54 = DIANA`, correctly.

**Effect on 10.x:** phantom "Rupture 73" is gone, replaced by **Diana 66**, Barraza 5, a
few others, 24 unknown. Consistent with his real history.

**Current confidence, whole corpus:**
| range | files | method | confidence |
|---|---|---|---|
| 6.06–9.00 | 3,898 | structural parser | reliable |
| 9.01+ | 170 | anchors | non-last 85%; last ~55% recovered, 0% observed error |

Golden regenerated: 18 legends withdrawn (now correctly declining), 19 corrected.
Many golden entries had themselves been forward-scan artifacts.

## 2026-08-07 — CORRECTION — "Rupture main" was a parsing artifact, not a fact
**The partner says he has never played Rupture. He is right; the data was wrong.**

All 73 "Rupture" readings came from matches where he was the LAST entity in the file.
The last entity has no following player name to anchor against, so the anchor method
fell back to scanning forward for the first plausible-looking hero entry. That scan
finds the SAME WRONG OFFSET every time and decodes it as hero id 70 (Rupture).
When he was *not* last (40 matches) the same code read Diana 24, Barraza 4 — real legends.

Fixed: the forward-scan fallback is removed. The last entity now reports `None` with
`hero_confidence="unknown"` rather than a confident wrong answer.

**Retracted claims** (previously logged as findings):
- "Current main is RUPTURE (70% of 10.x)" — FALSE.
- "Rupture's Dexterity 3 is a quantified weakness" — the frame maths is sound, but it
  was applied to a legend he does not play. Not a finding about him.
- Any instruction to retarget the option engine to Rupture — void.

On 10.x we now know: Diana 24, Barraza 4, a handful of others, **77 of 113 unknown**.
Legend identification on 9.01+ is an OPEN PROBLEM, not a solved one.

**Process failure worth recording.** The anchor heuristic had already been proven
unreliable earlier the same day (it disagreed with the structural parser on 11/12
sampled replays). Its output was then used, unverified, for every 9.x/10.x match —
and a whole engine retarget was built on top. Proving a method unreliable and then
trusting its output anyway is the actual mistake here.

**Rule going forward:** data from an unverified path must be marked low-confidence at
the source and must not underpin a conclusion until independently checked.

## 2026-08-07 — Claude — Data-quality audit found four real bugs
Built `fightlab/tests/audit.py`: 19 internal-consistency checks across the whole
corpus. Regression tests prove behaviour hasn't *changed*; they cannot prove it was
ever *right*, because the golden file is generated from the code under test. The audit
looks for contradictions instead.

**Bugs found and fixed:**
1. **Hero mis-identification.** The adapter used the anchor heuristic for all versions.
   The structural parser is authoritative where it lands and disagreed on ~11/12 sampled
   8.x replays. Adapter now prefers structural, anchors only as fallback (9.01+).
   *Caught by cross-checking two independent methods, not by any test.*
2. **5.4% silent parse failures.** My own spurious-block filter used MAX span as its
   reference; a false-positive block reporting a 14-hour span caused every real block to
   be rejected. 219 matches stored as empty documents, reported as successes.
   Filter now references the MEDIAN of plausible blocks. Failures: 219 -> 13 (0.3%).
3. **Empty parses reported as success.** Pipeline now treats a parse yielding no
   players/inputs/duration as a failure.
4. **Results never read from the structural parse.** Only the anchor path was consulted,
   which was built for 9.x/10.x. Valid results: **2% -> 88%** of the corpus.

Also: added adapter sanity guards (KOs must fall within the match; placements must look
like ranks) after finding a match with KOs at 37 hours and a placement of 2128.
And fixed a 27x performance regression by removing a double block-read (4.6s -> 0.29s).

**Audit result: 19 check types, 18 at 100%, one soft check at 99.9% (2/1754).**

**Lesson worth keeping:** a golden-file regression suite locks in today's bugs alongside
today's correctness. Where two independent methods exist for the same fact, compare them
deliberately — that is what found bug 1, and nothing else would have.

## 2026-08-07 — Claude — Frame data properly parsed and validated
Earlier frame values were read naively from raw columns and were wrong in two ways.

- **Startup** uses a timeline notation (`0@1,12:1@5`). A leading zero-delay segment is a
  lead-in, not the hitbox. Parser in `gamedata/frames.py`. **13/15 exact** vs community data.
- **Recovery** is not in the move's own row. It lives in child entries linked by the
  `OriginPower` column (`Hit` / `Hit2` / `Miss` / `Release`), can **chain** across several
  with zeros in the early links, and is stored **pre-division**:
  `real frames = raw / AirRecoverMod(dexterity)`. Resolver in `gamedata/moveframes.py`.
  **28/30 within ±1 frame (93%)**.
- 112 moves resolved across 14 weapons -> `gamedata/resolved_moves.json`.

**Concrete result: Rupture's Dexterity 3 is a quantified weakness.** He commits 2–3 frames
longer than a Dex 9 legend on every whiff (Katar recovery 14f vs 11f; sair 13f vs 11f).
Against ~8-frame punishes that is a real, exploitable difference — and it is now in the data
rather than being an assumption.

**Still open (needs the partner):** the payoff rules in the option engine are still
hand-assigned constants, so all weapons currently produce near-identical recommendations.
The model must be rewritten to *derive* payoffs from frame relationships before his tuning
is worth anything.

## 2026-08-06 — Claude — Results solved on 9.x/10.x; KO timeline still open
Built anchor-based results extraction (`analyzer/ko_anchor.py`): the results block stores
match length, and the true duration is known from the input streams, so the correct
candidate is the one whose following bits parse as a valid results table.

- **Results: 33/33 (100%) on 9.01 → 10.09.** Match length and final placements now
  available on current-patch replays — i.e. **win/loss works on 10.09**.
- **KO timeline: still unsolved on 9.x/10.x.** Three approaches tried (signature scan,
  forward walk from the results anchor, search past the input blocks). All produced
  untrustworthy timestamps, so low-confidence results are now **gated off** rather than
  emitted. Better to report "unknown" than invent severity-5 moments.

**Next step is quest R2**, which converts this from a blind search into a targeted match:
with three known death times, we search for those exact values instead of guessing.
R2 is now the highest-priority item after S4.

## 2026-08-06 — Raah + Claude — Architecture decisions
Product direction: **local client first, scaffolded toward a hybrid** (local agent does the
heavy work; a web layer later receives only small derived JSON). Tiers: L1 replay-only
habits (cheap, every match), L2 video-backed option analysis (on demand), L3 coaching (web,
multi-user).

Decisions taken:
- **Game-agnostic core: YES.** Implemented as `fightlab/core` (schema, detection, profiling,
  option/EV engine, bitstream) + `fightlab/games/brawlhalla` (container, input bits, hero
  tables, frame data). Only parsing and frame extraction are game-specific.
- **Identity / display-name handling: SHELVED** (not forgotten). Schema already carries a
  nullable `identity_id`, so it's additive later. Options when we return to it:
  (a) local self-identity — trivial, it's whoever installed the client;
  (b) Steam ID readable locally; (c) Brawlhalla's public API has real player IDs.
  Note: replays contain **display names only, no account IDs** — so opponents are the hard
  case, which matters less given opponent models are local.
- **Opponent models: LOCAL ONLY for now.** Pooling later is possible; un-pooling is not.

Also locked (see `ARCHITECTURE_DECISIONS.md`): frames not ms, patch+analyzer version on
every document, stable moment IDs for feedback, raw observations separated from
interpretation, never bundle game data, wire format is a projection of the full doc.

## 2026-08-05 — Claude — Re-simulation ruled out; pivot to video pairing
Investigated building a physics simulator for state reconstruction. **Blocked, and not
worth forcing.** Findings:
- Horizontal constants exist in `StatTypes` (run speed, accel, friction, air variants).
- **Gravity, jump velocity and fall speed are NOT in the game data files** — hardcoded in
  the engine's ActionScript. Not community-documented either.
- More fundamentally: reconstructing a real match requires knowing when attacks *connected*
  (knockback dominates position), which means simulating hitbox collision, the knockback
  formula, hitstun and DI — i.e. reimplementing the combat engine. All undocumented.
- **Decisive argument:** validating any simulator requires video ground truth anyway.
  If video is needed regardless, read state from the video instead of approximating it.

**Decision: state comes from paired video (Path B), not simulation.**
Video gives real positions/damage/stocks; the replay gives frame-accurate inputs; syncing
them provides everything the option engine needs. Also matches the product vision, which
called for real gameplay footage rather than an abstract rendering.

**Consequence:** quest S4 (one replay + screen recording of the same match) is now the
single highest-priority data item. S1/S2/S3 (movement/damage validation) are obsolete.

## 2026-08-05 — Claude — ~~Current main is RUPTURE~~  **RETRACTED — see 08-07 correction**
On patch 10.x: Rupture 70%, Diana 23% (n=105). The "Diana main" reading came from
4,068 mostly-historical replays. Analyser advice, payoff tuning and weapon priority
should target **Rupture (Katars + Rocket Lance)**. Diana is legacy data.

## 2026-08-05 — Claude — Switched to anchor-based extraction (10.09 now works)
Replaced strict forward parsing with signature/anchor-based extraction (`analyzer/robust.py`).
Locates player names, then derives the hero entry backwards from the next entity's name
position. Version-proof by construction: 10.01 6/6, 10.02 2/2, 10.06 5/6, 10.09 5/6.
**This matters because all newly collected data is on 10.09** — the quest replays are now usable.
## 2026-08-05 — Raah + Claude — Collaboration setup
Decided to bring a second person onto the project. Chose a shared git repo as the
working directory rather than relying on Claude's native sharing, because conversations
transfer poorly and the project is mostly code. Claude Team (2-seat minimum) requires a
business domain for the *creating* account; Gmail can be added as a permitted domain
afterwards for the second member.

## 2026-08-05 — Raah + Claude — Product vision clarified
The target is: upload matches → build a profile → run a new match against that profile →
walk through it showing mistakes and better options. Playback should be **video/gameplay**,
not an abstract timeline. Three possible paths identified (in-game replay viewer /
paired screen recording / re-simulated rendering). Paired recording is the likely product.

## 2026-08-05 — Raah + Claude — Core design principle locked
Score options against the opponent's **tendency distribution**, not against what they
actually did. Scoring against the actual choice teaches hindsight and is unlearnable.
This is the difference between a replay viewer and a coach.

## 2026-08-05 — Claude — Edgeguard option engine v1
Built payoff matrices for recovery/edgeguard using extracted frame data. Result confirms
the RPS structure: air dodge is the best option vs an aggressive edgeguarder (+0.48) and
nearly the worst vs a patient one (−0.32), driven by the dodge's 163-frame cooldown.
**Open:** the payoff rules are a model and need a strong player's correction.

## 2026-08-05 — Claude — Analysis possible without state reconstruction
Discovered that input timing + frame data alone catches provable errors: 17.3% of Raah's
dodge presses occur while a dodge is still active (vs 10.5% for opponents). This means a
useful v1 exists before the physics simulator is built.

## 2026-08-05 — Claude — Replay format cracked across 44 versions
State field grew from **3 bits to 4 bits at patch 8.06** — the change that broke every
public parser. 88% of 4,068 replays now fully parse; input streams parse on 100%.
**Open:** 9.01+ (incl. current 10.09) player block gained ~2 u32 fields, offset not pinned.
