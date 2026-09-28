"""배포 파이프라인: One Action → 여러 배포 대상.

  소스 가져오기 → 감지/Dockerfile → 빌드(1회) → 대상별 병렬 배포 → 헬스체크 → 기록
                                                   └ 실패 시 대상별 자동 롤백
"""
import threading
from concurrent.futures import ThreadPoolExecutor

from . import detect, health, providers, shell, source, store

_app_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


class Busy(RuntimeError):
    """같은 앱의 배포가 이미 진행 중."""


def _app_lock(app: str) -> threading.Lock:
    with _locks_guard:
        return _app_locks.setdefault(app, threading.Lock())


def _logger(rid: str, scope: str, echo: bool) -> shell.Log:
    def log(line: str) -> None:
        store.add_log(rid, scope, line)
        if echo:
            print(f"[{scope}] {line}", flush=True)
    return log


def validate_targets(targets: list[str]) -> None:
    if not targets:
        raise ValueError("배포 대상을 하나 이상 고르세요")
    for t in targets:
        p = providers.get(t)
        if err := p.problem():
            raise ValueError(f"{t}: {err}")


def start_deploy(src: str, targets: list[str], app: str | None = None,
                 wait: bool = False, echo: bool = False) -> str:
    """배포를 시작하고 release id를 반환한다. wait=False면 백그라운드에서 진행."""
    app = source.sanitize(app) if app else source.app_name_from(src)
    validate_targets(targets)
    lock = _app_lock(app)
    if not lock.acquire(blocking=False):
        raise Busy(f"'{app}' 앱의 배포가 이미 진행 중입니다")
    rid = store.create_release(app, src)
    deps = {t: store.create_deployment(rid, app, t) for t in targets}

    def job():
        try:
            _run_release(rid, app, src, deps, echo)
        finally:
            lock.release()

    if wait:
        job()
    else:
        threading.Thread(target=job, daemon=True).start()
    return rid


def start_rollback(app: str, target: str, wait: bool = False, echo: bool = False) -> str:
    """대상의 직전 성공 배포 이미지로 되돌린다 (빌드 없이 재배포)."""
    prev = store.previous_deployment(app, target)
    if not prev:
        raise ValueError(f"{app}/{target}: 되돌릴 이전 배포가 없습니다")
    validate_targets([target])
    lock = _app_lock(app)
    if not lock.acquire(blocking=False):
        raise Busy(f"'{app}' 앱의 배포가 이미 진행 중입니다")
    rid = store.create_release(app, f"rollback → {prev['release_id']}", "rollback", prev["image"])
    did = store.create_deployment(rid, app, target)

    def job():
        try:
            _deploy_target(rid, did, app, target, prev["image"], echo)
        finally:
            lock.release()

    if wait:
        job()
    else:
        threading.Thread(target=job, daemon=True).start()
    return rid


def _run_release(rid: str, app: str, src: str, deps: dict[str, str], echo: bool) -> None:
    log = _logger(rid, "build", echo)
    for did in deps.values():
        store.update_deployment(did, status=store.BUILDING)
    try:
        workdir = source.fetch(src, rid, log)
        detect.prepare(workdir, log)
        image = f"oneclick/{app}:{rid}"
        # 클라우드 런타임은 대부분 amd64만 받으므로 플랫폼을 고정한다
        shell.run(["docker", "build", "--platform", "linux/amd64", "-t", image, str(workdir)], log)
        store.set_release_image(rid, image)
    except Exception as e:
        log(f"빌드 실패: {e}")
        for did in deps.values():
            store.update_deployment(did, status=store.FAILED, error=f"빌드 실패: {e}")
        return

    log(f"빌드 완료: {image} → {len(deps)}개 대상에 동시 배포")
    with ThreadPoolExecutor(max_workers=len(deps)) as pool:
        for target, did in deps.items():
            pool.submit(_deploy_target, rid, did, app, target, image, echo)


def _deploy_target(rid: str, did: str, app: str, target: str, image: str, echo: bool) -> None:
    log = _logger(rid, target, echo)
    provider = providers.get(target)
    prev = store.live_deployment(app, target)
    store.update_deployment(did, status=store.DEPLOYING, image=image)
    try:
        ep = provider.deploy(app, image, image.rsplit(":", 1)[-1], log)
        health.wait_healthy(ep.health_url, provider.health_timeout, log)
        provider.on_success(app, log)
    except Exception as e:
        log(f"배포 실패: {e}")
        try:
            provider.on_failure(app, prev["image"] if prev else None, log)
        except Exception as re_err:
            log(f"자동 롤백도 실패: {re_err}")
        store.update_deployment(did, status=store.FAILED, error=str(e)[:500])
        return
    store.update_deployment(did, status=store.LIVE, url=ep.url)
    store.supersede(app, target, did)
    log(f"배포 완료: {ep.url}")
