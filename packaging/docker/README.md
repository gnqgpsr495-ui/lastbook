# Lastbook in a container

This runs the library server version (`server.py`, see `docs/LIBRARY-SERVER.md`) in Docker, for a home server or NAS
that has room for a large library. Phones, tablets and other computers on the same network open it in a browser.
The desktop apps are unchanged; this is another way to run the same engine.

## Start it

From the top of the repository:

```bash
docker build -f packaging/docker/Dockerfile -t lastbook:local .
docker run -d --name lastbook -p 8890:8890 -v /path/to/lastbook:/data -e LASTBOOK_PACK=small lastbook:local
docker logs -f lastbook
```

Or edit `compose.example.yml` and use `docker compose`.

On the first start there is no library yet, so the container runs setup first, with no window:
`headless_setup.py install` downloads the pack named by `LASTBOOK_PACK` (`small`, `medium` or `all`) through
setup's own downloader, checks its SHA-256, checks and unpacks the zip, and switches to it, exactly as the setup screen
does. Then the server starts. Small takes minutes; All (about 388 GB) takes hours. If the container stops, the next
start carries on where the download stopped.

The disk needs room for the pack twice while it installs: the zip and the unpacked library. Mount the folder that
will hold `LastbookData`, not `LastbookData` itself: setup builds the new library beside it and switches with one
rename.

## Open it

The server runs with `--lan`. A device other than the server itself needs the access link once; after that a cookie is
enough. The key is in `/data/LastbookData/derived/lan-key`, and the link is printed in the log:

```
http://<server address>:8890/?key=<key>
```

Set `LASTBOOK_LAN_KEY` to keep the same key across reinstalls, so a saved link or bookmark keeps working.

To serve on another port, set `LASTBOOK_PORT` and publish that port (`-e LASTBOOK_PORT=9000 -p 9000:9000`). The
health check follows it.

The access key was tested with Docker's default bridge network and a published port, as in the commands above: other
devices, and the server computer itself through the published port, need the key; `docker exec` inside the container
does not. With `--network host` the server computer reaches it on loopback and so needs no key; other devices still
do.

Use the server's IP address in the link, not a host name. The server refuses any host name except `localhost`
(this is its protection against DNS rebinding), so a reverse proxy that passes its own host name will get 403.

## Chat

Chat works without a model: it finds the passages. To have it write answers, point it at an OpenAI-compatible model
server. The assistant only connects to a loopback address, so the entrypoint forwards a port on 127.0.0.1 inside the
container to the real server:

```
MODEL_UPSTREAM=ollama:11434
SURVIVAL_MODEL_BASE=http://127.0.0.1:11434
SURVIVAL_MODEL=gemma4:12b
```

`MODEL_UPSTREAM` is the model server's `host:port`, with no `http://`. `SURVIVAL_MODEL_BASE` is the address the
assistant calls, and the entrypoint forwards its port: `http://127.0.0.1:PORT`, `http://localhost:PORT` or
`http://[::1]:PORT`, with no path (the assistant adds `/v1` itself). With `MODEL_UPSTREAM` set, any other value, or no
`SURVIVAL_MODEL_BASE`, stops the container at start with the reason in `docker logs`.

The pinned local AI (Gemma 4 26B A4B, about 19 GB of memory) is off in the server version unless `LASTBOOK_LOCAL_AI=1`,
and also needs the `lastbook-llm` runner built for Linux (`packaging/llm/build_llm_linux.sh`); this image does not
include it.

## Setup from inside the container

`/api/setup/*` answers only the server's own computer, which for a container means `docker exec`:

```bash
docker exec lastbook python3 /opt/lastbook/packaging/docker/headless_setup.py status   # installed pack, and the published one
docker exec lastbook curl -s http://127.0.0.1:8890/api/setup/state
```

## A newer library

`headless_setup.py status` says `"update_available": true` when the published pack's files differ from the ones this
library was installed from. To move to it without stopping the server, build the new one beside it, then swap the
folders with the container stopped. `stage` brings the open library's state map and its address search along (or
another state's with `--map ST`), and the access key:

```bash
docker exec lastbook python3 /opt/lastbook/packaging/docker/headless_setup.py stage --into /data/next --pack all
docker stop lastbook
mv /path/to/lastbook/LastbookData /path/to/lastbook/LastbookData.old
mv /path/to/lastbook/next/LastbookData /path/to/lastbook/LastbookData
docker start lastbook        # then delete LastbookData.old
```

A newer version of Lastbook itself is a `git pull` and a rebuild.

## What goes into the image

Only the server's own files: `server.py`, `assistant.py`, `retrieval.py`, `llm_local.py`, `engine/`, `web/`, `content/`
and `packaging/docker/`, each named in its own `COPY`. `Dockerfile.dockerignore`, an allowlist beside the Dockerfile,
keeps everything else out of the build context, and keeps settings, keys, `.env` files, `web/home-area.json` and
caches out even inside those folders. To check a build:

```bash
bash packaging/docker/check_image.sh
```

It places harmless sentinel files where private or local files would be (`.git`, `.env`, a library, a model, settings,
credentials, `web/home-area.json`, `__pycache__`), builds the image, saves it, and looks through every layer and the
image metadata for them by path and by content. Then it removes the files it made.

Both the build and the check need BuildKit, the default builder since Docker 23 and in Docker Desktop. The legacy
builder ignores `Dockerfile.dockerignore`, so the Dockerfile stops it before copying anything from the repository, with
`the --mount option requires BuildKit`. On an older Docker, build with `docker buildx build --load` (or set
`DOCKER_BUILDKIT=1`) instead. The check builds with `docker buildx build --load`, so it needs the buildx plugin (Docker
Desktop has it) and stops with a message without it. It runs under Bash 3.2 (the macOS system Bash) or newer.

## Code in the library folder

Run from source, `engine/library.py` imports `library-data/tools/vendor-py312/` and runs `library-data/tools/remote_storage.py`
when they exist (the household library this grew from keeps its own tools there; the frozen apps never do this). Packs
leave `tools/` out (`derived/packs/pack-spec.json`), so the entrypoint refuses to start if a library has one: code
that arrived with downloaded data does not run.
