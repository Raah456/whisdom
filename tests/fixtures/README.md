# Test fixtures

Drop files here and the suites will find them automatically. Nothing in this
folder is committed — replays and recordings are personal gameplay data.

    [10.09] SmallFortressof.replay   the verified match (ground truth + review)
    <anything>.mp4                   the recording of that same match (vision)
    store/                           a store built by `whisdom ingest` (app)

Or point at them with environment variables instead:

    export WHISDOM_REPLAYS=~/BrawlhallaReplays
    export WHISDOM_REPLAY="$WHISDOM_REPLAYS/[10.09] SmallFortressof.replay"
    export WHISDOM_VIDEO=~/recordings/that-match.mp4
    export WHISDOM_STORE=~/.whisdom

WHISDOM_REPLAY and WHISDOM_VIDEO must be the same match. The vision suite checks
them against each other — that mutual check is the test.
