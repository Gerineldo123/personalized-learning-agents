import json


async def sse_event(event: str, data: str):
    return f"event: {event}\ndata: {data}\n\n"


async def sse_stream(generator):
    async for chunk in generator:
        text = "" if chunk is None else str(chunk)
        lines = text.splitlines()
        if not lines:
            yield "data: \n\n"
            continue
        payload = "\n".join(f"data: {line}" for line in lines)
        yield f"{payload}\n\n"
