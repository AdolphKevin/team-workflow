#!/usr/bin/env python3
"""Build the public source plugin ZIP; does not install or publish."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = args.output.resolve()
    if output.is_relative_to(root):
        parser.error('Archive must be outside the plugin directory')
    if output.exists():
        parser.error('Archive exists; choose a new path')
    manifest = json.loads((root / 'plugin.json').read_text())
    files = [root / name for name in ('plugin.json', '.claude-plugin/plugin.json', '.claude-plugin/marketplace.json',
                                      'README.md', 'LICENSE', 'VERSION')]
    for name in ('skills', 'assets', 'licenses', 'docs', 'upstream'):
        files.extend(p for p in (root / name).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc')
    if any(p.is_symlink() for p in files):
        parser.error('Do not package symlinks')
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(set(files)):
            archive.write(path, str(Path(manifest['name']) / path.relative_to(root)))
    print(json.dumps({'path': str(output), 'version': manifest['version'], 'files': len(set(files)),
                      'sha256': hashlib.sha256(output.read_bytes()).hexdigest()}, indent=2))


if __name__ == '__main__':
    main()
