"""Separate human-authored task IDs from resolved internal acceptance content."""
import copy

from common import obj, require, text


def validate_written(task):
    rows = task.get('acceptance')
    require(isinstance(rows, list) and bool(rows), 'Acceptance cannot be empty')
    for row in rows:
        require(not isinstance(row, dict) or not {'expectation', 'checks'} & row.keys(),
                '验收项只写编号，内容以方案为准')
        obj(row, {'id'})
        text(row['id'])
    return task


def written(task):
    result = copy.deepcopy(task)
    result['acceptance'] = [{'id': row['id']} for row in task['acceptance']]
    return result


def expand(task, design):
    """Resolve both local and platform IDs from the selected (possibly parent) design."""
    result = written(task)
    sections = {row['id']: row for row in design['sections']}
    for row in result['acceptance']:
        section = sections.get(row['id'], {})
        require(section.get('type') == 'acceptance', 'Missing acceptance section: ' + row['id'])
        row.update(expectation=section['body'], checks=copy.deepcopy(section['data']['checks']))
    return result
