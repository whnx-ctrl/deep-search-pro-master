import asyncio
import os
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient
from langgraph.checkpoint.base import empty_checkpoint
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from api import server
from api.monitor import monitor, manager
from api.task_store import TaskStore
from utils.path_utils import resolve_path


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.thread = str(uuid4())
        async def fake_agent(query, thread_id, checkpointer):
            monitor.report_tool('受控测试工具')
            await asyncio.sleep(.15)
            if query == 'fail':
                raise RuntimeError('test failure with secret')
            path = server.OUTPUT / f'session_{thread_id}'
            path.mkdir(parents=True, exist_ok=True)
            (path / 'report.md').write_text('# 测试报告', encoding='utf-8')
            return '# 运行成功'
        self.module = types.ModuleType('agent.main_agent')
        self.module.run_deep_agent = fake_agent
        self.patches = [
            patch.object(server, 'OUTPUT', root / 'output'),
            patch.object(server, 'UPLOAD', root / 'updated'),
            patch.object(server, 'DATA', root / 'data'),
            patch.object(server, 'CHECKPOINTS', root / 'data' / 'checkpoints.sqlite3'),
            patch.dict(sys.modules, {'agent.main_agent': self.module}),
        ]
        for item in self.patches:
            item.start()
        self.client = TestClient(server.app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        manager.active_connections.clear()
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def wait(self, run_id):
        for _ in range(100):
            item = self.client.get('/api/tasks/' + run_id).json()
            if item['status'] in {'succeeded','failed','interrupted'}:
                return item
            time.sleep(.02)
        self.fail('task timed out')

    def test_task_duplicate_and_final_snapshot(self):
        response = self.client.post('/api/task', json={'query':'hello','thread_id':self.thread})
        self.assertEqual(response.status_code, 202)
        duplicate = self.client.post('/api/task', json={'query':'hello','thread_id':self.thread})
        self.assertEqual(duplicate.status_code, 409)
        result = self.wait(response.json()['run_id'])
        self.assertEqual(result['status'], 'succeeded')
        self.assertEqual(result['result'], '# 运行成功')
        self.assertEqual(len([e for e in result['events'] if e['event']=='task_result']), 1)

    def test_error_is_terminal_and_sanitized(self):
        response = self.client.post('/api/task', json={'query':'fail','thread_id':self.thread})
        result = self.wait(response.json()['run_id'])
        self.assertEqual(result['status'], 'failed')
        self.assertNotIn('secret', result['error'])
        health = self.client.get('/api/health')
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()['status'], 'ok')

    def test_health_exposes_process_diagnostics(self):
        first = self.client.get('/api/health').json()
        time.sleep(.01)
        second = self.client.get('/api/health').json()
        self.assertEqual(first['pid'], os.getpid())
        self.assertEqual(first['pid'], second['pid'])
        self.assertEqual(first['started_at'], second['started_at'])
        self.assertGreaterEqual(second['uptime_seconds'], first['uptime_seconds'])

    def test_unhandled_background_failure_is_consumed(self):
        async def exercise():
            async def fail_outside_agent_boundary():
                raise RuntimeError('background failure')

            task = asyncio.create_task(fail_outside_agent_boundary())
            server.app.state.tasks.add(task)
            task.add_done_callback(server.task_finished)
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            self.assertNotIn(task, server.app.state.tasks)
            self.assertIsInstance(task.exception(), RuntimeError)

        with self.assertLogs(server.logger, level='ERROR') as logs:
            asyncio.run(exercise())
        self.assertTrue(any('Unhandled background task failure' in line for line in logs.output))

    def test_reload_is_opt_in(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(server.env_flag('BACKEND_RELOAD'))
        with patch.dict(os.environ, {'BACKEND_RELOAD': 'true'}, clear=True):
            self.assertTrue(server.env_flag('BACKEND_RELOAD'))

    def test_upload_download_and_boundary(self):
        response = self.client.post('/api/upload', data={'thread_id':self.thread},
                                    files=[('files', ('notes.txt', b'hello','text/plain'))])
        self.assertEqual(response.json()['files'][0]['status'], 'uploaded')
        response = self.client.post('/api/upload', data={'thread_id':self.thread},
                                    files=[('files', ('../../escape.txt', b'bad','text/plain'))])
        self.assertEqual(response.json()['files'][0]['status'], 'failed')
        response = self.client.get('/api/files', params={'thread_id':self.thread})
        self.assertEqual(response.json()['files'][0]['source'], 'uploaded')
        self.assertEqual(self.client.get('/api/download', params={'thread_id':self.thread, 'path':'notes.txt'}).content, b'hello')
        self.assertEqual(self.client.get('/api/download', params={'thread_id':self.thread, 'path':'../../.env'}).status_code, 403)
        with patch.object(server, 'MAX_FILE_BYTES', 3):
            response = self.client.post('/api/upload', data={'thread_id':self.thread},
                                        files=[('files',('big.txt',b'1234','text/plain'))])
            self.assertEqual(response.json()['files'][0]['status'], 'failed')
        self.assertFalse((server.session_root(self.thread) / 'big.txt').exists())

    def test_multiple_connections_survive_old_disconnect(self):
        with self.client.websocket_connect('/ws/' + self.thread) as first:
            self.assertEqual(first.receive_json()['type'], 'ready')
            with self.client.websocket_connect('/ws/' + self.thread) as second:
                self.assertEqual(second.receive_json()['type'], 'ready')
                first.close()
                second.send_text('ping')
                self.assertEqual(second.receive_json()['type'], 'pong')
                response = self.client.post('/api/task', json={'query':'hello','thread_id':self.thread})
                self.assertEqual(second.receive_json()['event'], 'tool_start')
                self.wait(response.json()['run_id'])

    def test_delete_session_removes_tasks_files_and_checkpoint(self):
        response = self.client.post('/api/task', json={'query':'hello','thread_id':self.thread})
        self.assertEqual(response.status_code, 202)
        run_id = response.json()['run_id']
        self.wait(run_id)

        response = self.client.post('/api/upload', data={'thread_id':self.thread},
                                    files=[('files', ('notes.txt', b'hello', 'text/plain'))])
        self.assertEqual(response.status_code, 200)
        output_directory = server.session_root(self.thread)
        upload_directory = server.UPLOAD / f'session_{self.thread}'
        self.assertTrue(output_directory.exists())
        self.assertTrue(upload_directory.exists())
        self.assertIsNotNone(server.app.state.store.get(run_id))

        with patch.object(server.app.state.checkpointer, 'adelete_thread',
                          new_callable=AsyncMock) as delete_checkpoint:
            response = self.client.delete(f'/api/sessions/{self.thread}')

        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.content, b'')
        delete_checkpoint.assert_awaited_once_with(self.thread)
        self.assertIsNone(server.app.state.store.get(run_id))
        self.assertFalse(output_directory.exists())
        self.assertFalse(upload_directory.exists())

        with patch.object(server.app.state.checkpointer, 'adelete_thread',
                          new_callable=AsyncMock):
            repeated = self.client.delete(f'/api/sessions/{self.thread}')
        self.assertEqual(repeated.status_code, 204)

    def test_running_session_cannot_be_deleted(self):
        response = self.client.post('/api/task', json={'query':'hello','thread_id':self.thread})
        self.assertEqual(response.status_code, 202)
        run_id = response.json()['run_id']
        response = self.client.delete(f'/api/sessions/{self.thread}')
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['error']['code'], 'session_busy')
        self.wait(run_id)

    def test_invalid_delete_session_uuid(self):
        response = self.client.delete('/api/sessions/not-a-valid-uuid')
        self.assertEqual(response.status_code, 422)

    def test_empty_session_can_be_deleted_before_first_checkpoint(self):
        response = self.client.delete(f'/api/sessions/{self.thread}')
        self.assertEqual(response.status_code, 204)

    def test_invalid_session_and_blank_query(self):
        self.assertEqual(self.client.post('/api/task', json={'query':'  '}).status_code, 422)
        self.assertEqual(self.client.post('/api/upload', data={'thread_id':'../../x'},
                                         files=[('files',('a.txt',b'x'))]).status_code, 422)


class StoreAndPathTests(unittest.TestCase):
    def test_path_escape(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'session'
            root.mkdir()
            for value in ('../../.env', str(Path(temp) / '.env'), 'updated/../../.env'):
                with self.assertRaises(ValueError):
                    resolve_path(value, str(root))
            self.assertEqual(Path(resolve_path('sub/a.md', str(root))), root / 'sub' / 'a.md')

    def test_terminal_and_restart(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'runs.db'
            store = TaskStore(path)
            run = store.create(str(uuid4()))
            store.close()
            store = TaskStore(path)
            self.assertEqual(store.get(run)['status'], 'interrupted')
            run = store.create(str(uuid4()))
            for _ in range(260):
                store.append(run, {'event':'tool_start','message':'x','data':{}})
            self.assertEqual(len(store.get(run)['events']), 250)
            self.assertTrue(store.get(run)['truncated'])
            store.append(run, {'event':'task_result','message':'done','data':{'result':'yes'}})
            self.assertIsNone(store.append(run, {'event':'error','message':'no','data':{}}))
            self.assertEqual(store.get(run)['result'], 'yes')
            store.close()

    def test_sql_rejects_mutation_and_limits(self):
        from tools.db_tools import get_db_config, validate_query
        for query in ('DELETE FROM products', 'SELECT * FROM products; DROP TABLE products',
                      "SELECT * FROM products INTO OUTFILE 'x'", 'SELECT SLEEP(30)',
                      'SELECT * FROM other.products', 'SELECT * FROM products FOR UPDATE'):
            with self.assertRaises(ValueError, msg=query):
                validate_query(query, {'products'})
        self.assertIn('LIMIT 100', validate_query('SELECT * FROM products', {'products'}))
        with patch.dict(os.environ, {
            'MYSQL_USER': 'reader',
            'MYSQL_PASSWORD': 'secret',
            'MYSQL_DATABASE': 'analytics',
        }, clear=True):
            self.assertIs(get_db_config()['use_pure'], True)


class CheckpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_checkpoint_survives_reopen_and_can_be_deleted(self):
        with tempfile.TemporaryDirectory() as temp:
            database = Path(temp) / 'checkpoints.sqlite3'
            thread_id = str(uuid4())
            config = {
                'configurable': {
                    'thread_id': thread_id,
                    'checkpoint_ns': '',
                }
            }
            checkpoint = empty_checkpoint()
            checkpoint['channel_values'] = {'remembered_value': '重启后仍然存在'}

            async with AsyncSqliteSaver.from_conn_string(str(database)) as saver:
                await saver.aput(config, checkpoint, {}, {})

            async with AsyncSqliteSaver.from_conn_string(str(database)) as saver:
                restored = await saver.aget_tuple(config)
                self.assertIsNotNone(restored)
                self.assertEqual(
                    restored.checkpoint['channel_values']['remembered_value'],
                    '重启后仍然存在',
                )
                await saver.adelete_thread(thread_id)
                deleted = await saver.aget_tuple(config)

            self.assertIsNone(deleted)


if __name__ == '__main__':
    unittest.main()
