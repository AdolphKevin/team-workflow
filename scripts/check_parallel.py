#!/usr/bin/env python3
"""Real CS + isolated Git branches: concurrent writes, retries, merge, and retrieval.

--prepare leaves an initialized pair of clones for independent Agent trials.
The default run executes deterministic process-level scenarios in a temporary root.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
WF = ROOT / 'skills/team-workflow/scripts/workflow.py'


def call(argv, cwd=None):
    result = subprocess.run([str(value) for value in argv], cwd=cwd, capture_output=True, text=True)
    if result.returncode:
        raise AssertionError(result.stdout + result.stderr)
    return result.stdout.strip()


def git(root, *args):
    return call(['git', '-C', root, *args])


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def cs(skill, root, *args):
    return json.loads(call([sys.executable, skill / 'scripts/cs_knowledge.py', '--root', root, *args]))


def task_payload(name):
    return {'task': {'title': name + ' validation', 'kind': 'task', 'status': 'completed',
        'request': 'Implement ' + name + ' validation', 'summary': 'Validated the public ' + name + ' function.',
        'result': name + ' rejects invalid values.', 'paths': [name + '.py'],
        'verification': ['python3 -m unittest discover -s tests -v'],
        'knowledge_summary': 'Register one original and one distinct implementation observation.'},
        'items': [{'title': name + ' implementation observation', 'category': 'error-handling',
            'knowledge': name + ' rejects boolean inputs before applying the numeric comparison.',
            'confidence': 'verified', 'paths': [name + '.py'],
            'evidence': [{'kind': 'implementation', 'artifact': name + '.py#valid', 'result': 'Explicit bool exclusion',
                          'supports': 'Boolean inputs cannot be treated as positive integers'}],
            'future_use': [{'change': 'Add batch validation', 'actor': 'Maintainer', 'constraint': 'Preserve bool exclusion'},
                           {'change': 'Replace the numeric adapter', 'actor': 'Maintainer', 'constraint': 'Keep the same rejection behavior'}]}]}


def prepare(parent, skill, optional_tools=True):
    parent.mkdir(parents=True, exist_ok=False)
    seed = parent / 'seed'
    seed.mkdir()
    git(seed, 'init', '-q', '-b', 'main')
    git(seed, 'config', 'user.name', 'Isolated validation')
    git(seed, 'config', 'user.email', 'validation@example.invalid')
    git(seed, 'config', 'commit.gpgsign', 'false')
    git(seed, 'remote', 'add', 'origin', 'https://github.com/example/parallel-validation.git')
    (seed / '.gitignore').write_text('.team-workflow/\n__pycache__/\n')
    (seed / 'AGENTS.md').write_text('Use the provided CS installation for project knowledge. Run python3 -m unittest discover -s tests -v.\nOriginal documents own their text. This small library has no services or external runtime dependencies.\n')
    (seed / 'README.md').write_text('# Validation library\n\nIndependent order and invoice functions use Python standard library only.\n')
    for name in ('orders', 'invoices'):
        (seed / (name + '.py')).write_text('def valid(value):\n    return value > 0\n')
    (seed / 'tests').mkdir()
    (seed / 'tests/test_baseline.py').write_text('import unittest\nimport orders, invoices\nclass Baseline(unittest.TestCase):\n    def test_positive(self):\n        self.assertTrue(orders.valid(1))\n        self.assertTrue(invoices.valid(1))\n')
    call([sys.executable, skill / 'scripts/bootstrap.py', '--root', seed])
    wiki = seed / '.codestable/wiki'
    overview = wiki / 'PROJECT.md'
    overview.write_text('# Project\n\n<!-- codestable:canonical:start -->\nTwo independent public validation functions in orders.py and invoices.py. Each accepts a value and returns a Boolean. Test via unittest. No database, transport, authentication or shared mutable state.\n<!-- codestable:canonical:end -->\n')
    summaries = {
        'requirements': 'Independent order and invoice validation; accepted inputs are determined by each task.',
        'architecture': 'Two standalone functions, no shared mutable runtime state.',
        'interfaces': 'Each module exports valid(value), returning a Boolean.',
        'data-model': 'Inputs are scalar values; no persisted entities.',
        'error-handling': 'Task requirements define invalid input behavior at each public function.',
        'transaction-boundaries': 'No storage or transactions in this library.',
        'compatibility': 'Python 3.10 or later, standard library only.',
        'performance-risks': 'Each function validates one scalar; there is no batch loop.',
        'security-boundaries': 'No network, authentication or secrets.',
        'acceptance': 'Run python3 -m unittest discover -s tests -v and inspect public behavior.',
        'decisions': 'Keep independent functions in separate modules.'}
    for category, body in summaries.items():
        (wiki / category / 'README.md').write_text('# ' + category + '\n\n<!-- codestable:canonical:start -->\n' + body + '\n<!-- codestable:canonical:end -->\n')
    write(seed / '.codestable/documents/project.json', {'path': 'README.md', 'always': True})
    cs(skill, seed, 'doctor')
    if optional_tools:
        write(seed / '.team-workflow.json', {'schema_version': 3, 'project': 'parallel-validation',
            'context': ['AGENTS.md'], 'knowledge': {'provider': 'cs', 'entry': '.codestable/wiki/INDEX.md'},
            'checks': {'unit': {'argv': ['python3', '-m', 'unittest', 'discover', '-s', 'tests', '-v'],
                'cwd': '.', 'timeout': 30, 'purpose': 'Check public validators', 'format': 'command',
                'required_cases': [], 'required_env': []}}, 'required_checks': {'code': ['unit'], 'docs': []},
            'risk_checks': {}, 'inputs': [], 'external_inputs': {'fixture': {'kind': 'file'}}, 'environment_versions': {}})
    git(seed, 'add', '.')
    git(seed, 'commit', '-qm', 'Initialized isolated knowledge and source')
    base = git(seed, 'rev-parse', 'HEAD')
    clones = {}
    for name in ('orders', 'invoices'):
        clone = parent / name
        call(['git', 'clone', '-q', '--no-hardlinks', seed, clone])
        git(clone, 'remote', 'set-url', 'origin', 'https://github.com/example/parallel-validation.git')
        git(clone, 'config', 'user.name', 'Isolated validation')
        git(clone, 'config', 'user.email', 'validation@example.invalid')
        git(clone, 'config', 'commit.gpgsign', 'false')
        git(clone, 'checkout', '-qb', 'codex/trial-' + name)
        local = parent / (name + '-resources')
        local.mkdir()
        (local / 'input.txt').write_text('identical external input\n')
        (local / 'context.md').write_text('# Shared external context\nAll fixture inputs are public and deterministic.\n')
        write(clone / '.codestable/local.json', {'repositories': {'context': str(local)}})
        if optional_tools:
            write(clone / '.team-workflow/local.json', {'inputs': {'fixture': str(local / 'input.txt')}})
        clones[name] = str(clone)
    return {'root': str(parent), 'seed': str(seed), 'base': base, 'clones': clones}


def merge_and_check(setup, skill, task_ids):
    seed = Path(setup['seed'])
    baseline = (seed / '.codestable/config.json').read_bytes()
    commits = {}
    for name, directory in setup['clones'].items():
        commits[name] = git(Path(directory), 'rev-parse', 'HEAD')
        git(seed, 'fetch', '-q', directory, 'HEAD')
        git(seed, 'merge', '--no-edit', 'FETCH_HEAD')
    assert not git(seed, 'status', '--porcelain'), 'Merged workspace is dirty'
    assert baseline == (seed / '.codestable/config.json').read_bytes(), 'Tasks changed shared configuration'
    call([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-v'], seed)
    for name, identifier in task_ids.items():
        result = cs(skill, seed, 'brief', '--task', name, '--path', name + '.py', '--format', 'json')
        assert identifier in json.dumps(result), name + ' task is not discoverable after merge'
        assert any(name in item['title'] for item in result['knowledge']), name + ' experience is not discoverable'
        document = cs(skill, seed, 'documents', 'read', '--id', name)
        assert document['ok']
    cs(skill, seed, 'doctor', '--check-current-references')
    changed = git(seed, 'diff', '--name-only', setup['base'], 'HEAD').splitlines()
    assert '.codestable/config.json' not in changed
    assert not any('INDEX.md' in path or 'TOPICS.md' in path or 'HISTORY.md' in path for path in changed)
    return {'commits': commits, 'merge_commit': git(seed, 'rev-parse', 'HEAD'), 'changed_files': changed}


def run(skill):
    with tempfile.TemporaryDirectory(prefix='workflow-parallel-') as directory:
        setup = prepare(Path(directory) / 'trial', skill)
        states = []
        for name, value in setup['clones'].items():
            root = Path(value)
            task = {'schema_version': 2, 'id': name, 'base': setup['base'], 'goal': name + ' validation',
                'kind': 'code', 'risks': [], 'non_goals': [], 'acceptance': [{'id': 'A1', 'expectation': 'Invalid values rejected', 'checks': ['unit']}]}
            write(root / '.team-workflow/task-input.json', task)
            state = json.loads(call([sys.executable, WF, 'snapshot', '--root', root, '--task', '.team-workflow/task-input.json']))
            states.append(state['workspace'])
        assert states[0] == states[1], 'Different local directories changed content identity'
        def develop(pair):
            name, directory = pair
            root = Path(directory)
            (root / (name + '.py')).write_text('def valid(value):\n    return isinstance(value, int) and not isinstance(value, bool) and value > 0\n')
            (root / ('tests/test_' + name + '.py')).write_text('import unittest\nfrom ' + name + ' import valid\nclass Contract(unittest.TestCase):\n    def test_boundary(self):\n        self.assertTrue(valid(1))\n        for value in (True, False, 0, -1, "1", None):\n            self.assertFalse(valid(value))\n')
            (root / 'docs').mkdir(exist_ok=True)
            (root / ('docs/' + name + '.md')).write_text('# ' + name + ' contract\n\nThe public validator accepts positive quantities and rejects other inputs.\n')
            write(root / ('.codestable/documents/' + name + '.json'), {'path': 'docs/' + name + '.md', 'title': name + ' contract', 'applies_to': [{'repository': 'self', 'path': name + '.py'}]})
            args = [sys.executable, WF, 'run', '--root', root, '--task', '.team-workflow/task-input.json', '--request-id', name + '-run']
            run_result = json.loads(call(args))
            assert run_result['ok'] and run_result == json.loads(call(args))
            payload = root / '.team-workflow/learn-input.json'
            write(payload, task_payload(name))
            plan = cs(skill, root, 'learn', '--file', str(payload), '--dry-run')
            applied = cs(skill, root, 'learn', '--file', str(payload), '--plan-token', plan['plan_token'])
            repeated = cs(skill, root, 'learn', '--file', str(payload), '--plan-token', plan['plan_token'])
            assert repeated['idempotent'] and applied['task_id'] == repeated['task_id']
            git(root, 'add', '.')
            git(root, 'commit', '-qm', name + ' independent task and knowledge')
            assert not git(root, 'status', '--porcelain')
            return name, applied['task_id']
        with ThreadPoolExecutor(2) as pool:
            tasks = dict(pool.map(develop, setup['clones'].items()))
        merged = merge_and_check(setup, skill, tasks)
        return {'ok': True, 'cs_runtime_sha256': hashlib.sha256((skill / 'scripts/cs_knowledge.py').read_bytes()).hexdigest(),
                'tasks': tasks, **merged, 'checks': ['different-local-paths-same-content-identity', 'concurrent-real-processes',
                'workflow-complete-retry', 'cs-lost-response-retry', 'independent-registrations-task-notes-and-experience',
                'git-merge-without-manual-conflict-resolution', 'both-tasks-and-knowledge-retrievable', 'shared-configuration-unchanged']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cs-skill', required=True, type=Path)
    parser.add_argument('--prepare', type=Path)
    args = parser.parse_args()
    result = prepare(args.prepare, args.cs_skill, optional_tools=False) if args.prepare else run(args.cs_skill)
    print(json.dumps(result, ensure_ascii=False, indent=2))
