# The yt-to-audiobook CLI with its pinned libraries. requirements.txt pins them by hash and is
# what Renovate updates; the package itself is installed without dependencies on top.
FROM docker.io/library/python:3.14-alpine
ENV PYTHONDONTWRITEBYTECODE=1
# ffmpeg cuts and remuxes the audio; node runs yt-dlp-ejs, the solver for YouTube's JS
# challenges.
RUN apk add --no-cache ffmpeg nodejs
WORKDIR /src
COPY requirements.txt ./
RUN pip install --no-cache-dir --require-hashes -r requirements.txt
COPY pyproject.toml README.md LICENSE ./
COPY yt_to_audiobook ./yt_to_audiobook
RUN pip install --no-cache-dir --no-deps . && rm -rf /src
WORKDIR /
ENTRYPOINT ["yt-to-audiobook"]
