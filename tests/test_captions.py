from conftest import rolling_vtt

from yt_to_audiobook.captions import clean_line, parse_vtt, vtt_time


def spans(cues):
    return [(round(c.start, 3), round(c.end, 3), c.text) for c in cues]


def test_rolling_auto_captions_keep_only_each_cues_new_line():
    vtt = rolling_vtt(
        [
            (0.16, 2.51, "the quick brown fox"),
            (2.52, 5.07, "jumps over the lazy dog"),
            (5.08, 7.31, "and runs away"),
        ]
    )
    # Each 10 ms repeat extends its line, and the next line's start ends it.
    assert spans(parse_vtt(vtt)) == [
        (0.16, 2.52, "the quick brown fox"),
        (2.52, 5.08, "jumps over the lazy dog"),
        (5.08, 7.32, "and runs away"),
    ]


def test_uploaded_cues_with_tags_entities_notes_and_short_stamps():
    vtt = """WEBVTT

NOTE a comment --> that looks like a timing line

1
00:01.000 --> 00:03.000
<v Ann>Hello &amp; welcome</v>

2
00:00:03.500 --> 00:00:05.000 align:start
<i>two</i>
lines
"""
    assert spans(parse_vtt(vtt)) == [(1.0, 3.0, "Hello & welcome"), (3.5, 5.0, "two lines")]


def test_overlapping_cues_end_where_the_next_begins():
    vtt = "WEBVTT\n\n00:00.000 --> 00:04.000\nfirst\n\n00:02.000 --> 00:05.000\nsecond\n"
    assert spans(parse_vtt(vtt)) == [(0.0, 2.0, "first"), (2.0, 5.0, "second")]


def test_crlf_and_empty_cues():
    vtt = "WEBVTT\r\n\r\n00:00.000 --> 00:01.000\r\n\r\n00:01.000 --> 00:02.000\r\nkept\r\n"
    assert spans(parse_vtt(vtt)) == [(1.0, 2.0, "kept")]


def test_vtt_time_and_clean_line():
    assert vtt_time("01:02:03.250") == 3723.25
    assert vtt_time("02:03.250") == 123.25
    assert clean_line("so<00:00:01.000><c> far</c>  &gt; away") == "so far > away"
