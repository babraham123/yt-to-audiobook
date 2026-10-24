"""Turns a YouTube video into a read-along EPUB: its m4a audio track with the SponsorBlock
segments cut out, and its captions as the text, each cue highlighted while it plays (EPUB 3
Media Overlays)."""

import tempfile
from pathlib import Path

from .captions import parse_vtt
from .common import Cue, Failure, NoCaptions, log, stop_child
from .cuts import Cuts, cut_audio, probe
from .epub import build_epub, chapter_starts, chapters
from .fetch import DEFAULT_SPONSORBLOCK, check_request, fetch, pick_captions, stt

__all__ = [
    "DEFAULT_SPONSORBLOCK",
    "Cue",
    "Failure",
    "NoCaptions",
    "convert",
    "parse_vtt",
    "stop_child",
    "stt",
]


def convert(url, out_epub, lang="en", workdir=None, sponsorblock=DEFAULT_SPONSORBLOCK, *, stt=stt):
    """Writes the read-along EPUB for the video at url to out_epub and returns its report.

    workdir keeps yt-dlp's downloads; pass the same one again after an interruption (see
    stop_child) to resume. Without one, a temporary directory is used and removed.
    sponsorblock is the SponsorBlock categories to cut; empty cuts nothing. stt is called
    as stt(audio, lang, workdir) for a video without captions and returns a VTT path.
    Raises Failure, or NoCaptions when there is no text to build from."""
    check_request(url, lang)
    out_epub = Path(out_epub)
    if workdir is None:
        with tempfile.TemporaryDirectory(prefix="yt-to-audiobook-") as tmp:
            return _convert(url, out_epub, lang, Path(tmp), sponsorblock, stt)
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    return _convert(url, out_epub, lang, workdir, sponsorblock, stt)


def _convert(url, out_epub, lang, wdir, sponsorblock, stt):
    info, audio = fetch(url, lang, wdir, sponsorblock)
    vtt, source, lang = pick_captions(info, audio, lang, wdir, stt)
    log(f"captions: {vtt.name} ({source})")
    cues = parse_vtt(vtt.read_text(encoding="utf-8"))
    if not cues:
        raise NoCaptions(f"no cues in {vtt.name}")

    before, rate = probe(audio)
    cuts = Cuts(info, before, 1024 / rate)
    if cuts.segments:
        cut = wdir / f"{info['id']}.cut.m4a"
        cut_audio(audio, cuts, cut)
        played = cut
        cues = cuts.apply(cues)
        if not cues:
            raise Failure("every cue is inside a SponsorBlock segment")
    else:
        played = audio
    after, _ = probe(played)
    log(f"{len(cues)} cues, {len(cuts.segments)} cuts, {before:.0f} s to {after:.0f} s")

    meta = {
        "id": info["id"],
        "title": info.get("title") or info["id"],
        "uploader": info.get("uploader") or info.get("channel"),
        "url": url,
        "upload_date": info.get("upload_date"),
        "description": info.get("description"),
    }
    cover = next(
        (p for p in (wdir / f"{info['id']}.jpg", wdir / f"{info['id']}.png") if p.exists()), None
    )
    parts = chapters(cues, chapter_starts(info, cuts, after))
    out_epub.parent.mkdir(parents=True, exist_ok=True)
    # Built beside the target and renamed, so a reader watching the directory never sees half
    # an EPUB.
    tmp = out_epub.with_name(f".{out_epub.name}.tmp")
    build_epub(tmp, meta, played, cover, parts, lang)
    tmp.replace(out_epub)
    return {
        "video_id": info["id"],
        "title": meta["title"],
        "url": url,
        "caption_source": source,
        "caption_track": vtt.name,
        "language": lang,
        "cues": len(cues),
        "chapters": len(parts),
        "cuts": cuts.report(),
        "duration_before": round(before, 3),
        "duration_after": round(after, 3),
    }
