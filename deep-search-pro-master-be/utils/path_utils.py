"""Session-scoped file resolution, including symlink boundary checks."""
from pathlib import Path, PureWindowsPath
from typing import Optional


def resolve_path(filename: str, session_dir: Optional[str] = None) -> str:
    if not session_dir:
        raise ValueError('文件操作缺少会话上下文')
    root = Path(session_dir).resolve()

    value = filename.replace('\\', '/')

    if not value or '\x00' in value or '..' in value.split('/'):
        raise ValueError('无效文件路径')

    for prefix in ('/workspace/', '/mnt/data/', '/home/user/'):
        if value.startswith(prefix):
            value = value[len(prefix):]
            break
    prefix = f'output/{root.name}/'
    if value.startswith(prefix):
        value = value[len(prefix):]
    elif value.startswith(root.name + '/'):
        value = value[len(root.name) + 1:]

    path = Path(value)
    # 判断有没有盘符(C: D:)与是不是绝对路径,真正拦截的是盘符相对路径，例如 D:report.md
    if PureWindowsPath(value).drive and not path.is_absolute():
        raise ValueError('无效盘符路径')
    target = (path if path.is_absolute() else root / path).resolve()
    #负责拒绝最终位于当前会话目录之外的路径
    if not target.is_relative_to(root) or target == root:
        raise ValueError('只能访问当前会话内的文件')
    return str(target)
