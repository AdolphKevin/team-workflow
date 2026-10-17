"""Explicit business declarations for the arithmetic fixture's complete public journey."""
import copy


def coverage(level='journey'):
    return {'level': level, 'entrypoints': ['app.add'], 'environment': 'isolated-test',
            'substitutes': [], 'isolation': 'isolated', 'isolation_evidence': []}


def sources():
    return [{'ref': 'SOP arithmetic#addition', 'version': '2026-01-01', 'confirmed_by': 'carol'}]


def scenario_reader(path):
    """按仓内路径读取 tests/fixtures 中的合成场景，与当前目录独立。"""
    from pathlib import Path
    import scenario_files
    profile = {'acceptance_entries': {'cli': {'surface': 'cli', 'operate': '运行合成命令',
               'observe': ['输出'], 'evidence': ['原始输出'], 'isolation': '临时目录'}}, 'checks': {}}
    return scenario_files.read(Path(__file__).resolve().parents[1] / path, profile)


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
        from pathlib import Path
        from common import sha
        row['data'].setdefault('scenarios', [{'path': 'tests/fixtures/scenarios.json',
            'sha256': sha(Path(__file__).parent / 'fixtures/scenarios.json'), 'nodes': ['SYNTH-01']}])
        row['data'].setdefault('sources', sources())
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
    from tw_runtime import gitutil
    from design_files import scenario_reader as file_reader
    root = gitutil.toplevel(path.resolve().parent)
    reader = file_reader(root) if root else scenario_reader
    assert designs.load(raw, scenario_reader=reader) == value, 'Markdown fixture must preserve the existing plan'
    assert designs.fingerprints(designs.load(raw, scenario_reader=reader)) == designs.fingerprints(value)
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
    path = source / 'design.md'
    import shutil
    target = source / 'tests/fixtures/scenarios.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(__import__('pathlib').Path(__file__).parent / 'fixtures/scenarios.json', target)
    write(source / '.tw/config.json', {'acceptance_entries': {'cli': {'surface': 'cli', 'operate': '运行命令', 'observe': ['输出'], 'evidence': ['输出'], 'isolation': '临时目录'}}, 'checks': {}})
    write_design(path, value)
    git('add', 'design.md', 'tests/fixtures/scenarios.json', '.tw/config.json')
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


def submit_scenarios(root, task, report=None):
    """合成项目的验收前置：从命令入口登记独立执行的合成场景结果。"""
    import contextlib
    from datetime import datetime, timezone
    import io
    import json
    import workflow
    import materials
    from unittest.mock import patch
    from tw_runtime.team import platform_script
    from common import write

    def command(*args):
        out = io.StringIO()
        # 平台传输建立前的本地准备覆盖开工、场景登记及其流程状态读取。
        isolation = patch.object(platform_script, 'is_task', return_value=False) if report is not None else contextlib.nullcontext()
        with isolation, contextlib.redirect_stdout(out):
            code = workflow.main([*args, '--root', str(root)])
        value = json.loads(out.getvalue())
        assert code == 0, value
        return value

    if report is not None:
        path = root / '.tw/local/scenario-fixture-task.json'
        write(path, written_task(task))
        args = ['start', '--task', str(path), '--design', report['design']]
        for name in report.get('approvals', []):
            args += ['--approval', name]
        command(*args)
    pending = command('scenarios', 'pending', '--task', task['id'])
    if pending['pending']:
        directory = root / '.tw/local/scenario-fixture'
        directory.mkdir(parents=True, exist_ok=True)
        (directory / 'evidence.txt').write_text('合成项目：从 app.add 的公开入口核对 1+2=3。\n')
        rows = [{'scenario': row['id'], 'status': 'pass', 'actual': '合成算术入口结果为 3，未写入额外数据',
                 'executor': 'carol', 'executed_at': datetime.now(timezone.utc).isoformat(), 'evidence': ['evidence.txt']}
                for row in pending['pending']]
        path = directory / 'results.jsonl'
        path.write_text(''.join(json.dumps(row) + '\n' for row in rows))
        command('scenarios', 'submit', '--task', task['id'], '--results', str(path))
    return materials.load(root, task['id'])['scenario_rounds']


def observations(root, ref, check='unit', cases=()):
    import materials
    # 此处只读取已由 submit 登记的轮次。
    from common import read
    from pathlib import Path
    try:
        record = read(Path(root) / ref['path'])
    except (ValueError, OSError):
        record = {}
    task_id = next(iter(record.get('task_digests', {})), 'TASK-fixture')
    group = materials.load(root, task_id) or {}
    return [observation(ref, check, cases), {'kind': 'scenarios', 'rounds': group.get('scenario_rounds', [])}]
