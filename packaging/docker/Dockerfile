# The library server version (server.py) in a container, for a home server or NAS.
# Build from the top of the repository:  docker build -f packaging/docker/Dockerfile -t lastbook .
# See packaging/docker/README.md.
FROM python:3.12-slim-bookworm

# poppler-utils: pdftotext, which engine/library.py uses for PDF text. curl: the health check, and /api/setup/*
# from `docker exec` (setup answers this computer only). socat: the loopback model forwarder in entrypoint.sh.
RUN apt-get update \
 && apt-get install -y --no-install-recommends poppler-utils curl socat ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# The same wheels as the Linux package: keyword search, no onnxruntime. The bind mount also stops the legacy builder
# here ("the --mount option requires BuildKit"), before any repository file is copied: only BuildKit reads
# Dockerfile.dockerignore, so a legacy build would copy in what that file keeps out.
RUN --mount=type=bind,source=packaging/linux/requirements_linux.txt,target=/tmp/requirements.txt \
    pip install --no-cache-dir -r /tmp/requirements.txt

# Only what the server runs, path by path (Dockerfile.dockerignore keeps the rest out of the context too): no
# .git, no local settings, no library, model or generated files. Deleting them in a later step would leave them in
# an earlier layer.
WORKDIR /opt/lastbook
COPY server.py assistant.py retrieval.py llm_local.py LICENSE THIRD_PARTY_NOTICES.md ./
COPY engine/ engine/
COPY web/ web/
COPY content/ content/
COPY packaging/docker/ packaging/docker/

# /data holds LastbookData/ and setup's work folder LastbookData.setup/ beside it. Switching to a new library is one
# rename between the two, so mount /data, not LastbookData itself.
ENV LASTBOOK_DATA=/data/LastbookData \
    XDG_CONFIG_HOME=/data/config \
    HOME=/data \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8890
# The port the entrypoint gives server.py: LASTBOOK_PORT, or 8890.
HEALTHCHECK --interval=60s --timeout=10s --start-period=24h \
    CMD curl -sf -o /dev/null "http://127.0.0.1:${LASTBOOK_PORT:-8890}/api/health" || exit 1
ENTRYPOINT ["/opt/lastbook/packaging/docker/entrypoint.sh"]
