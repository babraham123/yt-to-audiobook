import pytest

from yt_to_audiobook import Failure, NoCaptions
from yt_to_audiobook.fetch import caption_tracks, check_request, pick_captions


def tracks(tmp_path, *langs):
    for lang in langs:
        (tmp_path / f"X.{lang}.vtt").write_text("WEBVTT\n")


def pick(tmp_path, info, lang="en", **kw):
    vtt, source, got_lang = pick_captions({"id": "X", **info}, None, lang, tmp_path, **kw)
    return vtt.name, source, got_lang


def test_uploaded_captions_come_first(tmp_path):
    tracks(tmp_path, "en", "en-orig")
    assert pick(tmp_path, {"subtitles": {"en": []}}) == ("X.en.vtt", "uploaded", "en")


def test_untranslated_auto_captions_beat_the_translated_auto_track(tmp_path):
    tracks(tmp_path, "en", "en-orig")
    info = {"automatic_captions": {"en": [], "en-orig": []}}
    assert pick(tmp_path, info) == ("X.en-orig.vtt", "auto", "en")


def test_a_translated_auto_track_alone_is_no_captions(tmp_path):
    tracks(tmp_path, "de")
    with pytest.raises(NoCaptions):
        pick(tmp_path, {"automatic_captions": {"de": []}}, lang="de")


@pytest.mark.parametrize("info, track, source", [
    ({"subtitles": {"pt-BR": []}}, "pt-BR", "uploaded"),
    ({"automatic_captions": {"pt-BR-orig": []}}, "pt-BR-orig", "auto"),
])  # fmt: skip
def test_a_track_is_found_under_its_key_in_info(tmp_path, info, track, source):
    tracks(tmp_path, track)
    assert pick(tmp_path, info, lang="pt-br") == (f"X.{track}.vtt", source, "pt-br")


@pytest.mark.parametrize("info, lang, found", [
    ({}, "en", (None, None)),
    ({"automatic_captions": {"en": [], "en-orig": []}}, "en", (None, "en-orig")),
    ({"automatic_captions": {"en": [], "de-orig": []}}, "en", (None, None)),
    ({"subtitles": {"en": []}}, "en", ("en", None)),
    ({"subtitles": {"en": []}, "automatic_captions": {"en-orig": []}}, "en", ("en", "en-orig")),
    # Language tags ignore case; the key is info.json's own.
    ({"subtitles": {"pt-BR": []}, "automatic_captions": {"pt-BR-orig": []}}, "pt-br",
     ("pt-BR", "pt-BR-orig")),
    ({"subtitles": {"zh-Hant": []}}, "zh-hant", ("zh-Hant", None)),
])  # fmt: skip
def test_caption_tracks(info, lang, found):
    assert caption_tracks(info, lang) == found


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
