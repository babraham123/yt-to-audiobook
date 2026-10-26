# The yt-to-audiobook CLI with its pinned libraries. requirements.txt pins them by hash and is
# what Renovate updates; the package itself is installed without dependencies on top.
FROM docker.io/library/python:3.15-alpine@sha256:d44b1254cb92329418d164b22b20d86bbd3869d48e80e09e476531a409a728bb
ENV PYTHONDONTWRITEBYTECODE=1
# ffmpeg cuts and remuxes the audio; node runs yt-dlp-ejs, the solver for YouTube's JS
# challenges.
RUN apk add --no-cache ffmpeg nodejs
WORKDIR /src
COPY requirements.txt ./
RUN pip install --no-cache-dir --require-hashes -r requirements.txt
COPY pyproject.toml README.md LICENSE ./
COPY yt_to_audiobook ./yt_to_audiobook
# pip goes last: nothing installs at run time, and its vendored urllib3 and msgpack would
# fail the scan gate.
RUN pip install --no-cache-dir --no-deps . && rm -rf /src && pip uninstall -y pip
# The batch runner: one request from an inbox per run, as an alternative entrypoint.
COPY batch/yt_to_audiobook_batch.py /opt/
WORKDIR /
ENTRYPOINT ["yt-to-audiobook"]
