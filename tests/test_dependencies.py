"""yt-dlp loads only the yt-dlp-ejs version it pins and a curl_cffi inside its range; a lock
that splits them leaves YouTube's JS challenges unsolved or its caption requests refused, which
no other offline test would notice."""

import importlib.metadata
import re
import subprocess
import sys


def test_yt_dlp_ejs_is_the_version_yt_dlp_pins():
    pinned = [
        m[1]
        for r in importlib.metadata.requires("yt-dlp")
        if "extra == 'default'" in r and (m := re.match(r"yt-dlp-ejs\s*==\s*([^;\s]+)", r))
    ]
    assert pinned == [importlib.metadata.version("yt-dlp-ejs")]


def test_yt_dlp_has_an_impersonate_target():
    out = subprocess.run(
        [sys.executable, "-m", "yt_dlp", "--list-impersonate-targets"],
        capture_output=True, text=True, check=True,
    ).stdout  # fmt: skip
    targets = [line for line in out.splitlines() if "curl_cffi" in line]
    assert targets and not all(line.endswith("(unavailable)") for line in targets), out
