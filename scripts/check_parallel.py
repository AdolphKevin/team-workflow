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
sys.path.insert(0, str(WF.parent))


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
    result = json.loads(call([sys.executable, skill / 'scripts/cs_knowledge.py', '--root', root, *args]))
    if result.get('ok') is False:
        raise RuntimeError('CS operation failed: ' + str(result))
    return result


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
        write(seed / '.team-workflow.json', {'schema_version': 5, 'project': 'parallel-validation',
            'context': ['AGENTS.md'], 'knowledge': {'provider': 'cs', 'entry': '.codestable/wiki/INDEX.md'},
            'checks': {'unit': {'argv': [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-v'],
                'cwd': '.', 'timeout': 30, 'purpose': 'Check public validators', 'format': 'command',
                'required_cases': [], 'required_env': [], 'environment': {'kind': 'stateless'},
                'coverage': {'level': 'journey', 'entrypoints': ['orders.valid', 'invoices.valid'],
                'environment': 'isolated-library', 'substitutes': [], 'isolation': 'isolated', 'isolation_evidence': []}}}, 'required_checks': {'code': ['unit'], 'docs': []},
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
            task = {'schema_version': 5, 'design_id': name, 'section_ids': ['T1'], 'acceptance_scope': 'requirement', 'paths': [name + '.py'], 'id': name, 'base': setup['base'], 'goal': name + ' validation',
                'kind': 'code', 'risks': [], 'non_goals': [], 'acceptance': [{'id': 'A1', 'expectation': 'Invalid values rejected', 'checks': ['unit']}]}
            write(root / '.team-workflow/task-input.json', task)
            state = json.loads(call([sys.executable, WF, 'snapshot', '--root', root, '--task', '.team-workflow/task-input.json']))
            states.append(state['source_digest'])
        assert states[0] == states[1], 'Different local directories changed content identity'
        def develop(pair):
            name, directory = pair
            root = Path(directory)
            import knowledge, validation, designs, delivery
            from common import artifact, read
            task = read(root / '.team-workflow/task-input.json')
            profile = read(root / '.team-workflow.json')
            brief = knowledge.brief(root, task, skill, task['paths'], [])
            write(root / '.team-workflow/brief.json', brief)
            coverage = dict(profile['checks']['unit']['coverage'])
            coverage['entrypoints'] = [name + '.valid']
            design = {'schema_version': 5, 'kind': 'design', 'id': name, 'revision': 1, 'task_id': name,
                'assessment': {'complexity': 'simple', 'risks': [], 'effort': 'one function',
                    'drivers': ['Independent scalar input validation'], 'uncertainties': [], 'required_skills': ['Python']},
                'roles': {'design_owner': 'alice', 'implementation_owner': 'bob', 'acceptance_owner': 'carol'},
                'issues': [], 'sections': [
                    {'id': 'scope-global', 'type': 'global-scope', 'title': name, 'body': task['goal'], 'depends_on': [],
                     'data': {'requirement_acceptance': ['A1'], 'impact': [{'repository': 'self', 'entrypoint': name + '.valid',
                         'operations': ['validate'], 'producer': 'caller', 'consumer': 'caller', 'commit_owner': 'function', 'acceptance': ['A1']}]}},
                    {'id': 'A1', 'type': 'acceptance', 'title': 'Public input journey', 'body': task['acceptance'][0]['expectation'], 'depends_on': [],
                     'data': {'checks': ['unit'], 'scenario': {'actor': 'caller', 'initial_state': 'Fresh process',
                         'steps': ['Call valid with accepted and rejected inputs'], 'expected': 'Only positive integers accepted',
                         'negative_cases': ['Boolean, text and nonpositive values rejected'],
                         'sources': [{'ref': 'Validator SOP#positive-integers', 'version': '1', 'confirmed_by': 'carol'}]},
                         'verification': {'method': 'automatic', 'coverage': coverage, 'cases': []}}},
                    {'id': 'T1', 'type': 'task', 'title': 'Implement validator', 'body': task['goal'], 'depends_on': [],
                     'data': {'acceptance': ['A1'], 'scope': [name + '.py', 'tests', 'docs'], 'blocked_by': []}}]}
            write(root / '.team-workflow/design.json', design)
            ready = json.loads(call([sys.executable, WF, 'resume', '--root', root,
                '--task', '.team-workflow/task-input.json', '--design', '.team-workflow/design.json', '--cs-skill', skill]))
            assert ready['ok'] and ready['implementation_ready'], ready
            (root / (name + '.py')).write_text('def valid(value):\n    return isinstance(value, int) and not isinstance(value, bool) and value > 0\n')
            (root / ('tests/test_' + name + '.py')).write_text('import unittest\nfrom ' + name + ' import valid\nclass Contract(unittest.TestCase):\n    def test_boundary(self):\n        self.assertTrue(valid(1))\n        for value in (True, False, 0, -1, "1", None):\n            self.assertFalse(valid(value))\n')
            (root / 'docs').mkdir(exist_ok=True)
            (root / ('docs/' + name + '.md')).write_text('# ' + name + ' contract\n\nThe public validator accepts positive quantities and rejects other inputs.\n')
            write(root / ('.codestable/documents/' + name + '.json'), {'path': 'docs/' + name + '.md', 'title': name + ' contract', 'applies_to': [{'repository': 'self', 'path': name + '.py'}]})
            args = [sys.executable, WF, 'run', '--root', root, '--task', '.team-workflow/task-input.json', '--request-id', name + '-run']
            run_result = json.loads(call(args))
            assert run_result['ok'] and run_result == json.loads(call(args))
            run_ref = run_result['artifact']
            approval = designs.approval_draft(design, 'carol', 'Fixture reviewer accepted actual plan and code',
                code_digest=validation.source_digest(root, profile), run_refs=[run_ref])
            write(root / '.team-workflow/approval.json', approval)
            report = {'schema_version': 5, 'task_id': name, 'design': '.team-workflow/design.json',
                'approvals': ['.team-workflow/approval.json'], 'brief': '.team-workflow/brief.json',
                'runs': [run_ref['path']], 'review': '.team-workflow/review.json'}
            review = delivery.review_template(root, profile, task, report)
            review.update(reviewer='carol', knowledge_conflicts_resolved=True)
            for axis in ('standards', 'spec'):
                review[axis] = {'status': 'passed', 'summary': 'Inspected the public contract and actual test output', 'evidence': [run_ref]}
            review['acceptance'] = [{'id': 'A1', 'status': 'passed', 'summary': 'Public positive and negative cases executed',
                'evidence': [run_ref], 'observations': [{'kind': 'execution', 'run': run_ref, 'check': 'unit', 'cases': []}]}]
            write(root / report['review'], review)
            acceptance = delivery.verify(root, profile, task, report, skill, 'acceptance')
            accepted_path = root / '.team-workflow/acceptance.json'
            write(accepted_path, acceptance)
            payload = root / '.team-workflow/learn-input.json'
            learning = knowledge.completion_template(root, profile, task, skill, accepted_path)
            supplied = task_payload(name)
            learning['task'].update(supplied['task'])
            learning['items'] = supplied['items']
            write(payload, learning)
            plan = cs(skill, root, 'learn', '--file', str(payload), '--dry-run')
            applied = cs(skill, root, 'learn', '--file', str(payload), '--plan-token', plan['plan_token'])
            repeated = cs(skill, root, 'learn', '--file', str(payload), '--plan-token', plan['plan_token'])
            assert repeated['idempotent'] and applied['task_id'] == repeated['task_id']
            final_brief = knowledge.brief(root, task, skill, task['paths'], [])
            write(root / '.team-workflow/final-brief.json', final_brief)
            completion = knowledge.finish(root, profile, task, skill, applied['task_id'],
                root / '.team-workflow/brief.json', 'added', 'Verified reusable validator boundary',
                accepted_path, root / '.team-workflow/final-brief.json')
            write(root / '.team-workflow/knowledge.json', completion)
            report['knowledge'] = '.team-workflow/knowledge.json'
            assert delivery.verify(root, profile, task, report, skill)['delivery_complete']
            git(root, 'add', '.')
            git(root, 'commit', '-qm', name + ' independent task and knowledge')
            assert not git(root, 'status', '--porcelain')
            return name, applied['task_id']
        with ThreadPoolExecutor(2) as pool:
            tasks = dict(pool.map(develop, setup['clones'].items()))
        merged = merge_and_check(setup, skill, tasks)
        return {'ok': True, 'cs_runtime_sha256': hashlib.sha256((skill / 'scripts/cs_knowledge.py').read_bytes()).hexdigest(),
                'tasks': tasks, **merged, 'checks': ['different-local-paths-same-content-identity', 'concurrent-real-processes',
                'workflow-readiness-acceptance-and-knowledge', 'workflow-complete-retry', 'cs-lost-response-retry', 'independent-registrations-task-notes-and-experience',
                'git-merge-without-manual-conflict-resolution', 'both-tasks-and-knowledge-retrievable', 'shared-configuration-unchanged']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cs-skill', required=True, type=Path)
    parser.add_argument('--prepare', type=Path)
    args = parser.parse_args()
    result = prepare(args.prepare, args.cs_skill, optional_tools=False) if args.prepare else run(args.cs_skill)
    print(json.dumps(result, ensure_ascii=False, indent=2))
