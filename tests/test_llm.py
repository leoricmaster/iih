"""LLM 接入单测：客户端工厂走配置注入（不触网）。"""

import instructor

from iih.agents.llm import make_llm_client
from iih.config import Settings


def test_make_llm_client_reads_provider_config() -> None:
    settings = Settings(
        llm_api_key="sk-test",
        llm_base_url="https://api.deepseek.com",
    )

    client = make_llm_client(settings)

    assert isinstance(client, instructor.Instructor)
    # base_url 生效：切 provider 只改环境变量不动代码
    assert str(client.client.base_url) == "https://api.deepseek.com"
