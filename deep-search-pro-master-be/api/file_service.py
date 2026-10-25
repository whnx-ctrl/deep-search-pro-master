"""FileRepository(MySQL元数据) + MinioStorage(MinIO对象存储) + 本地临时workspace工作目录"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import mimetypes
import re
import shutil
import time
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import uuid4

import aiofiles
from fastapi import UploadFile

from api.file_repository import FileRepository
from api.minio_storage import MinioStorage

# Windows 保留设备名，文件名不能叫 CON、COM1 这类，否则 Windows 会报错，文件名校验黑名单
_WINDOWS_DEVICE_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
logger = logging.getLogger(__name__)


class FileService:
    def __init__(
        self,
        *,
        repository: FileRepository,
        storage: MinioStorage,
        output_root: Path,
        upload_root: Path,
        max_file_bytes: int,
        extensions: set[str],
    ) -> None:
        self.repository = repository
        self.storage = storage
        self.output_root = output_root
        self.upload_root = upload_root
        self.max_file_bytes = max_file_bytes
        self.extensions = {suffix.lower() for suffix in extensions}

# 静态工具方法（内部辅助），这个函数用来计算一个文件的 SHA-256 哈希值，它判断的是“文件内容是否相同”
    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

   # 文件名安全校验
    def _validate_filename(self, value: str) -> str:
        if (
            not value
            or value != Path(value).name
            or re.search(r'[<>:"/\\|?*\x00-\x1f]', value)
            or value.endswith((" ", "."))
            or value.split(".")[0].upper() in _WINDOWS_DEVICE_NAMES
        ):
            raise ValueError("文件名不能包含路径或特殊字符")
        if Path(value).suffix.lower() not in self.extensions:
            raise ValueError("仅支持 TXT、Markdown、PDF、DOCX 和 XLSX")
        return value

    # 从数据库拿到 workspace_name，拼接成本地文件路径
    @staticmethod
    def _safe_workspace_path(workspace: Path, workspace_name: str) -> Path:
        #把传入的名字，解析成 Posix 风格路径对象（Linux 路径格式，统一用 `/`）
        relative = PurePosixPath(workspace_name)
        if relative.is_absolute() or ".." in relative.parts or not relative.parts:
            raise ValueError("数据库中的工作区文件名无效")
        target = (workspace / Path(*relative.parts)).resolve()
        root = workspace.resolve()
        if not target.is_relative_to(root) or target == root:
            raise ValueError("数据库中的工作区文件名越界")
        return target

    # 自动重命名，避免同会话重名文件
    @staticmethod
    def _unique_name(name: str, occupied: set[str]) -> str:
        # occupied：当前会话已经存在的 workspace_name 集合，来自 repository.workspace_names()
        candidate = name
        path = Path(name)
        index = 1
        while candidate.casefold() in occupied:
            candidate = f"{path.stem} ({index}){path.suffix}"
            index += 1
        # .casefold()：大小写不敏感，A.TXT 和 a.txt 视为重名
        occupied.add(candidate.casefold())
        return candidate

    @staticmethod
    def _response(row: dict[str, Any]) -> dict[str, Any]:
        created_at = row.get("created_at")
        return {
            "uuid": str(row["uuid"]),
            "originalName": row["original_name"],
            "workspaceName": row["workspace_name"],
            "contentType": row["content_type"],
            "sizeBytes": int(row["size_bytes"]),
            "source": row["file_source"],
            "createdAt": created_at.isoformat() + "Z" if created_at else None,
        }

    async def upload_files(
            self,
            *,
            thread_uuid: str,
            uploads: list[UploadFile],
    ) -> list[dict[str, Any]]:
        # 查询当前会话已经存在的工作空间文件名，用来做重名判断
        existing = await self.repository.workspace_names(thread_uuid)
        # 全部转小写存入集合，大小写不敏感判断重名
        occupied = {name.casefold() for name in existing}
        # 当前会话上传文件的本地临时缓存目录
        staging = self.upload_root / f"session_{thread_uuid}"
        # 目录不存在就创建，已存在不会报错
        staging.mkdir(parents=True, exist_ok=True)
        # 保存每个文件上传结果（成功/失败），最后返回给前端
        results: list[dict[str, Any]] = []

        try:
            # 循环处理本次批量上传的每一个文件
            for upload in uploads:
                file_uuid: str | None = None
                temp_path: Path | None = None
                # 获取前端传上来的原始文件名，为空则赋值空字符串
                name = upload.filename or ""
                try:
                    # 1. 文件名安全校验：非法字符、禁止后缀、Windows保留名校验
                    original_name = self._validate_filename(name)
                    # 生成会话内唯一展示名称，重名自动追加 (1)、(2)
                    workspace_name = self._unique_name(original_name, occupied)
                    # 生成全局唯一文件ID，对外接口使用
                    file_uuid = str(uuid4())
                    # 构造MinIO中的对象路径，用户上传文件统一放在 uploads 路径下，和agent生成文件隔离
                    object_key = (
                        f"sessions/{thread_uuid}/uploads/{file_uuid}/{original_name}"
                    )
                    # 自动识别文件MIME类型：优先取fastapi上传自带类型，其次猜测，兜底二进制流
                    content_type = (
                            upload.content_type
                            or mimetypes.guess_type(original_name)[0]
                            or "application/octet-stream"
                    )
                    # 2. MySQL插入pending状态记录：先登记元数据，代表开始上传流程
                    await self.repository.create_pending(
                        file_uuid=file_uuid,
                        thread_uuid=thread_uuid,
                        original_name=original_name,
                        workspace_name=workspace_name,
                        object_key=object_key,
                        content_type=content_type,
                        file_source="uploaded",
                    )
                    # 生成本地临时文件路径，临时文件只做中转，上传完立刻删除
                    temp_path = staging / f"{file_uuid}{Path(original_name).suffix.lower()}"
                    size_bytes = 0
                    digest = hashlib.sha256()
                    # 异步打开临时文件，分片写入（1MB一片，避免大文件一次性占满内存）
                    async with aiofiles.open(temp_path, "wb") as stream:
                        while chunk := await upload.read(1024 * 1024):
                            size_bytes += len(chunk)
                            # 超过单文件大小上限，直接抛出异常拦截
                            if size_bytes > self.max_file_bytes:
                                raise ValueError("单个文件不能超过 20 MiB")
                            # 累加计算sha256，用于后续文件完整性校验
                            digest.update(chunk)
                            # 分片写入本地临时文件
                            await stream.write(chunk)
                    # 4. 将本地临时文件上传到MinIO对象存储
                    await self.storage.upload(object_key, temp_path, content_type)
                    # 5. 上传成功：更新数据库状态为ready，回填真实大小和sha256哈希
                    await self.repository.mark_ready(
                        file_uuid,
                        size_bytes=size_bytes,
                        sha256=digest.hexdigest(),
                    )
                    # 记录成功结果，放入结果列表
                    results.append({
                        "uuid": file_uuid,
                        "name": workspace_name,
                        "status": "uploaded",
                        "size": size_bytes,
                    })
                except Exception as exc:
                    # 任意异常进入这里：标记数据库状态为 failed
                    if file_uuid:
                        try:
                            await self.repository.mark_failed(file_uuid)
                        except Exception:
                            logger.exception("Failed to mark upload metadata as failed: %s", file_uuid)
                    # 区分业务校验异常和未知异常，返回给前端不同提示
                    if isinstance(exc, ValueError):
                        message = str(exc)
                    else:
                        logger.exception("File upload failed: %s", file_uuid or name)
                        message = "上传失败，请检查后端日志"
                    # 记录失败结果
                    results.append({"name": name or "未命名文件", "status": "failed", "error": message})
                finally:
                    # 【无论成功失败】删除本地临时中转文件，防止磁盘堆积垃圾
                    if temp_path:
                        temp_path.unlink(missing_ok=True)
        finally:
            # 全部文件处理完后，尝试删除这个会话的临时文件夹（只有空目录才会删掉）
            await asyncio.to_thread(self._remove_empty_tree, staging)
        # 返回全部文件的上传结果给前端
        return results

    async def list_files(self, *, thread_uuid: str) -> list[dict[str, Any]]:
        # 1. 调用 repository，从 MySQL 查询该会话所有 ready、未软删除的文件元数据
        # 2. 遍历每一行数据库记录，用 _response 做格式转换（蛇形 → 前端驼峰）
        # 3. 返回格式化后的文件列表，直接给到前端 /api/files 接口
        return [self._response(row) for row in await self.repository.list_ready(thread_uuid)]

    async def create_download_url(self, *, file_uuid: str) -> dict[str, Any]:
        # 根据文件id去查MySQL，只查状态ready、未被软删的文件
        row = await self.repository.get_ready(file_uuid)
        # 查不到：文件不存在、已删除、还没上传成功，抛异常
        if not row:
            raise FileNotFoundError("文件不存在或不可下载")
        # 调用MinIO存储服务，生成限时预签名下载链接
        return {
            "downloadUrl": await self.storage.presigned_download_url(
                row["object_key"],  # MinIO里面文件的唯一key
                row["workspace_name"],  # 前端下载时显示的文件名（自动去重后的名字）
            ),
            "expiresIn": self.storage.download_expires_seconds,  # 链接有效期，单位秒
            "filename": row["workspace_name"],  # 给前端展示的文件名
        }

# Agent 跑任务之前，把会话里所有用户上传文件从 MinIO 下载到本地 workspace，做完整性校验，生成一份文件哈希清单。
    async def prepare_workspace(self, *, thread_uuid: str, workspace: Path) -> dict[str, str]:
        # 先清空本次Agent要使用的工作目录，防止残留旧文件干扰
        await self.cleanup_workspace(workspace)
        # 重建工作目录
        workspace.mkdir(parents=True, exist_ok=True)
        # manifest：清单字典 key=文件相对路径，value=sha256哈希，用来区分原始输入文件
        manifest: dict[str, str] = {}
        # 查出这个会话所有可用文件
        for row in await self.repository.list_ready(thread_uuid):
            # 安全拼接路径，防路径穿越攻击，文件一定落在workspace内部
            target = self._safe_workspace_path(workspace, row["workspace_name"])
            # 从MinIO把文件下载到本地工作目录，给Agent读取使用
            await self.storage.download(row["object_key"], target)
            # 计算下载后本地文件的sha256（sha256是同步阻塞函数，丢到线程执行）
            digest = await asyncio.to_thread(self._sha256, target)
            # 如果数据库里存了哈希，对比校验；不一致说明文件损坏/篡改，直接报错终止
            if row["sha256"] and digest != row["sha256"]:
                raise RuntimeError(f"文件完整性校验失败：{row['workspace_name']}")
            # 写入清单：相对路径 -> 哈希
            manifest[target.relative_to(workspace).as_posix()] = digest

        # 返回清单给后面 publish_generated_files 使用
        return manifest

    # Agent 在本地 workspace 跑完之后，把新生成/改动过的文件上传 MinIO + 写入 MySQL 元数据；
    # 原始未修改的上传文件直接跳过，避免重复存储
    async def publish_generated_files(
            self,
            *,
            thread_uuid: str,
            workspace: Path,
            input_manifest: dict[str, str],
    ) -> list[dict[str, Any]]:
        # 获取当前会话已有的文件名，用来做重名判断
        existing = await self.repository.workspace_names(thread_uuid)
        # 全部转小写，大小写不敏感查重名
        occupied = {name.casefold() for name in existing}
        # 存放本次成功发布的文件信息，最后返回给上层
        published: list[dict[str, Any]] = []
        # 遍历工作目录下所有文件（排序遍历）
        for path in sorted(item for item in workspace.rglob("*") if item.is_file()):
            # 拿到文件相对于workspace的路径，posix格式统一用 /
            relative = path.relative_to(workspace).as_posix()
            # 计算该文件sha256哈希（同步阻塞，丢线程跑）
            digest = await asyncio.to_thread(self._sha256, path)
            # ✅ 核心判断：和prepare_workspace传进来的清单对比
            # 路径相同、哈希一样 = 用户原始上传文件，没有改动，跳过不上传
            if input_manifest.get(relative) == digest:
                continue
            # 后缀不在允许列表里，直接跳过该文件
            if path.suffix.lower() not in self.extensions:
                continue
            # 文件名安全校验
            original_name = self._validate_filename(path.name)
            # 生成会话内唯一名称，重名自动加 (1)、(2)
            workspace_name = self._unique_name(original_name, occupied)
            # 生成文件唯一ID
            file_uuid = str(uuid4())
            # MinIO路径：generated目录，专门存放Agent生成的文件，和用户上传uploads分开
            object_key = (
                f"sessions/{thread_uuid}/generated/{file_uuid}/{original_name}"
            )
            # 猜测MIME类型，兜底二进制
            content_type = mimetypes.guess_type(original_name)[0] or "application/octet-stream"
            # MySQL先插入pending记录，标记开始处理这个生成文件，来源是generated（Agent产出）
            await self.repository.create_pending(
                file_uuid=file_uuid,
                thread_uuid=thread_uuid,
                original_name=original_name,
                workspace_name=workspace_name,
                object_key=object_key,
                content_type=content_type,
                file_source="generated",
            )
            try:
                # 把Agent生成的这个文件上传MinIO
                await self.storage.upload(object_key, path, content_type)
                # 上传成功，更新数据库为ready，填入大小和哈希
                await self.repository.mark_ready(
                    file_uuid,
                    size_bytes=path.stat().st_size,
                    sha256=digest,
                )
            except Exception:
                # 上传异常兜底：删掉MinIO里残留的文件，数据库标记失败，然后向外抛异常
                try:
                    await self.storage.remove(object_key)
                finally:
                    await self.repository.mark_failed(file_uuid)
                raise

            # 查询这条新文件记录，转成前端格式，加入结果列表
            row = await self.repository.get_ready(file_uuid)
            if row:
                published.append(self._response(row))
        return published

# 删除一个会话全部文件：清 MinIO 文件、标记 MySQL 会话已删除、清理本地所有临时工作目录
    async def delete_session_files(self, *, thread_uuid: str) -> None:
        # 查询该会话所有还存在的文件记录（MySQL里的runs+events关联的文件）
        rows = await self.repository.list_active_for_session(thread_uuid)
        if rows:
            # 标记会话任务状态为删除中，防止并发读写
            await self.repository.mark_session_deleting(thread_uuid)
            # 循环，逐个从MinIO删除对应的对象文件
            for row in rows:
                await self.storage.remove(row["object_key"])
            # MySQL侧做软删除：不是直接DELETE，而是更新状态，前端看不见了，但数据还在库里（可追溯）
            await self.repository.soft_delete_session(thread_uuid)
        # 并行清理两处本地临时目录：Agent输出目录、上传中转目录
        await asyncio.gather(
            self.cleanup_workspace(self.output_root / f"session_{thread_uuid}"),
            self.cleanup_workspace(self.upload_root / f"session_{thread_uuid}"),
        )

    async def cleanup_workspace(self, workspace: Path) -> None:
        # shutil.rmtree 是同步阻塞删除文件夹，丢到线程里执行，不阻塞async事件循环
        # 第二个参数 True：文件夹不存在也不会抛错
        await asyncio.to_thread(shutil.rmtree, workspace, True)

    # 用来在后端启动时，清理因为异常退出而遗留太久的本地临时会话目录。，一般在lifespan里面调用
    async def cleanup_stale_workspaces(self, *, max_age_hours: int) -> None:
        # 计算时间阈值：当前时间减去最大保留时长，早于这个时间就是过期目录
        cutoff = time.time() - max_age_hours * 3600
        # 遍历两个根目录：Agent输出目录、上传临时目录
        for root in (self.output_root, self.upload_root):
            if not root.exists():
                continue
            # 匹配所有 session_ 开头的会话文件夹
            for path in root.glob("session_*"):
                try:
                    # 是文件夹，并且最后修改时间早于阈值 → 过期，直接删除
                    if path.is_dir() and path.stat().st_mtime < cutoff:
                        await self.cleanup_workspace(path)
                except FileNotFoundError:
                    # 遍历过程中文件夹已经被别的逻辑删掉了，忽略
                    pass

    @staticmethod
    def _remove_empty_tree(path: Path) -> None:
        try:
            # rmdir 只能删除空文件夹
            path.rmdir()
        except (FileNotFoundError, OSError):
            # 文件夹不存在 / 里面还有文件（非空），直接忽略，不抛异常
            pass
