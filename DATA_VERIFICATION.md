# Retroactive data verification

Triggered by the partner correctly rejecting a finding ("he never played Rupture").
Question asked: **was legend data wrong for other characters too?**

**Short answer: no. 95.8% of the corpus was never affected. The bug was confined to
patch 9.01+ (170 of 4,068 files), which is exactly where the reliable parser stops working.**

---

## What was actually broken

`heroes_from_anchors()` had two paths:

| path | used for | measured accuracy |
|---|---|---|
| backward anchor (derive from the *next* player's name position) | every player except the last | **85% correct**, 2.5% wrong, 12% no answer |
| forward scan (no next name to anchor against) | the **last** player only | **0% correct** — returned hero id 70 every time |

The forward scan is what produced "Rupture". It found the same wrong offset in every
file and decoded it as a valid-looking legend. 73 of 73 last-entity reads returned it.

**Now removed.** The last entity returns `None` / `hero_confidence="unknown"` instead.

---

## Which data used which path

Measured by testing whether the structural parser lands, per patch:

| patch range | files | path | legend data |
|---|---|---|---|
| 6.06 – 9.00 | **3,898 (95.8%)** | structural parser | **reliable** |
| 9.01 – 10.09 | **170 (4.2%)** | anchors | 85% for non-last, unknown for last |

The cutover is exactly at 9.01 — the patch where the player block gained fields and the
forward walk stopped landing. Nothing before that ever touched the buggy code.

---

## Independent validation of the structural path

The structural parser self-validates (heroCount bounds, version echo must match), but
"authoritative by design" is not evidence. Three checks on a 641-match sample:

1. **No positional spike.** The artifact showed one legend at 65% of a slot's reads.
   Structural shows slot 0 top legend at 28.7%, slot 1 at 25.9% — a normal distribution.
2. **Opponent spread looks like a population.** 61 distinct legends, top one (Mordex)
   at 7.0%. A misread field would cluster; this doesn't.
3. **Player consistency.** xugo54 reads Diana 52%, Kaya 18% — matching his known history
   and stable across independent code paths.

---

## What is and isn't affected

**Unaffected — never touched hero identification:**
- All input streams, and therefore **every habit metric** (APM, dodge rate, wasted
  inputs, movement, attack mix). The headline behavioural findings stand.
- Player names — 99.5% accurate even via anchors.
- Match durations, moments, KO timings.

**Affected and now corrected:**
- Legend identity on 9.01+ only. Previously ~77 of 113 recent matches carried a phantom
  legend; they now correctly report "unknown".

**Unchanged conclusions:**
- All-time mains: **Diana ~1,900, Kaya ~780** — from the structural path, sound.
- Habit profile vs opponents — derived from inputs, sound.

**Retracted:**
- "Current main is Rupture" and everything built on it.

**RESOLVED (same day):** the last-entity case was fixed by anchoring on the results block
instead of scanning forward — validated at 30 correct / 0 wrong / 25 declined on the 8.07+
generation. On 10.x his legends now read **Diana 66**, Barraza 5, others, 24 unknown.
A ground-truth replay confirms `xugo54 = Diana`.

---

## Process changes adopted

1. **No confident answers from unverified paths.** A heuristic that cannot be checked
   returns `None`, not its best guess.
2. **Confidence travels with the data.** `hero_confidence` and `player_source` are now
   recorded per match so downstream code and reports can tell what they're standing on.
3. **Cross-validate wherever two methods exist.** This bug, and the earlier hero
   mis-identification, were both found by disagreement between methods — not by tests.
