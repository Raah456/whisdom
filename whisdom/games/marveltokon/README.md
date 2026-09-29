# Marvel Tōkon: Fighting Souls

Tokon ships no replay file. There is nothing on disk to parse, so this adapter
reads the match from **video you recorded yourself** — frame by frame, with
template matching and OCR.

## What is here

```
extract/     video perception
  replay_intake.py   segment a recording into rounds
  nameplate.py       who is playing, from the plate
  hud.py             health, meter, timer
  inputs.py          the input display, frame by frame
  caption.py         training-mode captions
  find_openings.py   where a turn actually started
  find_captions.py   locate the caption region
  combos.py          combo segmentation
  moves.py           which move was that, from the panel alone
  parse_trials.py    combo trial parsing
  *.npz, *.npy       template banks, built from recorded frames
data/replays/        per-recording output: events, inputs, openings, combos
app/                 local coach server and UI
```

## How move identification works

The training-mode panel shows three numbers. Only one of them is usable, and
finding out which took measuring 3,541 move instances across a long recording:

- **Attack Startup** is stable for the duration of a move, then changes. Usable.
- **Active** is stable but disagrees with the frame tables. Not used.
- **Total** is not the move's total. It ramps and resets like a stopwatch.

Startup is the primary fingerprint: 2,609 of 3,541 measured startups (73.7%)
land exactly on a value in that character's own table. Magik's measured startups
pile up on hers — 6 appears 331 times, 9 appears 365 times. Random values would
not do that.

Where two moves share both a startup and a damage figure, the pair is printed
rather than one of them picked. More than three candidates reports as not
identified. Nothing is guessed down to a single name.

## Not in this repository

The original version of this adapter also read the shipped game's own asset
archives to build reference tables. None of that is here — no archive readers,
no script decoders, no decoded tables, and no scraped wiki data.

The consequence is that the features which cross-check a measurement against a
reference table will report an error instead of a result. That is the intended
failure: the project's rule is that an unvalidated path returns nothing rather
than its best guess.
