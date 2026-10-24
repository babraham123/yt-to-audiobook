"""Synthetic inputs: rolling and uploaded-style VTT, short generated audio, and a stand-in
yt-dlp that writes what a real download leaves in the work directory."""

import json
import os
import shutil
import subprocess
import sys
import textwrap

import pytest

HAVE_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
needs_ffmpeg = pytest.mark.skipif(not HAVE_FFMPEG, reason="ffmpeg and ffprobe not on PATH")


def stamp(t):
    ms = round(t * 1000)
    return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02}.{ms % 1000:03}"


def rolling_vtt(lines):
    """YouTube's auto-caption shape for [(start, end, text)]: each cue shows the previous
    line above its new one, with word timings, and a 10 ms cue between repeats the line alone.
    The first cue has a lone space where the previous line would be."""
    out = ["WEBVTT", "Kind: captions", "Language: en", ""]
    prev = " "
    for start, end, text in lines:
        first, *rest = text.split()
        step = (end - start) / (len(rest) + 1)
        timed = first + "".join(
            f"<{stamp(start + step * (i + 1))}><c> {w}</c>" for i, w in enumerate(rest)
        )
        out += [f"{stamp(start)} --> {stamp(end)} align:start position:0%", prev, timed, ""]
        out += [f"{stamp(end)} --> {stamp(end + 0.01)} align:start position:0%", text, " ", ""]
        prev = text
    return "\n".join(out) + "\n"


def make_audio(path, seconds):
    subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i",
         f"sine=frequency=440:duration={seconds}", "-c:a", "aac", "-f", "mp4", str(path)],
        check=True,
    )  # fmt: skip
    return path


def make_cover(path):
    subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i",
         "color=c=navy:s=64x36:d=1", "-frames:v", "1", str(path)],
        check=True,
    )  # fmt: skip
    return path


FAKE_YT_DLP = textwrap.dedent(
    """\
    #!{python}
    # Stands in for yt-dlp: writes the files the spec in $FAKE_YT_DLP_SPEC describes into -P.
    import json, os, subprocess, sys
    from pathlib import Path
    args = sys.argv[1:]
    wdir = Path(args[args.index("-P") + 1])
    spec = json.loads(Path(os.environ["FAKE_YT_DLP_SPEC"]).read_text())
    Path(os.environ["FAKE_YT_DLP_ARGS"]).write_text(json.dumps(args))
    if spec.get("fail"):
        sys.exit(1)
    info = spec["info"]
    vid = info["id"]
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i",
                    "sine=duration=%s" % spec["seconds"], "-c:a", "aac", "-f", "mp4",
                    str(wdir / (vid + ".m4a"))], check=True)
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i",
                    "color=c=navy:s=64x36:d=1", "-frames:v", "1", str(wdir / (vid + ".jpg"))],
                   check=True)
    (wdir / (vid + ".info.json")).write_text(json.dumps(info))
    for lang, text in spec.get("vtt", {{}}).items():
        (wdir / (vid + "." + lang + ".vtt")).write_text(text)
    """
)


@pytest.fixture
def fake_yt_dlp(tmp_path, monkeypatch):
    """Puts the stand-in yt-dlp first on PATH; call it with the spec to serve. Returns a
    function that reads back the arguments of the last call."""
    if not HAVE_FFMPEG:
        pytest.skip("ffmpeg and ffprobe not on PATH")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    script = bin_dir / "yt-dlp"
    script.write_text(FAKE_YT_DLP.format(python=sys.executable))
    script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    spec_path = tmp_path / "spec.json"
    args_path = tmp_path / "args.json"
    monkeypatch.setenv("FAKE_YT_DLP_SPEC", str(spec_path))
    monkeypatch.setenv("FAKE_YT_DLP_ARGS", str(args_path))

    def serve(spec):
        spec_path.write_text(json.dumps(spec))
        return lambda: json.loads(args_path.read_text())

    return serve
