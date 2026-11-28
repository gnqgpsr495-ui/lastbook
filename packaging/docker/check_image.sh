#!/bin/bash
# Builds the image with harmless sentinel files placed where private or local files would be, saves it, and checks
# that no layer and no image metadata holds any of them, by name or by content. Run from the top of the repository:
#   bash packaging/docker/check_image.sh
# It creates only files that are not there yet, and removes exactly those when it ends. Works with Bash 3.2 (macOS):
# with set -u, Bash before 4.4 calls an empty array unbound, so arrays that can be empty expand as ${a[@]+"${a[@]}"}.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
# Only BuildKit reads Dockerfile.dockerignore; the legacy builder would copy in what it keeps out. So the image is built
# with `docker buildx build --load`, which is always BuildKit (plain `docker build` is not with a daemon older than
# Docker 23) and always lands in the local image store (with a docker-container builder it otherwise stays in the
# build cache).
docker buildx version >/dev/null 2>&1 || { echo "needs the docker buildx plugin (Docker Desktop has it)"; exit 2; }

TOKEN="lastbook-sentinel-$(od -An -N8 -tx1 /dev/urandom | tr -d ' \n')"
TAG="lastbook-image-check:$$"
WORK=$(mktemp -d)
MADE=() DIRS=()

cleanup() {
    for f in ${MADE[@]+"${MADE[@]}"}; do rm -f "$f"; done
    for ((i=${#DIRS[@]}-1; i>=0; i--)); do rmdir "${DIRS[i]}" 2>/dev/null || true; done   # only the folders made here
    rm -rf "$WORK"
    docker rmi -f "$TAG" >/dev/null 2>&1 || true
}
trap cleanup EXIT

plant() {    # plant <path>: a file holding the token, only if nothing is there
    [ -e "$1" ] && { echo "skip (exists): $1"; return; }
    local d=$(dirname "$1") new=()
    while [ "$d" != . ] && [ ! -d "$d" ]; do new=("$d" ${new[@]+"${new[@]}"}); d=$(dirname "$d"); done
    mkdir -p "$(dirname "$1")"
    DIRS+=(${new[@]+"${new[@]}"})
    printf '%s\n' "$TOKEN" > "$1"
    MADE+=("$1")
}

# Outside what the image copies: the checkout's own history and anything a person keeps beside it.
plant .env
plant .env.local
plant .git/lastbook-sentinel/file
plant library-data/catalog.json
plant LastbookData/library-data/catalog.json
plant models/lastbook-sentinel.gguf
plant derived/lastbook-sentinel/build.log
plant tools/lastbook-sentinel.py
plant settings.json
plant packaging/ship_edits.local.json
# Inside the folders the image does copy: only Dockerfile.dockerignore keeps these out.
plant engine/.env
plant engine/setup/credentials.json
plant engine/lastbook-sentinel.key
plant web/home-area.json
plant web/settings.json
plant content/__pycache__/topics.cpython-312.pyc
plant packaging/docker/.env
plant packaging/docker/secrets.txt

echo "building $TAG with ${#MADE[@]} sentinel files"
docker buildx build -q --load -f packaging/docker/Dockerfile -t "$TAG" . >/dev/null
docker save "$TAG" -o "$WORK/image.tar"
mkdir "$WORK/x" && tar -xf "$WORK/image.tar" -C "$WORK/x"

# A layer path ending in a planted file's own path, wherever the image put it (sed escapes it for grep -E).
printf '%s\n' ${MADE[@]+"${MADE[@]}"} | sed -e 's#[.[\*^$()+?{|]#\\&#g' -e 's#^#(^|.*/)#' > "$WORK/paths"
fail=0 layers=0 found_server=0
while IFS= read -r -d '' blob; do
    if tar -tf "$blob" >/dev/null 2>&1; then list() { tar -tf "$blob"; }; body() { tar -xOf "$blob"; }
    elif gzip -t "$blob" 2>/dev/null; then list() { gzip -dc "$blob" | tar -tf -; }; body() { gzip -dc "$blob" | tar -xOf -; }
    else    # image config, manifests and index: JSON, checked for the token as they are
        if grep -qa "$TOKEN" "$blob"; then echo "FOUND token in image metadata ${blob##*/}"; fail=1; fi
        continue
    fi
    layers=$((layers + 1))
    # grep -c reads to the end: grep -q would stop early, and with pipefail tar's SIGPIPE would hide a match.
    if [ "$(list | grep -cx 'opt/lastbook/server.py' || true)" != 0 ]; then found_server=1; fi
    hits=$(list | grep -xEf "$WORK/paths" || true)
    if [ -n "$hits" ]; then echo "FOUND in layer ${blob##*/}:"; echo "$hits"; fail=1; fi
    if [ "$(body | grep -ca "$TOKEN" || true)" != 0 ]; then echo "FOUND token in layer ${blob##*/}"; fail=1; fi
done < <(find "$WORK/x" -type f -print0)

# The scan must be able to see: the server is in a layer, and the path and token checks catch a planted file.
[ "$found_server" = 1 ] || { echo "check broken: opt/lastbook/server.py not found in any layer"; exit 2; }
mkdir -p "$WORK/probe/opt/lastbook/engine" && printf '%s\n' "$TOKEN" > "$WORK/probe/opt/lastbook/engine/.env"
tar -cf "$WORK/probe.tar" -C "$WORK/probe" opt
tar -tf "$WORK/probe.tar" | grep -qxEf "$WORK/paths" || { echo "check broken: a planted path was not recognised"; exit 2; }
tar -xOf "$WORK/probe.tar" | grep -qa "$TOKEN" || { echo "check broken: the token was not recognised"; exit 2; }

if [ "$fail" = 0 ]; then
    echo "OK: ${#MADE[@]} sentinel files, $layers layers and the image metadata checked; none of them is in the image"
else
    echo "FAILED: sentinel content reached the image"; exit 1
fi
