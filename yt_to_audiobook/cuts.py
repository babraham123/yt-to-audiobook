"""The SponsorBlock cuts: which spans go, how the cues shift, and the stream-copy remux."""

import bisect
import json
import subprocess

from .common import Cue, run


class Cuts:
    """The SponsorBlock skip segments, snapped to the audio's AAC frames so the cue shift
    matches where a stream copy can actually cut."""

    def __init__(self, info, duration, frame):
        spans = sorted(
            (max(0.0, s["start_time"]), min(duration, s["end_time"]), s.get("category", ""))
            for s in info.get("sponsorblock_chapters") or []
            if s.get("type") == "skip"
        )
        merged = []
        for start, end, cat in spans:
            start, end = round(start / frame) * frame, round(end / frame) * frame
            if end - start < frame:
                continue
            if merged and start <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], end)
                merged[-1][2].add(cat)
            else:
                merged.append([start, end, {cat}])
        self.segments = [(s, e, sorted(c)) for s, e, c in merged]
        self.duration = duration
        self.starts = [s for s, _, _ in self.segments]
        self.removed = [0.0]
        for s, e, _ in self.segments:
            self.removed.append(self.removed[-1] + e - s)

    def kept(self):
        intervals, at = [], 0.0
        for s, e, _ in self.segments:
            if s > at:
                intervals.append((at, s))
            at = e
        if at < self.duration:
            intervals.append((at, None))
        return intervals

    def inside(self, t):
        i = bisect.bisect_right(self.starts, t) - 1
        return i >= 0 and t < self.segments[i][1]

    def shift(self, t):
        """t on the cut audio's clock; a time inside a segment lands on its cut point."""
        i = bisect.bisect_right(self.starts, t) - 1
        if i < 0:
            return t
        s, e, _ = self.segments[i]
        return s - self.removed[i] if t < e else t - self.removed[i + 1]

    def apply(self, cues):
        out = []
        for c in cues:
            if self.inside((c.start + c.end) / 2):
                continue
            start, end = self.shift(c.start), self.shift(c.end)
            if end - start > 0.001:
                out.append(Cue(start, end, c.text))
        return out

    def report(self):
        return [
            {"start": round(s, 3), "end": round(e, 3), "categories": c} for s, e, c in self.segments
        ]


def probe(path):
    out = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=duration,sample_rate",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    # The audio stream's own length: the file's also counts the chapter text track.
    stream = json.loads(out)["streams"][0]
    return float(stream["duration"]), int(stream["sample_rate"])


def cut_audio(audio, cuts, dest):
    # The concat demuxer stream-copies every kept interval of the one file in a single pass;
    # AAC packets are all keyframes, and the cut points sit on packet boundaries already.
    lines = ["ffconcat version 1.0"]
    for start, end in cuts.kept():
        lines += [f"file '{audio.name}'", f"inpoint {start:.6f}"]
        if end is not None:
            lines.append(f"outpoint {end:.6f}")
    listing = audio.with_name("cut.ffconcat")
    listing.write_text("\n".join(lines) + "\n")
    # The second input carries the tags and the embedded cover; its chapters are SponsorBlock
    # marks on the uncut clock, so they're dropped.
    run(
        [
            "ffmpeg",
            "-nostdin",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(listing),
            "-i",
            str(audio),
            "-map",
            "0:a",
            "-map",
            "1:v?",
            "-map_metadata",
            "1",
            "-map_chapters",
            "-1",
            "-c",
            "copy",
            "-disposition:v",
            "attached_pic",
            "-movflags",
            "+faststart",
            "-f",
            "mp4",
            str(dest),
        ],
        "ffmpeg",
    )
