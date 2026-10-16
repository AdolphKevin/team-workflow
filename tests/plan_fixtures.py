"""Explicit business declarations for the arithmetic fixture's complete public journey."""
import copy


def coverage(level='journey'):
    return {'level': level, 'entrypoints': ['app.add'], 'environment': 'isolated-test',
            'substitutes': [], 'isolation': 'isolated', 'isolation_evidence': []}


def sources():
    return [{'ref': 'SOP arithmetic#addition', 'version': '2026-01-01', 'confirmed_by': 'carol'}]


def plan(value):
    value['data_version'] = 1
    value.setdefault('issues', [])
    acceptance = [r for r in value['sections'] if r['type'] == 'acceptance']
    global_data = next(r['data'] for r in value['sections'] if r['id'] == 'scope-global')
    global_data.setdefault('requirement_acceptance', [r['id'] for r in acceptance])
    global_data.setdefault('impact', [{'repository': 'self', 'entrypoint': 'app.add',
        'operations': ['calculate'], 'producer': 'caller', 'consumer': 'caller',
        'commit_owner': 'arithmetic function', 'acceptance': [r['id'] for r in acceptance]}])
    for row in acceptance:
        row['data'].setdefault('scenario', {'actor': 'caller', 'initial_state': 'Fresh process',
            'steps': ['Call the public function with 1 and 2'], 'expected': row['body'],
            'negative_cases': ['Incorrect sums are rejected by the assertion'], 'sources': sources()})
        row['data'].setdefault('verification', {'method': 'automatic', 'cases': [], 'substitutes': []})
    return value


def observation(ref, check='unit', cases=()):
    return {'kind': 'execution', 'run': copy.deepcopy(ref), 'check': check, 'cases': list(cases)}


def write_design(path, value):
    """All caller-supplied plans use the production Markdown renderer."""
    from pathlib import Path
    import designs
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = designs.render(value)
    assert designs.load(raw) == value, 'Markdown fixture must preserve the existing plan'
    assert designs.fingerprints(designs.load(raw)) == designs.fingerprints(value)
    path.write_text(raw, encoding='utf-8')
    return path


def design_name(name):
    return '.tw/local/' + name + ('.md' if name in {'design', 'design-2', 'design-copy', 'bad-design', 'wrong-design'} else '.json')


def design_source(root, value):
    """A committed shared design repo keeps fixture code/run bindings independent of publication."""
    import json
    import subprocess
    from common import read, write
    source = root / '.tw/local/design-source'
    source.mkdir(parents=True, exist_ok=True)
    def git(*args):
        return subprocess.run(['git', '-C', str(source), *args], check=True, capture_output=True, text=True).stdout
    repository = 'github.com/example/design-source'
    if not (source / '.git').exists():
        git('init', '-q')
        git('config', 'user.email', 'test@example.invalid')
        git('config', 'user.name', 'Fixture')
        git('config', 'commit.gpgsign', 'false')
        git('remote', 'add', 'origin', 'https://' + repository + '.git')
    path = write_design(source / 'design.md', value)
    git('add', 'design.md')
    if subprocess.run(['git', '-C', str(source), 'diff', '--cached', '--quiet']).returncode:
        git('commit', '-qm', 'Publish Markdown design fixture')
    mappings_path = root / '.tw/local/repositories.json'
    mappings = read(mappings_path) if mappings_path.exists() else {}
    mappings.setdefault('repositories', {})[repository] = str(source)
    write(mappings_path, mappings)
    return path


def draft_design(root, url, value, **kwargs):
    import coordination
    return coordination.draft_design(url, value, path=design_source(root, value), root=root, **kwargs)


def task_body(task, parent=None, prose=''):
    import issue_draft
    return issue_draft.body({'body': prose}, written_task(task), parent)


def written_task(task):
    return {**copy.deepcopy(task), 'acceptance': [{'id': row['id']} for row in task['acceptance']]}


def task_design(task):
    """Provide the selected original for explicit execution fixtures without a prepared context."""
    sections = [{'id': 'scope-global', 'type': 'global-scope', 'title': 'Arithmetic',
                 'body': task['goal'], 'data': {}, 'depends_on': []}]
    sections += [{'id': row['id'], 'type': 'acceptance', 'title': 'Result', 'body': row['expectation'],
                  'data': {'checks': row['checks']}, 'depends_on': []} for row in task['acceptance']]
    sections += [{'id': key, 'type': 'task', 'title': 'Implement', 'body': 'Implement arithmetic',
                  'data': {'acceptance': [row['id'] for row in task['acceptance']],
                           'scope': task.get('paths') or ['.'], 'blocked_by': []}, 'depends_on': []}
                 for key in task['section_ids']]
    return plan({'data_version': 1, 'kind': 'design', 'id': task['design_id'], 'revision': 1,
                 'task_id': task.get('parent') or task['id'],
                 'assessment': {'complexity': 'medium', 'risks': task['risks'], 'effort': 'One hour',
                                'drivers': ['Arithmetic'], 'uncertainties': [], 'required_skills': []},
                 'roles': {'design_owner': 'alice', 'implementation_owner': 'bob', 'acceptance_owner': 'carol'},
                 'sections': sections, 'issues': []})
