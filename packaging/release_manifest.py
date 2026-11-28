#!/usr/bin/env python3
"""Builds the manifest the app carries: setup/manifest-v1.json (docs/SETUP-API.md, "The manifest").

  python3 -I -B packaging/release_manifest.py [--packs derived/release/manifest-v1.json] [--out derived/release/setup/manifest-v1.json]
                                              [--measure /path/to/the.gguf] [--small-from derived/release/1.0.0-20261104-1507]

Packs come from derived/release/manifest-v1.json, which session publish-packs writes for each verified pack. The model entry comes
from llm_local.py's constants (file, size, SHA-256, revision), so the two cannot drift. memory_bytes is llama.cpp's measure of
the model and its context (device + host bytes from lastbook-llm --measure): MEASURED_MEMORY below, or measured again with --measure.
--small-from builds the Small pack's entry from a release folder's SHA256SUMS.txt when the packs file has none (before
publish-packs has written it). Every URL must be on an allowed host (engine/setup/download.py) or the build stops.
The packaging spec bundles the output as setup/manifest-v1.json.
"""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT)]
import llm_local                                   # noqa: E402  (constants only: importing it starts nothing)
from engine.setup import download, manifest        # noqa: E402

MEASURED_MEMORY = 18_160_150_464 + 867_233_792     # Mac Studio M3 Ultra, 12 Nov 2026, --ctx 16384: device_bytes + host_bytes
BASE = 'https://downloads.lastbook.org'     # live since 12 Nov 2026; packs and maps are accepted from this host only
SMALL_SUMMARY = 'The essentials: first aid, water, food, shelter and repair, with the maps of this area.'


def model_entry(memory_bytes):
    rev = re.search(r'revision ([0-9a-f]{40})', llm_local.SOURCE).group(1)
    repo = llm_local.SOURCE.split(',')[0].strip()
    return {'id': 'gemma-4-26b-a4b', 'title': 'Gemma 4 26B A4B', 'file': llm_local.FILE,
            'url': f'https://huggingface.co/{repo}/resolve/{rev}/{llm_local.FILE}?download=true',
            'size': llm_local.SIZE, 'sha256': llm_local.SHA256, 'memory_bytes': int(memory_bytes), 'available': True}


def measure(gguf):
    runner = llm_local.runner_path()
    if not runner:
        sys.exit('no lastbook-llm runner to measure with')
    out = subprocess.run([str(runner), '--model', str(gguf), '--ctx', str(llm_local.CTX), '--threads', '8', '--measure'],
                         stdin=subprocess.DEVNULL, capture_output=True, timeout=300)
    fit = next(json.loads(l) for l in out.stdout.decode().splitlines() if l.startswith('{"ev":"fit"'))
    return fit['device_bytes'] + fit['host_bytes']


def small_from(folder):
    folder = Path(folder)
    sums = dict(reversed(l.split()) for l in (folder / 'SHA256SUMS.txt').read_text().splitlines() if l.strip())
    z = folder / 'Lastbook-Small.zip'
    with zipfile.ZipFile(z) as zf:
        installed = sum(i.file_size for i in zf.infolist())
        try:
            records = sum(json.loads(zf.read('LastbookData/pack.json')).get('counts', {}).values())
        except (KeyError, ValueError):
            records = None
    return {'id': 'small', 'title': 'Small', 'summary': SMALL_SUMMARY, 'records': records, 'installed_bytes': installed, 'available': True,
            'files': [{'name': z.name, 'url': f'{BASE}/{z.name}', 'size': z.stat().st_size, 'sha256': sums[z.name], 'kind': 'zip'}]}


def split_pack(packs, archive, destination, part_size):
    """Write immutable cache-sized objects and return the selected pack with their pins."""
    matches = [p for p in packs if len(p.get('files', [])) == 1 and p['files'][0]['name'] == archive.name]
    if len(matches) != 1:
        raise ValueError(f'{archive.name} must be the sole ZIP of one pack in --packs')
    pack = matches[0]
    source = pack['files'][0]
    if source.get('kind', 'zip') != 'zip' or not manifest.SHA.fullmatch(source['sha256']):
        raise ValueError(f'{archive.name} needs its published ZIP size and SHA-256 in --packs')
    size = source['size']
    if not 0 < part_size <= manifest.MAX_PACK_PART:
        raise ValueError('part size must be between 1 byte and 256 MiB')
    if archive.stat().st_size != size or size <= part_size:
        raise ValueError(f'{archive.name} must match the published size and be larger than one part')
    destination.mkdir(parents=True)
    try:
        files, full = [], hashlib.sha256()
        with archive.open('rb') as input_file:
            for index, offset in enumerate(range(0, size, part_size), 1):
                name = f'pack-{source["sha256"]}-{part_size}-{index:05d}.bin'
                remaining = length = min(part_size, size - offset)
                digest = hashlib.sha256()
                with (destination / name).open('xb') as output_file:
                    while remaining:
                        data = input_file.read(min(remaining, 8 * 1024 * 1024))
                        if not data:
                            raise ValueError(f'{archive.name} ended before its published size')
                        output_file.write(data)
                        full.update(data)
                        digest.update(data)
                        remaining -= len(data)
                files.append({'name': name, 'url': f'{BASE}/{name}', 'size': length, 'sha256': digest.hexdigest()})
            if input_file.read(1) or full.hexdigest() != source['sha256']:
                raise ValueError(f'{archive.name} does not match the published size and SHA-256')
    except BaseException:
        shutil.rmtree(destination)
        raise
    return {**pack, 'parts': files}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--packs', default=str(ROOT / 'derived' / 'release' / 'manifest-v1.json'))
    ap.add_argument('--out', default=str(ROOT / 'derived' / 'release' / 'setup' / 'manifest-v1.json'))
    ap.add_argument('--measure', help='a copy of the model file to measure memory_bytes from')
    ap.add_argument('--small-from', help='a release folder holding Lastbook-Small.zip and SHA256SUMS.txt')
    ap.add_argument('--split-pack', type=Path, help='split a published ZIP into cacheable objects for the bundled desktop manifest')
    ap.add_argument('--parts-dir', type=Path, help='new directory for --split-pack objects, to publish at downloads.lastbook.org')
    ap.add_argument('--part-bytes', type=int, help='bytes per part (default and maximum: 256 MiB)')
    a = ap.parse_args()
    if a.part_bytes is not None and not a.split_pack:
        ap.error('--part-bytes requires --split-pack')
    if bool(a.split_pack) != bool(a.parts_dir):
        ap.error('--split-pack and --parts-dir must be used together')
    try:
        src = json.loads(Path(a.packs).read_text(encoding='utf-8'))
    except FileNotFoundError:
        src = {'version': 1, 'packs': []}
    packs = list(src.get('packs') or [])
    if a.small_from and not any(p.get('id') == 'small' for p in packs):
        packs.insert(0, small_from(a.small_from))
    for p in packs:      # the detailed map a pack already holds ("CA", "us"), from the pack as built, when its entry does not say
        if 'map' not in p:
            try:
                p['map'] = json.loads((ROOT / 'derived' / 'packs' / p['id'] / 'pack.json').read_text(encoding='utf-8')).get('map')
            except (OSError, ValueError):
                pass
    if not packs:
        sys.exit(f'no packs: {a.packs} is missing or empty (publish-packs writes it); --small-from builds Small alone')
    out = {'version': 1, 'published': src.get('published') or time.strftime('%Y-%m-%d'), 'packs': packs, 'maps': list(src.get('maps') or []),
           'address_indexes': list(src.get('address_indexes') or []),
           'models': [model_entry(measure(a.measure) if a.measure else MEASURED_MEMORY)]}
    if manifest.validate(out, bundled=True) is None:
        bad = [f.get('url') for p in packs for f in p.get('files', []) if not download.url_allowed(f.get('url'))]
        sys.exit('the manifest does not pass engine/setup/manifest.validate' + (f'; addresses not allowed: {bad}' if bad else ''))
    if a.split_pack:
        try:
            split = split_pack(packs, a.split_pack, a.parts_dir, manifest.MAX_PACK_PART if a.part_bytes is None else a.part_bytes)
        except (OSError, ValueError) as e:
            ap.error(str(e))
        out['packs'] = [split if p['id'] == split['id'] else p for p in packs]
        if manifest.validate(out, bundled=True) is None:
            shutil.rmtree(a.parts_dir)  # split_pack created this directory for this invocation.
            sys.exit('Generated parts do not pass the bundled Setup manifest validator. Check their names, URLs, sizes and SHA-256.')
        print(f'{a.parts_dir}: {len(split["parts"])} parts for {a.split_pack.name}; publish them before shipping this manifest')
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, indent=1) + '\n', encoding='utf-8')
    print(f'{a.out}: {len(out["maps"])} maps, {len(packs)} packs ({", ".join(p["id"] + ("" if p.get("available") else " later") for p in packs)}), 1 model')


if __name__ == '__main__':
    main()
