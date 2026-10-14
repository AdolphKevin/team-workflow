"""Release manifest and installation integrity of the skills."""
import hashlib
import json
from pathlib import Path

from . import VERSION, Invalid, require

SKILL = Path(__file__).resolve().parents[2]
MANIFEST = 'MANIFEST.json'
SKILL_HOMES = ('.agents/skills', '.claude/skills', '.codex/skills', '.cursor/skills')


def skill_files(skill):
    found = {}
    for path in sorted(Path(skill).rglob('*')):
        relative = path.relative_to(skill)
        if '__pycache__' in relative.parts or path.suffix in ('.pyc', '.pyo') or path.name == '.DS_Store':
            continue
        require(not path.is_symlink(), '技能目录中不能有符号链接：' + relative.as_posix())
        if path.is_file() and relative.as_posix() != MANIFEST:
            found[relative.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return found


def manifest(skill=SKILL, name=None, version=VERSION):
    name = name or Path(skill).name
    return {'schema_version': 1, 'skill': name, 'version': version, 'algorithm': 'sha256', 'files': skill_files(skill)}


def integrity(skill, expected_version=None):
    """Compare a skill directory with its shipped manifest; optionally require a release version."""
    try:
        shipped = json.loads((Path(skill) / MANIFEST).read_text(encoding='utf-8'))
        expected = shipped['files']
        require(isinstance(expected, dict), 'files 必须是对象')
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return {'status': 'unknown', 'reason': f'无法读取 {MANIFEST}：{exc}', 'version': None}
    try:
        actual = skill_files(skill)
    except (Invalid, OSError) as exc:
        return {'status': 'modified', 'reason': str(exc), 'version': shipped.get('version'),
                'changed': [], 'missing': [], 'unexpected': []}
    result = {'version': shipped.get('version'),
              'changed': sorted(k for k in expected.keys() & actual.keys() if expected[k] != actual[k]),
              'missing': sorted(expected.keys() - actual.keys()), 'unexpected': sorted(actual.keys() - expected.keys())}
    modified = result['changed'] or result['missing'] or result['unexpected']
    if expected_version is not None and shipped.get('version') != expected_version:
        modified = True
    return {'status': 'modified' if modified else 'intact', **result}


LEGACY_SKILLS = ('cs', 'cs-analysis')


def check_install(home=None, require_team=False):
    """`problems` concern the running tool and block verification; `installation_problems` concern the
    copies that clients load from the user's skill directories and are reported, not enforced."""
    home = Path(home).expanduser() if home else Path.home()
    own = integrity(SKILL, VERSION)
    team = SKILL.parent / 'team-workflow'
    team_integrity = integrity(team, VERSION) if (team / MANIFEST).is_file() else None
    team_version = team_integrity.get('version') if team_integrity else None
    running = {SKILL.resolve(), team.resolve()}
    copies, seen = [], set()
    for base in SKILL_HOMES:
        for name in ('team-knowledge', 'team-workflow'):
            candidate = home / base / name
            if not candidate.exists():
                continue
            real = candidate.resolve()
            if real in running or real in seen:
                continue
            seen.add(real)
            state = integrity(real)
            copies.append({'path': str(candidate), 'skill': name, 'version': state.get('version'),
                           'status': state['status'], 'changed': state.get('changed', []),
                           'missing': state.get('missing', []), 'unexpected': state.get('unexpected', []),
                           **({'reason': state['reason']} if state.get('reason') else {})})
    legacy = sorted(str(home / base / name) for base in SKILL_HOMES for name in LEGACY_SKILLS if (home / base / name).exists())
    problems, notes = [], []
    if own['status'] != 'intact':
        problems.append('正在运行的 team-knowledge 与发行清单不一致：' + describe(own))
    if team_integrity is None:
        (problems if require_team else notes).append('没有找到同一目录下的 team-workflow 技能；团队功能需要同一发行的两个技能')
    elif team_version != VERSION:
        problems.append(f'team-workflow 版本 {team_version} 与 team-knowledge {VERSION} 不是同一发行')
    elif team_integrity['status'] != 'intact':
        problems.append('正在使用的 team-workflow 与发行清单不一致：' + describe(team_integrity))
    installation = []
    for copy in copies:
        if copy['status'] != 'intact':
            installation.append(f'{copy["path"]} 的文件被改动：' + describe(copy))
        elif copy['version'] != VERSION:
            installation.append(f'{copy["path"]} 是另一个发行（{copy["version"]}），客户端可能加载旧版本')
    installation += [f'存在应卸载的旧技能：{path}（npx skills remove -g cs cs-analysis）' for path in legacy]
    return {'ok': not problems, 'installed_ok': not installation, 'version': VERSION, 'skill': str(SKILL),
            'integrity': own, 'team_workflow': team_version, 'team_integrity': team_integrity,
            'other_copies': copies, 'legacy_skills': legacy, 'problems': problems,
            'installation_problems': installation, 'notes': notes}


def describe(state):
    parts = [f'{label} {", ".join(state[key][:5])}' for key, label in (('changed', '改动'), ('missing', '缺少'),
             ('unexpected', '多出')) if state.get(key)]
    if state.get('reason'):
        parts.append(f'清单状态 {state.get("status", "unknown")}：{state["reason"]}')
    return '；'.join(parts) or f'版本 {state.get("version")}'
