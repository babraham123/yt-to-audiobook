# yt-to-audiobook

Turns one YouTube video into a read-along EPUB: the video's audio with the SponsorBlock segments
cut out, and its captions as the text, highlighted as they play.

## Language

### Input

**Track**:
One caption file yt-dlp downloads for a video, named by its language key: `en` (uploaded by
the channel), `en-orig` (the automatic captions in the spoken language, untranslated). YouTube's
automatic `en` is a translation and is never downloaded. Speech to text adds an `stt` track.
_Avoid_: subtitle file, transcript

**Caption source**:
Where the chosen track came from: `uploaded` by the channel, `auto` (YouTube's speech
recognition), or `stt` (the speech-to-text hook).
_Avoid_: caption type, origin

**Work directory**:
Where yt-dlp's downloads and the intermediate files live. Reusing one after an interruption
resumes the download.
_Avoid_: cache, temp dir (unless none was given)

### Text and timing

**Cue**:
One span of time and the text shown during it. From YouTube's automatic captions, a cue holds
only the line that cue adds, not the lines it repeats.
_Avoid_: caption, subtitle, line, segment

**Cut**:
One stretch of audio removed: a SponsorBlock skip segment in a requested category, snapped to
the audio's AAC frames, with overlapping segments merged. Cues centred in a cut are dropped and
the rest move earlier by the cut time before them.
_Avoid_: segment (SponsorBlock's word for what a cut is made from), skip, trim

**Chapter**:
One XHTML document and its SMIL overlay in the EPUB, taken from SponsorBlock chapter segments,
else the video's own chapters.
_Avoid_: section, part (for a titled chapter)

**Part**:
A chapter cut every ten minutes when the video has no chapters, titled by its time span.
_Avoid_: chapter (for an untitled one), segment

### Output

**Read-along EPUB**:
An EPUB 3 with Media Overlays: a `<p>` per cue, and a SMIL `<par>` per `<p>` playing that cue's
span of the one audio file.
_Avoid_: audiobook (the EPUB is both), ebook

**Report**:
The JSON that `convert()` returns and the CLI writes: video id, caption source and track, cue
and chapter counts, the cuts, and the audio's duration before and after them.
_Avoid_: log, summary, metadata

**Request**:
What a caller asks for: a URL, a caption language and the SponsorBlock categories to cut. A
queue of requests, and what happens to a failed one, belong to the caller; the batch runner's
queue is an inbox of `<slug>.json` files.
_Avoid_: job, task
