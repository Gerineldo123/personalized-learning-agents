import asyncio
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from services.event_service import subscribe, unsubscribe

router = APIRouter(prefix="/api/events", tags=["事件"])


@router.get("/stream")
async def event_stream():
    queue = subscribe()

    async def generate():
        try:
            while True:
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=30)
                    yield f"data: {payload}\n\n"
                except asyncio.TimeoutError:
                    yield f"data: {chr(10)}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            unsubscribe(queue)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream; charset=utf-8",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
