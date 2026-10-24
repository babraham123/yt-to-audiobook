"""yt-to-audiobook URL OUT.epub: one video to one read-along EPUB."""

import argparse
import json
import logging
import signal
import sys

from . import DEFAULT_SPONSORBLOCK, Failure, convert, stop_child


def parse_args(argv):
    parser = argparse.ArgumentParser(
        prog="yt-to-audiobook",
        description="Turn a YouTube video into a read-along EPUB: its audio, with the "
        "SponsorBlock segments cut out, and its captions highlighted as they play.",
    )
    parser.add_argument("url", help="the video's URL")
    parser.add_argument("out", help="the EPUB to write")
    parser.add_argument("--lang", default="en", help="caption language (default: en)")
    parser.add_argument(
        "--work",
        metavar="DIR",
        help="keep downloads here; rerun with the same DIR to resume (default: a temp dir)",
    )
    parser.add_argument(
        "--report", metavar="FILE", help="write the JSON report here (default: stdout)"
    )
    parser.add_argument(
        "--sponsorblock",
        metavar="CATS",
        default=",".join(DEFAULT_SPONSORBLOCK),
        help="comma-separated SponsorBlock categories to cut, or '' for none "
        "(default: %(default)s)",
    )
    return parser.parse_args(argv)


def stop(signum, frame):
    stop_child()
    sys.exit(128 + signum)


def main(argv=None):
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    categories = [c for c in args.sponsorblock.split(",") if c]
    try:
        report = convert(args.url, args.out, args.lang, args.work, categories)
    except Failure as e:
        print(f"yt-to-audiobook: {e}", file=sys.stderr)
        return 1
    text = json.dumps(report, indent=2) + "\n"
    if args.report:
        with open(args.report, "w") as fd:
            fd.write(text)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
