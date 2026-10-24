"""Shared by the modules: the failures a conversion reports, the cue type, logging, and the
one child process a caller's SIGTERM handler stops."""

import logging
import subprocess
from dataclasses import dataclass

logger = logging.getLogger("yt_to_audiobook")

_child = None


class Failure(Exception):
    """A conversion that can't finish; the message says why."""


class NoCaptions(Failure):
    """The video has no usable captions, and the stt() hook has nothing to offer."""


@dataclass
class Cue:
    start: float
    end: float
    text: str


def log(msg):
    logger.info(msg)


def run(cmd, what):
    global _child
    _child = subprocess.Popen(cmd)
    try:
        rc = _child.wait()
    finally:
        _child = None
    if rc != 0:
        raise Failure(f"{what} exited {rc}")


def stop_child(timeout=60):
    """Stops the running yt-dlp or ffmpeg, if any. For a caller's signal handler: the work
    directory stays as it is, and a later convert() with it resumes the download."""
    child = _child
    if child and child.poll() is None:
        child.terminate()
        try:
            child.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            child.kill()
