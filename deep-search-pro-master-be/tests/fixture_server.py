"""Isolated browser-test backend; never calls a real model."""
import asyncio
import sys
import tempfile
import types
from pathlib import Path
from api import server
from api.monitor import monitor

temporary = tempfile.TemporaryDirectory(prefix='deep-search-e2e-')
root = Path(temporary.name)
server.DATA = root / 'data'
server.OUTPUT = root / 'output'
server.UPLOAD = root / 'updated'
server.CHECKPOINTS = server.DATA / 'checkpoints.sqlite3'


async def fake_agent(query, thread_id, checkpointer):
    monitor.report_session_dir('')
    monitor.report_assistant('受控测试助手')
    monitor.report_tool('测试文件生成')
    await asyncio.sleep(1)
    if '失败' in query:
        raise RuntimeError('deliberate test failure')
    directory = server.session_root(thread_id)
    directory.mkdir(parents=True, exist_ok=True)
    answer = '# 研究报告\n\n运行成功，已完成资料整理。\n\n| 方向 | 结论 |\n| --- | --- |\n| 测试 | 链路正常 |'
    (directory / 'report.md').write_text(answer, encoding='utf-8')
    return answer


module = types.ModuleType('agent.main_agent')
module.run_deep_agent = fake_agent
sys.modules['agent.main_agent'] = module
app = server.app
