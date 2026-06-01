import json
import httpx
from services.config_service import get_video_config


class IflytekVMSClient:

    def __init__(self):
        cfg = get_video_config()
        self.base_url = cfg.base_url.rstrip("/")
        self.api_key = cfg.api_key
        self.api_secret = cfg.api_secret

    def _headers(self) -> dict:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}:{self.api_secret}",
        }

    def _request(self, method: str, path: str, body: dict | None = None) -> httpx.Response:
        url = self.base_url + path
        with httpx.Client(timeout=15) as client:
            resp = client.request(
                method, url,
                headers=self._headers(),
                content=json.dumps(body) if body else None,
            )
            return resp

    def test_connection(self) -> dict:
        try:
            resp = self._request("POST", "/v1/tts", {})
            return {
                "ok": True,
                "status": resp.status_code,
                "message": resp.json().get("header", {}).get("message", ""),
            }
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    def list_models(self) -> list[str]:
        return []

    def create_tts_task(self, text: str, voice: str = "", scene_id: str = "") -> dict:
        cfg = get_video_config()
        scene = scene_id or cfg.model or "virtual_human_video_create"
        body = {
            "common": {"app_id": cfg.api_key},
            "business": {"scene": scene},
            "data": {
                "text": text,
                "voice": voice or "xiaoyan",
            },
        }
        resp = self._request("POST", f"/v1/tts/{scene}", body)
        data = resp.json()
        return {
            "status": resp.status_code,
            "code": data.get("header", {}).get("code", 0),
            "message": data.get("header", {}).get("message", ""),
            "task_id": data.get("header", {}).get("sid", ""),
        }


_vms_client: IflytekVMSClient | None = None


def get_vms_client() -> IflytekVMSClient:
    global _vms_client
    if _vms_client is None:
        _vms_client = IflytekVMSClient()
    return _vms_client
