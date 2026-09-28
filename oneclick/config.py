"""환경 변수 기반 설정. 모든 설정은 ONECLICK_ 접두사를 쓴다."""
import os
from pathlib import Path


def env(name: str, default: str = "") -> str:
    return os.environ.get(f"ONECLICK_{name}", default)


# 상태(DB, 작업 폴더)는 짧은 경로에 둔다: Windows 260자 경로 제한 회피
HOME = Path(env("HOME", str(Path.home() / ".oneclick"))).resolve()
DB_PATH = HOME / "oneclick.db"
WORK_DIR = HOME / "work"

# 앱 계약: 컨테이너는 $PORT(기본 8080)에서 HTTP로 응답한다.
APP_PORT = 8080
HEALTH_PATH = env("HEALTH_PATH", "/")
HEALTH_TIMEOUT_LOCAL = int(env("HEALTH_TIMEOUT_LOCAL", "90"))
HEALTH_TIMEOUT_CLOUD = int(env("HEALTH_TIMEOUT_CLOUD", "600"))

# GCP Cloud Run
GCP_PROJECT = env("GCP_PROJECT")
GCP_REGION = env("GCP_REGION", "asia-northeast3")  # 서울
GCP_REPO = env("GCP_REPO", "oneclick")  # Artifact Registry 저장소 이름

# AWS Lightsail Containers
AWS_REGION = env("AWS_REGION", "ap-northeast-2")  # 서울
AWS_LIGHTSAIL_POWER = env("AWS_LIGHTSAIL_POWER", "nano")

# 로컬 배포를 외부에 공개할지 (cloudflared quick tunnel)
LOCAL_PUBLIC_TUNNEL = env("LOCAL_PUBLIC_TUNNEL", "0") == "1"


def ensure_dirs() -> None:
    WORK_DIR.mkdir(parents=True, exist_ok=True)
