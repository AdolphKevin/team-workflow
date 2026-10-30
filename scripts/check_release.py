#!/usr/bin/env python3
"""Offline release checks for the standalone project knowledge skill."""
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]


def text_rules():
    spec = importlib.util.spec_from_file_location('release_text_rules', Path(__file__).with_name('release_text_rules.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def skill_document_checks(root=ROOT):
    return text_rules().check(root)


def markdown_links(root, path, text):
    errors = text_rules().links(root, path, text, skills_only=path.is_relative_to(root / 'skills'))[0]
    assert not errors, '; '.join(f'{e["path"]}:{e["line"]}: {e["problem"]}' for e in errors)


def check(root=ROOT):
    manifest = json.loads((root / 'plugin.json').read_text())
    version = (root / 'VERSION').read_text().strip()
    assert manifest['name'] == 'team-workflow' and manifest['version'] == version
    assert version == '1.0.1'
    sys.path.insert(0, str(root / 'skills/team-knowledge/scripts'))
    from tw_runtime import VERSION, install
    assert VERSION == version
    from tw_runtime.check import local_reference_problems
    assert {p.name for p in (root / 'skills').iterdir()} == {'team-knowledge'}, 'Only team-knowledge may be shipped'
    assert not (root / 'skills/team-knowledge/scripts/tw_runtime/team').exists()
    assert not (root / 'upstream').exists()
    assert not (root / 'licenses/MATT-MIT.txt').exists()
    catalog = json.loads((root / '.agents/plugins/marketplace.json').read_text())
    assert catalog['name'] == 'team-workflow'
    assert len(catalog['plugins']) == 1
    assert catalog['plugins'][0]['name'] == manifest['name']
    assert catalog['plugins'][0]['source'] == {'source': 'local', 'path': './'}
    claude_manifest = json.loads((root / '.claude-plugin/plugin.json').read_text())
    assert claude_manifest['name'] == manifest['name'] and claude_manifest['version'] == version
    assert claude_manifest['description'] == manifest['description']
    claude_catalog = json.loads((root / '.claude-plugin/marketplace.json').read_text())
    assert claude_catalog['name'] == 'team-workflow'
    assert len(claude_catalog['plugins']) == 1
    assert claude_catalog['plugins'][0]['name'] == manifest['name']
    assert claude_catalog['plugins'][0]['source'] == './'
    for required in ('LICENSE', 'README.md', 'CHANGELOG.md'):
        assert (root / required).is_file(), required
    files = [p for p in root.rglob('*') if p.is_file() and not any(
        name in p.relative_to(root).parts for name in ('.git', '.claude', '.codestable', '.team-workflow', '__pycache__', 'dist'))
        and not p.relative_to(root).as_posix().startswith('.tw/local/')]
    for path in files:
        assert not path.is_symlink(), f'symlink in release source: {path.name}'
        if path.suffix == '.py':
            compile(path.read_text(), path.relative_to(root).as_posix(), 'exec')
        if path.suffix not in ('.md', '.py', '.json', '.yaml', '.yml', '.patch', '.txt'):
            continue
        text = path.read_text()
        if path.is_relative_to(root / 'docs'):
            problems = local_reference_problems(text)
            assert not problems, f'{path.relative_to(root)}: ' + '; '.join(problems)
        for pattern in (r'/' + r'Users/[^/\s]+/', r'/private/' + 'var/folders/', r'gh[pousr]_[A-Za-z0-9]{30,}',
                        r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'):
            assert not re.search(pattern, text), f'private material in {path.relative_to(root)}'
        if path.suffix == '.md' and not path.is_relative_to(root / 'skills'):
            markdown_links(root, path, text)
    budgets = knowledge_checks(root)
    docs = skill_document_checks(root)
    errors = [e for row in docs for e in row['errors']]
    assert not errors, '; '.join(f'{e["path"]}:{e["line"]}: {e["problem"]}' for e in errors)
    names = lint_names(root)
    imported = import_scripts(root)
    return {'ok': True, 'version': version, 'skills': ['team-knowledge'], 'source_files_checked': len(files),
            'undefined_name_lint': {'files': names['files'], 'lint_version': names['lint_version']},
            'scripts_imported': imported, 'knowledge': budgets, 'document_checks': docs}


KNOWLEDGE_BUDGETS = {'SKILL.md': 2500, 'references/writing.md': 3000, 'references/migration.md': 3000,
                     'references/lessons-from-history.md': 1500}
FIRST_READ = ('SKILL.md', 'references/writing.md')


def knowledge_checks(root):
    """team-knowledge: manifest is current and instruction text stays within its character budgets."""
    skill = root / 'skills/team-knowledge'
    sys.path.insert(0, str(skill / 'scripts'))
    from tw_runtime import install
    shipped = json.loads((skill / 'MANIFEST.json').read_text())
    assert shipped == install.manifest(skill), \
        'skills/team-knowledge/MANIFEST.json is stale; run python3 scripts/package.py --manifest'
    sizes = {name: len((skill / name).read_text(encoding='utf-8')) for name in KNOWLEDGE_BUDGETS}
    for name, limit in KNOWLEDGE_BUDGETS.items():
        assert sizes[name] <= limit, f'skills/team-knowledge/{name} has {sizes[name]} characters, budget {limit}'
    extra = sorted(p.relative_to(skill).as_posix() for p in (skill / 'references').glob('*.md')) 
    assert set(extra) <= set(KNOWLEDGE_BUDGETS), f'new reference needs a budget: {sorted(set(extra) - set(KNOWLEDGE_BUDGETS))}'
    first = sum(sizes[name] for name in FIRST_READ)
    assert first <= 8000, f'team-knowledge first-read chain has {first} characters, budget 8000'
    return {'manifest_files': len(shipped['files']), 'characters': sizes, 'first_read': first}


def lint_names(root):
    spec = importlib.util.spec_from_file_location('lint_undefined_names', root / 'scripts/lint_undefined_names.py')
    lint = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lint)
    result = lint.check([root / 'scripts', root / 'skills'], root=root.resolve())
    assert result['ok'], 'undefined names: ' + json.dumps(result['findings'], ensure_ascii=False)
    return result


def import_scripts(root):
    """Import every tool module in a fresh interpreter so import-time errors fail the release."""
    scripts = root / 'skills/team-knowledge/scripts'
    modules = ['tw_runtime.' + p.stem for p in sorted((scripts / 'tw_runtime').glob('*.py'))
               if p.stem != '__init__']
    code = 'import importlib, sys\nsys.path.insert(0, sys.argv[1])\nfor name in sys.argv[2:]: importlib.import_module(name)'
    result = subprocess.run([sys.executable, '-I', '-B', '-c', code, str(scripts), *modules],
                            text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    return len(modules)


def write_junit(path, rows, integrity_error=None):
    import xml.etree.ElementTree as ET
    rows = [*rows, {'name': 'release-integrity', 'errors': ([{'path': 'release', 'line': 1, 'problem': integrity_error}] if integrity_error else [])}]
    suite = ET.Element('testsuite', tests=str(len(rows)), failures=str(sum(bool(r['errors']) for r in rows)), errors='0', skipped='0')
    for row in rows:
        case = ET.SubElement(suite, 'testcase', classname='SkillDocs', name=row['name'])
        if row['errors']:
            message = '\n'.join(f'{e["path"]}:{e["line"]}: {e["problem"]}' for e in row['errors'])
            ET.SubElement(case, 'failure', message=message).text = message
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(suite).write(path, encoding='utf-8', xml_declaration=True)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--junitxml', type=Path)
    args = parser.parse_args()
    rows = skill_document_checks()
    error = None
    try:
        value = check()
    except (AssertionError, OSError, ValueError) as exc:
        error = str(exc)
        value = {'ok': False, 'problem': error, 'document_checks': rows}
    if args.junitxml:
        write_junit(args.junitxml, rows, error)
    print(json.dumps(value, ensure_ascii=False, indent=2))
    return 0 if value['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
