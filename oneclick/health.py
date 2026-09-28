"""배포 후 헬스체크: URL이 응답할 때까지 재시도한다."""
import time
import urllib.error
import urllib.request

from .shell import Log


def wait_healthy(url: str, timeout: int, log: Log, interval: float = 2.0) -> None:
    """5xx가 아닌 응답이 오면 성공. 404도 '서버는 떠 있음'으로 본다."""
    deadline = time.time() + timeout
    last = ""
    log(f"헬스체크: {url} (최대 {timeout}초)")
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=5) as r:
                log(f"헬스체크 통과: HTTP {r.status}")
                return
        except urllib.error.HTTPError as e:
            if e.code < 500:
                log(f"헬스체크 통과: HTTP {e.code}")
                return
            last = f"HTTP {e.code}"
        except Exception as e:  # 연결 거부, 타임아웃 등
            last = type(e).__name__
        time.sleep(interval)
    raise TimeoutError(f"헬스체크 실패 ({timeout}초, 마지막 결과: {last})")
