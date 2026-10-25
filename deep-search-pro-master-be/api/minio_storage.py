"""Small asynchronous facade around the synchronous MinIO SDK."""
from __future__ import annotations

import asyncio
from datetime import timedelta
from pathlib import Path
from urllib.parse import quote

from minio import Minio
from minio.error import S3Error


class MinioStorage:
    def __init__(
        self,
        *,
        endpoint: str,
        public_endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        secure: bool,
        download_expires_seconds: int,
    ) -> None:
        if not access_key or not secret_key:
            raise ValueError("MINIO_ACCESS_KEY 和 MINIO_SECRET_KEY 不能为空")
        self.bucket = bucket
        self.download_expires_seconds = download_expires_seconds
        self._client = Minio(
            endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
        )
        self._public_client = Minio(
            public_endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
        )

    # 检查bucket是否存在，不存在就创建 bucket
    async def ensure_bucket(self) -> None:
        exists = await asyncio.to_thread(self._client.bucket_exists, self.bucket)
        if not exists:
            await asyncio.to_thread(self._client.make_bucket, self.bucket)

    # 上传本地文件
    async def upload(self, object_key: str, path: Path, content_type: str) -> None:
        await asyncio.to_thread(
            self._client.fput_object,
            self.bucket,
            object_key,
            str(path),
            content_type,
        )

    # 下载对象到本地临时目录
    async def download(self, object_key: str, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(
            self._client.fget_object,
            self.bucket,
            object_key,
            str(path),
        )

    # 删除对象
    async def remove(self, object_key: str) -> None:
        try:
            await asyncio.to_thread(
                self._client.remove_object,
                self.bucket,
                object_key,
            )
        except S3Error as exc:
            if exc.code not in {"NoSuchKey", "NoSuchObject"}:
                raise
    # 生成 MinIO 预签名下载链接，给前端浏览器直接下载文件，链接有过期时间
    async def presigned_download_url(self, object_key: str, filename: str) -> str:
        # attachment：告诉浏览器，打开这个链接弹出下载框，而不是直接在页面预览
        disposition = f"attachment; filename*=UTF-8''{quote(filename)}"
        return await asyncio.to_thread(
            self._public_client.presigned_get_object,
            self.bucket,
            object_key,
            # 链接有效期
            expires=timedelta(seconds=self.download_expires_seconds),
            # response-content-disposition：MinIO 返回文件时带上这个响应头，控制下载文件名
            response_headers={"response-content-disposition": disposition},
        )
