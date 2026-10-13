#!/usr/bin/env python3
"""Exercise the knowledge bridge against the real, independently installed CS CLI."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'skills/team-workflow/scripts'))
from common import Invalid, write, sha
import knowledge


def run(skill):
    with tempfile.TemporaryDirectory(prefix='team-cs-integration-') as directory:
        root = Path(directory) / 'service'
        external = Path(directory) / 'contracts'
        root.mkdir()
        external.mkdir()
        original = '# Business terms\n\n## Owner\nEach resource has one owner.\n'
        doc = external / 'GLOSSARY.md'
        doc.write_text(original)
        (root / 'AGENTS.md').write_text('Use CS for source documents and experience.\n')
        (root / 'README.md').write_text('Example service.\n')
        (root / '.gitignore').write_text('.team-workflow/\n.codestable/cache/\n')
        def git(*argv):
            return subprocess.check_output(['git', '-C', str(root), *argv], text=True).strip()
        git('init', '-q')
        git('config', 'user.email', 'workflow-tests@example.invalid')
        git('config', 'user.name', 'Workflow tests')
        git('config', 'commit.gpgsign', 'false')
        git('remote', 'add', 'origin', 'https://github.com/example/cs-integration.git')
        knowledge.call(skill, root, [], bootstrap=True)
        write(root / '.codestable/local.json', {'repositories': {'contracts': str(external)}})
        write(root / '.codestable/documents/terms.json', {'repository': 'contracts', 'path': 'GLOSSARY.md',
            'title': 'Owner terminology', 'category': 'requirements', 'always': True})
        git('add', '.')
        git('commit', '-qm', 'isolated baseline')
        task = {'schema_version': 5, 'id': 'https://github.com/example/cs-integration/issues/1', 'base': git('rev-parse', 'HEAD'),
                'goal': 'Document the public owner terminology', 'non_goals': [], 'kind': 'docs', 'risks': [],
                'acceptance': [{'id': 'A1', 'expectation': 'README identifies the single owning source', 'checks': []}],
                'design_id': 'D-terms', 'section_ids': ['T1'], 'acceptance_scope': 'requirement', 'paths': ['README.md']}
        brief = knowledge.brief(root, task, skill, ['README.md'], [])
        assert brief['brief']['authoritative_documents'][0]['source'] == 'contracts:GLOSSARY.md'
        (root / 'README.md').write_text('Ownership is defined in the registered terms document, section Owner.\n')
        payload = {'task': {'title': 'Document owner terminology', 'kind': 'task', 'status': 'completed',
                           'request': task['id'] + ': ' + task['goal'], 'summary': 'Linked the registered terminology.',
                           'result': 'README refers to the sole original document.', 'paths': ['README.md'],
                           'verification': ['Read README and registered Owner section through CS.'],
                           'knowledge_summary': 'No new long-term conclusion; keep one source body.'}, 'items': []}
        payload_path = root / '.team-workflow/learning.json'
        write(payload_path, payload)
        preview = knowledge.call(skill, root, ['learn', '--file', str(payload_path), '--dry-run'])
        applied = knowledge.call(skill, root, ['learn', '--file', str(payload_path), '--plan-token', preview['plan_token']])
        # Reuse the task record and registered original through the real CS entry.
        payload['task'].update(id=applied['task_id'], update_existing=True, expected_revision=1)
        write(payload_path, payload)
        preview = knowledge.call(skill, root, ['learn', '--file', str(payload_path), '--dry-run'])
        assert preview['idempotent'] and preview['task_id'] == applied['task_id']
        if 'plan_state' in preview:
            assert preview['plan_state'] == 'not-needed' and preview['plan_token'] is None
        # A no-op preview has nothing to apply. Add the actual delivery result
        # to exercise a real update, then retry that same payload and plan.
        payload['task']['verification'].append('Workflow document delivery verification passed.')
        write(payload_path, payload)
        preview = knowledge.call(skill, root, ['learn', '--file', str(payload_path), '--dry-run'])
        assert preview['plan_token']
        updated = knowledge.call(skill, root, ['learn', '--file', str(payload_path), '--plan-token', preview['plan_token']])
        assert updated['task_id'] == applied['task_id'] and updated['task_revision'] == 2
        repeated = knowledge.call(skill, root, ['learn', '--file', str(payload_path), '--plan-token', preview['plan_token']])
        assert repeated['idempotent'] and repeated['task_id'] == applied['task_id'] and repeated['task_revision'] == 2
        later = knowledge.brief(root, task, skill, ['README.md'], [])
        assert applied['task_id'] in json.dumps(later), 'Task outcome must be discoverable in the later brief'
        assert later['brief']['authoritative_documents'][0]['source'] == 'contracts:GLOSSARY.md'
        doc.write_text(original + '\nChanged external definition.\n')
        try:
            knowledge.receipt_check(skill, root, later['brief'])
        except Invalid as exc:
            assert 'receipt-check' in str(exc), str(exc)
        else:
            raise AssertionError('External document change accepted stale completion')
        doc.unlink()
        try:
            knowledge.receipt_check(skill, root, later['brief'])
        except Invalid:
            pass
        else:
            raise AssertionError('Missing authoritative document accepted')
        return {'ok': True, 'cs_version': brief['cs_version'], 'cs_runtime_sha256': sha(skill / 'scripts/cs_knowledge.py'), 'checks': [
            'unified-cross-repository-brief', 'real-learn-preview-apply', 'same-task-update-and-later-retrieval',
            'changed-external-document-rejected', 'missing-source-rejected']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cs-skill', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(knowledge.skill_path(args.cs_skill)), indent=2))
