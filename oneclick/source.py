"""배포할 소스를 작업 디렉터리로 가져온다: Git URL 또는 로컬 경로."""
import os
import re
import shutil
from pathlib import Path

from . import config, shell

IGNORE = shutil.ignore_patterns(".git", "node_modules", ".venv", "venv", "__pycache__",
                                ".next", "dist", ".oneclick")


def is_git_url(source: str) -> bool:
    return bool(re.match(r"^(https?://|git@)", source)) or source.endswith(".git")


def app_name_from(source: str) -> str:
    base = source.rstrip("/\\").split("/")[-1].split("\\")[-1]
    return sanitize(base.removesuffix(".git"))


def sanitize(name: str) -> str:
    """클라우드 서비스 이름 규칙(소문자, 숫자, 하이픈, 문자로 시작)에 맞춘다."""
    name = re.sub(r"[^a-z0-9-]+", "-", name.lower()).strip("-")
    if not name or not name[0].isalpha():
        name = "app-" + name
    return name[:40].rstrip("-")


def _long(p: Path) -> str:
    """Windows의 260자 경로 제한을 피한다 (OneDrive/한글 폴더처럼 깊은 경로 대비)."""
    s = str(p)
    return "\\\\?\\" + s if os.name == "nt" and not s.startswith("\\\\?\\") else s


def fetch(source: str, release_id: str, log: shell.Log) -> Path:
    dest = config.WORK_DIR / release_id
    if is_git_url(source):
        shell.run(["git", "-c", "core.longpaths=true", "clone", "--depth", "1", source, str(dest)], log)
    else:
        src = Path(source).expanduser().resolve()
        if not src.is_dir():
            raise FileNotFoundError(f"소스 폴더가 없습니다: {src}")
        log(f"로컬 폴더 복사: {src}")
        shutil.copytree(_long(src), _long(dest), ignore=IGNORE)
    return dest
