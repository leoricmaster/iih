"""原文快照对象存储（doc-04）：自动拉取条目的原始网页 HTML 存 MinIO。

键为内容寻址（原始 HTML 的 SHA-256）：同页多采共享对象、put 幂等；
采集（判断层）写入、Web 快照回放读出，均经本模块，不散落客户端调用。
"""

import hashlib
import io

from minio import Minio

SNAPSHOT_CONTENT_TYPE = "text/html; charset=utf-8"


def snapshot_key(html: str) -> str:
    """内容寻址对象键。"""
    return f"snapshots/{hashlib.sha256(html.encode('utf-8')).hexdigest()}.html"


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


def make_snapshot_store(settings) -> SnapshotStore:
    """按运行时配置构造快照仓。"""
    return SnapshotStore(
        endpoint=settings.snapshot_endpoint,
        access_key=settings.snapshot_access_key,
        secret_key=settings.snapshot_secret_key,
        bucket=settings.snapshot_bucket,
        secure=settings.snapshot_secure,
    )
