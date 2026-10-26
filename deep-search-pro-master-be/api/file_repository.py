"""Async persistence for workbench file metadata."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import URL, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


FILES_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS files (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '内部自增主键',
    uuid CHAR(36) NOT NULL COMMENT '对外文件UUID',
    thread_uuid CHAR(36) NOT NULL COMMENT '所属会话UUID',
    original_name VARCHAR(255) NOT NULL COMMENT '上传或生成时的原始文件名',
    workspace_name VARCHAR(255) NOT NULL COMMENT 'Agent工作区中的唯一文件名',
    object_key VARCHAR(512) NOT NULL COMMENT 'MinIO对象键，不含bucket和endpoint',
    content_type VARCHAR(128) NOT NULL DEFAULT 'application/octet-stream' COMMENT 'MIME类型',
    size_bytes BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '文件大小，字节',
    sha256 CHAR(64) NOT NULL COMMENT '文件SHA-256摘要',
    file_source VARCHAR(16) NOT NULL COMMENT 'uploaded或generated',
    file_status VARCHAR(16) NOT NULL COMMENT 'pending、ready、failed、deleting',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '创建时间，UTC',
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
        ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '更新时间，UTC',
    deleted_at DATETIME(3) NULL DEFAULT NULL COMMENT '软删除时间，NULL表示未删除',
    PRIMARY KEY pk_id (id),
    UNIQUE KEY uk_uuid (uuid),
    UNIQUE KEY uk_object_key (object_key),
    KEY idx_thread_uuid_id (thread_uuid, id),
    KEY idx_thread_uuid_status_id (thread_uuid, file_status, id)
)
ENGINE=InnoDB
DEFAULT CHARACTER SET=utf8mb4
COLLATE=utf8mb4_0900_ai_ci
COMMENT='工作台文件元信息'
"""


class FileRepository:
    """Owns SQL access to the workbench ``files`` table."""

    def __init__(self, database_url: URL | str) -> None:
        self._engine: AsyncEngine = create_async_engine(
            database_url, # 接收数据库连接地址
            pool_pre_ping=True, # 每次从池拿连接前先探活
            pool_recycle=1800,  # 连接最长存活 30 分钟
        )

    async def open(self) -> None:
        async with self._engine.begin() as connection:
            await connection.execute(text("SELECT 1"))
            await connection.execute(text(FILES_TABLE_DDL))

    async def close(self) -> None:
        await self._engine.dispose()


    # FileService 传入文件元数据
    #           ↓
    # create_pending() 创建 SQL 参数
    #           ↓
    # 向 files 表插入一条记录
    #           ↓
    # 初始状态设为 pending
    #           ↓
    # 等待 MinIO 上传
    # pending 表示：数据库已经知道有这个文件，但真实文件尚未确认成功保存。
    async def create_pending(
        self,
        *,
        file_uuid: str,
        thread_uuid: str,
        original_name: str,
        workspace_name: str,
        object_key: str,
        content_type: str,
        file_source: str,
    ) -> None:
        statement = text(
            """
            INSERT INTO files (
                uuid, thread_uuid, original_name, workspace_name, object_key,
                content_type, size_bytes, sha256, file_source, file_status
            ) VALUES (
                :uuid, :thread_uuid, :original_name, :workspace_name, :object_key,
                :content_type, 0, '', :file_source, 'pending'
            )
            """
        )
        async with self._engine.begin() as connection:
            await connection.execute(statement, {
                "uuid": file_uuid,
                "thread_uuid": thread_uuid,
                "original_name": original_name,
                "workspace_name": workspace_name,
                "object_key": object_key,
                "content_type": content_type,
                "file_source": file_source,
            })


    # ready 表示:件元数据完整，并且已经确认 MinIO 上传成功，可以向前端展示和下载。
    async def mark_ready(self, file_uuid: str, *, size_bytes: int, sha256: str) -> None:
        async with self._engine.begin() as connection:
            await connection.execute(text(
                """
                UPDATE files
                SET file_status = 'ready', size_bytes = :size_bytes, sha256 = :sha256
                WHERE uuid = :uuid AND deleted_at IS NULL
                """
            ), {"uuid": file_uuid, "size_bytes": size_bytes, "sha256": sha256})

   #failed 表示：这次文件处理没有成功，可以排查或清理。
    async def mark_failed(self, file_uuid: str) -> None:
        async with self._engine.begin() as connection:
            await connection.execute(text(
                """
                UPDATE files SET file_status = 'failed'
                WHERE uuid = :uuid AND deleted_at IS NULL
                """
            ), {"uuid": file_uuid})

   # 查询一个会话可用的文件
    async def list_ready(self, thread_uuid: str) -> list[dict[str, Any]]:
        async with self._engine.connect() as connection:
            rows = await connection.execute(text(
                """
                SELECT uuid, thread_uuid, original_name, workspace_name, object_key,
                       content_type, size_bytes, sha256, file_source, file_status,
                       created_at, updated_at
                FROM files
                WHERE thread_uuid = :thread_uuid
                  AND file_status = 'ready'
                  AND deleted_at IS NULL
                ORDER BY id ASC
                """
            ), {"thread_uuid": thread_uuid})
            # rows.mappings()：把每一行结果变成字典映射(RowMapping)，键就是数据库字段名
            # dict(row)：把这个 RowMapping 转成普通 Python 字典
            return [dict(row) for row in rows.mappings()]

    # 根据 file_uuid 查询可下载文件,uuid 逻辑唯一，LIMIT 1 + first 是防御性兜底,可以给前端展示下载的文件
    async def get_ready(self, file_uuid: str) -> dict[str, Any] | None:
        async with self._engine.connect() as connection:
            row = await connection.execute(text(
                """
                SELECT uuid, thread_uuid, original_name, workspace_name, object_key,
                       content_type, size_bytes, sha256, file_source, file_status,
                       created_at, updated_at
                FROM files
                WHERE uuid = :uuid AND file_status = 'ready' AND deleted_at IS NULL
                LIMIT 1
                """
            ), {"uuid": file_uuid})
            item = row.mappings().first()
            return dict(item) if item else None

   #拿到这个会话（thread_uuid）下所有还没被软删除的文件,给后台清理逻辑用，不给前端文件列表
    async def list_active_for_session(self, thread_uuid: str) -> list[dict[str, Any]]:
        async with self._engine.connect() as connection:
            rows = await connection.execute(text(
                """
                SELECT uuid, object_key, file_status
                FROM files
                WHERE thread_uuid = :thread_uuid AND deleted_at IS NULL
                ORDER BY id ASC
                """
            ), {"thread_uuid": thread_uuid})
            return [dict(row) for row in rows.mappings()]

    # 1.先调用 mark_session_deleting，标记状态为 deleting
    # 2. 循环每个 object_key，去 MinIO 删除真实文件
    # 3. 全部删完 MinIO 之后，再调用 soft_delete_session，打上 deleted_at 软删除时间
    async def mark_session_deleting(self, thread_uuid: str) -> None:
        async with self._engine.begin() as connection:
            await connection.execute(text(
                """
                UPDATE files SET file_status = 'deleting'
                WHERE thread_uuid = :thread_uuid AND deleted_at IS NULL
                """
            ), {"thread_uuid": thread_uuid})

    async def soft_delete_session(self, thread_uuid: str) -> None:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        async with self._engine.begin() as connection:
            await connection.execute(text(
                """
                UPDATE files SET deleted_at = :deleted_at
                WHERE thread_uuid = :thread_uuid AND deleted_at IS NULL
                """
            ), {"thread_uuid": thread_uuid, "deleted_at": now})

    # 检查当前会话中已经使用了哪些本地文件名，上传新文件时，为新文件分配不会覆盖其他文件的工作区名称
    async def workspace_names(self, thread_uuid: str) -> set[str]:
        async with self._engine.connect() as connection:
            rows = await connection.execute(text(
                """
                SELECT workspace_name FROM files
                WHERE thread_uuid = :thread_uuid AND deleted_at IS NULL
                """
            ), {"thread_uuid": thread_uuid})
            return {str(row[0]) for row in rows}
