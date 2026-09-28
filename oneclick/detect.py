"""프레임워크 감지 + Dockerfile 자동 생성.

규칙으로 감지할 수 있으면 템플릿을 쓰고, 못 하면 ai_fallback()으로 넘긴다.
AI 기능(Dockerfile 생성, 코드 수정 제안 등)은 ai_fallback 자리에 붙이면 된다.
"""
import json
import re
from dataclasses import dataclass
from pathlib import Path

from . import shell

DOCKERIGNORE = "\n".join([".git", "node_modules", ".venv", "venv", "__pycache__",
                          ".next", ".env", ".oneclick", ""])


@dataclass
class Plan:
    framework: str       # 감지 결과 (예: "node", "python-fastapi", "dockerfile")
    generated: bool      # Dockerfile을 우리가 만들었는가
    dockerfile: str      # 사용한 Dockerfile 내용


class DetectError(RuntimeError):
    pass


NODE = """FROM node:20-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci || npm install
COPY . .
{build}ENV PORT=8080 NODE_ENV=production
EXPOSE 8080
CMD ["npm", "start"]
"""

PYTHON = """FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PORT=8080
COPY requirements.txt* ./
RUN if [ -f requirements.txt ]; then pip install --no-cache-dir -r requirements.txt; fi{extra}
COPY . .
EXPOSE 8080
CMD {cmd}
"""

GO = """FROM golang:1.23-alpine AS build
WORKDIR /src
COPY . .
RUN CGO_ENABLED=0 go build -o /app .

FROM gcr.io/distroless/static
COPY --from=build /app /app
ENV PORT=8080
EXPOSE 8080
ENTRYPOINT ["/app"]
"""

STATIC = """FROM nginx:alpine
RUN sed -i 's/listen  *80;/listen 8080;/' /etc/nginx/conf.d/default.conf
COPY . /usr/share/nginx/html
EXPOSE 8080
"""


def _node(root: Path) -> str | None:
    pkg = root / "package.json"
    if not pkg.exists():
        return None
    scripts = json.loads(pkg.read_text(encoding="utf-8")).get("scripts", {})
    if "start" not in scripts:
        raise DetectError("package.json에 start 스크립트가 없습니다")
    build = "RUN npm run build\n" if "build" in scripts else ""
    return NODE.format(build=build)


def _python(root: Path) -> tuple[str, str] | None:
    if not ((root / "requirements.txt").exists() or (root / "pyproject.toml").exists()):
        return None
    procfile = root / "Procfile"
    if procfile.exists():
        m = re.search(r"^web:\s*(.+)$", procfile.read_text(encoding="utf-8"), re.M)
        if m:
            return "python-procfile", PYTHON.format(extra="", cmd=json.dumps(["sh", "-c", m.group(1)]))
    for entry in ("main.py", "app.py", "server.py"):
        f = root / entry
        if not f.exists():
            continue
        code = f.read_text(encoding="utf-8", errors="ignore")
        mod = entry.removesuffix(".py")
        if "FastAPI(" in code:
            cmd = f"uvicorn {mod}:app --host 0.0.0.0 --port $PORT"
            return "python-fastapi", PYTHON.format(extra="", cmd=json.dumps(["sh", "-c", cmd]))
        if "Flask(" in code:
            cmd = f"gunicorn -b 0.0.0.0:$PORT {mod}:app"
            return "python-flask", PYTHON.format(extra=" && pip install --no-cache-dir gunicorn",
                                                 cmd=json.dumps(["sh", "-c", cmd]))
        return "python", PYTHON.format(extra="", cmd=json.dumps(["python", entry]))
    return None


def detect(root: Path) -> Plan:
    df = root / "Dockerfile"
    if df.exists():
        return Plan("dockerfile", False, df.read_text(encoding="utf-8"))

    if (text := _node(root)) is not None:
        return Plan("node", True, text)
    if (py := _python(root)) is not None:
        return Plan(py[0], True, py[1])
    if (root / "go.mod").exists():
        return Plan("go", True, GO)
    if (root / "index.html").exists():
        return Plan("static", True, STATIC)
    return ai_fallback(root)


def ai_fallback(root: Path) -> Plan:
    """TODO(AI): 규칙으로 감지 못 한 앱을 AI가 분석해 Dockerfile을 만든다.

    구현 아이디어: 파일 트리 + 주요 설정 파일 내용을 LLM에 주고 Dockerfile과
    필요한 코드 수정(PORT 환경변수, /healthz 등)을 받아 사용자 승인 후 적용.
    """
    files = sorted(p.name for p in root.iterdir())[:30]
    raise DetectError(f"프레임워크를 감지하지 못했습니다. 파일: {files}")


def prepare(root: Path, log: shell.Log) -> Plan:
    """감지하고, 필요하면 Dockerfile/.dockerignore를 작업 디렉터리에 쓴다."""
    plan = detect(root)
    if plan.generated:
        (root / "Dockerfile").write_text(plan.dockerfile, encoding="utf-8")
        log(f"감지: {plan.framework} → Dockerfile 자동 생성")
    else:
        log("감지: 프로젝트의 Dockerfile 사용")
    if not (root / ".dockerignore").exists():
        (root / ".dockerignore").write_text(DOCKERIGNORE, encoding="utf-8")
    return plan
