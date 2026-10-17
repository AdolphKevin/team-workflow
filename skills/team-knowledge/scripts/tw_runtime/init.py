"""Create the minimal `.tw/` layout and the knowledge pointer in AGENTS.md. Preview unless --apply."""
import json

from . import DATA_VERSION, FORMAT, KB, Invalid, files, frontmatter, gitutil, install, require
from .new import SOURCE_REQUIRED

IGNORE = 'local/\n'
POINTER = """## 项目知识

开工前读取 `.tw/` 中与任务相关的现行约束、决策和踩过的坑：
`python3 <team-knowledge 技能目录>/scripts/tw.py brief --task "<任务>" --path <相关路径>`。
完成后按 team-knowledge 技能的规则更新知识（与代码同一个 PR），并运行 `tw.py check`。"""
# Neutral on purpose: many projects keep their own rules in CLAUDE.md, so the block only imports AGENTS.md.
CLAUDE = '共享的项目规则与项目知识入口在 AGENTS.md，由此引入：\n@AGENTS.md'


def plan(root, guidance=False, sources=()):
    actions = []
    config_path = root / KB / 'config.json'
    if config_path.exists():
        try:
            existing = json.loads(config_path.read_text(encoding='utf-8'))
        except ValueError as exc:
            raise Invalid(f'{KB}/config.json 已存在但无法解析，请手工修复：{exc}') from exc
        require(isinstance(existing, dict) and existing.get('format') == FORMAT,
                f'{KB}/ 已被其他工具使用（format 不是 {FORMAT}），拒绝接管')
        actions.append({'path': f'{KB}/config.json', 'action': 'unchanged'})
    else:
        own = {'.gitignore', 'local', 'overview.md', 'glossary.md', 'rules', 'decisions', 'lessons'}
        foreign = sorted(p.name for p in (root / KB).iterdir() if p.name not in own) if (root / KB).is_dir() else []
        if foreign:
            raise Invalid(f'{KB}/ 已存在且含有本工具布局之外的文件（{", ".join(foreign[:3])}），可能属于其他工具，拒绝接管')
        config = {'format': FORMAT, 'data_version': DATA_VERSION,
                  'project': {'id': gitutil.remote_identity(root) or f'local:{root.name}', 'name': root.name}}
        actions.append({'path': f'{KB}/config.json', 'action': 'create',
                        'text': json.dumps(config, ensure_ascii=False, indent=2) + '\n'})
    ignore = root / KB / '.gitignore'
    if not ignore.exists():
        actions.append({'path': f'{KB}/.gitignore', 'action': 'create', 'text': IGNORE})
    else:
        text = files.read_text(ignore)
        if 'local/' in [line.strip() for line in text.splitlines()]:
            actions.append({'path': f'{KB}/.gitignore', 'action': 'unchanged'})
        else:
            actions.append({'path': f'{KB}/.gitignore', 'action': 'append',
                            'text': text + ('' if not text or text.endswith('\n') else '\n') + IGNORE})
    overview = root / KB / 'overview.md'
    if overview.exists():
        actions.append({'path': f'{KB}/overview.md', 'action': 'unchanged'})
    else:
        title = f'{root.name} 项目总览'
        source = list(sources) or (['self:README.md'] if (root / 'README.md').is_file() else [])
        body = f'# {title}\n\n（待填写：项目做什么、与谁协作、从哪里开始读代码；不超过 1200 字）\n'
        actions.append({'path': f'{KB}/overview.md', 'action': 'create',
                        **({'text': frontmatter.dump({'title': title, 'source': source}, body)}
                           if source else {'requires': ['--source']})})
    if guidance:
        agents = root / 'AGENTS.md'
        text, action = files.merge(files.read_text(agents) if agents.is_file() else None, 'knowledge',
                                   files.block('knowledge', POINTER))
        actions.append({'path': 'AGENTS.md', 'action': action, 'text': text})
        claude = root / 'CLAUDE.md'
        existing = files.read_text(claude) if claude.is_file() else None
        if existing is not None and any(f'@{prefix}AGENTS.md' in files.strip_block(existing, 'claude') for prefix in ('', './')):
            actions.append({'path': 'CLAUDE.md', 'action': 'unchanged'})
        else:
            text, action = files.merge(existing, 'claude', files.block('claude', CLAUDE))
            actions.append({'path': 'CLAUDE.md', 'action': action, 'text': text})
    return actions


def run(root, apply=False, guidance=False, sources=()):
    actions = plan(root, guidance, sources)
    changes = [a for a in actions if a['action'] in ('create', 'append', 'update')]
    if apply:
        require(not any(a.get('requires') for a in actions), SOURCE_REQUIRED)
        for action in changes:
            files.write_text(root / action['path'], action['text'])
    for action in actions:
        action.pop('text', None)
    if not changes:
        summary = '已是最新，无需写入'
    elif apply:
        summary = f'已写入 {len(changes)} 个文件；填写 overview.md 后运行 tw check，再与代码一起提交'
    else:
        summary = f'预览：将写入 {len(changes)} 个文件；确认后加 --apply'
    result = {'applied': apply, 'actions': actions, 'summary': summary}
    config_path = root / KB / 'config.json'
    config = json.loads(files.read_text(config_path)) if config_path.is_file() else {}
    if 'platform' not in config and gitutil.run(root, 'remote', check=False).stdout.strip():
        guide = install.SKILL.parent / 'team-workflow/references/onboarding.md'
        result['platform_hint'] = (f'提示：项目有 git 远端但未配置 platform；如需接入，请读接入指南'
                                   f'“项目平台脚本”：{guide}#项目平台脚本')
    return result


def render(result):
    lines = [result['summary']] + [f'- {a["action"]}：{a["path"]}'
             + ('（需要 ' + '、'.join(a['requires']) + '）' if a.get('requires') else '') for a in result['actions']]
    if result.get('platform_hint'):
        lines.append(result['platform_hint'])
    return '\n'.join(lines) + '\n'
