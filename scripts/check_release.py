#!/usr/bin/env python3
"""Offline release checks, including byte-for-byte upstream reconstruction."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(root=ROOT):
    manifest = json.loads((root / 'plugin.json').read_text())
    version = (root / 'VERSION').read_text().strip()
    assert manifest['name'] == 'team-workflow' and manifest['version'] == version
    assert version == '0.9.0-dev'
    sys.path.insert(0, str(root / 'skills/team-knowledge/scripts'))
    from tw_runtime import VERSION, install
    assert VERSION == version
    sys.path.insert(0, str(root / 'skills/team-knowledge/scripts/tw_runtime/team'))
    import common
    assert common.VERSION == VERSION
    from tw_runtime.project import config_problems
    template = json.loads((root / 'skills/team-workflow/templates/config.json').read_text())
    assert not config_problems(template)
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
    for required in ('LICENSE', 'licenses/MATT-MIT.txt', 'README.md'):
        assert (root / required).is_file(), required
    lock = json.loads((root / 'upstream/matt.lock.json').read_text())
    assert len(lock['files']) == 41 and len({Path(row['path']).parts[1] for row in lock['files']}) == 15
    # The lock must say what it is: an unreleased main snapshot names its commit, a release names its tag commit.
    if lock['version'].startswith('main@'):
        assert lock['commit'].startswith(lock['version'][5:]) and len(lock['version']) >= 12, 'MATT lock version must name its commit'
    else:
        assert lock.get('tag_commit') == lock['commit'], 'MATT lock release version needs tag_commit equal to commit'
    with tempfile.TemporaryDirectory(prefix='upstream-check-') as directory:
        temp = Path(directory)
        for row in lock['files']:
            path = root / row['path']
            assert path.resolve().is_relative_to(root.resolve()) and not path.is_symlink(), row['path']
            assert sha(path) == row['sha256'], f"local MATT file differs from reviewed patch: {row['path']}"
            dest = temp / row['path']
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, dest)
        result = subprocess.run(['git', 'apply', '--no-index', '--reverse', str(root / 'upstream/matt.patch')],
                                cwd=temp, text=True, capture_output=True,
                                env={**os.environ, 'GIT_CEILING_DIRECTORIES': str(temp.parent)})
        assert result.returncode == 0, result.stderr
        for row in lock['files']:
            assert sha(temp / row['path']) == row['upstream_sha256'], row['source']
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
        for pattern in (r'/' + r'Users/[^/\s]+/', r'/private/' + 'var/folders/', r'gh[pousr]_[A-Za-z0-9]{30,}',
                        r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'):
            assert not re.search(pattern, text), f'private material in {path.relative_to(root)}'
        if path.suffix == '.md':
            for link in re.findall(r'\]\(([^)]+)\)', re.sub(r'```.*?```', '', text, flags=re.DOTALL)):
                if '://' in link or link.startswith(('#', '<')):
                    continue
                target = link.split('#')[0]
                assert (path.parent / target).is_file(), f'broken file link: {path.relative_to(root)} -> {link}'
    assert not (root / 'skills/cs').exists(), 'Legacy CS runtime must not be shipped'
    assert not (root / 'skills/team-workflow/scripts').exists(), 'Team runtime must live in tw_runtime/team'
    assert (root / 'skills/team-knowledge/scripts/tw_runtime/team/workflow.py').is_file()
    shipped = json.loads((root / 'skills/team-workflow/MANIFEST.json').read_text())
    assert shipped == install.manifest(root / 'skills/team-workflow'), \
        'skills/team-workflow/MANIFEST.json is stale; run python3 scripts/package.py --manifest'
    budgets = knowledge_checks(root)
    team_budget = team_checks(root)
    names = lint_names(root)
    imported = import_scripts(root)
    return {'ok': True, 'version': version, 'upstream_files': len(lock['files']), 'source_files_checked': len(files),
            'undefined_name_lint': {'files': names['files'], 'lint_version': names['lint_version']},
            'scripts_imported': imported, 'skill_manifest_files': len(shipped['files']), 'knowledge': budgets,
            'team': team_budget}


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


TEAM_BUDGETS = {'SKILL.md': 3000, 'references/matt-integration.md': 3000}


def team_checks(root):
    """team-workflow entry and the method rules every task reads first stay within their budgets."""
    skill = root / 'skills/team-workflow'
    sizes = {name: len((skill / name).read_text(encoding='utf-8')) for name in TEAM_BUDGETS}
    for name, limit in TEAM_BUDGETS.items():
        assert sizes[name] <= limit, f'skills/team-workflow/{name} has {sizes[name]} characters, budget {limit}'
    first = sum(sizes.values())
    assert first <= 8000, f'team-workflow first-read chain has {first} characters, budget 8000'
    return {'characters': sizes, 'first_read': first}


def lint_names(root):
    spec = importlib.util.spec_from_file_location('lint_undefined_names', root / 'scripts/lint_undefined_names.py')
    lint = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lint)
    result = lint.check([root / 'scripts', root / 'skills', root / 'tests'], root=root.resolve())
    assert result['ok'], 'undefined names: ' + json.dumps(result['findings'], ensure_ascii=False)
    return result


def import_scripts(root):
    """Import every tool module in a fresh interpreter so import-time errors fail the release."""
    code = 'import importlib, sys\nsys.path[:0] = sys.argv[1:3]\nfor name in sys.argv[3:]: importlib.import_module(name)'
    count = 0
    for scripts, modules in ((root / 'skills/team-knowledge/scripts/tw_runtime/team', sorted(p.stem for p in (root / 'skills/team-knowledge/scripts/tw_runtime/team').glob('*.py'))),
                             (root / 'skills/team-knowledge/scripts', ['tw_runtime.' + p.stem for p in sorted((root / 'skills/team-knowledge/scripts/tw_runtime').glob('*.py')) if p.stem != '__init__'])):
        result = subprocess.run([sys.executable, '-I', '-c', code, str(scripts),
                                 str(root / 'skills/team-knowledge/scripts'), *modules], text=True, capture_output=True)
        assert result.returncode == 0, result.stderr
        count += len(modules)
    return count


if __name__ == '__main__':
    print(json.dumps(check(), indent=2))
