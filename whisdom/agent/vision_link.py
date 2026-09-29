"""
Pair a recording with a stored match and attach damage.

The replay gives frame-accurate inputs and KO times but no game state; the video
gives damage but no inputs. Joining them needs a time offset and a mapping from
HUD position to player slot — and BOTH are derived here from the death pattern,
so nothing has to be measured or labelled by hand.

That matters practically: the old data-collection quest asked the player to note
when the match starts in the recording. It no longer needs to.
"""
from whisdom.vision import damage as dmg
from whisdom.vision import video as vid


def ko_seconds_by_slot(doc):
    """{slot: [death seconds]} from a match document. Slots are victims."""
    fps = doc["match"].get("fps") or 60
    out = {}
    for m in doc.get("analysis", {}).get("moments", []):
        if m.get("kind") == "ko" and m.get("slot") is not None:
            out.setdefault(m["slot"], []).append(m["frame"] / float(fps))
    for v in out.values():
        v.sort()
    return out


def analyse(doc, video_path, sample_fps=2.0, detect_frames=24, progress=None):
    """
    Read damage for every player in `doc` from `video_path`.

    Returns a dict:
        arcs      [ArcRegion]
        offset    seconds; video_seconds = match_seconds + offset
        mapping   {arc_index: slot}
        tracks    {slot: [DamageReading]}
        check     {slot: (matched, missed, spurious)}
        score     alignment score
    Raises RuntimeError with a plain message when it cannot be done.
    """
    say = progress or (lambda *_a: None)
    kos = ko_seconds_by_slot(doc)
    if not kos:
        raise RuntimeError(
            "this match has no KOs recorded, so there is nothing to align the "
            "video against. Damage still needs one shared reference point.")

    say("locating HUD arcs")
    with vid.sample(video_path, count=detect_frames) as f:
        arcs = dmg.find_arcs(f.images())
    if not arcs:
        raise RuntimeError(
            "could not find the damage arcs. This looks for a pair of "
            "same-sized, same-row elements that change colour through "
            "yellow/orange/red over the match — check the HUD is visible and "
            "not cropped out of the recording.")
    say("found %d arcs" % len(arcs))

    series = []
    for i, a in enumerate(arcs):
        say("reading arc %d" % i)
        with vid.sample(video_path, fps=sample_fps, region=a) as f:
            series.append(dmg.series(list(f), a))

    say("aligning to replay")
    aligned = dmg.align(series, kos)
    if not aligned:
        raise RuntimeError("could not align the recording to this match")
    score, offset, mapping = aligned

    tracks, check = {}, {}
    for ai, slot in mapping.items():
        tracks[slot] = series[ai]
        want = [k + offset for k in kos[slot]]
        check[slot] = dmg.validate(series[ai], want)

    return dict(arcs=arcs, offset=offset, mapping=mapping, tracks=tracks,
                check=check, score=score, sample_fps=sample_fps)


def attach(doc, result, video_path):
    """Write the damage track into a match document, in place."""
    fps = doc["match"].get("fps") or 60
    doc["match"]["has_video"] = True
    doc["match"]["video_offset_frames"] = int(round(result["offset"] * fps))
    doc["match"]["video_path"] = video_path
    obs = doc.setdefault("observations", {})
    obs["damage"] = [
        {"slot": slot,
         "seconds": round(r.seconds - result["offset"], 2),   # match time
         "estimate": round(r.estimate, 3)}
        for slot, track in sorted(result["tracks"].items())
        for r in track
    ]
    return doc


def damage_at(doc, slot, seconds, tolerance=1.5):
    """Damage estimate for a player at a match time, or None if not covered."""
    best = None
    for d in doc.get("observations", {}).get("damage", []):
        if d["slot"] != slot:
            continue
        gap = abs(d["seconds"] - seconds)
        if gap <= tolerance and (best is None or gap < best[0]):
            best = (gap, d["estimate"])
    return best[1] if best else None
