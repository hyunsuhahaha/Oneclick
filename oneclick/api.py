"""웹 API + 대시보드."""
import asyncio
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from . import pipeline, providers, store

app = FastAPI(title="oneclick")
STATIC = Path(__file__).parent / "static"


class DeployReq(BaseModel):
    source: str
    targets: list[str]
    app: str | None = None


class RollbackReq(BaseModel):
    app: str
    target: str


def _guard(fn, *args):
    try:
        return fn(*args)
    except pipeline.Busy as e:
        raise HTTPException(409, str(e))
    except (ValueError, KeyError) as e:
        raise HTTPException(400, str(e))


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/targets")
def targets():
    return [{"name": p.name, "label": p.label, "kind": p.kind, "problem": p.problem()}
            for p in providers.PROVIDERS.values()]


@app.post("/api/deploy")
def deploy(req: DeployReq):
    rid = _guard(pipeline.start_deploy, req.source, req.targets, req.app)
    return {"release_id": rid}


@app.post("/api/rollback")
def rollback(req: RollbackReq):
    rid = _guard(pipeline.start_rollback, req.app, req.target)
    return {"release_id": rid}


@app.get("/api/releases")
def releases():
    return store.list_releases()


@app.get("/api/releases/{rid}/logs")
async def logs(rid: str):
    """Server-Sent Events로 로그를 흘려보낸다. 릴리스가 끝나면 'done' 이벤트."""
    async def stream():
        last = 0
        while True:
            rows = store.logs_since(rid, last)
            for r in rows:
                last = r["id"]
                yield f"data: {json.dumps(r, ensure_ascii=False)}\n\n"
            if not rows and store.release_done(rid):
                yield "event: done\ndata: {}\n\n"
                return
            await asyncio.sleep(0.5)
    return StreamingResponse(stream(), media_type="text/event-stream")
