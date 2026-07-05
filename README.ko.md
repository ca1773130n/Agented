<div align="center">

# Agented

**자율 AI 에이전트로 가상 스타트업을 운영하기 위한 메타-하네스 엔지니어링 플랫폼.**

Agented는 AI 하네스 엔지니어링의 최신 기법 — 루프 엔지니어링, 에이전트
오케스트레이션, 스웜, 자기개선, 오토리서치, 영속 메모리 — 을 하나의
제품·프로젝트 중심 운영자 콘솔로 모읍니다. Hermes 스타일 에이전트 시스템을
떠올리되, 더 넓고, 단순히 모델과 대화하는 것이 아니라 **회사를 운영하기 위한**
WebUI를 갖춘 형태입니다.

[아키텍처](docs/ko/self-improving-harness-architecture.md) · [튜토리얼](docs/self-improving-harness-tutorial.md) · [체인지로그](CHANGELOG.md) · [보안](docs/SECURITY.md) · [배포](docs/deploy.ko.md)

**다른 언어로 읽기:** [English](README.md) · [日本語](README.ja.md) · [中文](README.zh.md)

</div>

---

## Agented란

AI 에이전트로부터 실질적이고 지속적인 결과물을 얻는 방법은 **바로 지금** —
컨퍼런스 발표, 블로그 글, 그리고 하네스를 만드는 사람들의 작업 노트 속에서 —
정립되고 있습니다. Agented의 전제는, 이런 아이디어들이 일회성 스크립트와 개인용
장치에 흩어져 있어서는 안 된다는 것입니다. Agented는 이들을 하나의
**메타-하네스 레이어**로 모아 코딩 CLI(Claude Code, Codex, Gemini CLI,
OpenCode 등) 위에 얹고, 이들을 **가상 스타트업**의 인력으로 바꿉니다 —
**제품과 프로젝트**를 중심으로 조직되어, 하나의 콘솔에서 운영됩니다.

아직 **초기 단계이며 빠르게 발전 중**입니다. 이미 구현된 것들:

- **🔁 루프 엔지니어링** — 하나의 `LoopSpec` 스키마와 단일 실행기가 모든 루프
  패턴(goal-loop, Ralph)을 구동합니다: 종료 사다리(품질 게이트 → 정체 →
  수렴 → 예산), 반복별 체크포인트, 재개, 휴먼 게이트.
  → [아키텍처](docs/ko/self-improving-harness-architecture.md)
- **🎛 에이전트 오케스트레이션** — **제품 → 프로젝트 → 팀 → 에이전트**를
  일급 모델로 다루며, 하나의 대시보드에서 조율하고, 각 실행을 프로젝트별
  컨텍스트·계정·프리미티브로 구성합니다.
- **🐝 다중 AI 계정에 걸친 스웜** — (`ai-accounts` 사이드카를 통해) 여러 제공자
  계정에 작업을 스케줄링·핸드오프하고, 올바른 백엔드와 모델로 **자동 라우팅**합니다.
- **♻️ 자기개선** — 하네스 자신의 프리미티브를 진화시키는, eval-게이트가 걸린
  git 되돌리기 가능한 "life-harness" 루프.
- **🔬 오토리서치** — GRD 엔진이 리서치 → 계획 → 실행 → 검증을 자율적인
  마일스톤 계획 파이프라인으로 수행합니다.
- **🧠 영속 메모리 + LLM-위키** — Tesserae가 코드·문서·세션 이력의 타입드
  지식 그래프(및 생성된 위키 페이지)를 컴파일해 모든 검색을 근거화합니다.
- **⏳ 장기 지평 에이전트** — 내구성 있는 실행별 상태, 증분 체크포인트,
  `--resume`으로 실행이 크래시를 견디고 며칠에 걸쳐 이어집니다.
- **📊 관측성** — 실시간 SSE 트레이스, 세션 이벤트, 감사 추적, 그리고 에이전트가
  한 모든 일의 일간/주간 **활동 요약**.
- **🧩 하네스 공유와 조합** — Forge에서 **프리미티브**(스킬·훅·커맨드·룰·서브에이전트)를
  조직해 하네스를 만들고, 플러그인 마켓플레이스로 공유합니다.
- **📦 제품·프로젝트 관리** — 경쟁사 모니터링·발굴·전략 수립, 프로젝트 계획,
  프로젝트별 **원클릭 팀-하네스 셋업**.
- **🛡 거버넌스와 안전** — 스택 가능한 정책 엔진, 기본 차단(egress deny-by-default)
  OS 레벨 샌드박싱, 실시간 다중 사용자 협업.

그 아래에서는, 에이전트의 모든 동작이 체크포인트되고, 출처가 귀속되며, 예산으로
통제되고, 검증 가능합니다 — **출처 추적, 감사 가능성, 롤백이 나중에 덧붙인 게
아니라 설계에 내장**되어 있습니다.

## 빠른 시작

```bash
# 새 머신 — just, uv, Node.js를 자동 설치한 뒤 모든 의존성 설치 (재실행 안전)
bash scripts/setup.sh

# 사전 요구사항이 이미 있다면?
just setup        # 모든 의존성 설치
just dev-all      # 백엔드 :20000 + 사이드카 :20001 + 프론트엔드 :3000
```

콘솔은 **http://localhost:3000** 에서 엽니다. 인터랙티브 API 문서(Swagger UI)는
**http://localhost:20000/schema** 에 있습니다. `just dev-backend`,
`just dev-frontend`, `just dev-ai-accounts` 로 개별 실행할 수 있습니다.

### 사전 빌드 이미지 배포

**권장 — 먼저 클론해서 확인**(코드를 읽고 *나서* 실행):

```bash
git clone https://github.com/ca1773130n/Agented && cd Agented
./install.sh                 # 사전 빌드 이미지 pull + 스택 기동
```

`install.sh`는 함께 클론된 `docker-compose.yml`을 재사용하므로, 확인 없이
가져와 실행되는 코드가 없습니다.

<details>
<summary>편의 한 줄 명령 (덜 안전)</summary>

원격 스크립트를 셸로 파이핑하면 읽지 않은 코드가 실행됩니다. **불변 릴리스
태그**에 고정했을 때만 하세요 — 그러면 인스톨러가 내려받은 compose 파일을
SHA-256으로 검증하고 불일치 시 중단합니다:

```bash
curl -fsSL https://raw.githubusercontent.com/ca1773130n/Agented/v0.10.0/install.sh | bash
```

가변 `main` 브랜치에서 가져오는 것은 `AGENTED_INSTALL_UNVERIFIED=1`을 명시적으로
설정하지 않는 한 거부됩니다(이 경우 체크섬 검증을 건너뛰고 보안 경고를 출력).
[docs/deploy.md](docs/deploy.md#2-single-install-script) 참고.
</details>

```bash
# 기존 설치를 한 명령으로 업데이트 (이미지가 업데이트 단위)
just self-update
```

위의 **Deploy to Render** 배지는 Blueprint 가이드(web + 사이드카 +
`DATABASE_URL`에 연결된 관리형 Postgres)를 엽니다. 이 단독 저장소에서 원클릭은
**아닙니다**: 이미지 빌드에 형제 `ai-accounts/` 트리가 필요하므로, Render는
`Agented/`와 `ai-accounts/`를 모두 담은 **부모 모노레포**(루트에 `render.yaml`)를
연결해야 합니다. 선택적 Postgres 구성을 포함한 전체 설정은
**[docs/deploy.ko.md](docs/deploy.ko.md)** 에 있습니다.

> **첫 실행:** **처음** 등록한 계정이 관리자가 됩니다. 등록을 마치면 —
> 신뢰할 수 없는 네트워크에 노출하기 전에 반드시 — `AGENTED_DISABLE_SIGNUP=1`을
> 설정하세요.

## 구성 요소가 맞물리는 방식

제품과 프로젝트가 모델의 최상위이고, 팀과 에이전트가 작업을 수행하며, 루프·메모리·
정책·프리미티브가 각 실행이 끌어다 쓰는 기계 장치입니다. **트리거**(웹훅, GitHub
이벤트, 스케줄, 수동 실행)는 전달 메커니즘일 뿐입니다 — 제품은 트리거가 시작하는
자율 에이전트 워크플로 그 자체입니다.

| 레이어 | 스택 | 포트 |
|---|---|---|
| **백엔드** | Litestar (gunicorn / UvicornWorker), 순수 SQLite (실험적 Postgres), subprocess + SSE | `:20000` |
| **프론트엔드** | Vue 3 + TypeScript 운영자 콘솔 | `:3000` |
| **사이드카** | `ai-accounts` — AI 백엔드 신원·자격증명·로그인 플로 | `:20001` |
| **메모리** | Tesserae 타입드 지식 그래프 + CodeGraph 심볼 인덱스 | — |

## 설정

| 변수 | 설명 | 기본값 |
|---|---|---|
| `AGENTED_DISABLE_SIGNUP` | 공개 셀프 등록 차단 (첫 관리자 등록 후 설정) | unset (열림) |
| `DATABASE_URL` | 실험적 PG 어댑터를 쓰기 위한 Postgres URL (미설정 ⇒ SQLite) | unset (SQLite) |
| `AGENTED_SANDBOX` | OS 레벨 하네스 샌드박싱(bwrap / seatbelt) 활성화 | unset (꺼짐) |
| `AI_ACCOUNTS_API_KEY` | `ai-accounts` 사이드카 토큰 | 관리자 키 재사용 |

전체 환경변수 레퍼런스와 컨벤션은 [CLAUDE.md](CLAUDE.md) 에 있습니다.

## 검증

배포 전 세 가지 게이트가 모두 통과해야 합니다:

```bash
just build                       # vue-tsc 타입체크 + vite 빌드
cd backend && uv run pytest      # 백엔드 스위트
cd frontend && npm run test:run  # 프론트엔드 스위트
```

## 문서

| 주제 | 링크 |
|---|---|
| 체인지로그 | [CHANGELOG.md](CHANGELOG.md) |
| 자기개선 하네스 — 아키텍처 | [docs/ko/self-improving-harness-architecture.md](docs/ko/self-improving-harness-architecture.md) |
| 배포 — Render Blueprint / 설치 / 셀프 업데이트 | [docs/deploy.ko.md](docs/deploy.ko.md) |
| 보안 | [docs/SECURITY.md](docs/SECURITY.md) |
| ai-accounts 사이드카 | [docs/ai-accounts/ARCHITECTURE.md](docs/ai-accounts/ARCHITECTURE.md) |
| 국제화(i18n) | [docs/i18n.md](docs/i18n.md) |

<div align="center"><sub>1인 스타트업 — 그리고 그 뒤를 잇는 팀 — 을 위한 하네스 엔지니어링.</sub></div>
