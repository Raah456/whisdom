# How we work together

Two people, two Claude accounts, one project. Conversations don't transfer well —
**artifacts do**. This is the workflow that keeps both sides in sync.

---

## The layers

| Layer | What lives there | Why |
|---|---|---|
| **Git repo** (private GitHub) | code, extracted data, docs | The working directory. Both of us clone it and point Cowork at our local copy. Versioned, no conflicts, works async. |
| **Claude Project knowledge** | `PROJECT_HANDOFF.md`, `DECISION_LOG.md` | Makes both our Claude sessions *start* with full context. Re-upload when they change meaningfully. |
| **Shared chat links** | rare, on demand | Only when the *reasoning* matters, not the conclusion. |

---

## The one habit that makes it work

**End any substantial session by updating `DECISION_LOG.md`, then commit and push.**

Literally say to Claude: *"update the decision log with what we changed and why."*

That single step is what turns a private conversation into shared knowledge. Skipping it
is how two people end up with two divergent mental models of the same project.

---

## Session start checklist

1. `git pull`
2. Skim `DECISION_LOG.md` for anything new since you last worked
3. Tell Claude what you're working on — it can read the repo for the rest

## Session end checklist

1. Ask Claude to update `DECISION_LOG.md`
2. `git commit && git push`
3. If the handoff doc changed materially, re-upload it to the Claude Project

---

## Who owns what

Split by strength, not by file — but roughly:

- **Raah** — pipeline, parsing, data extraction, engine implementation, product shape.
  Owns a Brawlhalla install for tests/experiments (not a serious player).
- **Partner** (`xugo54`) — domain judgment: payoff rule tuning, match annotation, quest
  data collection, "is this actually how the game works" review.
  **Also the analysis subject** — all replay data is from his account, so he is uniquely
  placed to validate whether the tool's conclusions about a player are correct.

The payoff rules in `engine/rps.py` are the highest-value place for game expertise.
The frame numbers are ground truth; the interaction rules are a model, and models are
wrong until a strong player corrects them.

---

## Avoiding the classic failure

The most likely way this goes wrong is **silent divergence**: both of you ask Claude
similar questions, get slightly different answers, and build on different assumptions
for weeks. The decision log exists specifically to prevent that. If a decision isn't
written down, assume the other person doesn't know it.

## Naming conventions

- Replays from quests: `Q<id>_<description>.replay` (e.g. `R1a_Bodvar.replay`)
- Anything experimental: prefix `wip_` so it's obviously not settled
- Don't rename files others depend on without noting it in the decision log
