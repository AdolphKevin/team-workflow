"""Separate human-authored task IDs from resolved internal acceptance content."""
import copy

from common import Invalid, obj, require, text


class WrittenTaskError(Invalid):
    def __init__(self, identifier, fields, source=None):
        location = f'任务 {source} 的验收项' if source else '任务的验收项'
        names = '、'.join(fields)
        super().__init__(f'{location} {identifier} 含 {names}；验收项只写编号，内容以方案为准')
        target = '任务文件 ' + str(source) if source else '任务'
        self.next_action = f'修正{target}：删除验收项 {identifier} 中的 {names}，只保留编号。'


def validate_written(task, source=None):
    rows = task.get('acceptance')
    require(isinstance(rows, list) and bool(rows), 'Acceptance cannot be empty')
    for row in rows:
        fields = [key for key in ('expectation', 'checks') if isinstance(row, dict) and key in row]
        if fields:
            raise WrittenTaskError(row.get('id', '（未填写编号）'), fields, source)
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
