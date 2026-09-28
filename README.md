# oneclick

**One Action, Infinite Clouds.** 로컬에서 만든 웹앱을 한 번의 동작으로 여러 배포 대상(로컬 PC, Cloud Run, AWS …)에 동시에 배포하는 기초 뼈대.

SoftBank Hackathon 2026 예선용 베이스 코드. 원클릭 배포 시스템이라면 공통으로 필요한 흐름만 담백하게 구현해 두었고, 팀 아이디어는 이 위에 얹는다.

```
소스(폴더/Git) → 감지·Dockerfile 자동 생성 → docker build (1회)
                                                 ├→ local     (이 PC의 Docker)      ┐
                                                 ├→ cloudrun  (Google Cloud Run)    ├ 병렬 배포 → 헬스체크 → URL
                                                 └→ lightsail (AWS Lightsail)       ┘      └ 실패 시 대상별 자동 롤백
```

## 빠른 시작

필요: Python 3.11+, Docker Desktop

```bash
pip install -r requirements.txt
python -m oneclick serve                 # 대시보드 http://localhost:7000
```

CLI로도 된다:

```bash
python -m oneclick targets                                   # 배포 대상 준비 상태
python -m oneclick deploy examples/hello-node -t local       # 로컬 배포
python -m oneclick deploy https://github.com/me/app -t local -t cloudrun   # 여러 대상 동시 배포
python -m oneclick rollback hello-node -t local              # 직전 버전으로
python -m oneclick list                                      # 이력
python -m unittest discover -s tests                         # 단위 테스트 (Docker 불필요)
```

## 지금 되는 것

| 기능 | 상태 |
|---|---|
| 소스 가져오기: 로컬 폴더 복사 / Git clone | ✅ |
| 프레임워크 감지 → Dockerfile 자동 생성: Dockerfile 우선, Node(package.json), Python(FastAPI·Flask·Procfile), Go, 정적 HTML | ✅ |
| 빌드 1회 → 여러 대상에 병렬 배포 | ✅ |
| 헬스체크 (5xx가 아니면 통과) | ✅ |
| 실패 시 자동 롤백 (로컬: 이전 컨테이너 복구 / 클라우드: 이전 이미지 재배포) | ✅ 로컬 검증 |
| 수동 롤백 ("이전 버전으로") | ✅ 로컬 검증 |
| 같은 앱 동시 배포 방지 (앱별 락, API는 409) | ✅ |
| 배포 이력 · 대상별 상태 · 로그 저장 (SQLite) | ✅ |
| 웹 대시보드 + 실시간 로그 (SSE) | ✅ |
| 로컬 배포를 외부 공개 (`ONECLICK_LOCAL_PUBLIC_TUNNEL=1`, cloudflared) | ⚠️ 코드만, 미검증 |
| Google Cloud Run 어댑터 | ⚠️ 코드만, 실계정 미검증 |
| AWS Lightsail Containers 어댑터 | ⚠️ 코드만, 실계정 미검증 |

## 앱 계약

앱은 **`PORT` 환경 변수(8080)에서 HTTP로 응답**하면 된다. 헬스체크 경로는 기본 `/` (`ONECLICK_HEALTH_PATH`로 변경).

## 구조

```
oneclick/
  pipeline.py        배포 흐름 전체 (여기부터 읽기)
  source.py          폴더 복사 / git clone, 앱 이름 정리
  detect.py          프레임워크 감지 + Dockerfile 템플릿, ai_fallback() 자리
  health.py          헬스체크
  store.py           SQLite: releases / deployments / logs / local_ports
  shell.py           외부 명령 실행 (출력 → 로그)
  providers/
    base.py          배포 대상 인터페이스 (deploy / on_success / on_failure / destroy)
    local.py         이 PC의 Docker
    cloudrun.py      gcloud CLI
    lightsail.py     aws CLI + lightsailctl
  api.py             FastAPI (REST + SSE)
  static/index.html  대시보드
examples/            Dockerfile 없는 예제 앱 (Node, FastAPI)
tests/               단위 테스트
```

상태(DB, 작업 폴더)는 `~/.oneclick`에 저장된다 (`ONECLICK_HOME`으로 변경).

## 확장 포인트

| 하고 싶은 것 | 고칠 곳 |
|---|---|
| 새 클라우드 추가 (Azure Container Apps, ECS Fargate, GCE VM …) | `providers/`에 `Provider` 상속 파일 하나 + `providers/__init__.py`에 등록 |
| AI로 앱 분석 · Dockerfile 생성 · 코드 수정 제안 | `detect.ai_fallback()` |
| 카나리 / 트래픽 분할 | `Provider`에 `deploy(..., traffic=10)` 류 메서드 추가. Cloud Run은 `--no-traffic --tag` + `update-traffic`, 로컬은 앞단 프록시 가중치 |
| 링(Ring) 배포: 로컬 → GCP → AWS 순차 | `pipeline._run_release`의 병렬 배포를 단계별 순차 + 게이트로 변경 |
| DB (SQLite → Cloud SQL/RDS 등) | 새 단계 추가: 감지 → 프로비저닝 → `DB_URL` 주입 |
| GitHub 연동 (push/PR 시 자동 배포) | GitHub Actions에서 `python -m oneclick deploy` 호출 또는 `/api/deploy` 호출 |

## 클라우드 준비

**Cloud Run**
```bash
gcloud auth login
gcloud config set project <PROJECT_ID>
gcloud services enable run.googleapis.com artifactregistry.googleapis.com
gcloud auth configure-docker asia-northeast3-docker.pkg.dev
export ONECLICK_GCP_PROJECT=<PROJECT_ID>
```

**AWS Lightsail**
```bash
aws configure            # 리전 ap-northeast-2
# lightsailctl 설치: https://lightsail.aws.amazon.com/ls/docs/en_us/articles/amazon-lightsail-install-software
```

## 알려진 한계

- 클라우드 어댑터 두 개는 실제 계정에서 아직 돌려 보지 않았다.
- 로컬 교체는 기존 컨테이너를 멈추고 새로 띄우는 방식이라 수 초간 끊긴다 (무중단은 앞단 프록시가 필요).
- 대시보드 서버에 인증이 없다. 로컬(127.0.0.1)에서만 띄울 것.
- 빌드 이미지는 `linux/amd64` 고정 (클라우드 런타임 호환).
