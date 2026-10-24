import pytest
from conftest import make_audio, needs_ffmpeg

from yt_to_audiobook.common import Cue
from yt_to_audiobook.cuts import Cuts, cut_audio, probe

# Skip 10-20 s and 30-36 s (two overlapping segments) of a 60 s file; the poi and the
# chapter are not cuts. A 1 ms frame keeps the arithmetic exact.
INFO = {
    "sponsorblock_chapters": [
        {"start_time": 10, "end_time": 20, "category": "sponsor", "type": "skip"},
        {"start_time": 30, "end_time": 35, "category": "intro", "type": "skip"},
        {"start_time": 33, "end_time": 36, "category": "outro", "type": "skip"},
        {"start_time": 40, "end_time": 40, "category": "poi_highlight", "type": "poi"},
        {"start_time": 45, "end_time": 50, "category": "chapter", "type": "chapter"},
    ]
}


@pytest.fixture
def cuts():
    return Cuts(INFO, 60.0, 0.001)


def test_segments_merge_and_kept_intervals(cuts):
    assert [(s, e) for s, e, _ in cuts.segments] == [(10, 20), (30, 36)]
    assert cuts.kept() == [(0.0, 10), (20, 30), (36, None)]
    assert cuts.report() == [
        {"start": 10, "end": 20, "categories": ["sponsor"]},
        {"start": 30, "end": 36, "categories": ["intro", "outro"]},
    ]


def test_shift_moves_times_by_what_was_cut_before_them(cuts):
    assert cuts.shift(5) == 5
    assert cuts.shift(15) == 10  # inside the first cut: its cut point
    assert cuts.shift(25) == 15
    assert cuts.shift(33) == 20
    assert cuts.shift(50) == pytest.approx(34)


def test_apply_drops_cues_centred_in_a_cut_and_shifts_the_rest(cuts):
    cues = [
        Cue(1, 2, "kept"),
        Cue(12, 14, "sponsor"),
        Cue(9, 11, "centred on the cut"),
        Cue(19, 22, "starts inside"),
        Cue(29, 37, "spans the second cut"),
        Cue(55, 60, "end"),
    ]
    got = [(round(c.start, 3), round(c.end, 3), c.text) for c in cuts.apply(cues)]
    assert got == [(1, 2, "kept"), (10, 12, "starts inside"), (39, 44, "end")]


def test_segments_snap_to_frames_and_clamp_to_the_audio():
    frame = 1024 / 44100
    info = {
        "sponsorblock_chapters": [
            {"start_time": 1.0, "end_time": 2.0, "type": "skip"},
            {"start_time": 9.5, "end_time": 99, "type": "skip"},
            {"start_time": 5.0, "end_time": 5.001, "type": "skip"},  # under a frame
        ]
    }
    cuts = Cuts(info, 10.0, frame)
    assert len(cuts.segments) == 2
    for start, end, _ in cuts.segments:
        assert start / frame == pytest.approx(round(start / frame))
        assert end <= 10.0 + frame


def test_no_segments_means_no_cuts():
    cuts = Cuts({}, 30.0, 0.001)
    assert cuts.segments == [] and cuts.kept() == [(0.0, None)]
    assert cuts.shift(12.5) == 12.5


@needs_ffmpeg
def test_cut_audio_removes_the_segments_in_one_stream_copy(tmp_path):
    audio = make_audio(tmp_path / "in.m4a", 12)
    duration, rate = probe(audio)
    frame = 1024 / rate
    info = {"sponsorblock_chapters": [{"start_time": 2, "end_time": 5, "type": "skip"}]}
    cuts = Cuts(info, duration, frame)
    out = tmp_path / "out.m4a"
    cut_audio(audio, cuts, out)
    after, _ = probe(out)
    removed = sum(e - s for s, e, _ in cuts.segments)
    # A stream copy cuts on packet boundaries: at most a frame either side.
    assert after == pytest.approx(duration - removed, abs=2 * frame)
