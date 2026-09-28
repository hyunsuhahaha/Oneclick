"""배포 대상(Provider) 인터페이스.

새 클라우드를 추가하려면 이 클래스를 상속한 파일 하나를 만들고
providers/__init__.py의 PROVIDERS에 등록하면 된다.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass

from ..shell import Log


@dataclass
class Endpoint:
    url: str          # 사용자에게 보여 줄 URL
    health_url: str   # 헬스체크할 URL (로컬 터널이면 localhost 쪽)


class Provider(ABC):
    name: str = ""
    label: str = ""
    kind: str = "cloud"     # "local" 또는 "cloud"
    health_timeout: int = 600

    def problem(self) -> str | None:
        """배포할 준비가 안 됐으면 이유를 반환 (CLI 미설치, 설정 누락 등)."""
        return None

    @abstractmethod
    def deploy(self, app: str, image: str, tag: str, log: Log) -> Endpoint:
        """로컬에 빌드된 image를 이 대상에 배포하고 접속 주소를 반환한다."""

    def on_success(self, app: str, log: Log) -> None:
        """헬스체크 통과 후 정리 작업 (예: 이전 컨테이너 삭제)."""

    def on_failure(self, app: str, prev_image: str | None, log: Log) -> None:
        """헬스체크 실패 시 복구. 기본 동작: 이전 이미지를 다시 배포."""
        if prev_image:
            log(f"자동 롤백: {prev_image}")
            self.deploy(app, prev_image, prev_image.rsplit(":", 1)[-1], log)

    def destroy(self, app: str, log: Log) -> None:
        raise NotImplementedError
