"""외부 명령(docker, gcloud, aws) 실행. 출력은 한 줄씩 로그로 흘려보낸다."""
import shutil
import subprocess
from typing import Callable

Log = Callable[[str], None]


class CommandError(RuntimeError):
    pass


def which(name: str) -> str | None:
    return shutil.which(name)


def run(cmd: list[str], log: Log | None = None, cwd: str | None = None,
        check: bool = True, quiet: bool = False) -> str:
    """명령을 실행하고 stdout+stderr 전체를 반환한다.

    Windows에서 gcloud 같은 .cmd 래퍼를 찾을 수 있도록 실행 파일 경로를 먼저 해석한다.
    """
    exe = which(cmd[0]) or cmd[0]
    if log and not quiet:
        log("$ " + " ".join(cmd))
    proc = subprocess.Popen([exe, *cmd[1:]], cwd=cwd, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                            errors="replace")
    out = []
    assert proc.stdout
    for line in proc.stdout:
        line = line.rstrip()
        out.append(line)
        if log and not quiet and line:
            log(line)
    code = proc.wait()
    text = "\n".join(out)
    if check and code != 0:
        tail = "\n".join(out[-5:])
        raise CommandError(f"{cmd[0]} {cmd[1] if len(cmd) > 1 else ''} 실패 (exit {code})\n{tail}")
    return text


def ok(cmd: list[str]) -> bool:
    """성공 여부만 확인 (출력 없음)."""
    try:
        run(cmd, check=True, quiet=True)
        return True
    except (CommandError, FileNotFoundError):
        return False
