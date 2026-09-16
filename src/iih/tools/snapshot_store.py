"""原文快照与素材原件对象存储（doc-04）：网页 HTML 快照 + 附件原件存 MinIO。

键为内容寻址（内容的 SHA-256）：同内容多采共享对象、put 幂等；
采集（判断层）写入、Web 快照回放与素材管线读出，均经本模块，不散落客户端调用。
"""

import hashlib
import io

from minio import Minio

SNAPSHOT_CONTENT_TYPE = "text/html; charset=utf-8"
AUDIO_CONTENT_TYPE = "audio/mpeg"


def snapshot_key(html: str) -> str:
    """内容寻址对象键。"""
    return f"snapshots/{hashlib.sha256(html.encode('utf-8')).hexdigest()}.html"


def material_key(data: bytes, ext: str) -> str:
    """素材原件内容寻址键（doc-04 §1 materials/ 前缀）。"""
    return f"materials/{hashlib.sha256(data).hexdigest()}.{ext}"


class SnapshotStore:
    """MinIO 快照仓：桶不存在时自建（幂等），put/get 以键存取。"""

    def __init__(
        self,
        *,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        secure: bool = False,
    ) -> None:
        client = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure)
        if not client.bucket_exists(bucket):
            client.make_bucket(bucket)
        self._client = client
        self._bucket = bucket

    def put_html(self, html: str) -> str:
        """存入原始 HTML，返回内容寻址键。"""
        data = html.encode("utf-8")
        key = snapshot_key(html)
        self._client.put_object(
            self._bucket,
            key,
            io.BytesIO(data),
            length=len(data),
            content_type=SNAPSHOT_CONTENT_TYPE,
        )
        return key

    def get_html(self, key: str) -> str:
        """按键取回原始 HTML。"""
        response = self._client.get_object(self._bucket, key)
        try:
            return response.read().decode("utf-8")
        finally:
            response.close()
            response.release_conn()

    def put_material(self, data: bytes, ext: str) -> str:
        """存入素材原件（附件路径），返回内容寻址键。"""
        key = material_key(data, ext)
        self._client.put_object(
            self._bucket,
            key,
            io.BytesIO(data),
            length=len(data),
            content_type=AUDIO_CONTENT_TYPE,
        )
        return key

    def get_material(self, key: str) -> bytes:
        """按键取回素材原件。"""
        response = self._client.get_object(self._bucket, key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()


def make_snapshot_store(settings) -> SnapshotStore:
    """按运行时配置构造快照仓。"""
    return SnapshotStore(
        endpoint=settings.snapshot_endpoint,
        access_key=settings.snapshot_access_key,
        secret_key=settings.snapshot_secret_key,
        bucket=settings.snapshot_bucket,
        secure=settings.snapshot_secure,
    )
