# Adding a game to whisdom

whisdom is **one platform with one agent**. Games plug in as adapters; the store,
pipeline, watcher, reports, clip pipeline and analyses are shared.

Everything game-specific is declared in a `GameAdapter` (`whisdom/games/base.py`).
Nothing in `core/` or `agent/` should ever need to change to support a new game.

## What you implement

```
whisdom/games/<yourgame>/__init__.py
```

exposing a registered `GameAdapter`:

| field | what it is |
|---|---|
| `name` / `display_name` | identifier and label |
| `load_match(path)` | **the only real work** — parse a replay into `core.Match` |
| `action_model` | how many frames each action occupies the player |
| `categories` | action groupings for habit metrics |
| `replay_ext` | file extension, e.g. `.replay` |
| `replay_paths` | candidate folders per platform (`win` / `darwin` / `linux`) |
| `character_noun` | "Legend", "Fighter", "Character" — used in reports |
| `fps` | engine tick rate |
| `pressure` | which committed action to measure, and how long it lasts |

`load_match` must return a `core.Match`: **frames** (never milliseconds), **slots**
(never player names), and free-form action strings. Core never hardcodes a vocabulary.

## The reference adapter

`whisdom/games/example/` is a fake game that exercises the whole platform with a
completely different vocabulary (`Guard`/`Strike`/`Slam` instead of `Dodge`/`Light`/
`Heavy`), a different file extension, a different character noun and a different
pressure action.

**It is a leak detector.** If a real game's terminology creeps back into `core/` or
`agent/`, the example adapter stops working. It caught two leaks while this
contract was being written — a hardcoded `.replay` pattern and hardcoded replay
paths.

## What is genuinely shared

Moment detection, habit profiling, the pressure analysis, the option/EV engine, the
store and schema, reports, the clip pipeline, the watcher and the CLI — none of
these know which game they are looking at.

## What is genuinely per-game

Replay parsing, frame-data extraction, and the tables that give characters and
stages names. In Brawlhalla that is roughly 900 lines; everything else is shared.
