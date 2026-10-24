import json
import sys
import threading
import time
import xml.etree.ElementTree as ET
import zipfile

import pytest
from conftest import rolling_vtt

from yt_to_audiobook import DEFAULT_SPONSORBLOCK, Failure, NoCaptions, convert, stop_child
from yt_to_audiobook.cli import main
from yt_to_audiobook.common import run


def seconds(clock):
    h, m, s = clock.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


URL = "https://www.youtube.com/watch?v=vid1"
INFO = {
    "id": "vid1",
    "title": "A talk",
    "uploader": "A channel",
    "upload_date": "20250102",
    "subtitles": {"en": [{"ext": "vtt"}]},
    "chapters": [{"start_time": 0, "title": "Start"}, {"start_time": 20, "title": "End"}],
    "sponsorblock_chapters": [
        {"start_time": 10, "end_time": 15, "category": "sponsor", "type": "skip"}
    ],
}
UPLOADED = """WEBVTT

00:00:01.000 --> 00:00:04.000
Before the sponsor.

00:00:11.000 --> 00:00:14.000
Buy the thing.

00:00:16.000 --> 00:00:19.000
After the sponsor.

00:00:21.000 --> 00:00:24.000
In the last chapter.
"""


def test_convert_cuts_the_sponsor_and_shifts_the_cues(tmp_path, fake_yt_dlp):
    args = fake_yt_dlp({"info": INFO, "seconds": 30, "vtt": {"en": UPLOADED}})
    out = tmp_path / "out" / "talk.epub"
    report = convert(URL, out, workdir=tmp_path / "work")

    assert args()[args().index("--sponsorblock-mark") + 1] == ",".join(DEFAULT_SPONSORBLOCK)
    assert report["video_id"] == "vid1" and report["title"] == "A talk"
    assert report["caption_source"] == "uploaded" and report["language"] == "en"
    assert report["cues"] == 3 and report["chapters"] == 2
    assert len(report["cuts"]) == 1 and report["cuts"][0]["categories"] == ["sponsor"]
    assert report["duration_after"] == pytest.approx(report["duration_before"] - 5, abs=0.05)
    assert not (tmp_path / "out" / ".talk.epub.tmp").exists()
    with zipfile.ZipFile(out) as z:
        text = z.read("OEBPS/text/ch001.xhtml").decode()
        smil = ET.fromstring(z.read("OEBPS/smil/ch001.smil"))
    assert "Buy the thing" not in text
    clips = [
        (seconds(a.get("clipBegin")), seconds(a.get("clipEnd")))
        for a in smil.iter("{http://www.w3.org/ns/SMIL}audio")
    ]
    # The cue after the 5 s cut plays 5 s earlier, within a frame of the snapped cut.
    assert clips == [(1.0, 4.0), (pytest.approx(11.0, abs=0.03), pytest.approx(14.0, abs=0.03))]


def test_no_sponsorblock_categories_cut_nothing(tmp_path, fake_yt_dlp):
    args = fake_yt_dlp({"info": {**INFO, "sponsorblock_chapters": []}, "seconds": 30,
                        "vtt": {"en": UPLOADED}})  # fmt: skip
    report = convert(URL, tmp_path / "a.epub", sponsorblock=())
    assert "--sponsorblock-mark" not in args()
    assert report["cuts"] == [] and report["cues"] == 4


def test_auto_captions_are_deduplicated(tmp_path, fake_yt_dlp):
    vtt = rolling_vtt([(0.5, 3.0, "one two three"), (3.01, 6.0, "four five six")])
    fake_yt_dlp({"info": {"id": "vid2"}, "seconds": 8, "vtt": {"en-orig": vtt, "en": vtt}})
    report = convert(URL, tmp_path / "a.epub")
    assert report["caption_source"] == "auto"
    assert report["caption_track"] == "vid2.en-orig.vtt"
    assert report["cues"] == 2


def test_no_captions_raises_and_writes_nothing(tmp_path, fake_yt_dlp):
    fake_yt_dlp({"info": {"id": "vid3"}, "seconds": 5})
    with pytest.raises(NoCaptions):
        convert(URL, tmp_path / "a.epub", workdir=tmp_path / "work")
    assert not (tmp_path / "a.epub").exists()
    # The work directory keeps the download for a later retry.
    assert (tmp_path / "work" / "vid3.m4a").exists()


def test_a_failed_download_is_a_failure(tmp_path, fake_yt_dlp):
    fake_yt_dlp({"fail": True})
    with pytest.raises(Failure, match="yt-dlp exited 1"):
        convert(URL, tmp_path / "a.epub")


def test_cli_writes_the_epub_and_report(tmp_path, fake_yt_dlp):
    fake_yt_dlp({"info": INFO, "seconds": 30, "vtt": {"en": UPLOADED}})
    report = tmp_path / "r.json"
    assert main([URL, str(tmp_path / "a.epub"), "--report", str(report),
                 "--sponsorblock", "sponsor"]) == 0  # fmt: skip
    assert json.loads(report.read_text())["video_id"] == "vid1"
    assert (tmp_path / "a.epub").exists()


def test_cli_reports_a_failure(tmp_path, capsys):
    assert main(["ftp://nope", str(tmp_path / "a.epub")]) == 1
    assert "url must be http(s)" in capsys.readouterr().err


def test_stop_child_ends_the_running_command():
    errors = []

    def work():
        try:
            run([sys.executable, "-c", "import time; time.sleep(30)"], "sleeper")
        except Failure as e:
            errors.append(str(e))

    thread = threading.Thread(target=work)
    started = time.monotonic()
    thread.start()
    while not errors and time.monotonic() - started < 5:
        stop_child(timeout=5)
        time.sleep(0.1)
    thread.join(10)
    assert errors and errors[0].startswith("sleeper exited")
    assert time.monotonic() - started < 10
