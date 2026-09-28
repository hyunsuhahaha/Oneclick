"""Google Cloud Run에 배포한다 (gcloud CLI 사용).

사전 준비 (한 번):
  gcloud auth login
  gcloud config set project <PROJECT>
  gcloud services enable run.googleapis.com artifactregistry.googleapis.com
  gcloud auth configure-docker <REGION>-docker.pkg.dev
환경 변수: ONECLICK_GCP_PROJECT, ONECLICK_GCP_REGION(기본 asia-northeast3)

TODO(클라우드 고유 기능): Cloud Run은 리비전별 트래픽 분할을 지원한다.
  gcloud run deploy --no-traffic --tag canary  → update-traffic --to-tags canary=10
  로 카나리 배포를, update-traffic --to-revisions 로 즉시 롤백을 구현할 수 있다.
"""
from .. import config, shell
from .base import Endpoint, Provider


class CloudRun(Provider):
    name = "cloudrun"
    label = "Google Cloud Run"
    health_timeout = config.HEALTH_TIMEOUT_CLOUD

    def problem(self) -> str | None:
        if not shell.which("gcloud"):
            return "gcloud CLI가 없습니다"
        if not config.GCP_PROJECT:
            return "ONECLICK_GCP_PROJECT가 설정되지 않았습니다"
        return None

    def _g(self, *args: str) -> list[str]:
        return ["gcloud", *args, "--project", config.GCP_PROJECT, "--quiet"]

    def _ensure_repo(self, log) -> None:
        if shell.ok(self._g("artifacts", "repositories", "describe", config.GCP_REPO,
                            "--location", config.GCP_REGION)):
            return
        shell.run(self._g("artifacts", "repositories", "create", config.GCP_REPO,
                          "--repository-format", "docker", "--location", config.GCP_REGION), log)

    def deploy(self, app, image, tag, log) -> Endpoint:
        self._ensure_repo(log)
        ref = (f"{config.GCP_REGION}-docker.pkg.dev/{config.GCP_PROJECT}/"
               f"{config.GCP_REPO}/{app}:{tag}")
        shell.run(["docker", "tag", image, ref], log)
        shell.run(["docker", "push", ref], log)
        shell.run(self._g("run", "deploy", app, "--image", ref, "--region", config.GCP_REGION,
                          "--port", str(config.APP_PORT), "--allow-unauthenticated"), log)
        url = shell.run(self._g("run", "services", "describe", app, "--region",
                                config.GCP_REGION, "--format", "value(status.url)"),
                        quiet=True).strip().splitlines()[-1]
        return Endpoint(url=url, health_url=url + config.HEALTH_PATH)

    def destroy(self, app, log) -> None:
        shell.run(self._g("run", "services", "delete", app, "--region", config.GCP_REGION), log)
