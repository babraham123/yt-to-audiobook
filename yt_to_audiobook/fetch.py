"""The yt-dlp download and the choice of caption track."""

import json
import re

from .common import Failure, NoCaptions, run

LANG_CODE = re.compile(r"^[a-z]{2,3}(-[A-Za-z0-9]{2,8})*$")
DEFAULT_SPONSORBLOCK = ("sponsor", "selfpromo", "interaction", "intro", "outro", "preview")
# node runs yt-dlp-ejs, the solver for YouTube's JS challenges.
YT_DLP = ("yt-dlp", "--no-playlist", "--no-progress", "--no-cache-dir", "--js-runtimes", "node")


def check_request(url, lang):
    if not re.match(r"^https?://", str(url)):
        raise Failure(f"url must be http(s): {url!r}")
    if not LANG_CODE.match(str(lang)):
        raise Failure(f"lang must be a language code: {lang!r}")


def fetch(url, lang, wdir, sponsorblock=DEFAULT_SPONSORBLOCK):
    """Downloads the audio, thumbnail and info.json into wdir, then the caption tracks
    caption_langs() picks from it; returns the parsed info.json and the m4a's path. A wdir
    from an interrupted run resumes the download."""
    # SponsorBlock in mark mode: the segments land in info.json, and cuts.py cuts the audio
    # and shifts the cues together, since yt-dlp's remove mode doesn't shift subtitles.
    marks = ["--sponsorblock-mark", ",".join(sponsorblock)] if sponsorblock else []
    run(
        [
            *YT_DLP, "-f", "ba[ext=m4a]", "--embed-metadata", "--embed-thumbnail",
            "--write-thumbnail", "--convert-thumbnails", "jpg", "--write-info-json", *marks,
            "--continue", "-P", str(wdir), "-o", "%(id)s.%(ext)s", url,
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
    # A second extraction rather than --load-info-json: the caption URLs in a resumed
    # wdir's info.json may have expired.
    if langs := caption_langs(info, lang):
        run(
            [
                *YT_DLP, "--skip-download", "--write-subs", "--write-auto-subs",
                "--sub-lang", ",".join(langs), "--sub-format", "vtt",
                "-P", str(wdir), "-o", "%(id)s.%(ext)s", url,
            ],
            "yt-dlp",
        )  # fmt: skip
    return info, audio


def caption_langs(info, lang):
    """The tracks to download: <lang> if the channel uploaded it, and <lang>-orig, YouTube's
    automatic captions in the spoken language. Never the automatic <lang> track: it is a
    machine translation (from any of the video's speech tracks, even an English one for
    lang=en), and YouTube answers a translated track's download with 429."""
    langs = [lang] if lang in (info.get("subtitles") or {}) else []
    if f"{lang}-orig" in (info.get("automatic_captions") or {}):
        langs.append(f"{lang}-orig")
    return langs


def stt(audio, lang, wdir):
    """The speech-to-text hook for a video without captions: transcribe the audio into
    <id>.stt.vtt beside it and return that path. Not implemented yet."""
    raise NoCaptions("no captions")


def pick_captions(info, audio, lang, wdir, stt=stt):
    """The VTT to build from, its source and its language: uploaded captions first, then the
    untranslated automatic captions, then stt(audio, lang, wdir)."""
    vid = info["id"]
    uploaded = wdir / f"{vid}.{lang}.vtt"
    if lang in (info.get("subtitles") or {}) and uploaded.exists():
        return uploaded, "uploaded", lang
    auto = wdir / f"{vid}.{lang}-orig.vtt"
    if auto.exists():
        return auto, "auto", lang
    return stt(audio, lang, wdir), "stt", lang
