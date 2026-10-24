import pytest

from yt_to_audiobook import Failure, NoCaptions
from yt_to_audiobook.fetch import check_request, pick_captions


def tracks(tmp_path, *langs):
    for lang in langs:
        (tmp_path / f"X.{lang}.vtt").write_text("WEBVTT\n")


def pick(tmp_path, info, lang="en", **kw):
    vtt, source, got_lang = pick_captions({"id": "X", **info}, None, lang, tmp_path, **kw)
    return vtt.name, source, got_lang


def test_uploaded_captions_come_first(tmp_path):
    tracks(tmp_path, "en", "en-orig")
    assert pick(tmp_path, {"subtitles": {"en": []}}) == ("X.en.vtt", "uploaded", "en")


def test_untranslated_auto_captions_beat_the_plain_auto_track(tmp_path):
    tracks(tmp_path, "en", "en-orig")
    assert pick(tmp_path, {}) == ("X.en-orig.vtt", "auto", "en")


def test_any_auto_track_when_the_original_is_missing(tmp_path):
    tracks(tmp_path, "de")
    assert pick(tmp_path, {}, lang="de") == ("X.de.vtt", "auto", "de")


def test_no_track_falls_to_the_stt_hook(tmp_path):
    with pytest.raises(NoCaptions, match="no captions"):
        pick_captions({"id": "X"}, tmp_path / "X.m4a", "en", tmp_path)

    def stt(audio, lang, wdir):
        path = wdir / "X.stt.vtt"
        path.write_text("WEBVTT\n")
        return path

    assert pick(tmp_path, {}, stt=stt) == ("X.stt.vtt", "stt", "en")


def test_a_leftover_stt_track_is_not_a_caption_track(tmp_path):
    tracks(tmp_path, "stt")
    with pytest.raises(NoCaptions):
        pick_captions({"id": "X"}, None, "en", tmp_path)


@pytest.mark.parametrize("url, lang", [("ftp://x", "en"), ("https://x", "english"),
                                       ("https://x", "en_US")])  # fmt: skip
def test_bad_requests(url, lang):
    with pytest.raises(Failure):
        check_request(url, lang)


def test_good_requests():
    check_request("https://www.youtube.com/watch?v=x", "pt-BR")
    check_request("http://youtu.be/x", "zh-Hans")
