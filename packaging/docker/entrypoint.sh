#!/bin/sh
set -e
mkdir -p "$XDG_CONFIG_HOME"

# The assistant only talks to a loopback model server. With MODEL_UPSTREAM=ollama:11434 and
# SURVIVAL_MODEL_BASE=http://127.0.0.1:11434, forward that port on loopback inside the container to the real one.
# SURVIVAL_MODEL_BASE is checked by the assistant's own loopback_base(), so what is forwarded is what it will call; a
# setting it would not use stops the container here, before setup, with the reason.
if [ -n "$MODEL_UPSTREAM" ]; then
    listen=$(cd /opt/lastbook && python3 -c '
import os, re, sys
eg = " (e.g. MODEL_UPSTREAM=ollama:11434 and SURVIVAL_MODEL_BASE=http://127.0.0.1:11434)"
up, base = os.environ["MODEL_UPSTREAM"], os.environ.pop("SURVIVAL_MODEL_BASE", "")
m = re.fullmatch(r"([A-Za-z0-9._-]+|\[[0-9A-Fa-f:.]+\]):(\d+)", up)
if not m or not 0 < int(m[2]) < 65536:
    sys.exit("MODEL_UPSTREAM=%r is not host:port, with no http://" % up + eg)
if not base:
    sys.exit("MODEL_UPSTREAM is set but SURVIVAL_MODEL_BASE is not: set the loopback address to forward" + eg)
from assistant import loopback_base
try:
    host, port = loopback_base(base)[len("http://"):].rsplit(":", 1)
except ValueError:
    host = port = None
if not port or not 0 < int(port) < 65536:
    sys.exit("SURVIVAL_MODEL_BASE=%r is not an address the assistant uses: http://127.0.0.1:PORT, "
             "http://localhost:PORT or http://[::1]:PORT, with no path (it adds /v1 itself)" % base + eg)
print("TCP6-LISTEN:%s,bind=[::1]" % port if host == "[::1]" else "TCP4-LISTEN:%s,bind=127.0.0.1" % port)
') || exit 1
    socat "${listen},fork,reuseaddr" "TCP:${MODEL_UPSTREAM}" &
    sleep 1
    if ! kill -0 $! 2>/dev/null; then
        echo "the model forwarder ($listen) did not start; see the socat error above" >&2
        exit 1
    fi
fi

# server.py needs a library to start. On first run (or after an interrupted one) build it with the app's own
# setup code; a stopped download picks up where it was.
if [ ! -f "$LASTBOOK_DATA/library-data/catalog.json" ]; then
    python3 /opt/lastbook/packaging/docker/headless_setup.py install
fi

# Run from source (not frozen like the desktop apps), engine/library.py imports library-data/tools/vendor-py312
# and executes library-data/tools/remote_storage.py when present. Packs exclude tools/ (pack-spec.json), so
# one that has it is not a published pack: refuse to run code that arrived with the data.
if [ -e "$LASTBOOK_DATA/library-data/tools" ]; then
    echo "refusing to start: $LASTBOOK_DATA/library-data/tools exists (code in the library folder)" >&2
    exit 1
fi

mkdir -p "$LASTBOOK_DATA/derived"
# A fixed LAN key, so links holding it (a dashboard tile) survive a reinstall. server.py only makes one if absent.
if [ -n "$LASTBOOK_LAN_KEY" ] && [ ! -s "$LASTBOOK_DATA/derived/lan-key" ]; then
    (umask 077; printf '%s' "$LASTBOOK_LAN_KEY" > "$LASTBOOK_DATA/derived/lan-key")
fi
cd /opt/lastbook
exec python3 server.py --lan --port "${LASTBOOK_PORT:-8890}" "$@"
