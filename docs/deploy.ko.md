# Agented 배포

**언어:** [English](deploy.md) · 한국어 (현재)

Agented를 프로덕션에서 실행하는 세 가지 방법을 노력이 적은 순서대로 정리했습니다.
사전 빌드된 컨테이너 이미지(`ghcr.io/ca1773130n/agented`)가 전 과정에서 배포 단위이며,
배포나 업데이트에 로컬 Python/Node 툴체인이 전혀 필요하지 않습니다.

| 경로 | 노력 | 사용 시점 |
|---|---|---|
| [1. 원클릭 Render](#1-원클릭-render) | 클릭 | 가장 빠른 호스팅 시작; 관리형 Postgres |
| [2. 단일 설치 스크립트](#2-단일-설치-스크립트) | 명령 한 줄 | Docker가 있는 자체 호스트/VM |
| [3. 자체 업데이트](#3-자체-업데이트) | 명령 한 줄 | 기존 설치 업그레이드 |

---

## 1. 원클릭 Render

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/ca1773130n/Agented)

이 저장소는 다음을 선언하는 [`render.yaml`](../render.yaml) Blueprint를 제공합니다:

- **`agented-web`** — 기존 `Dockerfile`로 빌드되는 백엔드 + 정적 프런트엔드
  (`healthCheckPath: /health/liveness`).
- **`agented-sidecar`** — `:20001`의 `ai-accounts` 아이덴티티 서비스로, 같은 이미지를
  `dockerCommand: python scripts/run_ai_accounts.py`로 재사용합니다.
- **`agented-postgres`** — 연결 문자열이 웹 서비스의 **`DATABASE_URL`** 환경 변수로
  주입되는 관리형 Postgres 데이터베이스.

이 마지막 연결은 **Postgres 어댑터를 도그푸딩**합니다(Phase 26-01). `DATABASE_URL`이
설정되면 백엔드는 Postgres에서 실행되고, 그 외 모든 곳에서는 설정이 필요 없는 SQLite
기본값을 유지합니다([§선택적 Postgres](#선택적-postgres-database_url) 참조).

### 빌드 컨텍스트 주의사항 (배포 전 필독)

`Dockerfile`은 빌드 시 **형제 디렉터리 `ai-accounts/` 트리**를 필요로 합니다 —
백엔드 `pyproject.toml`과 프런트엔드 `package.json`이 모두 `../../ai-accounts/packages/*`
경로 의존성을 참조하기 때문입니다. 로컬에서는 상위 디렉터리에서 빌드하여 이를 충족합니다
(`cd .. && docker build -f Agented/Dockerfile .`).

Render는 **연결된 저장소를 Docker 컨텍스트 루트로** 빌드하므로, `render.yaml`은
`dockerContext: .` + `dockerfilePath: ./Agented/Dockerfile`을 사용합니다. 빌드가
`ai-accounts/`를 해석하려면 **연결된 Render 저장소가 `Agented/`와 `ai-accounts/`를 형제로
모두 포함하는 상위 모노레포여야 합니다.**

독립형 `Agented` 저장소(형제 미포함)를 연결하면 빌드는 `COPY ai-accounts/ …` 단계에서
실패합니다. 두 가지 우회 방법:

1. **상위 모노레포 연결**(권장) — `render.yaml`의 경로를 그대로 유지합니다.
2. **`ai-accounts/` 벤더링** — Agented 저장소에 (git submodule 또는 복사로) 포함한 뒤,
   `dockerContext: .`와 `dockerfilePath: Dockerfile`로 설정합니다.

> 형제 빌드 컨텍스트를 종단 간으로 확인하는 실제 Render blueprint 배포는 이 단계의
> 지연된 라이브 인프라 검증으로 추적됩니다.

---

## 2. 단일 설치 스크립트

Docker + `docker compose`(v2)가 있는 임의의 호스트에서:

```bash
curl -fsSL https://raw.githubusercontent.com/ca1773130n/Agented/main/install.sh | bash
```

[`install.sh`](../install.sh)는:

- `ghcr.io/ca1773130n/agented:${GHCR_TAG:-latest}`를 pull하고,
- `docker-compose.yml`과 `.env`가 있는지 확인하며(기존 파일은 덮어쓰지 않아 커스터마이즈가
  유지됨),
- `docker compose pull && docker compose up -d`를 실행합니다.

이 스크립트는 **멱등적**입니다 — 재실행은 no-op 업그레이드입니다. 아무것도 실행하지 않고
정확한 명령을 미리 볼 수 있습니다:

```bash
./install.sh --dry-run
```

환경 변수: `GHCR_TAG`(이미지 태그, 기본값 `latest`), `INSTALL_DIR`(compose 파일이 기록되는
위치, 기본값 현재 디렉터리). 시크릿은 `.env`에 추가하세요 —
[docs/deploy/SECRETS.md](deploy/SECRETS.md) 참조.

---

## 3. 자체 업데이트

기존 설치를 최신 이미지로 이동하려면:

```bash
just self-update
```

이는 `docker compose pull && docker compose up -d`를 실행합니다 — **이미지가 업데이트
단위**이므로 소스 pull이나 재빌드가 없습니다. `GHCR_TAG`로 특정 버전을 고정할 수 있습니다:

```bash
GHCR_TAG=v0.10.0 just self-update
```

저장소가 체크아웃되지 않은 호스트에서는 [`install.sh`](../install.sh)를 재실행해도 동일하게
동작합니다.

> 라이브 자체 업데이트 pull-and-restart(구 → 신 이미지, DB 스키마 유지)는 이 단계의 지연된
> 라이브 인프라 검증으로 추적됩니다.

---

## 선택적 Postgres (`DATABASE_URL`)

**SQLite가 설정이 필요 없는 기본값입니다.** `DATABASE_URL`이 **설정되지 않으면** 동작은
바이트 단위로 동일합니다 — compose 스택과 로컬 개발 흐름은 `AGENTED_DB_PATH`의 임베디드
SQLite 데이터베이스를 사용합니다.

Postgres 지원(Phase 26-01)은 순수하게 **추가적**이며 `DATABASE_URL`이 설정된 경우에만
활성화됩니다:

```bash
export DATABASE_URL="postgresql://user:pass@host:5432/agented"
```

Render blueprint는 관리형 데이터베이스에서 이를 자동으로 설정합니다. 자체 호스팅 설치에서는
`.env`에 `DATABASE_URL`을 추가하여 임의의 Postgres 인스턴스를 가리킬 수 있습니다. SQLite를
유지하려면 설정하지 않은 상태로 두세요.

---

## 함께 보기

- [Runbook](deploy/RUNBOOK.md) · [Backup](deploy/BACKUP.md) · [Secrets](deploy/SECRETS.md)
- [Security](SECURITY.md)
- [i18n 규약](i18n.md)
