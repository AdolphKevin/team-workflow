"""Read current evidence without executing checks or publishing workflow materials."""
import copy

from common import Invalid, artifact, artifact_valid, digest, read
import delivery
import knowledge
import validation


def inspect(args, root, profile, task, progress, approval_status):
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
            design = read(local(root, expected['design']))
            hashes = designs.fingerprints(design)['sections']
            selected = {key: hashes[key] for key in task['section_ids']}
            review = read(local(root, expected['review']))
            delivery.check_review_format(root, profile, task, review, selected, design)
            result['review_current'] = rows['review']['state'] != 'stale'
            result['review_failures'] = delivery.review_failures(review, approval_status['required_sections'])
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
            checked = delivery.verify(root, profile, task, expected, 'acceptance', live=False)
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
            verified = delivery.verify(root, profile, task, report, 'delivery', live=False)
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
        return None
    current = platform.get('current')
    pointer = platform.get('previous') or {}
    published = bool(current and current.get('handoff_kind') in ('implementation', 'close'))
    return {'published': published, 'kind': current.get('handoff_kind') if current else None,
            'complete': published and not bool(current.get('remaining')),
            'url': pointer.get('url') if published else None,
            'summary': '收尾说明或交接已发布' if published else '尚未发布收尾说明或完整实施交接'}
