"""Public entry points prefer bundled team modules while preserving standard-library imports."""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

import test_workflow as fixtures


class TeamImports(unittest.TestCase):
    setUp = fixtures.WorkflowCases.setUp
    git = fixtures.WorkflowCases.git

    def test_team_modules_take_priority_and_validation_uses_stdlib_platform(self):
        repository = Path(__file__).resolve().parents[1]
        team = repository / 'skills/team-knowledge/scripts/tw_runtime/team'
        external = self.root / '.tw/local/fake-site-packages'
        external.mkdir(parents=True)
        (external / 'metrics.py').write_text('raise RuntimeError("third-party metrics was selected")\n')
        bootstrap = '''import contextlib, io, json, runpy, sys, sysconfig
from pathlib import Path
entry, external, root = map(Path, sys.argv[1:])
# Reproduce a third-party package before installed packages, outside the team directory.
sys.path[:0] = [str(entry.parent), str(external)]
sys.argv = [str(entry), *(('team',) if entry.name == 'tw.py' else ()),
            'metrics', '--root', str(root), '--issue', 'TASK-fixture']
output = io.StringIO()
with contextlib.redirect_stdout(output):
    try:
        runpy.run_path(str(entry), run_name='__main__')
    except SystemExit as result:
        status = result.code
modules = {name: getattr(sys.modules.get(name), '__file__', None) for name in ('metrics', 'platform')}
validation = sys.modules.get('validation')
print(json.dumps({'status': status, 'response': output.getvalue(), 'modules': modules,
                  'validation_platform': getattr(getattr(validation, 'platform', None), '__file__', None),
                  'stdlib_platform': str(Path(sysconfig.get_path('stdlib')) / 'platform.py')}))
'''
        for entry in (team.parents[1] / 'tw.py', team / 'workflow.py'):
            with self.subTest(entry=entry.name):
                result = subprocess.run([sys.executable, '-c', bootstrap, str(entry), str(external), str(self.root)],
                                        capture_output=True, text=True, timeout=30,
                                        env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                actual = json.loads(result.stdout)
                self.assertEqual(actual['status'], 0, actual['response'])
                self.assertEqual(Path(actual['modules']['metrics']).resolve(), team / 'metrics.py')
                self.assertEqual(Path(actual['validation_platform']).resolve(), Path(actual['stdlib_platform']).resolve())
                self.assertEqual(actual['modules']['platform'], actual['validation_platform'])


if __name__ == '__main__':
    unittest.main()
