import os
from openai import AsyncOpenAI
from services.config_service import build_client_kwargs, get_model, is_configured

DEFAULT_BASE_URL = "https://spark-api-open.xf-yun.com/v1"
DEFAULT_MODEL = "generalv3.5"


def _build_kwargs() -> dict:
    if is_configured("main"):
        return build_client_kwargs("main")
    api_key = os.getenv("SPARK_API_KEY", "")
    api_secret = os.getenv("SPARK_API_SECRET", "")
    base_url = os.getenv("SPARK_BASE_URL", DEFAULT_BASE_URL)
    key = f"{api_key}:{api_secret}" if api_secret else api_key
    return {"api_key": key, "base_url": base_url}


def _get_model() -> str:
    if is_configured("main"):
        return get_model("main")
    return os.getenv("SPARK_MODEL", DEFAULT_MODEL)


async def chat_completion(messages: list, stream: bool = False, **kwargs):
    client = AsyncOpenAI(**_build_kwargs())
    return await client.chat.completions.create(
        model=_get_model(),
        messages=messages,
        stream=stream,
        **kwargs,
    )


def build_video_client_kwargs() -> dict:
    if is_configured("video"):
        return build_client_kwargs("video")
    return _build_kwargs()


def get_video_model() -> str:
    if is_configured("video"):
        return get_model("video")
    return _get_model()
