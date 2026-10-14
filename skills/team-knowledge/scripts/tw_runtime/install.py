"""Release manifest and installation integrity of the skills."""
import hashlib
import json
from pathlib import Path

from . import VERSION, require

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


def manifest(skill=SKILL, name='team-knowledge', version=VERSION):
    return {'schema_version': 1, 'skill': name, 'version': version, 'algorithm': 'sha256', 'files': skill_files(skill)}


def integrity(skill):
    try:
        shipped = json.loads((Path(skill) / MANIFEST).read_text(encoding='utf-8'))
        expected = shipped['files']
        require(isinstance(expected, dict), 'files 必须是对象')
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return {'status': 'unknown', 'reason': f'无法读取 {MANIFEST}：{exc}'}
    actual = skill_files(skill)
    result = {'version': shipped.get('version'),
              'changed': sorted(k for k in expected.keys() & actual.keys() if expected[k] != actual[k]),
              'missing': sorted(expected.keys() - actual.keys()), 'unexpected': sorted(actual.keys() - expected.keys())}
    modified = result['changed'] or result['missing'] or result['unexpected']
    return {'status': 'modified' if modified else 'intact', **result}


def check_install(home=None):
    home = Path(home).expanduser() if home else Path.home()
    own = integrity(SKILL)
    team = SKILL.parent / 'team-workflow'
    team_version = None
    if (team / MANIFEST).is_file():
        try:
            team_version = json.loads((team / MANIFEST).read_text(encoding='utf-8')).get('version')
        except ValueError:
            team_version = 'unreadable'
    copies = []
    for base in SKILL_HOMES:
        candidate = home / base / 'team-knowledge'
        if candidate.exists() and candidate.resolve() != SKILL.resolve():
            copies.append({'path': str(candidate), 'version': integrity(candidate.resolve()).get('version')})
    problems, notes = [], []
    if own['status'] != 'intact':
        problems.append('team-knowledge 的已安装文件与发行清单不一致')
    if team_version is None:
        notes.append('没有找到同一目录下的 team-workflow 技能；只用知识功能时可以忽略')
    elif team_version != VERSION:
        problems.append(f'team-workflow 版本 {team_version} 与 team-knowledge {VERSION} 不是同一发行')
    if any(c['version'] != VERSION for c in copies):
        problems.append('其他客户端目录中有不同版本的 team-knowledge')
    return {'ok': not problems, 'version': VERSION, 'skill': str(SKILL), 'integrity': own,
            'team_workflow': team_version, 'other_copies': copies, 'problems': problems, 'notes': notes}
