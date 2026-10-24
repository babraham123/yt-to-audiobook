"""yt-dlp loads only the yt-dlp-ejs version it pins; a lock that splits them leaves YouTube's
JS challenges unsolved, which no offline test would otherwise notice."""

import importlib.metadata
import re


def test_yt_dlp_ejs_is_the_version_yt_dlp_pins():
    pinned = [
        m[1]
        for r in importlib.metadata.requires("yt-dlp")
        if "extra == 'default'" in r and (m := re.match(r"yt-dlp-ejs\s*==\s*([^;\s]+)", r))
    ]
    assert pinned == [importlib.metadata.version("yt-dlp-ejs")]
