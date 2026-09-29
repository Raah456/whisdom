# Corrected analysis — what actually holds

*Recomputed 2026-08-11 on 4,055 matches after the KO-semantics fix. Everything below
uses verified semantics: KO events are victim-attributed, win/loss is derived from deaths
(52%) or from the decoded result field (38%, validated 228/228).*

---

## The headline finding is RETRACTED

The original claim — *"under pressure, before you die, you mash dodge"* — was an
artefact of reading the KO block backwards. With correct attribution:

| | wasted dodges |
|---|---|
| in the 5s before he **dies** | **15.7%** |
| in the 5s before he **scores a kill** | **35.4%** |

The direction is reversed. Dodge mashing accompanies *scoring* kills — long aggressive
exchanges — not dying. As coaching that is close to worthless, and it is certainly not
evidence of a weakness. **Do not use it.**

---

## What genuinely holds

**1. He mashes dodge far more than his opponents.** Untouched by any correction, because
it never involved KO attribution:

| | wasted-dodge rate |
|---|---|
| xugo54 | **15.1%** (59,059 of 391,182) |
| opponents | **11.0%** (41,397 of 377,369) |

About **37% more wasted dodge inputs** than the people he plays against, measured over
768,000 dodge presses. A real mechanical habit.

**2. His actual win rate is 44%, not 56%.** The earlier figure was inverted by the same
misread field. He loses somewhat more than he wins — worth knowing, and it reframes the
whole profile.

**3. Style vs opponents** (medians per match, unaffected by the corrections):

| metric | him | opponents | diff |
|---|---|---|---|
| Actions/min | 242.9 | 291.2 | −17% |
| Movement/min | 77.0 | 86.9 | −11% |
| Dodges/min | 31.4 | 28.6 | +10% |
| Attacks/min | 45.8 | 45.6 | 0% |

Same attack output, less movement, more dodging.

---

## Wins vs losses: essentially nothing

With outcomes now correct (1,594 wins / 2,031 losses), habits barely differ:

| metric | won | lost | diff |
|---|---|---|---|
| Actions/min | 242.7 | 244.0 | −0.6% |
| Movement/min | 76.6 | 77.9 | −1.7% |
| Dodges/min | 32.6 | 31.2 | +4.5% |
| Attacks/min | 46.0 | 45.5 | +1.0% |
| **Wasted-dodge %** | **14.9** | **12.7** | **+17.5%** |

Only one metric moves at all, and it moves the *wrong* way — he wastes **more** dodge
inputs in matches he **wins**. Consistent with the corrected pressure finding, and with
mashing being a by-product of aggressive exchanges rather than a cause of losing.

**This is the important negative result:** input-level habits do not separate his wins
from his losses. Whatever decides his matches is not visible at this level of analysis.
That is a direct argument for the option-comparison engine, which reasons about decisions
in context rather than about aggregate behaviour.

---

## Method note

Two semantic errors produced a confident, wrong, actionable-sounding finding that survived
a 19-check internal audit at 99.9%. They were caught by one screen recording and one
sentence from the player. Aggregate statistics cannot validate themselves.
