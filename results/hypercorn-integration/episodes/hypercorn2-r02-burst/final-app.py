from __future__ import annotations
CONTENT = "WD0000091016"
print("WATCHDELTA_HYPERCORN_IMPORT", CONTENT, flush=True)

async def app(scope, receive, send):
    if scope["type"] == "lifespan":
        while True:
            event = await receive()
            if event["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            elif event["type"] == "lifespan.shutdown":
                await send({"type": "lifespan.shutdown.complete"})
                return
    elif scope["type"] == "http":
        body = CONTENT.encode("utf-8")
        await send({"type": "http.response.start", "status": 200,
                     "headers": [(b"content-type", b"text/plain; charset=utf-8")]})
        await send({"type": "http.response.body", "body": body})
