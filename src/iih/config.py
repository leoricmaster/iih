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

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
