from __future__ import annotations

import unittest
from unittest.mock import patch

from api.file_repository import FileRepository


class FakeConnection:
    def __init__(self) -> None:
        self.statements: list[str] = []

    async def execute(self, statement) -> None:
        self.statements.append(str(statement))


class FakeTransaction:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection

    async def __aenter__(self) -> FakeConnection:
        return self.connection

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None


class FakeEngine:
    def __init__(self) -> None:
        self.connection = FakeConnection()

    def begin(self) -> FakeTransaction:
        return FakeTransaction(self.connection)

    async def dispose(self) -> None:
        return None


def run_immediate(coroutine) -> None:
    """Drive a coroutine whose test doubles never suspend to an event loop."""
    with unittest.TestCase().assertRaises(StopIteration):
        coroutine.send(None)


class FileRepositoryTests(unittest.TestCase):
    def test_open_probes_connection_and_bootstraps_table_idempotently(self) -> None:
        engine = FakeEngine()
        with patch('api.file_repository.create_async_engine', return_value=engine):
            repository = FileRepository('mysql+asyncmy://user:password@db/app')
            run_immediate(repository.open())
            run_immediate(repository.open())

        self.assertEqual(engine.connection.statements[0], 'SELECT 1')
        self.assertIn('CREATE TABLE IF NOT EXISTS files', engine.connection.statements[1])
        self.assertEqual(engine.connection.statements[2], 'SELECT 1')
        self.assertIn('CREATE TABLE IF NOT EXISTS files', engine.connection.statements[3])


if __name__ == '__main__':
    unittest.main()
