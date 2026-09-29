# Whisdom for Tōkon — the app

Local, stdlib only, no install.

```
cd ~/Desktop/TokonFW
python3 -m whisdom.games.marveltokon.app.server
```

Opens http://127.0.0.1:8765/ in your browser. Ctrl-C stops it.

## What works (build 1 — 2026-08-25)

- Start screen: press any key, click, or any controller button.
- Language: button glyph set (PlayStation default), notation level, bindings
  learned from your pad (press each of the 8 actions once), text language.
- Profile: username, PSN, Parsec, Discord. Saved to `data/app/profile.json`.
- Team: 20 fighters in the five teams, click order = slot order. Hover a
  fighter for the card: game knowledge (fastest button, longest reach, most
  punishable, moves on record), systems from the game's own state names.
- Menu: Replay, Matchup, Training, Knowledge, Community (all built in later builds below).

## Build 2 additions (2026-08-25)

- Menu shows one still of your point character with your username under it.
  Full-size stills go in `data/app/hero/<CODE>.png` (or .jpg/.webp), e.g.
  `RSN.png` for Magik. Until one exists the 220px portrait is used and marked
  placeholder. Codes are in `data/app/roster.json`.
- Bottom strip: in-game level and rank (typed in on the Profile screen for now),
  and Whisdom level — in-app progression for using the app. XP table is at the
  top of `server.py`; state in `data/app/progress.json`.
- Animated background: drifting grid and halftone, a slow light sweep. CSS only.
  Honours the OS reduce-motion setting.

## Build 3 (2026-08-26) — Options

- Menu → Options: Language (reopens the setup screen; confirm returns here),
  Profile (edit handles, level, rank — rank offers the game's tiers Bronze …
  Master), Coach (Anthropic API key → `data/app/secrets.json`, mode 600,
  gitignored; `GET /api/secrets` only ever reports set/not set).

## Build 4 (2026-08-26) — Matchup

- Menu → Matchup. Pick the opponent (21 portraits), then one of their moves
  that is negative on block — each with the game's own command-list screenshot
  where the join finds one (specials, supers, uniques, throws; normals have no
  shot in the game files). Right side: the versus card (on-block, frames you
  have, their reach), then every answer of yours with startup ≤ the gap —
  picture, glyphs in your button set, startup and spare frames, damage, reach
  verdict, meter cost. Sort by damage / fastest / reach.
- Quiz me: their move as a picture, four buttons, one fits the gap. Awards XP
  (`matchup_answered`).
- Glyphs: `glyphFor(action)` uses your learned bindings (PS or Xbox index →
  glyph); before bindings are learned the PS table is a guess.
- Data: `/api/moves/<name>` (command list joined to wiki rows, `punishable`,
  `rows`), `/api/matchup?them=&move=&you=`. The join from command-list keys to
  wiki inputs is a text rule (`_entry_inputs`) — `[model]`.

## Build 5 (2026-08-26) — Replay

- Menu → Replay. Captures on file (every `data/replays/*-segments.json`), the
  timeline of what was read vs skipped, the six numbers, who you fought, and
  the findings — every opening ("X had N free frames and threw nothing") and
  every `Punish!` the game printed, ranked, each with its receipt and its open
  question. Grade each Right / Wrong / Actually with a one-line note →
  `data/app/grades.json` (gitignored). Grading pays XP once per finding.
- Locked cards say what is missing and why: move-level findings and habits
  (T-020), the coach's take (API key + the agent call, not wired).
- Drop a match: the five terminal commands, until the app runs them itself.
- Data: `/api/replays`, `/api/replay/<video>`, `/api/grades`, `POST /api/grade`.

## Build 6 (2026-08-26) — Knowledge

- Menu → Knowledge. The game's own Battle Guide — 125 topics in Mechanics /
  Offense / Defense / Assemble (Fuzzy Guard, Frame Traps, Meaty, Punishes,
  Hit Confirms, Reversals…) — verbatim from `GameText_en-US`, with the game's
  button markup rendered in your glyph set. Where the game has a tutorial
  mission for the topic, its brief is shown as "the game's own drill".
- Under four topics, our numbers: Punishes (your fastest buttons + the verified
  frame-advantage fact), Fuzzy Guard (slow overheads from the fighters you
  actually face, from your capture), Meaty (openings in your capture), Attack
  parameters (where the numbers come from). Reading a topic pays XP once.
- Data: `data/app/knowledge.json` (gitignored, game text) built by the T-022
  pipeline; `/api/knowledge`.

## Build 7 (2026-08-26) — Community fetcher

- `app/community.py`: fetches tokon.gg's tier list and 21 character pages
  from this Mac (one request every 2 s, a User-Agent naming the tool), parses
  tier / overview / how-to-play / combos, stores
  `data/app/community/tokon_gg.json` with source and date. Options →
  Community → Fetch now runs it in the background; the Team card's Community
  section shows tier, overview, three combos, source and date, marked
  "editorial". Until a snapshot exists the card says so.
- Not run against the live site from the build environment (no network
  there). The first fetch on the Mac is the first real test; failures are
  listed per character in Options → Community.
- The Team card now also shows the game's own character description ("The
  game says"), from the command list text.

## Build 8 (2026-08-26) — Sound and motion

- UI sounds synthesised with WebAudio (cursor, confirm, back, quiz right /
  wrong). No files. Music: a 75-second loop cut from LongBatch1's menu stretch
  (`data/app/audio/menu_loop.m4a` + `.ogg`, gitignored) — a placeholder until
  the game's own tracks are reachable (they are Wwise events; the media is not
  on disk). Options → Sound & motion: on/off and volume for each, saved with
  the profile. Music starts on the Start-screen press.
- Motion: a muted 8-second gameplay loop plays behind the menu still
  (`data/app/clips/menu_LongBatch1.mp4`); every Replay finding carries a
  4-second receipt clip (hover to play) cut by `app/clips.py` from the footage
  — 70 clips, 47 MB, gitignored. Matchup pictures zoom on hover. Reduce-motion
  in macOS is honoured; the Motion toggle turns clips off.
- Clips are H.264 for Safari/Chrome on the Mac. Regenerate with
  `python3 -m whisdom.games.marveltokon.app.clips LongBatch1 --menu`.
- The real animated move pictures exist: `MTFS/Content/Movies/CommandList/
  <CODE>/CMD<CODE>###.bk2` — Bink 2 video of every command-list move, 845
  files. ffmpeg cannot decode Bink 2; RAD's free Bink tools on Windows can
  (bk2 → mp4). Once converted into `data/app/movies/<CODE>/…mp4` they drop
  into the same slots as the pictures (task T-030).

## Build 9 (2026-08-26) — Drop a match

- Replay → Drop a match lists every `.mp4` the app can see (repo root, the
  PS5 drive) with Analyse / Re-run. `app/runner.py` runs classify → read
  panels → openings → name plates as a background thread, progress and log in
  the card, the screen reloads when done. Tested end to end on `Mgk.mp4`
  (10 s). Punish! captions are not run for new captures (T-031).
- Data: `/api/videos`, `POST /api/replay/run`, `/api/jobs` (state in
  `data/app/jobs.json`, gitignored). Needs ffmpeg + numpy + OpenCV in the
  Python running the server; a missing one fails the job with the error shown.

## Build 10 (2026-08-26) — Training

- Menu → Training, three tabs. **Routes:** the game's own Trial-mode combos
  for your character (229 across the roster), each step with its picture,
  glyphs, startup and on-block, the weakest link on block marked; log a rep
  Landed / Dropped → `data/app/drills.json`, mastery pips, XP. **Builder:**
  start from any move; what can follow is what the game's trials actually
  contain (solid, fact) plus the L → M → H chain rule (dashed, model); cost and
  weakest link shown; whether the chain connects is not claimed. **Pad:** live
  stick and buttons in your learned bindings, motion recogniser (236 / 214 /
  623 / 22), and a link-timing drill that measures the gap between two presses
  in frames against a target.
- Data: `/api/routes/<name>` (Trial routes in wiki notation, from
  `data/verified.json`), `/api/drills`, `POST /api/drill`.
- Rep completion is self-reported until move naming (T-020) lets the next
  capture verify it. The pad cannot see the game.

## Build 11 (2026-08-26) — Input, motion, concepts, tech

- **Input method.** First run asks Controller / Keyboard / Just looking.
  Controller goes straight to pad binding; Keyboard opens a 12-key binding
  screen (four directions + the 8 actions; your Light key or Enter confirms);
  Just looking keeps the mouse — everything clicks. Change later in
  Language → Change. Saved in the profile as `lang.input`, `lang.keys`.
- **One highlight everywhere.** The d-pad / left stick, the arrow keys / WASD /
  your bound directions, and the mouse all move the same highlight. On the main
  menu and the Options / Language menus the highlight is the coloured block
  itself and it slides between items (hovering moves it too; on the side menus
  it opens that pane). On grids and lists it is an orange outline. Confirm =
  pad button 0 / Enter / your Light key; back = pad button 1 / Esc / your
  Medium key. Geometric navigation: the nearest item in the direction pressed.
- **Page transitions.** Leaving screen slides out, a cyan wipe crosses, a
  short page sound plays. Off under reduce-motion or the Motion toggle.
- **Knowledge → Concepts.** A first tab of 14 game-agnostic concepts (frame
  advantage, punish, okizeme, meaty, safe jump, fuzzy guard, frame trap, hit
  confirm, neutral, mixup, anti-air, reversal, setplay, resources) from
  `data/app/concepts.json` — definition, why it matters, how to practise it,
  and a "go" button to the Training tab or mode that drills it. Under each:
  the game's own Battle Guide topics for it (linked, not copied, `[fact]`) and
  the fighters whose in-game descriptions mention the idea (`[model]`, keyword
  rules in the same file; hover a name for the sentence that matched).
- **Team card → Excels at.** The same tags on the character card, so the
  card says what the fighter is for and the Concepts tab says what the idea is
  — one source, no repeated text. Click a chip to open the concept.
- **Community → Tech.** Write up a tech: title, fighter, steps in numpad
  notation one per line, concepts it uses, notes. Saved as one JSON file in
  `data/app/tech/` (gitignored) — yours to keep. Export the file, send it,
  the other player imports it (Import a file) and it appears under Imported.
  Every tech is a drill: **Drill it in Training** puts it first in the
  Training → Routes list, steps resolved against the game's move pictures and
  frame data where the notation matches, reps logged like any route
  (`tech:<id>`), mastery pips back on the Community card. Marked "written
  by a player, not by the game — no claim it connects".
- Data: `/api/concepts`, `/api/tech` (+ `POST`, `/import`, `/delete`),
  `/tech/<id>.json` for export.

## Build 12 (2026-08-26) — Look, notation, feel

- **Bolder, still the game's.** White ground with a halftone and a diagonal
  slash, black type, electric blue, hot orange, gauge yellow. Display type is
  now Kanit ExtraBold Italic (Barlow Condensed stays as the fallback); labels
  are Barlow Semi Condensed. Every block — menu items, panes, cards, stats,
  buttons — has a 2px black edge and a solid offset shadow (black, or blue on
  the selected item) instead of a soft grey one.
- **Notation levels that look different.** *Buttons & arrows* (now the
  default) draws inputs the way the game's input display does: solid arrow
  icons in black pills (one pill per direction, one pill for a motion like
  ↓↘→) plus the button glyph — no digits. *Numpad* keeps 2M / 236H with
  glyphs; *Game letters* uses the trial letters A/B/C/D. The Language →
  Notation pane shows the same four inputs in all three. Arrows are drawn
  (one SVG shape rotated), so they stay sharp at any size.
- **Feel.** Controller rumble on cursor / confirm / back / page / right /
  wrong, through the browser's Gamepad haptics (Chrome and Edge on the Mac;
  Safari has no rumble API). Only fires when the pad was the last thing you
  touched, so a mouse hover never shakes the pad. Toggle in Options → Sound.
  Every press already had a cue; the pad's confirm/back now go through the
  same ones.
- **BGM picker** on the menu head: ‹ › cycles every track in
  `data/app/audio/` (m4a / mp3 / ogg / wav), the name toggles mute, the choice
  is saved with the profile. `data/app/audio/tracks.json` can name tracks
  (`{"menu_loop": {"name": "Lobby"}}`). Cut more loops from footage with
  `python3 -m whisdom.games.marveltokon.app.clips LongBatch1 --music NAME START SECONDS`.
- **Menu.** The hero slides through your whole team every 7 s (crossfade;
  off under reduce-motion / Motion off); the four slots sit up top as portraits
  with their role, the one on screen lit — click one to jump to it. A slanted
  strip of the point character's command-list frames fills the space under
  the menu note.
- **Game frames in the blank space.** Every empty pane — Options, Training
  before a route, Knowledge before a topic, Replay before a capture, Community,
  the input-method and key-binding screens — carries the game's own wide
  banner art (`data/app/hero_wide/<CODE>.png`, the cyan-silhouette cards the
  game uses on loading screens) on a navy slab, or a strip of command-list
  frames where no banner exists (5 of 21 fighters). `/api/art` reports what
  is on disk; nothing is faked when a file is missing.
- Start screen: three full-body stills on cyan slabs instead of stretched
  portraits.

## Build 12b (2026-08-26, evening) — Review deck, Admin

- **Replay → Review.** One finding at a time: the receipt clip as big as the
  pane (click to pause, ↺ restart, ½× slow), the debrief in a card under it
  (title, receipt, open question), Right / Wrong / Actually and the note box,
  Prev / Next. Right and Wrong move to the next finding; Actually stays so you
  can type, Enter moves on. A row of bars shows every finding's grade (blue
  right, orange wrong, yellow actually); click one to jump. Timeline, stats,
  opponents and locked cards live behind the **Breakdown** tab. Every grade is
  saved the moment you click it (`POST /api/grade` → `data/app/grades.json`);
  closing the browser loses nothing.
- Clips are now cut at 1280 wide (`clips.py --width`, `--redo` re-cuts anything
  narrower than the target).
- **Admin panel** — press **`** anywhere (or Options → Admin). A note you write
  there is appended to `ops/INBOX.md` with the screen you were on and what was
  selected (capture + finding, route, matchup, topic, tech), plus every error
  the page saw since the last note — a clip that didn't load, a failed request,
  a JS error. Sessions read the inbox first. Also `data/app/admin/notes.jsonl`.
  **Test mode** (checkbox in the panel, saved in the profile) paints ids on
  cards, the clip path on the player, and an error badge bottom-left.
- `~/Desktop/Whisdom.app` — double-click to start the server (inside Terminal,
  because macOS won't let a bare script app read the Desktop folder) and open
  Chrome. Closing that Terminal window stops the server.

## Build 12c (2026-08-26, evening) — Community feed: other players' combos, cited

- **Community → Feed.** Paste an X post link. The app asks X's own oEmbed
  endpoint for it (`app/social.py`) — the sanctioned, login-free way to
  republish a public post: author name, profile link, the text, and X's
  embed, which renders the real post with its video inside the app (needs the
  internet; the text is the fallback). No scraping, no copies of their media.
- **Notation → steps.** The post's text is parsed for fighting-game notation
  (numpad + L/M/H/U, j., 236…, the game's A/B/C/D letters, words like jump /
  dash / land) into the app's steps with a confidence figure. **Make it a
  drill · cite @handle** saves it to Imported with the source on it (author,
  handle, URL, when fetched, the line it came from); the fighter is read from
  the post text when named. The Training card shows *by @handle · source on
  X*; **▶ Play the steps** walks the pictures at combo tempo; reps log as
  usual. *Edit steps first* opens the form prefilled. A link that is not an X
  post is kept as the citation and you type the steps.
- **Files cite too.** An exported tech carries its author and source, so
  importing someone's file credits them. Profile has an X handle field so your
  own exports carry yours.
- **Watch the lab:** set an X list URL on the Feed home and X's list widget
  scrolls inside the app. **Pull recent posts** tries X's undocumented
  syndication endpoint for the accounts you list — may fail, failures shown.
  There is no free, sanctioned search of X; discovery is by link or list.
- **Your own videos, tagged clips.** The tech form takes an upload (mp4 / mov
  / webm → `data/app/tech/clips/<id>.<ext>`, gitignored, played inline on the
  card and in Training) and a *Clip by* tag with a link, for a recording that
  isn't yours; a tech made from a post is tagged with the poster automatically.
- Data: `data/app/community/posts.json` (gitignored — other people's text);
  `/api/social/*` in `server.py`. Not run against X from the build
  environment (no network) — the first paste on the Mac is the first live test.

## Build 12d (2026-08-26, evening) — BGM everywhere, a library screen

- The BGM bar (‹ ▶/❚❚ name ›) now sits in the prompt bar of every screen, not
  just the menu. Click the name to open the **BGM screen**: the library as
  cover tiles (embedded cover art is pulled out of the file on upload; a
  png / jpg with the same name works too), the one playing marked, a
  now-playing pane with play / prev / next, Loop one / Shuffle all, volume,
  rename, add a cover, remove (files go to `data/app/audio/_removed/`).
  **Add tracks** uploads mp3 / m4a / ogg / wav / flac straight into
  `data/app/audio/`; titles, artist and album are read from the tags when
  ffprobe is on the machine. Options → BGM and Options → Sound both link to it.
- Library seeded with 15 tracks Raah supplied (Ultimate Tenkaichi, Budokai
  Tenkaichi 2, one Sonic Unleashed track) + the lobby loop. The folder is
  gitignored; the music is his.
- Data: `/api/audio` (now with `art`, `artist`, `album`, `seconds`),
  `POST /api/audio/upload` (raw body + X-Filename [+ X-Stem for art]),
  `POST /api/audio/meta`, `POST /api/audio/remove`.

## Build 12e (2026-08-26) — Takes, not verdicts

- Replay → Review no longer asks Right / Wrong. Each finding shows **the
  app's read** (receipt + open question) beside **your take** — free text —
  plus tags for what the moment really was (real opening / lag-rollback /
  defending on purpose / out of range / misread / unsure) and an optional
  line for your own gap. Saves on Next, ⌘↵, blur, or a click on a bar.
  **Send my takes** bundles every take on the capture into
  `ops/takes/<video>_<date>.md` — the app's read next to yours per finding,
  tag counts on top — and drops a line in `ops/INBOX.md`; additive, run it
  again later. `verdict` is still derived from the tags so the accuracy count
  keeps working.
- Raah's first pass already changed the pipeline's to-do: some "nothing
  thrown" windows are rollback stalls (both idle, counter stutters), and a
  window where the player is deliberately defending is not a missed opening.
  Both become discriminators (T-041).

## Build 13 (2026-08-26) — The coach

- Replay → **Coach** tab. One Claude call per capture through your own key
  (`app/coach.py`, stdlib urllib, model in Options → Coach, default
  `claude-sonnet-4-5`). The prompt is the capture's numbers, the findings with
  their receipts, **your takes verbatim beside each one**, your team, the
  concept list, and the rules: every sentence must point at a finding id or
  start with "Guess:"; believe the player's take over the app's number where
  they disagree; windows tagged lag / unsure are not evidence; say what to
  do, tie it to a concept and a Training drill; 4–7 sentences, then exactly
  one question, then one drill. Output is JSON; the server checks every cited
  id exists and demotes any sentence with a bad or missing citation to *guess*.
- The take renders sentence by sentence with the finding chips (#n — click →
  that finding in Review) and a fact / model / guess label; the question has a
  reply box (your answer joins the thread and the coach takes again); the
  drill links into Knowledge or Training. Confidence, model, tokens and time
  underneath. Cached in `data/app/coach/<video>.json` (gitignored) with every
  prompt and raw reply; re-asked only on **Ask again** or a reply. No key →
  **Show what it would send** prints the exact prompt. Reading the coach pays
  no XP on purpose.
- Not run live from the build environment (no network). The mock-API test
  covers the parse, the citation check, the cache and the thread.

## Build 14 (2026-08-26, night) — Sources: guides and commentary as words with names on them

- **Community → Sources.** A guide video on your disk (Add a video → copied
  into `data/app/sources/video/`) or a pasted transcript (YouTube's "Show
  transcript" panel, .srt, .vtt). Title, creator, link, fighter, kind.
- **`app/sources.py`** does the reading: one frame every 2 s; the top 45% of
  each frame — where guides put captions and combo cards — is cut as a band;
  the near-white text fill is isolated and drawn black on white, upscaled and
  thickened, and tesseract reads *that* (the raw frame over gameplay gave
  garbage). Blocks with ≥ 3 real words or notation are kept and merged
  across consecutive frames; OCR slips inside notation are normalised
  (S→5, 21U→214, ")."→"j."); the notation parser turns lines into steps,
  now with repeated-button runs (`j.HH`, `5MM`) as one press each. Slice-safe
  with checkpoints; runs as a background job from the app when ffmpeg and
  tesseract are on the machine (the screen says which tools it found).
- First source: *The Essential MAGIK Character Guide* (Marv Media, 14:22) —
  431 frames read, 78 caption blocks (the guide's steps and tips as text),
  13 combos off the combo cards, each with its frame and a timestamp link.
  **Make it a drill · cite Marv Media @ 10:38** → a tech in Imported with the
  source, the timestamp link and the clip credit on it.
- Quotes and combos flow to the **Team card** ("What the guides say", yellow
  community stripe, creator + timestamp on every line) and into the **coach
  prompt** ("what other players say — quote with the creator's name and
  timestamp, never as your own idea").
- Speech-to-text: none on this machine yet (`brew install whisper-cpp` would
  add it); until then transcripts are pasted. Data: `/api/sources`,
  `/api/source/<id>`, `/api/quotes`, `POST /api/sources/{upload,add,meta,
  process,transcript,to_tech}`; files under `data/app/sources/` (gitignored —
  other people's video and words).

## Build 15 (2026-08-27) — T-041: honest openings

- **One moment, one finding.** Windows on the same side of the same segment
  within 1.5 s are merged into one event (`merge()` in `find_openings.py`,
  written to `<video>-events.json`). LongBatch1: **60 windows → 48 events.**
  Segment 13's seven findings inside seven seconds — the largest of which
  ranked #1 in the whole capture — are now one 105-frame moment. The event
  keeps the frame count *and the id* of its largest member, so every take
  already given survives: 57 of Raah's 69 land directly, the other 12 are
  inside merged events and the deck shows them as "takes you left inside this
  moment" rather than losing them.
- **You / them, derived from the capture.** The player is the fighter on screen
  in most segments (Magik, 25 of 25; next is Doom at 8) — not the profile's
  point fighter, which read Captain America and would have labelled every one
  of Raah's own windows as the opponent's. Mirrors say which side. `you_why`
  carries the count as the receipt. The hardcoded `!= "Magik"` in the opponent
  tally is gone.
- **No-fault wording.** "X had N free frames and threw nothing" →
  **"You — N frames free, no new attack"**, and the open question now says the
  panel cannot tell blocking from dashing from a repeated move, so whether it
  was a mistake is the player's to say. 17 of the 69 takes were windows where
  he was deliberately defending.
- **Lag: no classifier ships.** Two panel discriminators were tested against
  the nine `lag`-tagged windows and both failed — per-window stopwatch stutter
  (median ramp 6.0 on lag windows *and* 6.0 on real ones) and per-segment
  health (28.1% vs 22.7%, while the two worst segments in the capture carry no
  lag tags at all). Both are recorded in `find_openings.py` so they are not
  retried. Instead the app carries **Raah's own tags** forward: a finding in a
  segment where he called something lag says "your call: you called N windows
  in this segment lag", labelled as his judgement. The untried route is the
  game's match clock in the HUD — a video read, not a panel read.
- A segment where the free side's name plate saw more than one fighter now
  carries a tag warning on the finding.

## Build 16 (2026-08-26) — T-042: what a hit is worth

- **The panel's damage fields, read properly.** `Damage` is the last hit's
  damage; `Combo` is the running damage total of the combo in progress; both
  linger at their last value after the combo ends. So a combo's first hit is
  the one sample where **`Combo == Damage`** — a later hit cannot tie, because
  the total before it would have to be zero. That is an exact boundary, not a
  threshold. It only counts on a sample where the value actually *changed*
  (on a lingering plateau the equality still holds; without that test the
  capture read 3,994 combos instead of 190), and a drop opens a combo too,
  covering two hits inside one 0.1 s sample.
- **Checked against its own output.** Every increment inside a combo should
  equal that sample's `Damage`: **702 of 756 do (92.9%)**, and every miss is an
  integer multiple of it (400 = 2×200, 3000 = 2×1500) — two hits in one
  sample. So the totals are right and the hit count is a **lower bound**,
  carried in the data as `hits_are`.
- **`extract/combos.py` → `<video>-combos.json`.** Every combo in a capture:
  side, character, damage, hits, span. LongBatch1: **190 combos**, 97 of them
  Magik's, typical 14,800, biggest 34,000, 20% stop at one hit. The first
  damage numbers the app has ever had. Mgk.mp4 gives 0 — nothing landed in
  it — and the file says that rather than inventing.
- **Punishes joined.** Each Punish! caption takes the combo whose first hit it
  followed. The caption lands **0.2–1.7 s after** that hit in all ten of
  LongBatch1's captions — that consistency is the join's receipt, and it is
  what ruled out two earlier attempts (a ±2.5 s peak window, and reset-bounded
  runs that produced 37.9 s "combos" because the counter lingers). Findings now
  read **"You — Punish! into 15,800 damage over 4 hits"**; a one-hit punish
  says *that can be the right call — no meter, wrong range, their assist was
  out — so this is the number, not a verdict.*
- **WHAT A HIT IS WORTH** on Replay → Breakdown: typical combo, typical punish,
  biggest, and the two one-hit shares, with `n=` on the header.
- **The honest result is that there is no punish problem here.** 14,100 typical
  punish against 14,800 for any combo; 2 of 8 punishes stop at one hit against
  20% of combos. Two of the ten captions are the *opponent* punishing him
  (Cap 2,000, Storm 5,500) — folding those in made the number say the opposite,
  so `_conversion()` filters to his own fighter. The strip prints "no gap worth
  chasing in this capture" rather than dressing n=8 as a habit.
- Comparing each punish to the best Trial route from the same starter — the
  spec's second half — needs move naming (T-012/T-020): a combo has damage and
  a hit count but no starter identity. Deferred, not attempted.
- Fixed in passing: the **coach prompt** was told the player was Captain
  America (the profile's point slot) while every segment has Magik in it — the
  same stale-profile bug T-041 caught in the server, one file over. It now
  takes `rep["you"]` and quotes the count as the reason.

## Build 17 (2026-08-26) — a second capture, and Progress / Doctor

- **`extract/find_captions.py`** — the Punish! pass as a CLI at last (T-031).
  Two passes: one ffmpeg process per segment pipes the caption band at 10 fps
  and every frame is tested for the teal banner; only the frames where the
  banner is up get the word template-matched at full resolution. Checkpoints
  after every segment. Validated against the ten hand-confirmed punishes:
  **all 10 found, none missed, 5 more found** — and every one of the 15 joins
  to a hit in the combo data 0.0–1.5 s earlier.
- **The name plate reader was refusing half the plates it could read.**
  `read_template` ranked raw templates and demanded a margin between the top
  two, but the bank holds up to 14 variants of the same word, so the top two are
  usually the same character. Ranking by NAME took the by-eye set from 23 of 50
  to 25. Reading five moments of a segment and voting (`read_plates`) takes it
  to **38 of 50, none wrong**, and fixes the one wrong read — segment 11 is a
  mid-segment tag, and `_seen` now carries both names instead of one confident
  wrong one.
- **`Vid1.mp4` is analysed** — 3 segments, 105 s of read playback, 19 combos,
  2 Punish!. Two combo-cutting fixes came out of it: a combo whose first hit was
  never sampled cleanly is now opened rather than dropped whole (marked
  `first_hit_inferred`), and a Punish! caption joins **the hit it follows**
  rather than a combo's first hit — Vid1's second caption trails hit 3 of a
  combo whose counter had not reset, and the finding says so.
- **A rule that looked airtight and was wrong, kept in the file so it is not
  retried:** "the comboing side cannot be the stuck side". Recovery is zero-sum
  and negative on whoever cannot act, and it fixed Vid1 cleanly — but
  LongBatch1 segment 20 has R at Recovery −40 for a second in the middle of a
  combo the game's own counter then continues to 31,055. The panel decides what
  one combo is.
- **Replay → Progress** (T-047). Every capture as rates, because they are not
  the same length: openings a minute, free time unused, combos a minute, typical
  combo, biggest, share that stop at one hit, typical punish, takes given. A
  capture under five minutes is marked **thin** and left out of the comparison.
  The change chips are coloured by *which way is better* — fewer openings a
  minute is an improvement, so it is cyan, not orange. Today it says "1 capture
  deep enough to compare", which is the truth.
- **Options → Doctor** (T-048). ffmpeg, ffprobe, tesseract, numpy, OpenCV, PIL,
  whisper, disk, and the serving interpreter's own path — checked where it
  matters, plus a per-job verdict. `doctor.gate()` is called by the capture
  runner and the Sources job, which now refuse with the missing piece named
  instead of failing four minutes in.
- **The left-side caption bias has a cause, not just a name:** 156 left banners
  detected, 3 read. Not the gutter blanking (tested). The left banner is clipped
  by the screen edge — x 0→250-320 against the right's 1520→1920 — so the start
  of the word is off-screen. Left-side captions stay a lower bound.

## Build 18 (2026-08-26) — what the opponents do, and a test you can run

- **Replay → Breakdown → WHAT THEY DO** (T-043). Per opponent, across every
  capture on file: the moments you gave them where they were free and you could
  not act (count, median frames, longest, how many segments), how many of those
  they took, how many combos they landed and what those were worth, and how
  often the game called Punish! on their side. Six named receipts each, behind a
  fold. The counts are `[fact]`; "they pressed" is `[model]` — a hit landing
  within 2 s of the window is the measurement, calling it a decision is the
  inference. Under three windows the card greys out and says so, and the coach
  is told the same in words.
  What it says about LongBatch1: Cap gave you the most openings and took 38% of
  them for a typical 10,000; **Doom is the one to worry about** — 35 combos and
  a 61,880 biggest. The character who takes the most openings is not the
  dangerous one.
- **`tests/smoke.py`** (T-039) — stdlib only, so it runs on the machine that
  runs the app. `python3 tests/smoke.py`. It starts the real server on a free
  port, walks 24 JSON endpoints and every analysed capture, checks every finding
  carries a receipt, and reads `index.html` for the ids and function names the
  render paths call. `--ui` also drives a browser if Playwright happens to be
  installed; `--quiet` prints only failures; the exit code is the failure count.
  **91 checks, 0 failures.**
  It earned its place immediately: `/api/quotes` was returning nothing and
  closing the connection, because a `from urllib.parse import parse_qs` inside
  `do_GET` made the module-level name local to that whole method and every later
  call raised `UnboundLocalError`. The panel just looked empty. Fixed, and
  `/api/health` added as the readiness probe.
- Still not vendored: the three Google font families. Offline the app falls back
  to Arial Narrow / Impact — legible, not the game's look. The smoke test
  asserts the font sheet and X's embed widget are the only external assets, so a
  new one shows up as a failure.

## Build 19 (2026-08-26) — the app can name a move

- **`extract/moves.py`**, `GET /api/starters/<video>`, and **WHAT YOU START
  WITH** on Replay → Breakdown. The keystone, without the two recordings.
- **The panel's `Total` field is a stopwatch, not a total.** It ramps +6 per
  0.1 s sample and resets, like Recovery. Matching moves on (startup, total)
  against the tables scored **15 of 3,568 — 0.4%**. The field name was the trap.
- **`Attack Startup` is stable for a move's whole duration**, and 2,609 of 3,541
  measured startups (**73.7%**) exist in that character's own table. Magik's land
  exactly on her table's values: 6 ×331 (5L / j.L), 9 ×365 (5M / j.M), 12 ×226,
  15 ×138, 11 ×100, 10 ×97.
- **Dustloop's damage percentage is the panel's raw number over a thousand**, on
  an unscaled hit: Magik 5M is 8.0% and reads 8,000, 2M is 7.0% and reads 7,000.
  Later hits in a combo are scaled and cannot be matched, so only first hits are
  named.
- **101 combo starters, 86 identified, 59 named exactly.** The leftover is the
  ground/air pair: 5L and j.L share a startup AND a damage figure, and the panel
  cannot tell a jump from a stance. Printed as a pair, never guessed. More than
  three candidates prints as "not identified" with the list as the reason.
- **The first move-level coaching line in the app:** *you open most often with
  5M for 20,300; 214M pays 22,570 and you used it 4 times.* 5H is thrown 8 times
  for 11,400 — less than 2M's 17,200 off a lighter button.
- **The table had holes and that was most of the residue.** `filefd.json` has no
  startup for 16 of Magik's 39 moves — every U button, both supers, the whole
  236 / 22 series. `dustloop_movedata.json` is merged in as a fallback (game file
  wins; the wiki only fills a gap) and supplied 22L/22M = 32 and 236M = 25,
  exactly the values measured 38 and 30 times as unmatched. **236M and 22L/22M
  appear as real starters for the first time.** The wiki's aggregates
  (`dc.214X`, `5XX > 5H`) are excluded — folding them in dropped 5H from 8 to 3
  by absorbing real starters into a series.
- A guess that was checked and dropped: "an unmatched startup means a tag".
  Startup 3, measured 148 times, exists in no character's table at all.
- Still owed to T-012: the ground/air split, naming later hits in a combo, and
  confirming the tag reading. The input gutter's direction rosette exists and is
  disabled; its button glyphs have never been read.

## Build 19b (2026-08-26) — the pose script

- **`data/move_states.json`** — move → BBScript state → startup / active / total
  → the per-frame pose script → the animation names it uses. 23 characters,
  937 moves. Nothing new was extracted; both halves were already on disk and
  had never been joined.
- **937 of 937 pose scripts sum to exactly the frame-data table's total. Zero
  off by a frame.** A BBScript opcode decode and a frame-data table, taken out
  of the game by different routes, agree on every move in the game. Startup
  lands on or within one frame of a pose boundary for all 599 moves that carry
  one, no misses. Both datasets are now cross-validated.
- 29 of the 31 animations Magik's moves reference exist as assets in the paks.
  Skeletons live at `Chara/<CODE>/Costume00/Mesh/`.
- **Three attempts to turn this into a move name from the panel, all failed and
  all recorded:** `Total` as a move length (its per-reset peaks track the
  startup values; 12.5% land on a table total — second failure for that field),
  the displayed duration between startup changes (5L 25 frames against j.L 29
  is 0.067 s, under the 0.1 s sampling floor), and `Active` as active frames
  (maxes at 1-4 whatever the table says, unchanged by re-reading at 30 Hz).
- **The ground/air split is not in the panel. It is in pixels.** The pose script
  is what makes either route to it cheap: rendering "Magik 5L at frame 7" is a
  lookup here, not a search.
- Watch the codes: Magik is **RSN**. The first pass ran against MGN and scored
  0%; the same code against RSN scored 100%. `roster.json`'s `charname` maps
  them.

## Build 20 (2026-08-26) — what you pressed

- **`extract/inputs.py`** → `<video>-inputs.json`, and every opening finding now
  carries what was entered inside its window.
- **One bad row was the whole blocker.** The gutter's rows sit on a 42 px
  ladder, but the first blob group the reader returns is at y=140 while the
  ladder starts at 232 — a 92 px gap. That row reads **0% (20 of 20, both masks
  tried)**; rows 1 onward read **70-100%**. Reading `Li[0]` as the newest input
  made the log look like a 13% signal. It is 70%.
- **The model, measured.** The newest row counts up while its input is held —
  1 per game frame, confirmed 2,629 times — and resets when a new input arrives,
  the old value sliding into row 1. **3,969 inputs in LongBatch1, 420 in Vid1**,
  each with its time and hold length. Median hold 5 frames, peaking at 4-6. The
  counter is two digits, so 99 means "99 or more"; 349 hit the cap and say so.
- **24 of the 48 openings had nothing entered at all.** A finding now reads
  *"105 frames free, no new attack · you entered 9 inputs in that window (held
  99+, 5, 58, 86, 99+, 6 frames)"*. Nothing entered adds *"this one is not
  blocking or dashing."* A hold of 20+ frames adds *"the panel cannot see
  blocking or walking, and that is what a long hold looks like. Yours to call."*
  The coach gets both.
  This is the first time the app separates **did nothing** from **did something
  the panel does not count** — the question the opening finder has been openly
  unable to answer since it was written.
- **What it still cannot do:** WHICH input. The direction rosette reader is
  disabled at 3/8 and the button glyphs are not located. An input here is
  "something was entered and held N frames" and nothing more.
- **A third lag discriminator, and a third failure.** Input rate looked strong
  (lag windows 6.87/s against ~2) and collapsed against the tags: the best
  threshold catches 3 of 7 with 1 false positive, F1 0.55, and three of the
  seven lag windows have no inputs at all. Three fields tried now — stopwatch
  ramp, segment health, input rate — none separates.

## What is a placeholder

- Community notes: only tokon.gg; player opinion and per-position rankings have no source yet.
- Coach's read on the card: needs an API key. Settings screen not built.
- Champion (21st fighter) is not in the five teams and is not shown.
- The PlayStation glyph layout shown before bindings are learned is a default
  guess. Bindings override it.

## Layout

```
app/server.py     the server and the JSON API (documented at the top of the file)
app/ui/index.html the whole UI, one file
data/app/         roster.json, moveart.json, portraits/, moveart/, profile.json
extract/combos.py the panel's Combo/Damage fields -> individual combos, and the
                  punish join (the rule and its check are in the docstring)
extract/find_captions.py  the teal banner -> Punish! / Good! / Knockdown!, per segment
app/doctor.py     what this machine can run, and the gate every job calls first
extract/moves.py  startup + unscaled damage -> which move; the fields and their
                  measured hit rates are in the docstring
extract/inputs.py the gutter's frame-count column -> every input, when and how
                  long; row 0 is not a log row and that is why it looked empty
tests/smoke.py    the whole app, checked with nothing installed: python3 tests/smoke.py
```

The look follows the game's own menus: paper ground, cyan slab titles, white
italic menu blocks, orange initial on the selected item, button prompts along
the bottom. No game assets are used except the portraits and command-list art
already extracted into `data/app/`.
