"""Read current evidence without executing checks or publishing workflow materials."""
import design_files
import copy

from common import Invalid, artifact, artifact_valid, digest, read
import delivery
import knowledge
import validation


def inspect(args, root, profile, task, progress, approval_status, *, workspace=None):
    from commands import local, report_input
    selection = getattr(args, 'material_selection', None) or {}
    group = selection.get('effective') or selection.get('value') or {}
    stale_roles = sorted(set(selection.get('stale_roles', [])))
    result = {'verified_records': {}, 'stale_steps': {}, 'review_current': False,
              'review_failures': [], 'stale_materials': stale_roles, 'report_complete': None}
    rows = {row['id']: row for row in progress['steps']}

    def candidate(role, step):
        ref = group.get(role)
        if ref:
            return ref
        path = rows[step].get('evidence')
        try:
            return artifact(root, local(root, path)) if path and rows[step]['state'] == 'done' else None
        except (Invalid, OSError, ValueError, TypeError, KeyError):
            return None

    accepted, delivered = candidate('acceptance', 'acceptance'), candidate('delivery', 'delivery')
    reports = {}
    for role, ref in [('acceptance', accepted), ('delivery', delivered)]:
        if ref:
            try:
                reports[role] = read(artifact_valid(root, ref))['report']
            except (Invalid, OSError, ValueError, TypeError, KeyError):
                result['stale_steps'][role] = '记录缺失、被改动或格式不完整'

    expected = None
    if group:
        expected = report_input(args, root, task, include_knowledge=False)
    elif reports:
        expected = copy.deepcopy(reports.get('acceptance') or reports['delivery'])
        for option, field in [('design', 'design'), ('brief', 'brief'), ('review', 'review')]:
            if getattr(args, option, None):
                expected[field] = local(root, getattr(args, option)).relative_to(root).as_posix()
        for option, field in [('run', 'runs'), ('approval', 'approvals'), ('design_history', 'design_history')]:
            if getattr(args, option, None):
                expected[field] = [local(root, path).relative_to(root).as_posix() for path in getattr(args, option)]
    if expected and expected.get('review'):
        try:
            import designs
            design = design_files.read(local(root, expected['design']), workspace=workspace)
            hashes = designs.fingerprints(design)['sections']
            selected = {key: hashes[key] for key in task['section_ids']}
            review = read(local(root, expected['review']))
            delivery.check_review_format(root, profile, task, review, selected, design, workspace=workspace)
            result['review_current'] = rows['review']['state'] != 'stale'
            result['review_failures'] = delivery.review_failures(review, approval_status['required_sections'])
            if result['review_current'] and any(row.get('cases') for row in review['acceptance']):
                try:
                    execution = validation.verify_runs(root, profile, task, expected['runs'], live=False, workspace=workspace)
                except Invalid:
                    pass  # The existing run step reports unavailable execution separately.
                else:
                    failures = delivery.review_case_failures(review, execution)
                    if failures:
                        import reviews
                        result['review_case_repair'] = reviews.case_repair(root, task['id'], artifact(root, local(root, expected['review'])))
                        result['review_failures'] += failures
        except (Invalid, OSError, ValueError, TypeError, KeyError):
            result['stale_steps']['review'] = '评审的任务、源码、配置或章节绑定已变化'

    if stale_roles:
        from materials import LABELS
        reason = '当前材料已变化：' + '、'.join(LABELS.get(role, role) for role in stale_roles)
        for name in ('prepare', 'review', 'acceptance', 'knowledge', 'delivery'):
            result['stale_steps'][name] = reason
        result['review_current'] = False
        return result

    checked = None
    if expected and accepted:
        try:
            proof = read(artifact_valid(root, accepted))
            checked = delivery.verify(root, profile, task, expected, 'acceptance', live=False, workspace=workspace)
            keys = ('task_id', 'task_digest', 'source_digest', 'sections')
            if not (proof.get('kind') == 'acceptance' and proof.get('business_accepted') is True
                    and all(proof.get(key) == checked[key] for key in keys)
                    and delivery.contents(proof.get('materials')) == delivery.contents(checked['materials'])):
                raise Invalid('业务验收所用的材料已变化')
            result['verified_records']['acceptance'] = accepted
        except (Invalid, OSError, ValueError, TypeError, KeyError) as exc:
            result['stale_steps']['acceptance'] = '业务验收记录已过期：' + str(exc)

    report_ref = candidate('delivery_report', 'knowledge')
    if report_ref:
        try:
            report = read(artifact_valid(root, report_ref))
            for key in ('task_id', 'design', 'approvals', 'brief', 'runs', 'review'):
                if expected and report.get(key) != expected.get(key):
                    raise Invalid('交付报告引用的材料已变化')
            knowledge.verify(root, report.get('knowledge'), task['base'])
            result['report_complete'] = True
        except (Invalid, OSError, ValueError, TypeError, KeyError) as exc:
            result['report_complete'] = False
            result['report_problem'] = str(exc)

    if delivered and 'acceptance' in result['verified_records']:
        try:
            proof = read(artifact_valid(root, delivered))
            report = copy.deepcopy(proof['report'])
            report.update({key: value for key, value in expected.items() if key not in ('knowledge', 'acceptance')})
            report['acceptance'] = accepted['path']
            verified = delivery.verify(root, profile, task, report, 'delivery', live=False, workspace=workspace)
            keys = ('task_id', 'task_digest', 'source_digest', 'sections')
            if not (proof.get('kind') == 'delivery-verification' and proof.get('delivery_complete') is True
                    and all(proof.get(key) == verified[key] for key in keys)
                    and delivery.contents(proof.get('materials')) == delivery.contents(verified['materials'])):
                raise Invalid('最终交付所用的材料已变化')
            result['verified_records']['delivery'] = delivered
        except (Invalid, OSError, ValueError, TypeError, KeyError) as exc:
            result['stale_steps']['delivery'] = '交付记录已过期：' + str(exc)
    if accepted and 'acceptance' not in result['verified_records']:
        for name in ('knowledge', 'delivery'):
            result['stale_steps'][name] = '业务验收所用的材料已变化，需要重新验收'
    return result


def publication(platform):
    if platform is None:
        return {'published': None, 'kind': 'local', 'complete': None, 'url': None,
                'summary': '发布状态：本地任务没有平台收尾说明或交接，按团队约定收尾'}
    current = platform.get('current')
    pointer = platform.get('previous') or {}
    published = bool(current and current.get('handoff_kind') in ('implementation', 'close'))
    return {'published': published, 'kind': current.get('handoff_kind') if current else None,
            'complete': published and not bool(current.get('remaining')),
            'url': pointer.get('url') if published else None,
            'summary': '收尾说明或交接已发布' if published else '尚未发布收尾说明或完整实施交接'}


def closing_action(root, task_id):
    from repairs import task_command
    return ('按已有授权发布收尾说明或完整交接，在报告副本记录关闭授权后运行 '
            + task_command(root, task_id, 'verify', '--report <报告>') + '，再由获授权成员关闭任务。')


def recorded(root, task_id, phase, group, platform):
    import checklist
    import records
    progress = {'steps': checklist.recorded_steps(root, checklist.records(root, task_id)),
                'next_step': None, 'finished': True, 'completion_summary': '任务已关闭' if phase == 'closed' else '任务已交付'}
    verified = {}
    proof = None
    for key in ('acceptance', 'delivery'):
        ref = (group or {}).get(key)
        if ref:
            value = read(artifact_valid(root, ref))
            if value.get('ok') and value.get('business_accepted' if key == 'acceptance' else 'delivery_complete'):
                verified[key] = ref
                if key == 'delivery':
                    proof = value
    if proof and 'summary_counts' in proof:
        row = {'id': 'scenarios', 'label': '场景验收', 'state': 'done',
               'evidence': (proof.get('scenario_rounds') or [{}])[-1].get('path'),
               'summary_counts': proof['summary_counts'], 'first_pass': proof['statistics']['first_pass']}
        progress['steps'].insert(2, row)
    delivery_fields = {}
    if proof:
        from summary import delivery_status
        delivery_fields = {key: proof[key] for key in ('delivery_complete',
            'summary_counts', 'statistics', 'scenario_rounds', 'scenario_files') if key in proof}
        state = delivery_status(proof)
        delivery_fields['overall_complete'] = state['overall_complete']
        next(row for row in progress['steps'] if row['id'] == 'delivery')['summary'] = state['summary']
    view = None
    if platform:
        view = platform if 'items' not in platform else {'current': None, 'previous': None}
        for item in platform.get('items', []):
            try:
                value = records.block(item['body'], 'handoff', required=False)
            except Invalid:
                continue
            if value:
                view.update(current=value, previous={'url': item['url']})
    summary = progress['completion_summary']
    action = '任务已关闭' if phase == 'closed' else closing_action(root, task_id)
    progress['completion_summary'] = summary if phase == 'closed' else action
    return {'ok': True, 'task_phase': phase, 'summary': summary, 'next_action': action, **delivery_fields,
            'steps': progress['steps'], 'next_step': None, 'step_lines': checklist.render(progress),
            'verified_records': verified, 'publication': publication(view), 'warnings': []}
