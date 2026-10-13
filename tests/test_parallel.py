"""Real processes and a local platform service exercise concurrent collaborators."""
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import copy
import http.client
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
import unittest
from urllib.request import Request, urlopen
from unittest.mock import patch

import test_workflow as fixtures
import test_continuation as continuation
from common import Invalid, LOCATIONS, digest, profile_valid, read, snapshot, write
import github_read
import handoffs
import portable
import verification


class ParallelMaterials(unittest.TestCase):
    setUp = fixtures.WorkflowCases.setUp
    git = fixtures.WorkflowCases.git
    check = fixtures.WorkflowCases.check
    fake_cs = fixtures.WorkflowCases.fake_cs
    complete = fixtures.WorkflowCases.complete
    run_check = fixtures.WorkflowCases.run_check

    def prepare(self, code='print("checked")'):
        self.profile['schema_version'] = 5
        self.task.update(schema_version=5, design_id='arithmetic', section_ids=['T1'], acceptance_scope='requirement', paths=['app.py'])
        self.check(code, environment={'kind': 'stateless'})
        write(self.root / '.team-workflow.json', self.profile)
        write(self.root / '.team-workflow/input/task.json', self.task)
        return [sys.executable, str(fixtures.SCRIPTS / 'workflow.py'), 'run', '--root', str(self.root),
                '--task', '.team-workflow/input/task.json']

    def start(self, args):
        process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
        self.addCleanup(lambda: process.poll() is None and os.killpg(process.pid, signal.SIGKILL))
        return process

    def result(self, process):
        out, error = process.communicate(timeout=15)
        self.assertFalse(error, error)
        return json.loads(out)

    def test_default_paths_and_same_request_competition(self):
        args = self.prepare('import time; time.sleep(0.4); print("checked")')
        processes = [self.start(args) for _ in range(4)]
        results = [self.result(p) for p in processes]
        self.assertTrue(all(r['ok'] for r in results), results)
        self.assertEqual(len({r['artifact']['path'] for r in results}), 4)
        for result in results:
            self.assertTrue(read(self.root / result['artifact']['path'])['source_unchanged'])
        processes = [self.start(args + ['--request-id', 'shared-request']) for _ in range(3)]
        results = [self.result(p) for p in processes]
        self.assertTrue(any(r['ok'] for r in results), results)
        self.assertTrue(all(r['ok'] or r['status'] == 'running' for r in results), results)
        self.assertEqual(len(list((self.root / '.team-workflow/tasks').glob('*/requests/shared-request/execution/run.json'))), 1)

    def test_retry_after_lost_response_preserves_files_and_rejects_changed_inputs(self):
        args = self.prepare()
        first = self.result(self.start(args + ['--request-id', 'response-lost']))
        before = {p: p.read_bytes() for p in (self.root / '.team-workflow/tasks').rglob('*') if p.is_file()}
        retry = self.result(self.start(args + ['--request-id', 'response-lost']))
        self.assertEqual(first, retry)
        self.assertEqual(before, {p: p.read_bytes() for p in (self.root / '.team-workflow/tasks').rglob('*') if p.is_file()})
        (self.root / 'app.py').write_text('def add(a,b): return 0\n')
        changed = self.result(self.start(args + ['--request-id', 'response-lost']))
        self.assertFalse(changed['ok'])
        self.assertIn('different inputs', changed['problem'])

    def test_interrupted_check_never_publishes_success_and_new_request_can_retry(self):
        args = self.prepare('import time; from pathlib import Path; Path(".team-workflow/started").touch(); time.sleep(1.5)')
        process = self.start(args + ['--request-id', 'interrupted'])
        deadline = time.monotonic() + 5
        while not (self.root / '.team-workflow/started').exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertTrue((self.root / '.team-workflow/started').exists())
        os.killpg(process.pid, signal.SIGKILL)
        process.communicate(timeout=5)
        result = self.result(self.start(args + ['--request-id', 'interrupted']))
        self.assertEqual(result['status'], 'interrupted')
        self.assertFalse(list((self.root / '.team-workflow/tasks').glob('*/requests/interrupted/**/run.json')))
        self.assertTrue(self.result(self.start(args + ['--request-id', 'new-attempt']))['ok'])

    def test_output_competition_is_atomic_and_failed_empty_output_is_retryable(self):
        args = self.prepare()
        # task exports compete for one explicitly requested filename, without replacing it.
        args[2] = 'task-export'
        processes = [self.start(args + ['--out', '.team-workflow/occupied.json']) for _ in range(2)]
        results = [self.result(p) for p in processes]
        self.assertEqual(sum(r['ok'] for r in results), 1)
        self.assertEqual(read(self.root / '.team-workflow/occupied.json'), self.task)
        args = self.prepare('pass')
        a = self.result(self.start(args + ['--request-id', 'empty-log']))
        b = self.result(self.start(args + ['--request-id', 'empty-log']))
        self.assertEqual(a, b)
        self.assertIn('request_artifacts', a)

    def test_machine_locations_do_not_change_identity_or_override_requirements(self):
        args = self.prepare()
        external = self.root / '.team-workflow/external'
        external.mkdir()
        left, right = external / 'left', external / 'right'
        left.write_text('same input')
        right.write_text('same input')
        self.profile['external_inputs'] = {'fixture': {'kind': 'file'}}
        write(self.root / '.team-workflow/local.json', {'inputs': {'fixture': str(left)}})
        a = snapshot(self.root, self.profile)
        token = LOCATIONS.set({'inputs': {'fixture': str(right)}, 'repositories': {}})
        try:
            self.assertEqual(a, snapshot(self.root, self.profile))
            right.write_text('different content')
            self.assertNotEqual(a, snapshot(self.root, self.profile))
        finally:
            LOCATIONS.reset(token)
        write(self.root / '.team-workflow/local.json', {'inputs': {'fixture': str(left)}, 'checks': {}})
        with self.assertRaises(Invalid):
            profile_valid(self.profile, self.root)
        self.profile['schema_version'] = 2
        with self.assertRaisesRegex(Invalid, 'configuration'):
            profile_valid(self.profile, self.root)

    def test_cs_source_version_and_unrelated_task_do_not_expire_completion(self):
        skill, report, _ = self.complete()
        (skill / 'scripts/cs_knowledge.py').write_text((skill / 'scripts/cs_knowledge.py').read_text() + '\n# compatible source change\n')
        (skill / 'scripts/bootstrap.py').write_text((skill / 'scripts/bootstrap.py').read_text().replace('2.1.0', '9.0.0'))
        (self.root / '.codestable/wiki/other-task.md').write_text('Unrelated task completed')
        self.assertTrue(verification.verify(self.root, self.profile, self.task, report, skill)['ok'])


class ParallelPlatform(unittest.TestCase):
    setUp = fixtures.WorkflowCases.setUp
    git = fixtures.WorkflowCases.git
    check = fixtures.WorkflowCases.check
    fake_cs = fixtures.WorkflowCases.fake_cs
    complete = fixtures.WorkflowCases.complete
    run_check = fixtures.WorkflowCases.run_check
    prepare = continuation.ContinuationCases.prepare
    body = continuation.ContinuationCases.body
    progress = continuation.ContinuationCases.progress

    def service(self):
        """Only the fixture accepts POST; production tools keep their GET-only adapter."""
        owner = self
        lock = threading.Lock()
        self.methods = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def reply(self, value):
                data = json.dumps(value).encode()
                self.send_response(200)
                self.end_headers()
                self.wfile.write(data)
            def do_GET(self):
                with lock:
                    owner.methods.append('GET')
                    if '/comments?' in self.path:
                        value = copy.deepcopy(owner.issue['comments_data'])
                    elif '/commits/' in self.path:
                        value = {'sha': self.path.rsplit('/', 1)[1]}
                    else:
                        value = copy.deepcopy(owner.issue)
                self.reply(value)
            def do_POST(self):
                value = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                with lock:
                    number = len(owner.issue['comments_data']) + 1
                    row = {'html_url': owner.url + '#issuecomment-' + str(number), **value['comment']}
                    owner.issue['comments_data'].append(row)
                if value.get('lose_response'):
                    self.close_connection = True
                else:
                    self.reply(row)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        address = 'http://127.0.0.1:' + str(server.server_port)
        def api(endpoint, **kw):
            with urlopen(address + '/' + endpoint) as response:
                return json.load(response)
        def append(draft, author='alice', lose=False):
            data = {'comment': {'body': draft['markdown'], 'user': {'login': author}}, 'lose_response': lose}
            request = Request(address + '/comments', data=json.dumps(data).encode(), method='POST')
            with urlopen(request) as response:
                return json.load(response)
        return api, append

    def test_parallel_progress_lost_response_owner_change_and_final_verification(self):
        self.prepare()
        skill, report, _ = self.complete()
        self.issue['body'] = self.body()
        api, append = self.service()
        with patch.object(github_read, 'api', side_effect=api):
            baseline = self.progress()
            baseline['remaining'] = []
            append(handoffs.draft(self.root, self.profile, self.url, baseline, skill))
            drafts = [handoffs.progress_draft(self.root, self.profile, self.url,
                {'author': user, 'done': [user + ' checked separate behavior'], 'verified': [], 'remaining': [], 'questions': []}, user + '-1')
                for user in ('alice', 'bob')]
            with ThreadPoolExecutor(2) as pool:
                results = list(pool.map(lambda pair: append(pair[1], pair[0]), zip(('alice', 'bob'), drafts)))
            self.assertEqual(len(results), 2)
            with self.assertRaises(http.client.RemoteDisconnected):
                append(drafts[1], 'bob', lose=True)
            append(drafts[1], 'bob')
            resumed = handoffs.resume(self.root, self.profile, self.url, skill)
            self.assertTrue(resumed['ok'], resumed)
            self.assertEqual(len(resumed['progress']), 2)
            self.assertEqual(len(resumed['pending_progress']), 2)
            report.update(schema_version=3, issue=self.url)
            review = read(self.root / report['review'])
            review['requirements'] = digest(handoffs.task_source(self.issue))
            write(self.root / report['review'], review)
            with self.assertRaisesRegex(Invalid, 'progress'):
                verification.verify(self.root, self.profile, self.task, report, skill)
            baseline['included_progress'] = [{key: item[key] for key in ('id', 'digest')} for item in resumed['pending_progress']]
            append(handoffs.draft(self.root, self.profile, self.url, baseline, skill))
            self.assertTrue(verification.verify(self.root, self.profile, self.task, report, skill)['ok'])
            # A contribution arriving during the knowledge check must also be observed.
            original_finish = verification.knowledge.finish
            late = handoffs.progress_draft(self.root, self.profile, self.url,
                {'author': 'bob', 'done': ['Late check'], 'verified': [], 'remaining': [], 'questions': []}, 'bob-late')
            def arrive_during_verification(*args, **kwargs):
                append(late, 'bob')
                return original_finish(*args, **kwargs)
            with patch.object(verification.knowledge, 'finish', side_effect=arrive_during_verification):
                with self.assertRaisesRegex(Invalid, 'progress|Platform'):
                    verification.verify(self.root, self.profile, self.task, report, skill)
            resumed = handoffs.resume(self.root, self.profile, self.url, skill)
            baseline['included_progress'] = [{key: item[key] for key in ('id', 'digest')} for item in resumed['pending_progress']]
            append(handoffs.draft(self.root, self.profile, self.url, baseline, skill))
            # A later owner inherits confirmed progress, and cannot hide responsibility or spec changes.
            self.issue['assignees'] = [{'login': 'bob'}]
            self.assertFalse(handoffs.resume(self.root, self.profile, self.url, skill)['ok'])
            baseline.pop('included_progress')
            baseline['owner'] = 'bob'
            append(handoffs.draft(self.root, self.profile, self.url, baseline, skill), 'bob')
            self.assertEqual(handoffs.resume(self.root, self.profile, self.url, skill)['pending_progress'], [])
            self.issue['body'] += '\nNew requirement.'
            self.assertIn('Requirements changed', str(handoffs.resume(self.root, self.profile, self.url, skill)['gaps']))
            with self.assertRaises(Invalid):
                verification.verify(self.root, self.profile, self.task, report, skill)
        self.assertTrue(self.methods and set(self.methods) == {'GET'})

    def test_nonowner_comment_cannot_confirm_handoff(self):
        self.prepare()
        api, append = self.service()
        with patch.object(github_read, 'api', side_effect=api):
            draft = handoffs.draft(self.root, self.profile, self.url, self.progress(), self.fake_cs())
            append(draft, 'someone-else')
            self.assertIn('confirmed by its owner', str(handoffs.chain(github_read.issue(self.url))[2]))

    def test_duplicate_progress_id_with_changed_content_is_explicit_conflict(self):
        self.prepare()
        api, append = self.service()
        with patch.object(github_read, 'api', side_effect=api):
            draft = handoffs.progress_draft(self.root, self.profile, self.url,
                {'author': 'alice', 'done': ['One'], 'verified': [], 'remaining': [], 'questions': []}, 'same')
            append(draft)
            append({'markdown': draft['markdown'].replace('One', 'Two')})
            self.assertIn('different content', str(handoffs.progress_history(github_read.issue(self.url))[1]))
