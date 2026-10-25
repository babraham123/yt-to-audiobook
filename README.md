# yt-to-audiobook

yt-to-audiobook turns a YouTube video into a read-along EPUB. The book holds the video's audio
track with the sponsor reads cut out, and its captions as the text, each line highlighted while
it plays (EPUB 3 Media Overlays). [Storyteller](https://storyteller-platform.gitlab.io/storyteller/)
and other readers with Media Overlays support play it like a narrated book.

No transcoding and no alignment: the audio is YouTube's own AAC track, stream-copied, and the
highlight timings come straight from the caption cues.

## Install

Needs Python 3.10+, `ffmpeg` and `ffprobe`, and `node` (yt-dlp runs YouTube's JS challenges
through it).

```bash
pip install --require-hashes -r requirements.txt   # the pinned yt-dlp, yt-dlp-ejs and mutagen
pip install --no-deps .
```

Or build the image, which carries all of it:

```bash
podman build -t yt-to-audiobook -f Containerfile .
podman run --rm -v "$PWD:/out" yt-to-audiobook URL /out/talk.epub
```

## Usage

```text
usage: yt-to-audiobook [-h] [--lang LANG] [--work DIR] [--report FILE] [--sponsorblock CATS] url out

  url                  the video's URL
  out                  the EPUB to write
  --lang LANG          caption language (default: en)
  --work DIR           keep downloads here; rerun with the same DIR to resume (default: a temp dir)
  --report FILE        write the JSON report here (default: stdout)
  --sponsorblock CATS  comma-separated SponsorBlock categories to cut, or '' for none
                       (default: sponsor,selfpromo,interaction,intro,outro,preview)
```

It exits 1 when the video can't be converted, with the reason on stderr. SIGTERM or Ctrl-C stops
yt-dlp or ffmpeg and leaves `--work` as it is, so the same command resumes the download.

From Python:

```python
from yt_to_audiobook import NoCaptions, convert, stop_child

report = convert("https://www.youtube.com/watch?v=...", "talk.epub", lang="en", workdir="work/talk")
```

`convert()` returns the report (below) and raises `Failure`, or its subclass `NoCaptions`. A
caller's own signal handler calls `stop_child()` to end the running yt-dlp or ffmpeg.

## Batch runner

`batch/yt_to_audiobook_batch.py`, in the image as `/opt/yt_to_audiobook_batch.py`, works through
an inbox one request per run: it converts the oldest, delivers the EPUB and its report, and posts
the outcome to ntfy. Run it as the container's entrypoint and start it again (a systemd path unit
on the inbox and a timer, say) until the inbox is empty.

```bash
podman run --rm -v ./videos:/videos -v ./readalouds:/readalouds \
    --entrypoint python3 yt-to-audiobook /opt/yt_to_audiobook_batch.py
```

A request is `<slug>.json` in `inbox/`: `{"url", "title", "linkding_id", "lang"}`, of which only
`url` is required. `lang` defaults to `en`, and `linkding_id` is copied into the report. A run:

- converts the request with `work/<slug>/` as its work directory and delivers
  `<slug>.readaloud.epub` and `<slug>.report.json` to `videos/<slug>/` under the readalouds
  directory, the report first, so a reader importing the directory never sees the EPUB alone;
- on any failure, moves the request and its work directory to `failed/<slug>/`, so a path unit
  watching the inbox doesn't start it again in a loop;
- on SIGTERM or Ctrl-C, leaves the request in the inbox and `work/<slug>/` in place, and the next
  run resumes the download.

It exits 0 when the request is done or the inbox is empty, 1 when the request failed.

| Variable | Default | |
|----------|---------|---|
| `VIDEOS_DIR` | `/videos` | holds `inbox/`, `work/` and `failed/` |
| `READALOUDS_DIR` | `/readalouds` | delivers to `videos/<slug>/` under it |
| `READALOUDS_OWNER` | `0:0` | `UID:GID` the delivered files and their directories belong to |
| `NTFY_URL`, `NTFY_ALERT_ACCESS_TOKEN` | unset | the ntfy topic URL and bearer token; no post without both |

## How it works

1. **Fetch**: yt-dlp downloads the `m4a` audio track, the captions in `<lang>` and
   `<lang>-orig`, the thumbnail and `info.json`, with SponsorBlock in mark mode. Nothing wider
   than those two caption tracks: yt-dlp matches language patterns without case, so `en-[A-Z]{2}`
   would take every auto-translation too, and YouTube answers a burst of caption requests with
   HTTP 429.
2. **Captions**, in this order:
   1. captions uploaded by the channel;
   2. `<lang>-orig`, YouTube's automatic captions in the spoken language;
   3. any other automatic track in `<lang>`;
   4. the speech-to-text hook (see below).

   YouTube's automatic captions roll: each cue repeats the line before it, and a 10 ms cue
   between them repeats it again. Each cue keeps only the line it adds.
3. **SponsorBlock**: mark mode writes the segments to `info.json` instead of removing them,
   since yt-dlp's remove mode doesn't shift subtitles. The segments in the requested categories
   become cuts, snapped to AAC frames and merged where they overlap. The cuts come out of the
   audio in one `ffmpeg -c copy` pass. Cues centred in a cut are dropped, and the rest move
   earlier by the time cut before them, so the highlight stays in sync after a sponsor read. The
   default categories are `sponsor`, `selfpromo`, `interaction`, `intro`, `outro` and `preview`.
   `filler` stays in.
4. **EPUB**: one chapter per SponsorBlock chapter segment, else per chapter of the video's own,
   else every ten minutes. Each chapter has an XHTML document with a `<p>` per cue and a SMIL
   overlay with a `<par>` per cue. The package sets `dc:title` (the video's title), `dc:creator`
   (the uploader), `dc:source` (the URL), `dc:language` (the caption language),
   `dc:identifier` (`urn:youtube:<id>`) and the thumbnail as the cover.

### Report

```json
{
  "video_id": "pTn6Ewhb27k",
  "title": "Why No One Has Measured The Speed Of Light",
  "url": "https://www.youtube.com/watch?v=pTn6Ewhb27k",
  "caption_source": "uploaded",
  "caption_track": "pTn6Ewhb27k.en.vtt",
  "language": "en",
  "cues": 400,
  "chapters": 9,
  "cuts": [{"start": 0.0, "end": 5.48, "categories": ["sponsor"]}],
  "duration_before": 1144.512,
  "duration_after": 1014.294
}
```

`caption_source` is `uploaded`, `auto` or `stt`.

### Speech to text

A video with no captions at all raises `NoCaptions` from the default `stt()` hook. Pass your own
as `convert(..., stt=my_stt)`. It's called as `stt(audio, lang, workdir)` and returns the path of
a WebVTT file, by convention `<id>.stt.vtt` in the work directory; the report then says `stt`.

## Dependencies

`requirements.txt` pins yt-dlp, yt-dlp-ejs and mutagen by hash:

```bash
uv pip compile pyproject.toml --generate-hashes --universal --output-file=requirements.txt
```

yt-dlp breaks when YouTube changes, about monthly, and the fix is a newer yt-dlp. Renovate opens
that PR weekly, with yt-dlp and yt-dlp-ejs in one group: yt-dlp loads only the yt-dlp-ejs version
it pins, and `tests/test_dependencies.py` fails a lock that splits them.

## Development

```bash
pip install --require-hashes -r requirements.txt && pip install -e '.[dev]'
ruff check . && ruff format --check .
pytest              # offline; the EPUB test runs epubcheck when it's on PATH
pytest -m network   # converts a real 19-second video
```

## Used by

The [homelab](https://github.com/babraham123/homelab) builds the image from `main` with its image
updater and runs the [batch runner](#batch-runner) in it, delivering to Storyteller.
