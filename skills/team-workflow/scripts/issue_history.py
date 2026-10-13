"""Retain issues actually submitted for review, including failed verification attempts."""
from artifacts import directory
from common import artifact_valid, now, read, require
from contracts import issues, reconcile


def known(root, task_id):
    requests = directory(root, task_id).parent
    values = []
    for path in requests.glob('*/review-input.json'):
        value = read(path)
        require(value['task_id'] == task_id, 'Review history belongs to another task')
        response = path.parent / 'response.json'
        if response.exists():
            refs = [r for r in read(response).get('request_artifacts', [])
                    if r['path'] == path.relative_to(root).as_posix()]
            require(len(refs) == 1, 'Review history has no immutable reference')
            artifact_valid(root, refs[0])
        issues(value['issues'])
        values.append(value)
    merged = {}
    for value in sorted(values, key=lambda v: v['at']):
        for row in value['issues']:
            if row['id'] in merged:
                reconcile([merged[row['id']]], [row])
            merged[row['id']] = row
    return list(merged.values())


def capture(request, task, review, section_ids=None):
    rows = review.get('findings', [])
    issues(rows, section_ids)
    reconcile(known(request.root, task['id']), rows)
    request.publish('review-input.json', {'schema_version': 5, 'task_id': task['id'], 'at': now(), 'issues': rows})
