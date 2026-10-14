#!/usr/bin/env python3
"""Build the public source plugin ZIP; does not install or publish."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'skills/team-workflow'
KNOWLEDGE = ROOT / 'skills/team-knowledge'


def skill_manifest():
    sys.path.insert(0, str(KNOWLEDGE / 'scripts'))
    from tw_runtime import install
    return install.manifest(SKILL)


def knowledge_manifest():
    sys.path.insert(0, str(KNOWLEDGE / 'scripts'))
    from tw_runtime import install
    return install.manifest(KNOWLEDGE)


def manifests():
    return {SKILL / 'MANIFEST.json': skill_manifest(), KNOWLEDGE / 'MANIFEST.json': knowledge_manifest()}


def write_manifest():
    written = []
    for path, data in manifests().items():
        path.write_text(json.dumps(data, indent=2, sort_keys=True) + '\n')
        written.append(path)
    return written


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--manifest', action='store_true', help='Regenerate the skills\' MANIFEST.json files only')
    args = parser.parse_args()
    root = ROOT
    if args.manifest:
        paths = write_manifest()
        print(json.dumps({'manifests': [p.relative_to(root).as_posix() for p in paths]}))
        return
    if args.output is None:
        parser.error('--output is required unless --manifest is given')
    for path, data in manifests().items():
        if json.loads(path.read_text()) != data:
            parser.error(f'{path.relative_to(root)} is stale; run scripts/package.py --manifest')
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
