"""온프레미스(이 PC)의 Docker에 배포한다.

교체 방식: 기존 컨테이너를 -prev로 이름을 바꿔 멈추고 새 컨테이너를 띄운다.
헬스체크에 성공하면 -prev를 지우고, 실패하면 새 것을 지우고 -prev를 되살린다.
"""
import re
import subprocess
import threading

from .. import config, shell, store
from .base import Endpoint, Provider

_tunnels: dict[str, tuple[subprocess.Popen, str]] = {}
_tunnel_lock = threading.Lock()


class LocalDocker(Provider):
    name = "local"
    label = "로컬 (이 PC · Docker)"
    kind = "local"
    health_timeout = config.HEALTH_TIMEOUT_LOCAL

    def problem(self) -> str | None:
        if not shell.which("docker"):
            return "docker CLI가 없습니다"
        if not shell.ok(["docker", "info", "--format", "{{.ServerVersion}}"]):
            return "Docker 데몬이 실행 중이 아닙니다"
        return None

    @staticmethod
    def _cname(app: str) -> str:
        return f"oneclick-{app}"

    def _exists(self, name: str) -> bool:
        return shell.ok(["docker", "container", "inspect", name])

    def deploy(self, app, image, tag, log) -> Endpoint:
        name, prev = self._cname(app), self._cname(app) + "-prev"
        port = store.local_port(app)
        if self._exists(prev):
            shell.run(["docker", "rm", "-f", prev], log, check=False)
        if self._exists(name):
            shell.run(["docker", "rename", name, prev], log)
            shell.run(["docker", "stop", prev], log)
        shell.run(["docker", "run", "-d", "--name", name, "--restart", "unless-stopped",
                   "-p", f"{port}:{config.APP_PORT}", "-e", f"PORT={config.APP_PORT}",
                   "-l", "oneclick.app=" + app, image], log)
        local_url = f"http://localhost:{port}"
        url = local_url
        if config.LOCAL_PUBLIC_TUNNEL:
            url = self._tunnel(app, port, log) or local_url
        return Endpoint(url=url, health_url=local_url + config.HEALTH_PATH)

    def on_success(self, app, log) -> None:
        prev = self._cname(app) + "-prev"
        if self._exists(prev):
            shell.run(["docker", "rm", "-f", prev], log)

    def on_failure(self, app, prev_image, log) -> None:
        name, prev = self._cname(app), self._cname(app) + "-prev"
        shell.run(["docker", "logs", "--tail", "20", name], log, check=False)
        shell.run(["docker", "rm", "-f", name], log, check=False)
        if self._exists(prev):
            log("자동 롤백: 이전 컨테이너 복구")
            shell.run(["docker", "rename", prev, name], log)
            shell.run(["docker", "start", name], log)

    def destroy(self, app, log) -> None:
        for n in (self._cname(app), self._cname(app) + "-prev"):
            shell.run(["docker", "rm", "-f", n], log, check=False)

    def _tunnel(self, app: str, port: int, log) -> str | None:
        """cloudflared quick tunnel로 로컬 앱에 공개 HTTPS 주소를 붙인다 (앱당 1회)."""
        with _tunnel_lock:
            if app in _tunnels and _tunnels[app][0].poll() is None:
                return _tunnels[app][1]
            exe = shell.which("cloudflared")
            if not exe:
                log("cloudflared가 없어 공개 터널을 건너뜁니다")
                return None
            proc = subprocess.Popen([exe, "tunnel", "--url", f"http://localhost:{port}"],
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, encoding="utf-8", errors="replace")
            assert proc.stdout
            for line in proc.stdout:
                m = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", line)
                if m:
                    _tunnels[app] = (proc, m.group(0))
                    log(f"공개 터널: {m.group(0)}")
                    # 남은 출력은 버퍼가 차지 않도록 계속 읽어 버린다
                    threading.Thread(target=lambda: [None for _ in proc.stdout], daemon=True).start()
                    return m.group(0)
            return None
