"""决定修复路径的错误代码；报错文字单独用于显示。"""


class Code:
    INVALID = 'invalid-or-incomplete-input'
    PROJECT_UNINITIALIZED = 'project-not-initialized'
    CURRENT_MATERIALS = 'current-materials-incomplete'
    REVIEW_INCOMPLETE = 'review-incomplete'
    REVIEW_NOT_SUBMITTED = 'review-not-submitted'
    REVIEW_NOT_PASSED = 'review-not-passed'
    CLOSE_AUTHORIZATION = 'close-authorization-incomplete'
    TOOL_MODIFIED = 'tool-modified'
    IMPORT_INCOMPLETE = 'import-incomplete'
    TOOL_DEFECT = 'tool-defect'
    TASK_INPUT = 'task-input-invalid'
    DESIGN_INPUT = 'design-input-invalid'
    REVIEW_BINDING_STALE = 'review-binding-stale'
    REVIEW_FILE_UNREADABLE = 'review-file-unreadable'
    REVIEW_RUN_INCOMPLETE = 'review-run-incomplete'
    REVIEW_MATERIALS_INCOMPLETE = 'review-materials-incomplete'
    INDEPENDENCE = 'independence-required'
    VALIDATION_ACTIVE = 'validation-active'
    REQUEST_CONFLICT = 'request-conflict'
    APPROVAL_INCOMPLETE = 'approval-incomplete'
    APPROVAL_NOT_SHARED = 'approval-not-shared'
    REPORT_INCOMPLETE = 'report-incomplete'
    SOURCE_STALE = 'source-stale'
    RUN_BINDING_STALE = 'run-binding-stale'
    DESIGN_MARKDOWN = 'design-markdown-invalid'
    PLATFORM_DESIGN = 'platform-design-invalid'
    PLATFORM_APPROVAL = 'platform-approval-invalid'
    PLATFORM_HANDOFF = 'platform-handoff-invalid'
    HANDOFF_REQUIREMENTS = 'handoff-requirements-changed'
    HANDOFF_MISSING = 'handoff-missing'
    OWNER_MISSING = 'owner-missing'
    PROGRESS_UNCONFIRMED = 'progress-unconfirmed'
    CHECK_RESULT = 'check-result-invalid'
    CHECK_CONFIG = 'check-config-invalid'
    APPROVAL_COMMIT = 'approval-commit-unavailable'
    APPROVAL_SOURCE = 'approved-source-invalid'
    ACCEPTANCE_STALE = 'acceptance-stale'
    ACCEPTANCE_MISSING = 'acceptance-record-missing'
    PLATFORM_CHANGED = 'platform-records-changed'
    BRIEF_INPUT = 'knowledge-brief-incomplete'
    DESIGN_HISTORY = 'design-history-incomplete'
    REQUEST_INPUT = 'request-input-invalid'
    REQUEST_ACTIVE = 'request-active'
    REQUEST_INTERRUPTED = 'request-interrupted'


def fields(exc):
    return {'error_code': getattr(exc, 'error_code', Code.INVALID),
            **{key: getattr(exc, key) for key in ('section', 'line', 'key')
               if getattr(exc, key, None) is not None}}


def gap(problem, error_code=Code.INVALID):
    return {'error_code': error_code, 'problem': problem}


def gap_fields(errors):
    """保留问题的代码；文字列表继续用于显示。"""
    unique = {(row['error_code'], row['problem']): row for row in errors}
    return {'gaps': sorted({row['problem'] for row in errors}),
            'gap_errors': [unique[key] for key in sorted(unique)]}


def check_error_code(codes, default):
    specific = sorted(code for code in codes if code not in (None, Code.INVALID))
    return next((code for code in (Code.CHECK_CONFIG, Code.CHECK_RESULT) if code in codes),
                specific[0] if specific else default)
