"""The yt-dlp download and the choice of caption track."""

import json
import re

from .common import Failure, NoCaptions, run

LANG_CODE = re.compile(r"^[a-z]{2,3}(-[A-Za-z0-9]{2,8})*$")
DEFAULT_SPONSORBLOCK = ("sponsor", "selfpromo", "interaction", "intro", "outro", "preview")


def check_request(url, lang):
    if not re.match(r"^https?://", str(url)):
        raise Failure(f"url must be http(s): {url!r}")
    if not LANG_CODE.match(str(lang)):
        raise Failure(f"lang must be a language code: {lang!r}")


def fetch(url, lang, wdir, sponsorblock=DEFAULT_SPONSORBLOCK):
    """Downloads the audio, captions, thumbnail and info.json into wdir; returns the parsed
    info.json and the m4a's path. A wdir from an interrupted run resumes the download."""
    # SponsorBlock in mark mode: the segments land in info.json, and cuts.py cuts the audio
    # and shifts the cues together, since yt-dlp's remove mode doesn't shift subtitles.
    marks = ["--sponsorblock-mark", ",".join(sponsorblock)] if sponsorblock else []
    # <lang>-orig is the untranslated auto-caption track. Nothing wider: the patterns match
    # without case, so en-[A-Z]{2} would take every auto-translation too, and YouTube answers
    # a burst of caption requests with 429.
    # node runs yt-dlp-ejs, the solver for YouTube's JS challenges.
    run(
        [
            "yt-dlp", "-f", "ba[ext=m4a]", "--embed-metadata", "--embed-thumbnail",
            "--write-thumbnail", "--convert-thumbnails", "jpg", "--write-info-json",
            "--write-subs", "--write-auto-subs", "--sub-lang", f"{lang},{lang}-orig",
            "--sub-format", "vtt", *marks, "--continue", "--no-playlist", "--no-progress",
            "--no-cache-dir", "--js-runtimes", "node",
            "-P", str(wdir), "-o", "%(id)s.%(ext)s", url,
        ],
        "yt-dlp",
    )  # fmt: skip
    infos = list(wdir.glob("*.info.json"))
    if len(infos) != 1:
        raise Failure(f"expected one info.json in {wdir}, found {len(infos)}")
    info = json.loads(infos[0].read_text())
    audio = wdir / f"{info['id']}.m4a"
    if not audio.exists():
        raise Failure(f"yt-dlp wrote no {audio.name}")
    return info, audio


def stt(audio, lang, wdir):
    """The speech-to-text hook for a video without captions: transcribe the audio into
    <id>.stt.vtt beside it and return that path. Not implemented yet."""
    raise NoCaptions("no captions")


def pick_captions(info, audio, lang, wdir, stt=stt):
    """The VTT to build from, its source and its language: uploaded captions first, then the
    untranslated auto-captions, then any other auto track, then stt(audio, lang, wdir)."""
    vid = info["id"]
    tracks = {p.name[len(vid) + 1 : -len(".vtt")]: p for p in wdir.glob(f"{vid}.*.vtt")}
    tracks.pop("stt", None)
    uploaded = info.get("subtitles") or {}
    ranked = sorted(tracks, key=lambda k: (k not in uploaded, k != f"{lang}-orig", k != lang, k))
    if ranked:
        key = ranked[0]
        source = "uploaded" if key in uploaded else "auto"
        return tracks[key], source, key.removesuffix("-orig")
    return stt(audio, lang, wdir), "stt", lang
