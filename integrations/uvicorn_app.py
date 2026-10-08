"""Small documentation application; Uvicorn's real reloader controls restarts."""
import os
from pathlib import Path
from watchdelta.core import build_docs
ROOT=Path(os.environ['WATCHDELTA_PROJECT']).resolve()
build_docs(ROOT)
print('WATCHDELTA_RENDER_COMPLETE',flush=True)

async def app(scope,receive,send):
    if scope['type']=='lifespan':
        while True:
            event=await receive()
            if event['type']=='lifespan.startup':await send({'type':'lifespan.startup.complete'})
            elif event['type']=='lifespan.shutdown':
                await send({'type':'lifespan.shutdown.complete'});return
    elif scope['type']=='http':
        allowed=scope.get('path') in ('/','/index.html')
        body=(ROOT/'out/index.html').read_bytes() if allowed else b'Not found'
        await send({'type':'http.response.start','status':200 if allowed else 404,'headers':[(b'content-type',b'text/html; charset=utf-8')]})
        await send({'type':'http.response.body','body':body})
