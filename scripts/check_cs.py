#!/usr/bin/env python3
"""Exercise real, independently installed CS through the workflow bridge."""
import argparse
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'skills/team-workflow/scripts'))
from common import Invalid, artifact, read, write
import knowledge
import verification
import handoffs
import github_read


def run(skill):
    locked = read(ROOT / 'dependencies.json')['cs']
    assert knowledge.identity(skill) == locked['files'], 'CS source differs from dependencies.json; review the dependency update first'
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
        config = read(root / '.codestable/config.json')
        config['wiki']['repositories'] = {'contracts': {'root': '../contracts'}}
        config['wiki']['documents'] = {'terms': {'repository': 'contracts', 'path': 'GLOSSARY.md',
            'title': 'Owner terminology', 'category': 'requirements', 'always': True}}
        write(root / '.codestable/config.json', config)
        git('add', '.')
        git('commit', '-qm', 'isolated baseline')
        task = {'schema_version': 2, 'id': 'https://github.com/example/cs-integration/issues/1', 'base': git('rev-parse', 'HEAD'),
                'goal': 'Document the public owner terminology', 'non_goals': [], 'kind': 'docs', 'risks': [],
                'acceptance': [{'id': 'A1', 'expectation': 'README identifies the single owning source', 'checks': []}]}
        profile = {'schema_version': 2, 'project': 'fixture-service', 'context': ['AGENTS.md'],
                   'knowledge': {'provider': 'cs', 'entry': '.codestable/wiki/INDEX.md'},
                   'checks': {}, 'required_checks': {'docs': [], 'code': []}, 'risk_checks': {},
                   'inputs': [], 'environment_versions': {}}
        brief_path = root / '.team-workflow/brief.json'
        brief = knowledge.brief(root, task, skill, ['README.md'], [])
        write(brief_path, brief)
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
        completion_path = root / '.team-workflow/knowledge.json'
        completion = knowledge.finish(root, task, skill, applied['task_id'], brief_path, 'none', 'Original document already owns the definition')
        write(completion_path, completion)
        review = verification.review_template(root, profile, task, brief_path, completion_path)
        evidence = [artifact(root, root / 'README.md'), artifact(root, brief_path)]
        review.update(reviewer='isolated-integration-test', knowledge_conflicts_resolved=True)
        for key in ('standards', 'spec'):
            review[key] = {'status': 'passed', 'summary': 'README points to the registered original and adds no competing definition.', 'evidence': evidence}
        review['acceptance'] = [{'id': 'A1', 'status': 'passed', 'summary': 'The Owner source is linked.', 'evidence': evidence}]
        review_path = root / '.team-workflow/review.json'
        write(review_path, review)
        report = {'schema_version': 2, 'task_id': task['id'], 'runs': [], 'review': '.team-workflow/review.json', 'knowledge': '.team-workflow/knowledge.json'}
        assert verification.verify(root, profile, task, report, skill)['ok']
        # Reuse the task record and registered original through the real CS entry.
        payload['task'].update(id=applied['task_id'], update_existing=True, expected_revision=1)
        write(payload_path, payload)
        preview = knowledge.call(skill, root, ['learn', '--file', str(payload_path), '--dry-run'])
        repeated = knowledge.call(skill, root, ['learn', '--file', str(payload_path), '--plan-token', preview['plan_token']])
        assert repeated['task_id'] == applied['task_id']
        later = knowledge.brief(root, task, skill, ['README.md'], [])
        assert applied['task_id'] in json.dumps(later), 'Task outcome must be discoverable in the later brief'
        assert later['brief']['authoritative_documents'][0]['source'] == 'contracts:GLOSSARY.md'
        git('add', 'README.md')
        git('commit', '-qm', 'document owner source')
        issue = {'html_url': task['id'], 'updated_at': '2026-10-01T00:00:00Z', 'assignees': [{'login': 'reader'}],
                 'body': '```team-workflow-task\n' + json.dumps({'schema_version': 3, 'parent': None, 'task': task}) + '\n```', 'comments_data': []}
        progress = {'owner': 'reader', 'done': ['Linked the owning source'], 'verified': [], 'remaining': [],
                    'questions': [], 'next': 'Review the documented source', 'versions': [{'repository': 'example/cs-integration', 'commit': git('rev-parse', 'HEAD')}],
                    'references': [], 'participants': [], 'contracts': [], 'dependencies': [], 'joint_owner': ''}
        # Only transport is a local fixture; all CS calls execute the locked dependency.
        with patch.object(github_read, 'issue', return_value=issue), patch.object(github_read, 'commit'):
            draft = handoffs.draft(root, profile, task['id'], progress, skill)
            assert draft['ok'], draft['gaps']
            issue['comments_data'] = [{'html_url': task['id'] + '#issuecomment-1', 'body': draft['markdown']}]
            resumed = handoffs.resume(root, profile, task['id'], skill)
            assert resumed['ok'] and resumed['knowledge']['brief']['authoritative_documents'][0]['source'] == 'contracts:GLOSSARY.md'
        doc.write_text(original + '\nChanged external definition.\n')
        try:
            knowledge.finish(root, task, skill, applied['task_id'], brief_path, 'none', 'Original owns the definition')
        except Invalid as exc:
            assert 'Source documents changed' in str(exc), str(exc)
        else:
            raise AssertionError('External document change accepted stale completion')
        doc.unlink()
        try:
            knowledge.finish(root, task, skill, applied['task_id'], brief_path, 'none', 'No new knowledge')
        except Invalid:
            pass
        else:
            raise AssertionError('Missing authoritative document accepted')
        return {'ok': True, 'cs_version': brief['cs_version'], 'checks': [
            'unified-cross-repository-brief', 'real-learn-preview-apply-doctor', 'task-only-completion',
            'complete-document-delivery', 'same-task-update-and-later-retrieval', 'v3-handoff-resume-real-cs',
            'changed-external-document-rejected', 'missing-source-rejected']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cs-skill', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(knowledge.skill_path(args.cs_skill)), indent=2))
