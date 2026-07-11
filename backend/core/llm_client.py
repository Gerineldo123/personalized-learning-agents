import os
import asyncio
from openai import AsyncOpenAI
from services.config_service import build_client_kwargs, get_model, is_configured

DEFAULT_BASE_URL = "https://spark-api-open.xf-yun.com/v1"
DEFAULT_MODEL = "generalv3.5"
DEFAULT_TIMEOUT = float(os.getenv("LLM_TIMEOUT_SECONDS", "60"))
DEFAULT_RETRIES = int(os.getenv("LLM_RETRIES", "2"))


def _build_kwargs() -> dict:
    if is_configured("main"):
        kwargs = build_client_kwargs("main")
        kwargs.setdefault("timeout", DEFAULT_TIMEOUT)
        return kwargs
    api_key = os.getenv("SPARK_API_KEY", "")
    api_secret = os.getenv("SPARK_API_SECRET", "")
    base_url = os.getenv("SPARK_BASE_URL", DEFAULT_BASE_URL)
    key = f"{api_key}:{api_secret}" if api_secret else api_key
    return {"api_key": key, "base_url": base_url, "timeout": DEFAULT_TIMEOUT}


def _get_model() -> str:
    if is_configured("main"):
        return get_model("main")
    return os.getenv("SPARK_MODEL", DEFAULT_MODEL)


async def chat_completion(messages: list, stream: bool = False, **kwargs):
    return await _completion_with_retry(_build_kwargs(), _get_model(), messages, stream, kwargs)


def build_video_client_kwargs() -> dict:
    if is_configured("video"):
        kwargs = build_client_kwargs("video")
        kwargs.setdefault("timeout", DEFAULT_TIMEOUT)
        return kwargs
    return _build_kwargs()


def get_video_model() -> str:
    if is_configured("video"):
        return get_model("video")
    return _get_model()


def _build_ppt_kwargs() -> dict:
    if is_configured("ppt"):
        kwargs = build_client_kwargs("ppt")
        kwargs.setdefault("timeout", DEFAULT_TIMEOUT)
        return kwargs
    return _build_kwargs()


def _get_ppt_model() -> str:
    if is_configured("ppt"):
        return get_model("ppt")
    return _get_model()


async def ppt_completion(messages: list, stream: bool = False, **kwargs):
    return await _completion_with_retry(_build_ppt_kwargs(), _get_ppt_model(), messages, stream, kwargs)


async def _completion_with_retry(client_kwargs: dict, model: str, messages: list, stream: bool, kwargs: dict):
    last_exc: Exception | None = None
    request_kwargs = dict(kwargs)
    retries = request_kwargs.pop("retries", DEFAULT_RETRIES)
    attempts = max(1, int(retries) + 1)
    for attempt in range(attempts):
        try:
            client = AsyncOpenAI(**client_kwargs)
            return await client.chat.completions.create(
                model=model,
                messages=messages,
                stream=stream,
                **request_kwargs,
            )
        except Exception as exc:
            last_exc = exc
            if attempt >= attempts - 1:
                break
            await asyncio.sleep(0.4 * (attempt + 1))
    raise RuntimeError("LLM 生成失败，请检查 API 配置或稍后重试") from last_exc
