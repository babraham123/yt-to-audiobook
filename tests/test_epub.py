import shutil
import subprocess
import xml.etree.ElementTree as ET
import zipfile

import pytest
from conftest import HAVE_FFMPEG, make_audio, make_cover

from yt_to_audiobook.common import Cue
from yt_to_audiobook.cuts import Cuts
from yt_to_audiobook.epub import build_epub, chapter_starts, chapters, clock, minutes

NS = {
    "opf": "http://www.idpf.org/2007/opf",
    "dc": "http://purl.org/dc/elements/1.1/",
    "smil": "http://www.w3.org/ns/SMIL",
    "x": "http://www.w3.org/1999/xhtml",
}


def test_clock_values():
    assert clock(0) == "0:00:00.000"
    assert clock(3725.5) == "1:02:05.500"
    assert clock(59.9996) == "0:01:00.000"
    assert minutes(65) == "1:05" and minutes(3725) == "1:02:05"


def test_chapter_starts_follow_the_videos_chapters_through_the_cuts():
    cuts = Cuts({"sponsorblock_chapters": [{"start_time": 10, "end_time": 20, "type": "skip"}]},
                60.0, 0.001)  # fmt: skip
    info = {"chapters": [{"start_time": 5, "title": "A"}, {"start_time": 25, "title": "B"}]}
    # A start before the first chapter gets an untitled one.
    assert chapter_starts(info, cuts, 50) == [(0.0, ""), (5, "A"), (15, "B")]


def test_sponsorblock_chapter_segments_win_over_the_videos_own():
    info = {
        "chapters": [{"start_time": 0, "title": "own"}],
        "sponsorblock_chapters": [{"start_time": 0, "title": "marked", "type": "chapter"}],
    }
    assert chapter_starts(info, Cuts({}, 60, 0.001), 60) == [(0, "marked")]


def test_without_chapters_a_part_every_ten_minutes():
    assert chapter_starts({}, Cuts({}, 1500, 0.001), 1500) == [(0.0, ""), (600.0, ""), (1200.0, "")]
    parts = chapters([Cue(601, 602, "x"), Cue(1199, 1201, "y")], [(0.0, ""), (600.0, "")])
    # The empty first part is dropped; an untitled part is named by its span.
    assert [(t, len(g)) for t, g in parts] == [("10:00 to 20:01", 2)]


def test_cues_go_to_the_chapter_they_start_in():
    parts = chapters([Cue(1, 2, "x"), Cue(15, 16, "y"), Cue(16, 17, "z")], [(0, "A"), (15, "B")])
    assert [(t, [c.text for c in g]) for t, g in parts] == [("A", ["x"]), ("B", ["y", "z"])]


@pytest.fixture
def media(tmp_path):
    if HAVE_FFMPEG:
        return make_audio(tmp_path / "a.m4a", 8), make_cover(tmp_path / "c.jpg")
    # Without ffmpeg the archive is still checked; epubcheck needs real media, so it skips.
    audio, cover = tmp_path / "a.m4a", tmp_path / "c.jpg"
    audio.write_bytes(b"\0" * 64)
    cover.write_bytes(b"\xff\xd8\xff\xd9")
    return audio, cover


@pytest.fixture
def epub(tmp_path, media):
    audio, cover = media
    parts = [
        ("One & two", [Cue(0.5, 2.0, "Hello <world>"), Cue(2.0, 3.25, "second")]),
        ("Three", [Cue(4.0, 6.5, "third")]),
    ]
    meta = {
        "id": "abc123",
        "title": "A <title>",
        "uploader": "Someone",
        "url": "https://www.youtube.com/watch?v=abc123",
        "upload_date": "20240131",
        "description": "about it",
    }
    path = tmp_path / "out.epub"
    build_epub(path, meta, audio, cover, parts, "en")
    return path


def test_archive_layout(epub):
    with zipfile.ZipFile(epub) as z:
        assert z.testzip() is None
        first = z.infolist()[0]
        assert first.filename == "mimetype" and first.compress_type == zipfile.ZIP_STORED
        assert not first.extra
        assert z.read("mimetype") == b"application/epub+zip"
        names = set(z.namelist())
        assert {
            "META-INF/container.xml", "OEBPS/package.opf", "OEBPS/nav.xhtml",
            "OEBPS/text/ch001.xhtml", "OEBPS/smil/ch001.smil", "OEBPS/text/ch002.xhtml",
            "OEBPS/smil/ch002.smil", "OEBPS/audio/abc123.m4a", "OEBPS/images/cover.jpg",
        } <= names  # fmt: skip
        for name in names:
            if name.endswith((".xml", ".opf", ".xhtml", ".smil")):
                ET.fromstring(z.read(name))


def test_package_metadata_and_overlays(epub):
    with zipfile.ZipFile(epub) as z:
        opf = ET.fromstring(z.read("OEBPS/package.opf"))
        smil = ET.fromstring(z.read("OEBPS/smil/ch001.smil"))
        text = ET.fromstring(z.read("OEBPS/text/ch001.xhtml"))
    md = opf.find("opf:metadata", NS)
    assert md.find("dc:identifier", NS).text == "urn:youtube:abc123"
    assert md.find("dc:title", NS).text == "A <title>"
    assert md.find("dc:creator", NS).text == "Someone"
    assert md.find("dc:source", NS).text == "https://www.youtube.com/watch?v=abc123"
    assert md.find("dc:language", NS).text == "en"
    assert md.find("dc:date", NS).text == "2024-01-31"
    durations = {
        m.get("refines"): m.text
        for m in md.findall("opf:meta", NS)
        if m.get("property") == "media:duration"
    }
    # Chapter one plays 1.5 + 1.25 s, chapter two 2.5 s; the total is their sum.
    assert durations == {None: "0:00:05.250", "#ch001-smil": "0:00:02.750",
                         "#ch002-smil": "0:00:02.500"}  # fmt: skip
    items = {i.get("id"): i for i in opf.find("opf:manifest", NS)}
    assert items["ch001"].get("media-overlay") == "ch001-smil"
    assert items["cover-image"].get("properties") == "cover-image"
    assert items["audio"].get("media-type") == "audio/mp4"

    pars = smil.findall(".//smil:par", NS)
    assert [(p.find("smil:text", NS).get("src"), p.find("smil:audio", NS).get("clipBegin"),
             p.find("smil:audio", NS).get("clipEnd")) for p in pars] == [
        ("../text/ch001.xhtml#cue00001", "0:00:00.500", "0:00:02.000"),
        ("../text/ch001.xhtml#cue00002", "0:00:02.000", "0:00:03.250"),
    ]  # fmt: skip
    paragraphs = text.findall(".//x:p", NS)
    assert [(p.get("id"), p.text) for p in paragraphs] == [
        ("cue00001", "Hello <world>"),
        ("cue00002", "second"),
    ]


@pytest.mark.skipif(not shutil.which("epubcheck"), reason="epubcheck not on PATH")
@pytest.mark.skipif(not HAVE_FFMPEG, reason="epubcheck needs real media from ffmpeg")
def test_epubcheck_passes(epub):
    result = subprocess.run(["epubcheck", str(epub)], check=False, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "0 errors / 0 warnings" in result.stdout
