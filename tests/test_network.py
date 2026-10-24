"""Against YouTube itself: run with `pytest -m network`. Deselected by default, since it needs
the network and node, and YouTube's answers change."""

import zipfile

import pytest

from yt_to_audiobook import convert

pytestmark = pytest.mark.network

# "Me at the zoo": 19 seconds, uploaded English captions, no SponsorBlock segments.
URL = "https://www.youtube.com/watch?v=jNQXAC9IVRw"


def test_convert_a_real_video(tmp_path):
    out = tmp_path / "zoo.epub"
    report = convert(URL, out, workdir=tmp_path / "work")
    assert report["video_id"] == "jNQXAC9IVRw"
    assert report["cues"] > 0 and report["caption_source"] in ("uploaded", "auto")
    with zipfile.ZipFile(out) as z:
        assert z.testzip() is None
