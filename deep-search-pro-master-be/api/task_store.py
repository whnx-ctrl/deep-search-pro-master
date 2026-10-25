"""前端刷新后仍需要恢复任务状态；仅把状态保存在 Python 内存中无法做到这一点。"""
import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

# 终止状态集合，任务到这三种状态后，不再接收新增事件
TERMINAL = {'succeeded', 'failed', 'interrupted'}

# 每个任务最多保留最近 250 条事件，防止单任务事件无限膨胀，自动删旧事件
MAX_EVENTS = 250


def now():
    # datetime.now(...)：获取当前时间  timezone.utc：指定使用 UTC 时区  isoformat()：转换成标准时间字符串
    return datetime.now(timezone.utc).isoformat()


class TaskStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        # 创建了一个“可重入线程锁”，用于保护多个线程同时访问或修改共享数据
        self.lock = threading.RLock()

        #`check_same_thread=False`允许多个线程共用这一个 db连接
        self.db = sqlite3.connect(path, check_same_thread=False)

        # row_factory：查询结果默认返回元组，取数据只能用下标 row[0]
        # 设置sqlite3.Row：查询结果可以既用下标取，也能用字段名字取，类似字典。
        self.db.row_factory = sqlite3.Row

        #WAL模式：写操作先写到单独的 wal 日志文件，不阻塞读 2. 读操作读取旧版本数据，读写可以并发执行
        self.db.execute('PRAGMA journal_mode=WAL')

        # executescript：一次性执行多条 SQL 语句，第一张表 runs（任务主表，一条记录 = 一次 Agent 任务）
        # PRIMARY KEY(run_id, sequence)联合主键，保证同一个任务里，事件序号唯一
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY, thread_id TEXT NOT NULL,
                status TEXT NOT NULL, result TEXT, error TEXT,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                sequence INTEGER NOT NULL DEFAULT 0);
            CREATE INDEX IF NOT EXISTS run_thread ON runs(thread_id);
            CREATE TABLE IF NOT EXISTS events (
                run_id TEXT NOT NULL, sequence INTEGER NOT NULL,
                payload TEXT NOT NULL, PRIMARY KEY(run_id, sequence));
        """)
        with self.db:
            self.db.execute("UPDATE runs SET status='interrupted', error=?, updated_at=? WHERE status IN ('queued','running')",
                            ('后端已重启，任务已中断，请新建会话重试。', now()))
# self.db：SQLite 事务。块内所有 SQL 属于同一个事务；全部成功自动提交；一旦报错，全部回滚，不会产生脏数据。
# self.lock：拿到线程锁。多线程并发调用这个方法时，同一时间只允许一个线程进入，防止并发创建多条任务。离开代码块自动释放锁。
    def create(self, thread_id):
        with self.lock, self.db:
            if self.db.execute("SELECT 1 FROM runs WHERE thread_id=? AND status IN ('queued','running')", (thread_id,)).fetchone():
                raise ValueError('当前会话已有任务执行中')
            run_id, timestamp = str(uuid4()), now()
            self.db.execute('INSERT INTO runs(run_id,thread_id,status,created_at,updated_at) VALUES(?,?,?,?,?)',
                            (run_id, thread_id, 'queued', timestamp, timestamp))
            return run_id

    def get(self, run_id):
        with self.lock:
            row = self.db.execute('SELECT * FROM runs WHERE run_id=?', (run_id,)).fetchone()
            if not row:
                return None
            item = dict(row)

            # SQL查出多行单行单列的元组；r[0] 取出 JSON 字符串；json.loads(r[0])把字符串转成 Python字典，全部装进 events 数组
            item['events'] = [json.loads(r[0]) for r in self.db.execute('SELECT payload FROM events WHERE run_id=? ORDER BY sequence', (run_id,))]

            # 检查当前拿到的事件列表第一条的序列号是否大于 1；
            # 大于 1 代表最开始的事件已经被清理，打上truncated=True标记
            # 用来告知前端：历史事件不全。
            item['truncated'] = bool(item['events'] and item['events'][0]['sequence'] > 1)
            return item

    def active(self, thread_id):
        with self.lock:
            row = self.db.execute(
                "SELECT run_id FROM runs "
                "WHERE thread_id=? AND status IN ('queued','running')",
                (thread_id,),
            ).fetchone()
            return row[0] if row else None

    def delete_thread(self, thread_id):
        """删除一个会话对应的全部任务记录和事件记录。"""
        with self.lock, self.db:
            self.db.execute(
                """
                DELETE FROM events
                WHERE run_id IN (
                    SELECT run_id FROM runs WHERE thread_id=?
                )
                """,
                (thread_id,),
            )
            self.db.execute(
                'DELETE FROM runs WHERE thread_id=?',
                (thread_id,),
            )

    def running(self, run_id):
        with self.lock, self.db:
            self.db.execute("UPDATE runs SET status='running',updated_at=? WHERE run_id=? AND status='queued'", (now(), run_id))

    def append(self, run_id, payload):
        with self.lock, self.db:
            # 如果是最终态，拒绝再写入
            row = self.db.execute('SELECT status,sequence FROM runs WHERE run_id=?', (run_id,)).fetchone()
            if not row or row['status'] in TERMINAL:
                return None
            seq = row['sequence'] + 1
            event = {**payload, 'run_id': run_id, 'sequence': seq}
            self.db.execute('UPDATE runs SET sequence=?,updated_at=? WHERE run_id=?', (seq, now(), run_id))
            self.db.execute('INSERT INTO events VALUES(?,?,?)', (run_id, seq, json.dumps(event, ensure_ascii=False)))
            self.db.execute('DELETE FROM events WHERE run_id=? AND sequence<=?', (run_id, seq - MAX_EVENTS))
            if payload['event'] in ('task_result', 'error', 'interrupted'):
                # 字典映射，把埋点事件类型，翻译成 runs 表里面存的任务状态
                status = {'task_result': 'succeeded', 'error': 'failed', 'interrupted': 'interrupted'}[payload['event']]
                self.db.execute('UPDATE runs SET status=?,result=?,error=? WHERE run_id=?',
                                (status, payload['data'].get('result'), payload['message'] if status != 'succeeded' else None, run_id))
            return event

    def close(self):
        with self.lock:
            self.db.close()

# 整个调动流程如下：

# 后端启动
#     ↓
# TaskStore.__init__()
#     ↓
# 创建/连接 tasks.sqlite3
#
# 用户发送问题
#     ↓
# create(thread_id)
#     ↓
# 任务状态 queued
#
# 后台任务开始
#     ↓
# running(run_id)
#     ↓
# 任务状态 running
#
# Agent 执行
#     ↓
# 工具或助手产生事件
#     ↓
# monitor._emit()
#     ↓
# append(run_id, event)
#
# 前端查询
#     ↓
# get(run_id)
#     ↓
# 返回状态、事件、结果
#
# Agent 成功
#     ↓
# monitor.report_task_result()
#     ↓
# append(task_result)
#     ↓
# 任务状态 succeeded
#
# 或者 Agent 失败
#     ↓
# append(error)
#     ↓
# 任务状态 failed
#
# 后端关闭
#     ↓
# close()