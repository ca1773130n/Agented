# Omnigent vs. Agented — 경쟁 분석 및 개선 계획

> 스냅샷: **2026-06-30**. 출처 신뢰도: omnigent가 **가지고 있는** 기능에 대한 주장은
> 높음(1차 출처 README / `deploy/README.md` / `POLICIES.md` / Releases API / 소스
> 파일, 모두 3-0 적대적 검증, 일부 SHA 고정). **"omnigent에 X가 없어서 Agented가
> 앞선다"**는 주장은 omnigent 공개 문서에서 *부재로부터 추론한 것* — "증명된 부재"가
> 아니라 "근거 없음"이다. omnigent는 약 18일 된 프로젝트로 약 8일마다 마이너 버전을
> 출시하므로, 실행 전 재검증할 것. Agented 측은 내부 설명 기반이며 여기서 코드베이스로
> 재감사하지 않았다.

## TL;DR

[omnigent-ai/omnigent](https://github.com/omnigent-ai/omnigent)은 **Databricks에서
시작한 Apache-2.0 Python 오픈소스 "meta-harness"** 로, Agented와 *정확히 같은 범주*다:
여러 코딩 하네스(Claude Code, Codex, Cursor, OpenCode, Hermes, Pi, Goose, Copilot,
Kiro, Kimi, Qwen, Antigravity + YAML "커스텀 에이전트") 위의 공통 오케스트레이션 레이어.
2026-06-11 생성, 이미 **약 5,437★ / 696 forks**, v0.3.0은 2026-06-27. 우리와 같은
명제 — 따라서 이건 **개념이 아니라 실행의 문제**다.

- **omnigent이 진짜로 앞선 5가지 운영자 측면:** (1) 일급 **중첩형 정책/거버넌스 엔진**,
  (2) **실시간 다중 사용자 협업**, (3) **샌드박싱/배포 범위**, (4) 배포 이미지에서 LLM
  키를 분리하는 **server/runner 분할**, (5) **마찰 없는 배포**(단일 `uv`/PyPI 설치 +
  자체 업데이트 + 데스크톱 앱).
- **Agented이 명확히 앞선 깊이:** **통합 루프 레이어**(LoopSpec + goal_loop_runner
  종료 사다리, checkpoint/resume, carry-vs-reset, LLM-judge 게이트), **연합 교차
  프로젝트 지식 그라운딩**(Tesserae/CodeGraph), **자기개선 life-harness**, **경쟁
  인텔리전스 파이프라인**, **트리거 기반 전달**, **GRD 플래닝**, **HarnessSync** —
  omnigent 문서에는 어느 것도 나타나지 않음.
- **결론:** omnigent은 **거버넌스/협업/배포의 모범 사례로 차용**하고, Agented은
  **자율성/메모리/자기개선 프런티어**를 소유한다. 우리의 루프/메모리 해자를 **희석하지
  않으면서** 그들의 정책 엔진, OS 수준 하네스 샌드박싱, 다중 사용자 협업을 채택한다.

## 1. Omnigent 역량 지도

- **범주 & 명제:** "오픈소스 meta-harness… Claude Code, Codex, Cursor, OpenCode,
  Hermes, Pi 및 직접 작성한 에이전트 위의 공통 오케스트레이션 레이어: 재작성 없이 하네스
  교체 또는 결합." 3대 기둥: **Composition / Control / Collaboration**. YAML
  `executor.harness` 필드로 한 줄 하네스 전환.
- **하네스 플릿(~12 executor):** `claude-sdk, claude-native, codex, codex-native,
  cursor, cursor-native, hermes, hermes-native, opencode, pi, pi-native,
  openai-agents`. v0.3.0에서 7개 추가(Hermes, Copilot, OpenCode, Goose, Qwen Code,
  Kiro, Kimi) + Antigravity를 full SDK + native CLI로 승격.
- **크리덴셜(4종):** API key / Subscription(Claude Pro/Max, 공식 CLI 통한 ChatGPT) /
  Gateway(OpenAI/Anthropic 호환 `base_url`: OpenRouter, LiteLLM, Ollama, vLLM,
  Azure) / Databricks. **에이전트별 기본값 공존**(Claude 기본과 Codex 기본 동시).
- **정책/거버넌스 엔진(그들의 강점):** 모든 액션에 `ALLOW/DENY/ASK`, **3계층 중첩**
  (server admin / per-agent / per-session), **더 엄격한 session 규칙을 먼저 검사**하고
  단락(short-circuit) 가능. 빌트인(실제 파일 — `cost.py` 42KB, `safety.py` 27KB):
  `cost_budget`(하드 `max_cost_usd` + 소프트 `ask_thresholds_usd`),
  `max_tool_calls_per_session`, `ask_on_os_tools`(shell/file-write 전 승인),
  `enforce_sandbox`, `deny_pii_in_llm_request`, `github_policy`, Google 정책.
  `/v1/policies` REST API + 커스텀 정책 SDK.
- **다중 에이전트 오케스트레이터(선언형):** Polly(기본 `omni`) + Debby — 계획하고,
  Claude Code/Codex/Pi 서브 에이전트에 **병렬 git worktree**로 위임한 뒤 **교차 벤더
  리뷰**(각 diff를 작성한 벤더와 *다른* 벤더가 리뷰). "Polly와 Debby는 그냥 YAML 설정" —
  17.6KB `config.yaml` + 마크다운 스킬, 명령형 코드 없음.
- **협업:** 라이브 세션 URL **공유**(실시간 관찰 + 채팅); **co-drive**(`omnigent
  attach` — 팀원 메시지가 *당신의* 머신에서 실행); 다른 머신으로 **fork**(`omnigent run
  --fork`). 다중 사용자 계정 + **OIDC SSO**(Google/GitHub/Okta/Microsoft).
- **샌드박싱/격리:** **9개 클라우드 샌드박스 제공자**(Modal, Daytona, Islo, E2B,
  CoreWeave, Kubernetes, OpenShell, Boxlite, Databricks) + **터미널별 OS 샌드박스**
  (Linux bwrap 필수, macOS seatbelt, Windows Job Object) + **L7 egress 프록시**.
- **배포:** **server/runner 분할** — 슬림한 FastAPI/WS 서버(하네스 SDK 없음, tmux 없음,
  **이미지에 LLM 키 없음**) + 사용자 머신/클라우드 샌드박스의 Runner가 다이얼인
  (`WS /v1/runner/tunnel`)하여 루프를 로컬에서 실행. 단일 공유 이미지 →
  **Render/Railway 원클릭(Postgres 자동), Fly, HF Spaces, Modal, Cloudflare(D1+R2,
  scale-to-zero)**; **Postgres + SQLite 둘 다 일급**(동일 스키마/마이그레이션,
  `DATABASE_URL`).
- **배포(distribution):** `uv tool install omnigent` → PATH에 `omnigent`/`omni`;
  **`omni upgrade` 자체 업데이트** + 시작 시 구버전 알림; `localhost:6767`에서 로컬 서버
  + 웹 UI 자동 시작; 네이티브 **데스크톱 앱**.
- **네이티브 하네스 패리티(v0.3.0, 7개 하네스 부분집합):** compaction, cost/token
  추적, resume, 히스토리 포함 true fork, 세션 내 모델 전환, tool-approval /
  AskQuestion 웹 카드.

## 2. 기능별 비교

| 차원 | omnigent | Agented | 우위 |
|---|---|---|---|
| 에이전트 오케스트레이션 모델 | meta-harness, 선언형 YAML | meta-harness, 계층 products→projects→teams→super-agents→agents→sessions | **TIE** |
| 멀티 하네스/백엔드 범위 | ~12 executor | ~11 백엔드(ai-accounts) | **TIE**(약간 omnigent) |
| 자율성 & 루프 제어 | 하네스 네이티브 resume/compaction | 통합 LoopSpec + 종료 사다리, checkpoint/resume, carry-vs-reset, LLM-judge 게이트 | **AGENTED** |
| HITL & 안전 게이트 | 중첩형 ALLOW/DENY/ASK 정책 엔진 | RBAC + 안전 봇 + 반복별 human-gate | **OMNIGENT** |
| 지식/메모리/그라운딩 | per-session(resume/fork/compaction)만 | Tesserae 연합 시맨틱 그래프 + CodeGraph MCP, 최신성 가중 | **AGENTED** |
| 관측성/텔레메트리 | cost/token 추적, AskQuestion 카드 | 반복별 기록 + 예산 | **TIE** |
| 확장성/플러그인 | 선언형 YAML 에이전트/정책/MCP | 코드 정의; HarnessSync 와이어링 | **OMNIGENT**(작성 용이성) |
| 통합 | GitHub / Google 정책 | 트리거: webhooks / GitHub / 스케줄 / 수동 | **AGENTED** |
| UI/운영자 UX | 다중 사용자 라이브 협업, 데스크톱 앱, 원클릭 설치 | 단일 운영자 Vue 콘솔 | **OMNIGENT** |
| 배포/운영 | 9 샌드박스 + 원클릭 타깃 + Postgres + 키 격리 분할 | clone-and-run, raw SQLite | **OMNIGENT** |
| 자기개선 | 발견되지 않음 | life-harness + 경쟁 인텔 + GRD | **AGENTED** |

## 3. 교훈 & 우선순위 개선 계획

### P1 — 중첩형 정책/거버넌스 엔진 *(높은 임팩트 / 중간 노력)* — 그들의 가장 명확한 우위
Agented의 흩어진 제어(RBAC, `bot-security`/`bot-pr-review`, goal_loop_runner
human-gate, 종료 사다리 예산)를 **하나의 `ALLOW/DENY/ASK` 정책 레이어**로 통합하여
**server / team / session** 범위로 중첩(더 엄격한 범위 먼저)하고, 비용 상한(하드 + 소프트
임계), 최대 도구 호출, shell/file-write 전 승인 빌트인을 제공한다.
**대상:** `app_litestar/middleware.py`(신규 정책 미들웨어), `ExecutionService`(액션
인터셉션), `goal_loop_runner.py`(human-gate 훅), 프런트엔드 `budgets.ts`/answer-eval
표면. **session** 범위에 앵커(session-not-bot 규칙대로), project/team/workflow/trigger
전반에 걸침.

### P1 — OS 수준 하네스 샌드박싱 + egress 제어 *(높은 임팩트 / 높은 노력)* — 오늘의 실제 안전 공백
각 `subprocess.Popen` 하네스를 **bwrap(Linux) / seatbelt(macOS)** + **L7 egress
허용목록 프록시**로 감싸, `sandbox_eval.py`를 결정론적 검사 너머 *라이브* 하네스로
일반화한다. 오늘 하네스는 git-worktree 격리만으로 운영자 호스트에서 자율 파일/shell/네트워크
접근을 갖는다 — **경쟁 인텔 auto-implement**와 **life-harness 자율** 루프가 최고 위험
소비자다.
**대상:** `ExecutionService`(서브프로세스 실행), `sandbox_eval.py`(일반화), 신규 egress
프록시. **저노력 임시:** 신뢰 불가 자율 실행용 선택적 **클라우드 샌드박스 러너(E2B/Modal)**.

### P2 — 실시간 다중 사용자 협업 *(높은 임팩트 / 높은 노력)*
라이브 SSE 세션 URL **공유**(읽기 + 채팅), **co-drive**(팀원 메시지가 운영자의 실행 중
세션에 대해 실행), 세션 **fork**; 선택적 **OIDC SSO**. Agented은 이미 하네스 출력을
SSE 스트리밍하므로 **라이브 공유는 기존 스트림의 점진적 확장**이고, co-drive + OIDC가 더
큰 작업이다. P1과 자연스럽게 짝지어 공유 세션이 거버넌스 하에 유지된다.
**대상:** 프런트엔드 SSE 레이어 + Vue 콘솔(share/attach UI), `ExecutionService` 세션
모델(multi-attach), 인증 미들웨어(범위 지정 공유 토큰), 선택적 OIDC(ApiKey 미들웨어 +
ai-accounts).

### P3 — 배포 & 확장성 에르고노믹스 *(중간 임팩트 / 중간 노력)*
(a) SQLite와 함께 일급 **Postgres**(동일 스키마/마이그레이션, `DATABASE_URL`) + 컨테이너
이미지 + 원클릭 타깃; (b) **단일 설치 / 자체 업데이트** 배포 경로; (c) **선언형 YAML**
에이전트/팀/오케스트레이터 정의("YAML 파일이 곧 에이전트")로 코드 없이 teams/super-agents
작성; (d) 호스팅 배포용 선택적 **server/runner 키 격리 분할**.
**대상:** `app/database.py`(Postgres 어댑터), 패키징/배포, teams/super-agents 설정
레이어, ai-accounts(runner 측 키 보관).

### Agented이 omnigent을 **쫓지 말아야 할** 곳
**해자**에 계속 투자한다 — 통합 루프 레이어, Tesserae/CodeGraph 그라운딩, life-harness,
경쟁 인텔, GRD, 트리거는 **omnigent 대응물이 없다**. 목표는 자율성/메모리/자기개선에서
격차를 **넓히면서** 거버넌스/협업/배포에서 격차를 **좁히는** 것.

## 실행 전 해소할 미해결 질문
1. omnigent에 우리의 수렴-까지-반복 종료 사다리에 *상응하는* 것이 있는가, 아니면 자율성이
   하네스 네이티브 resume + 오케스트레이터-YAML 위임뿐인가? (러너 루프 + Polly 스킬 점검.)
2. 영속적 교차 세션/교차 프로젝트 메모리가 있는가, 순수 per-session인가? (우리의
   Tesserae/CodeGraph 우위가 부재로부터 주장된 차원.)
3. 트리거/이벤트/스케줄 실행이 있는가, 순수 대화형/CLI인가?
4. 하네스 도구 접근을 깨지 않고 `subprocess.Popen` 하네스를 OS 샌드박싱하는 실제 비용 —
   클라우드 샌드박스 러너가 동일 보장으로 가는 더 빠른 경로인가?

## 출처(1차, 검증됨)
- README — https://github.com/omnigent-ai/omnigent/blob/main/README.md
- 배포 문서 — https://github.com/omnigent-ai/omnigent/blob/main/deploy/README.md
- Releases (v0.3.0) — https://github.com/omnigent-ai/omnigent/releases
- 빌트인 에이전트 문서 — https://omnigent.ai/docs/use/builtin-agents
- Databricks 출시 블로그 — https://www.databricks.com/blog/introducing-omnigent-meta-harness-combine-control-and-share-your-agents
