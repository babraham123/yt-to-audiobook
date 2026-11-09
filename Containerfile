# The yt-to-audiobook CLI with its pinned libraries. requirements.txt pins them by hash and is
# what Renovate updates; the package itself is installed without dependencies on top.
FROM docker.io/library/python:3.15-alpine@sha256:a0f2e268f2ce8f3709611a90054ec6a8ae31f6251f5896b8648b9bb99835e30a
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
RUN pip install --no-cache-dir --no-deps . && pip uninstall -y pip && rm -rf /src
# The batch runner: one request from an inbox per run, as an alternative entrypoint.
COPY batch/yt_to_audiobook_batch.py /opt/
WORKDIR /
ENTRYPOINT ["yt-to-audiobook"]
