from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """运行时配置：环境变量注入，密钥不入库不入 git（技术架构 §7）。"""

    database_url: str = "postgresql+psycopg://iih:iih@localhost:5432/iih"
    file_storage_dir: str = "/data/filestore"

    # LLM：OpenAI 兼容端点；切 provider 只改环境变量不动代码
    llm_provider: str = "deepseek"
    llm_model: str = "deepseek-chat"
    llm_base_url: str = "https://api.deepseek.com"
    llm_api_key: str = ""

    # 流水线后台自动循环间隔（秒）；0 = 关闭（doc-07 §2.2 常驻监控的最简实现）
    pipeline_interval_seconds: int = 300

    # 展示时区：库内时间戳一律 UTC，Web 展示按此时区换算
    display_timezone: str = "Asia/Shanghai"

    # 原文快照对象存储（doc-04）：自动拉取条目的原始网页 HTML 存 MinIO
    snapshot_endpoint: str = "minio:9000"
    snapshot_access_key: str = "minioadmin"
    snapshot_secret_key: str = "minioadmin"
    snapshot_bucket: str = "iih-snapshots"
    snapshot_secure: bool = False

    # 听悟 ASR（IIH-02.01 录音转写）：阿里云账号 AK + 听悟 AppKey + OSS 中转桶（按归属分组命名）
    aliyun_access_key_id: str = ""
    aliyun_access_key_secret: str = ""
    tingwu_app_key: str = ""
    oss_bucket: str = ""
    oss_region: str = "cn-hangzhou"
    tingwu_region_id: str = "cn-beijing"

    # Tavily 搜索 API（IIH-05.02 池外自由探索）：留空则探索环节静默跳过
    tavily_api_key: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
