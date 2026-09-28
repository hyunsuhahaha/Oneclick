"""CLI.

  python -m oneclick serve                                   대시보드 (http://localhost:7000)
  python -m oneclick deploy <폴더|git URL> -t local -t cloudrun   한 번에 여러 대상 배포
  python -m oneclick rollback <app> -t local                  직전 버전으로 되돌리기
  python -m oneclick targets                                  배포 대상 준비 상태
  python -m oneclick list                                     배포 이력
"""
import argparse
import sys

from . import pipeline, providers, store


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")  # Windows 파이프에서 한글 깨짐 방지
    ap = argparse.ArgumentParser(prog="oneclick")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve")
    s.add_argument("--port", type=int, default=7000)
    s.add_argument("--host", default="127.0.0.1")
    d = sub.add_parser("deploy")
    d.add_argument("source")
    d.add_argument("-t", "--target", action="append", default=[])
    d.add_argument("--app")
    r = sub.add_parser("rollback")
    r.add_argument("app")
    r.add_argument("-t", "--target", required=True)
    sub.add_parser("targets")
    sub.add_parser("list")
    a = ap.parse_args()

    if a.cmd == "serve":
        import uvicorn
        uvicorn.run("oneclick.api:app", host=a.host, port=a.port)
        return 0
    if a.cmd == "targets":
        for p in providers.PROVIDERS.values():
            print(f"{p.name:10} {p.label:28} {p.problem() or '준비됨'}")
        return 0
    if a.cmd == "list":
        for rel in store.list_releases():
            print(f"{rel['id']}  {rel['app']:20} {rel['kind']:8} {rel['source']}")
            for dep in rel["deployments"]:
                print(f"    {dep['target']:10} {dep['status']:10} {dep['url'] or dep['error'][:80]}")
        return 0
    try:
        if a.cmd == "deploy":
            rid = pipeline.start_deploy(a.source, a.target or ["local"], a.app, wait=True, echo=True)
        else:
            rid = pipeline.start_rollback(a.app, a.target, wait=True, echo=True)
    except (ValueError, KeyError, pipeline.Busy) as e:
        print(f"오류: {e}", file=sys.stderr)
        return 2
    deps = store.deployments_of(rid)
    print()
    for dep in deps:
        print(f"{dep['target']:10} {dep['status']:10} {dep['url'] or dep['error']}")
    return 0 if all(d["status"] == store.LIVE for d in deps) else 1


if __name__ == "__main__":
    sys.exit(main())
