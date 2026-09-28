"""배포 대상 등록소. 새 대상은 여기에 한 줄 추가."""
from .base import Endpoint, Provider
from .cloudrun import CloudRun
from .lightsail import Lightsail
from .local import LocalDocker

PROVIDERS: dict[str, Provider] = {p.name: p for p in (LocalDocker(), CloudRun(), Lightsail())}


def get(name: str) -> Provider:
    if name not in PROVIDERS:
        raise KeyError(f"알 수 없는 배포 대상: {name} (가능: {', '.join(PROVIDERS)})")
    return PROVIDERS[name]


__all__ = ["Endpoint", "Provider", "PROVIDERS", "get"]
