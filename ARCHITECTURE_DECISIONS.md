# Architecture Decisions — the expensive-to-retrofit list

Decisions that cost almost nothing today and are painful or impossible to change once
there is real data and real users. Grouped by whether they're settled or still open.

---

## ✅ Decided and implemented (in `schema/match_schema.py`)

### 1. Time is stored in FRAMES, not milliseconds
Replays use ms; frame data uses frames. Mixing units causes a permanent low-grade bug
supply. Everything internal is integer frames; ms is a *display* concern only. `fps` is
stored explicitly rather than assumed, so a future 120fps mode doesn't invalidate history.

**Retrofit cost if skipped:** every stored analysis, every threshold, every comparison
silently off by a rounding factor. Effectively a full recompute plus an audit.

### 2. Display name is an alias, never an identity
Players can rename in Brawlhalla. Profiles keyed on `"xugo54"` orphan themselves the day
someone changes their name. Documents carry `slot` (stable within a match) and a nullable
`identity_id` for later account linking.

**Retrofit cost if skipped:** fragmented histories that cannot be reliably merged, because
you can't retroactively prove two names were the same person.

### 3. Every document is tagged with game patch AND analyzer version
Frame data changes per patch; detectors change per release. Untagged results are
uncomparable and un-recomputable.

**Retrofit cost if skipped:** you cannot tell which results are stale, so you must discard
all of them.

### 4. Every moment has a stable ID
`m_<hash>` derived from match + slot + frame + kind. This is what user feedback
("this flag is wrong") attaches to.

**Retrofit cost if skipped:** all feedback gathered before IDs existed is unattachable —
and that feedback is the training signal for improving detection. Pure lost data.

### 5. Raw observations separated from interpretation
`observations` (what happened) vs `analysis` (what we think about it). Detectors improve
constantly; re-running them must not require re-parsing.

### 6. Provenance and confidence are first-class
Each document states parser used, frame-data patch, per-section confidence, and warnings
(e.g. "KO extraction unavailable for this patch"). Downstream code can degrade gracefully
instead of silently trusting missing data.

---

## 🔶 Decided in principle — enforce from the first line of product code

### 7. Never bundle extracted game data
The client reads the **user's own install** and extracts at runtime (already automated in
`gamedata/swz.py`). Same data, entirely different legal position, and it self-updates on
patch day.

**Retrofit cost if skipped:** rebuilding distribution, plus purging shipped assets from
release history.

### 8. Keep every original replay forever
20 KB each. They are the only irreplaceable artifact — derived data can always be
recomputed from them, never the reverse. 4,068 replays is under 80 MB.

### 9. The wire format is a *projection* of the full document
Full doc with raw inputs ≈ 145 KB. Analysis-only projection ≈ 20 KB. The local agent keeps
the full document; only the projection is ever uploaded.

**Retrofit cost if skipped:** either bloated storage costs or an API contract change once
clients exist in the wild.

### 10. Analysis must be deterministic
Same replay + same analyzer version + same patch data → byte-identical output. No wall
clock, no randomness, no unordered iteration. Enables caching, diffing and reproducible
bug reports.

---

## ❓ Still open — decide before they become expensive

### 11. Game-agnostic core vs Brawlhalla-specific
Almost everything conceptual — option comparison, habit profiling, moment detection —
generalises to other platform fighters. Only replay parsing and frame-data extraction are
Brawlhalla-specific.

**Recommendation:** split now into `core/` (generic) and `games/brawlhalla/` (adapter).
Cheap today; a substantial refactor once there are thousands of lines assuming one game.

### 12. Opponent models — local-only or pooled?
We compute tendencies about *opponents*, who are third parties that never opted in. Pooling
opponent data server-side is powerful (population-level reads, better EV estimates) but is
data about identifiable people.

**Recommendation:** keep opponent models **local-only** until there is a deliberate policy.
Pooling later is possible; un-pooling after the fact means purging and disclosure.
This is the one on this list with legal as well as technical weight.

### 13. What the free tier is
This decides how much analysis must run without video, which in turn decides how much
engineering goes into input-only detectors versus video-dependent ones.

### 14. Whether coaches see raw replays or only clips
Affects whether replay files ever need to leave the user's machine. Cheapest answer —
clips only — is also the most privacy-preserving.

---

## Summary rule of thumb

> Anything that touches **identity, time units, versioning, or what leaves the machine**
> is expensive to change later. Anything that touches **UI, framework, hosting, or
> pricing** is cheap to change later. Spend the early care on the first list.
