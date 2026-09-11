"""LLM 接入（技术架构 §1/§3）：OpenAI 兼容 SDK 直连 + instructor 结构化输出，不建网关容器。"""

import instructor
from instructor import Instructor
from openai import OpenAI

from iih.config import Settings


def make_llm_client(settings: Settings) -> Instructor:
    """OpenAI 兼容客户端（起步 DeepSeek）；切 provider 只改环境变量 LLM_*，不动代码。"""
    return instructor.from_openai(
        OpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
    )
