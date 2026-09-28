"""AWS Lightsail Containers에 배포한다 (aws CLI + lightsailctl 플러그인 사용).

AWS에서 컨테이너 하나를 공개 HTTPS URL로 띄우는 가장 짧은 경로라 기본값으로 골랐다.
ECS Fargate / App Runner 어댑터는 같은 인터페이스로 추가하면 된다.

사전 준비 (한 번):
  aws configure
  lightsailctl 설치: https://lightsail.aws.amazon.com/ls/docs/en_us/articles/amazon-lightsail-install-software
환경 변수: ONECLICK_AWS_REGION(기본 ap-northeast-2), ONECLICK_AWS_LIGHTSAIL_POWER(기본 nano)
"""
import json
import re
import time

from .. import config, shell
from .base import Endpoint, Provider


class Lightsail(Provider):
    name = "lightsail"
    label = "AWS Lightsail Containers"
    health_timeout = config.HEALTH_TIMEOUT_CLOUD

    def problem(self) -> str | None:
        if not shell.which("aws"):
            return "aws CLI가 없습니다"
        if not shell.which("lightsailctl"):
            return "lightsailctl 플러그인이 없습니다"
        return None

    def _a(self, *args: str) -> list[str]:
        return ["aws", "lightsail", *args, "--region", config.AWS_REGION]

    def _service(self, app: str) -> dict | None:
        try:
            out = shell.run(self._a("get-container-services", "--service-name", app,
                                    "--output", "json"), quiet=True)
        except shell.CommandError:
            return None
        return json.loads(out)["containerServices"][0]

    def _wait(self, app: str, log, want: set[str], timeout: int = 900) -> dict:
        deadline = time.time() + timeout
        last = ""
        while time.time() < deadline:
            svc = self._service(app) or {}
            state = svc.get("state", "")
            if state != last:
                log(f"Lightsail 상태: {state}")
                last = state
            if state in want:
                return svc
            time.sleep(10)
        raise TimeoutError(f"Lightsail 서비스가 {want} 상태가 되지 않았습니다")

    def deploy(self, app, image, tag, log) -> Endpoint:
        if not self._service(app):
            shell.run(self._a("create-container-service", "--service-name", app,
                              "--power", config.AWS_LIGHTSAIL_POWER, "--scale", "1"), log)
            self._wait(app, log, {"READY", "RUNNING"})
        out = shell.run(self._a("push-container-image", "--service-name", app,
                                "--label", "app", "--image", image), log)
        m = re.search(r'"(:[^"]+)"', out)
        if not m:
            raise RuntimeError("push-container-image 출력에서 이미지 참조를 찾지 못했습니다")
        containers = {"app": {"image": m.group(1),
                              "ports": {str(config.APP_PORT): "HTTP"},
                              "environment": {"PORT": str(config.APP_PORT)}}}
        endpoint = {"containerName": "app", "containerPort": config.APP_PORT,
                    "healthCheck": {"path": config.HEALTH_PATH}}
        shell.run(self._a("create-container-service-deployment", "--service-name", app,
                          "--containers", json.dumps(containers),
                          "--public-endpoint", json.dumps(endpoint)), log)
        time.sleep(5)
        svc = self._wait(app, log, {"RUNNING"})
        url = svc["url"].rstrip("/")
        return Endpoint(url=url, health_url=url + config.HEALTH_PATH)

    def destroy(self, app, log) -> None:
        shell.run(self._a("delete-container-service", "--service-name", app), log)
