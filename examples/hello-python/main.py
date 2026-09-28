# Dockerfile 없는 FastAPI 앱: oneclick이 requirements.txt와 FastAPI( 를 보고 Dockerfile을 만든다.
import os
import socket
from datetime import datetime, timezone

from fastapi import FastAPI

app = FastAPI()
STARTED = datetime.now(timezone.utc).isoformat()


@app.get("/")
def index():
    return {"app": "hello-python", "host": socket.gethostname(), "started": STARTED,
            "version": os.environ.get("APP_VERSION", "v1")}


@app.get("/healthz")
def healthz():
    return "ok"
