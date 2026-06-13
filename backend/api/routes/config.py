import httpx
from fastapi import APIRouter
from services.config_service import (
    ApiConfig,
    get_main_config, set_main_config,
    get_tavily_config, set_tavily_config,
    get_ppt_config, set_ppt_config,
    build_client_kwargs,
    get_model,
)

router = APIRouter(prefix="/api/config", tags=["配置"])


def _mask_key(key: str) -> str:
    if len(key) > 8:
        return key[:4] + "****" + key[-4:]
    return "****" if key else ""


def _list_models(config_key: str) -> dict:
    kwargs = build_client_kwargs(config_key)
    base_url = kwargs["base_url"].rstrip("/")
    model = get_model(config_key) or "spark-x"
    # Spark X2/X1.5 endpoints are /x2 or /v2 for chat/completions; /models may not exist.
    # For those endpoints, return a known model list and validate via a lightweight chat call.
    if base_url.endswith("/x2") or base_url.endswith("/v2") or base_url.endswith("/v1"):
        chat_url = base_url + "/chat/completions"
        body = {
            "model": model,
            "messages": [{"role": "user", "content": "ping"}],
            "stream": False,
            "max_tokens": 1,
        }
        try:
            with httpx.Client(timeout=20) as client:
                resp = client.post(
                    chat_url,
                    headers={
                        "Authorization": f"Bearer {kwargs['api_key']}",
                        "Content-Type": "application/json",
                    },
                    json=body,
                )
            if resp.status_code == 200:
                return {"models": [model], "error": None}
            return {"models": [], "error": f"HTTP {resp.status_code}: {resp.text[:200]}"}
        except Exception as e:
            return {"models": [], "error": str(e)[:200]}

    url = base_url + "/models"
    try:
        with httpx.Client(timeout=15) as client:
            resp = client.get(
                url,
                headers={"Authorization": f"Bearer {kwargs['api_key']}"},
            )
            if resp.status_code == 200:
                data = resp.json()
                if "data" in data:
                    return {"models": [m["id"] for m in data["data"]], "error": None}
            if resp.status_code == 404:
                chat_url = base_url + "/chat/completions"
                body = {
                    "model": model,
                    "messages": [{"role": "user", "content": "ping"}],
                    "stream": False,
                    "max_tokens": 1,
                }
                probe_resp = client.post(
                    chat_url,
                    headers={
                        "Authorization": f"Bearer {kwargs['api_key']}",
                        "Content-Type": "application/json",
                    },
                    json=body,
                )
                if probe_resp.status_code == 200:
                    return {"models": [model], "error": None}
                return {"models": [], "error": f"HTTP {probe_resp.status_code}: {probe_resp.text[:200]}"}
            return {"models": [], "error": f"HTTP {resp.status_code}: {resp.text[:200]}"}
    except Exception as e:
        return {"models": [], "error": str(e)[:200]}


@router.get("/main")
def get_main():
    cfg = get_main_config()
    return {
        "base_url": cfg.base_url,
        "api_key": _mask_key(cfg.api_key),
        "api_secret": _mask_key(cfg.api_secret),
        "model": cfg.model,
        "has_key": bool(cfg.api_key),
    }


@router.post("/main")
def update_main(body: ApiConfig):
    set_main_config(body)
    return {"ok": True}


@router.get("/main/models")
def list_main_models():
    return _list_models("main")


@router.get("/tavily")
def get_tavily():
    cfg = get_tavily_config()
    return {
        "api_key": _mask_key(cfg.api_key),
        "has_key": bool(cfg.api_key),
    }


@router.post("/tavily")
def update_tavily(body: ApiConfig):
    set_tavily_config(body)
    return {"ok": True}


@router.post("/tavily/test")
async def test_tavily():
    from agents.tools import tavily_search
    cfg = get_tavily_config()
    if not cfg.api_key:
        return {"ok": False, "error": "未配置 Tavily API Key"}
    if not cfg.api_key.startswith("tvly-"):
        return {"ok": False, "error": f"API Key 格式错误：Tavily 密钥应以 tvly- 开头，当前以 {cfg.api_key[:4]}... 开头"}
    try:
        result = await tavily_search("hello world", max_results=1)
        if result.get("error"):
            return {"ok": False, "error": result["error"]}
        return {"ok": True, "result_count": len(result.get("results", [])), "has_answer": bool(result.get("answer"))}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


@router.get("/ppt")
def get_ppt():
    cfg = get_ppt_config()
    return {
        "base_url": cfg.base_url,
        "api_key": _mask_key(cfg.api_key),
        "api_secret": _mask_key(cfg.api_secret),
        "model": cfg.model,
        "has_key": bool(cfg.api_key),
    }


@router.post("/ppt")
def update_ppt(body: ApiConfig):
    set_ppt_config(body)
    return {"ok": True}


@router.get("/ppt/models")
def list_ppt_models():
    return _list_models("ppt")
