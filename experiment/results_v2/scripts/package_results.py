#!/usr/bin/env python3
"""Archive the current experiment directory and verify retained raw outputs."""
from pathlib import Path
import argparse
import hashlib
import json
import zipfile


def main():
    base = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser()
    parser.add_argument('--target', type=Path,
                        default=base/'deliverables/experiment_complete.zip')
    args = parser.parse_args()
    target = args.target.resolve()
    required = [base/'implementation', base/'results_v2',
                base/'results_v2/source/outputs']
    missing = [str(path) for path in required if not path.is_dir()]
    if missing:
        raise FileNotFoundError('Missing required directories: ' + ', '.join(missing))
    roots = [base/'implementation', base/'results_v2']
    if any(target.is_relative_to(root.resolve()) for root in roots):
        raise ValueError('Place the output ZIP outside the archived input directories.')

    files = []
    for root in roots:
        for path in sorted(root.rglob('*')):
            relative = path.relative_to(base)
            if not path.is_file() or '__pycache__' in relative.parts or path.suffix == '.pyc':
                continue
            if any(part.startswith('.') for part in relative.parts):
                continue
            if path.parent == base/'results_v2/tables' and path.suffix in ['.aux', '.log', '.out']:
                continue
            if (path.name.endswith(('contactsheet.png', 'contact_sheet.png'))
                    or path.name == 'atlas_cover.pdf'):
                continue
            files.append(path)
    source = base/'results_v2/source/outputs'
    raw_files = [path for path in files if source in path.parents]
    if not any(path.name == 'raw.csv' for path in raw_files):
        raise ValueError('No raw.csv batches found; refusing to create an empty results package.')
    for name in ['README_zh.md']:
        if (base/name).is_file():
            files.append(base/name)
    target.parent.mkdir(parents=True, exist_ok=True)
    manifest = []
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in files:
            relative = path.relative_to(base).as_posix()
            archive.write(path, 'experiment/' + relative)
            manifest.append(hashlib.sha256(path.read_bytes()).hexdigest() + '  ' + relative)
        archive.writestr('experiment/SHA256SUMS.txt', '\n'.join(manifest) + '\n')

    # Verify exactly the source files selected by the same archive filtering above.
    with zipfile.ZipFile(target) as archive:
        bad = archive.testzip()
        if bad is not None:
            raise ValueError('ZIP integrity check failed: ' + bad)
        for path in raw_files:
            name = 'experiment/' + path.relative_to(base).as_posix()
            if hashlib.sha256(archive.read(name)).digest() != hashlib.sha256(path.read_bytes()).digest():
                raise ValueError('Raw source differs in archive: ' + name)
        file_count = len(archive.namelist())
    print(json.dumps({'path': str(target), 'size_bytes': target.stat().st_size,
                      'files': file_count, 'raw_source_files_checked': len(raw_files),
                      'publication_included': False,
                      'sha256': hashlib.sha256(target.read_bytes()).hexdigest()}))


if __name__ == '__main__':
    main()
