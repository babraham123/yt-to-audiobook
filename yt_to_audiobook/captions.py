"""WebVTT cues, with YouTube's rolling auto-captions reduced to each cue's new text."""

import html
import itertools
import re

from .common import Cue


def vtt_time(s):
    secs = 0.0
    for part in s.split(":"):
        secs = secs * 60 + float(part)
    return secs


def clean_line(line):
    # Inline word timings (<00:00:01.234>), <c> spans and voice tags carry no text.
    return " ".join(html.unescape(re.sub(r"<[^>]*>", "", line)).split())


def parse_vtt(text):
    """Cues with only their new text. YouTube's auto-captions roll: each cue repeats the line
    before it above its new one, and a 10 ms cue between them repeats the line on its own."""
    cues = []
    prev = []
    # Only an empty line ends a cue: auto-captions put a lone space above the first line.
    for block in re.split(r"\n{2,}", text.replace("\r\n", "\n").replace("\r", "\n")):
        lines = block.strip("\n").split("\n")
        at = next((i for i, line in enumerate(lines) if "-->" in line), None)
        if at is None:
            continue
        m = re.match(r"\s*([\d:.]+)\s+-->\s+([\d:.]+)", lines[at])
        if not m:
            continue
        start, end = vtt_time(m[1]), vtt_time(m[2])
        shown = [c for c in (clean_line(line) for line in lines[at + 1 :]) if c]
        overlap = next(
            (n for n in range(min(len(prev), len(shown)), 0, -1) if prev[-n:] == shown[:n]), 0
        )
        new = shown[overlap:]
        if shown:
            prev = shown
        if not new:
            if cues and shown:
                cues[-1].end = max(cues[-1].end, end)
            continue
        cues.append(Cue(start, end, " ".join(new)))
    # Rolling cues overlap the next one; a highlight has to end before the next begins.
    cues.sort(key=lambda c: c.start)
    for a, b in itertools.pairwise(cues):
        a.end = min(a.end, b.start)
    return [c for c in cues if c.end - c.start > 0.001]
