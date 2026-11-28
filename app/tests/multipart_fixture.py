"""Write a tiny single-ZIP pack, its equivalent release parts, and both catalogs to a new directory."""
import argparse
import hashlib
import io
import json
import zipfile
from pathlib import Path

PART_BYTES = 128
HOST = 'https://downloads.lastbook.org'


def write_fixture(folder):
    folder.mkdir()
    members = {'library-data/catalog.json': b'{"records": []}', 'pack.json': b'{"name": "small"}',
               'library-data/example.txt': b'A small offline library.\n'}
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, 'w') as z:
        for name, data in members.items():
            info = zipfile.ZipInfo('LastbookData/' + name, date_time=(2020, 1, 1, 0, 0, 0))
            info.create_system = 3
            z.writestr(info, data)
    raw = archive.getvalue()

    def put(name, data):
        (folder / name).write_bytes(data)
        return {'name': name, 'url': f'{HOST}/{name}', 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}

    file = put('Lastbook-Small.zip', raw)
    pack = {'id': 'small', 'available': True, 'installed_bytes': sum(map(len, members.values())),
            'files': [{**file, 'kind': 'zip'}]}
    catalog = {'version': 1, 'published': '2026-01-01', 'packs': [pack]}
    (folder / 'single.json').write_text(json.dumps(catalog, indent=2) + '\n', encoding='utf-8')
    pack['parts'] = [put(f'pack-{file["sha256"]}-{PART_BYTES}-{i:05d}.bin', raw[start:start + PART_BYTES])
                     for i, start in enumerate(range(0, len(raw), PART_BYTES), 1)]
    (folder / 'parts.json').write_text(json.dumps(catalog, indent=2) + '\n', encoding='utf-8')
    return catalog


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    write_fixture(parser.parse_args().output)
