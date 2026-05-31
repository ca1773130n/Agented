# 자기개선 하네스: 아키텍처

**언어:** [English](/self-improving-harness-architecture) · 한국어 (현재)

*[BLOG-self-improving-harness.md](https://github.com/ca1773130n/Agented/blob/main/BLOG-self-improving-harness.ko.md)의 동반 문서.
블로그는 에이전트 메모리 분야가 잘못된 축(회상 정확도)을 최적화하고 있으며,
실제 프로덕션에서 중요한 축(출처(provenance) + 감사가능성)을 놓치고 있다고
주장한다. 이 문서는 그 문제를 진지하게 받아들였을 때 나오는 시스템 —
메모리 저장소가 아니라 닫힌 **자기개선 루프(self-improvement loop)** — 을
설명하고, 블로그가 언급한 메모리 아키텍처들과 솔직하게 비교한다.*

---

## 1. 우리가 푼 문제는 메모리가 아니다

블로그가 언급한 모든 시스템 — Mastra, Letta/MemGPT, Zep/Graphiti, Mem0,
Cognee, Hermes Agent — 은 **메모리 아키텍처**다. 이들의 역할은: 대화
스트림이 주어졌을 때 사실을 *보존*하고 나중에 압박 속에서 *회상*하는 것이다.
벤치마크는 LongMemEval이고, 축은 검색 정확도다.

Agented의 자기개선 하네스는 그보다 한 층 위에 있다. 메모리는 기반(substrate)일
뿐 산출물이 아니다. 산출물은 다른 질문을 던지는 루프다:

> 에이전트가 여러 세션에 걸쳐 한 모든 것을 고려할 때, **하네스 자체가
> 어떻게 바뀌어야 하는가** — 규칙(rule), 훅(hook), 커맨드(command),
> 스킬(skill), MCP 바인딩 — 그리고 그 변경을 사람이 손으로 프리미티브를
> 편집하지 않고도, *감사 사슬을 잃지 않으면서* 채점하고, 승인하고,
> 되돌리고, 전파할 수 있는가?

이것은 **자기개선** 문제(자신의 운영 컨텍스트를 변형하는 것)이지,
**메모리** 문제(들은 것을 회상하는 것)가 아니다. 둘은 일상적으로 혼동된다.
이 둘은 다르며, 두 번째가 더 어렵다. "배포 스크립트가 옮겨졌다"를 회상하는
메모리 시스템은 여전히 그것을 규칙으로 바꿔줄 사람이 필요하다. 자기개선
하네스는 그 간극을 닫는다 — 그리고 그 순간, 순수 회상 시스템은 결코 마주치지
않는 보안 및 감사 부담을 떠안는다: 이제 시스템은 자신의 추론에 근거해
*실행 가능한 지시문을 디스크에 쓰고* 있는 것이다.

우리의 전체 아키텍처는, 그 쓰기가 채점 게이트, 승인(운영자 또는 정책으로
제한된 자율), 롤백 저널, 그리고 종단 간 출처(provenance) 없이는 일어나지
않도록 거부하는 것으로 형성된다.

---

## 2. 닫힌 루프

```
 ┌──────────────────────────────────────────────────────────────────────────┐
 │                                                                            │
 │   (1) CAPTURE            (2) ANNOTATE / EXTRACT        (3) GATHER          │
 │   every session   ──►    two asymmetric evidence  ──►  + KG-seeded        │
 │   → snapshot+events      streams (failures|wins)       evolution inputs    │
 │                                                            │               │
 │                                                            ▼               │
 │   (10) KG FEEDBACK                                    (4) PROPOSE          │
 │   sessions compiled  ◄────────────────────────        Codex in sandboxed  │
 │   into typed graph                                     scratch → patch     │
 │        ▲                                                   │               │
 │        │                                                   ▼               │
 │   (9) PROPAGATE                                       (5) EVAL-GATE        │
 │   proven primitives   ◄───────┐                       static checks +     │
 │   promote cross-project        │                      replay LLM judge     │
 │        ▲                       │                       → EvalVerdict       │
 │        │                       │                           │               │
 │   (8) ROLLBACK            (7) MATERIALIZE             (6) APPLY            │
 │   reverse journal     ◄──  .claude/ + one git    ◄──  operator-approved   │
 │   + git revert            commit per round            OR policy-autonomous │
 │                                                                            │
 └──────────────────────────────────────────────────────────────────────────┘
```

번호가 매겨진 각 단계는 코드베이스 안의 실제적이고 감사 가능한 산출물이다.
이 루프는 자유롭게 돌아가는 것이 아니라 **게이트로 통제**된다: 출처를
기록하는 명시적 경계를 넘지 않고서는 어떤 프리미티브도 변형되거나, 디스크에
안착하거나, 전파되지 않는다.

### (1) 캡처 — `harness_snapshot_service.py`, `session_events.py`
완료된 모든 세션마다(*모든* 세션 종류에 걸쳐 — 트리거 실행, 슈퍼-에이전트
실행, 팀 실행, 워크플로; 결코 "봇"만이 아니다) 해소된 하네스 번들의
**스냅샷**이 원시 세션 이벤트 스트림과 함께 영속화된다. 이것이 출처
원장(ledger)의 입력 계층이다. 블로그의 "12개의 조용한 실패" 막간은 바로 이
계층이 하류로 거짓말하지 않도록 만드는 것에 관한 이야기다 — 모든
페처(fetcher)/파서(parser)는 신뢰되기 전에 실제 프로덕션 데이터 ≥3행에 대해
도그푸딩된다.

### (2) 주석 + 추출 — 두 개의 비대칭 증거 스트림
둘 다 동일한 `session_complete` 채널에서 갈라져 나온다:

- **실패 주석기(failure annotator)** (`harness_failure_annotator.py`)는
  **Life-Harness 4계층 분류 체계** — `detect_h2`(인터페이스) →
  `detect_h3`(환경 계약) → `detect_h4`(궤적 규제) → 일반 — 를 실행하며,
  `_apply_priority_protocol`로 우선순위가 정해져 타입이 지정된 인시던트를
  `harness_annotations`에 기록한다.
- **테이크어웨이 추출기(takeaway extractor)**
  (`harness_takeaway_extractor.py`, 휴리스틱 + provider-kind LLM)는 *긍정적*
  신호 — 사용자 선호, 발견된 절차, 도구 사용 패턴, 제약, 도메인 사실, 근본
  원인, 성공 패턴 — 을 `harness_takeaways`에 표면화한다(안정적인 `tk-*` ID,
  `session_kind`/`session_id` 역참조, 추출기 버전, 신뢰도 포함).

**비대칭성이 핵심이다**: 실패는 규칙과 훅을 원하고, 성공은 스킬과 커맨드를
원한다. 대부분의 메모리 시스템은 한 방향(보통 긍정)만 포착하고 신호의 절반을
조용히 잃는다.

### (3) 수집(Gather) — `harness_evolver.gather_inputs`
진화 라운드의 입력을 조립한다: 프로젝트에 현재 바인딩된 Forge 프리미티브,
최근 궤적(스냅샷 + 그 주석 + 인시던트), 최근 테이크어웨이, **그리고** —
마지막 루프의 모서리 — 컴파일된 Tesserae 그래프에서 나온 **KG
신호**(`gather_kg_signals`, ≤3개의 제한된 `ask_tesserae` 발견 질문,
가중·중복제거, Tesserae 비활성 프로젝트는 비용 0이 되도록 게이트됨). 루프가
*생산*하는 그래프(10단계)가 이제 루프를 *씨앗으로 공급*한다(3단계). 이것이
이것을 파이프라인이 아니라 루프로 만든다.

### (4) 제안(Propose) — 샌드박스 스크래치 워크스페이스 안의 Codex
`build_workspace`는 입력을 임시 디렉터리(`forge/`, `trajectories/`,
`takeaways/`, `KG_SIGNALS.md`, `tesserae_context.md`)에 쓴다;
`codex exec --sandbox workspace-write`가 그에 대해 실행된다; 결과 패치가
파싱되고 스키마 검증된다. **모델은 diff를 제안한다; 라이브 프리미티브를
인-프로세스로 편집하는 일은 결코 없다.**

### (5) 평가 게이트(Eval-gate) — `harness_evolution_eval.py`
어떤 적용(apply) 이전에, 패치는 **`EvalVerdict`**(`passed: bool`,
`score: float ∈ [0,1]`, `per_check: [CheckResult]`)로 채점된다:

- **정적 검사(static checks)** (`_static_checks`) — 기계적: 스키마 유효성,
  프론트매터 정합성, 무동작(no-op) 탐지, 행 고정(line-anchored) 가드.
- **회귀-재현 판정자(regression-replay judge)** (`_run_judge`,
  `resolve_llm_cmd`를 통한 provider-kind) — 대표 세션 샘플을 *패치된*
  프리미티브 집합에 대해 재현하고, 동작이 회귀했는지 판정자에게 묻는다.

`_verdict`는 패치가 통과하지 못할 때 점수를 신뢰 하한(trust floor) 아래로
억제한다. 실패한 게이트(`eval_failed`)는 적용을 단락(short-circuit)시킨다.
게이트 *오류*는 fail-open이지만 **점수 0.0의 우회(bypass) 판정**을 기록하므로,
우회가 실제 통과와 조용히 구별 불가능해지는 일은 결코 없다. 이것이 모든
"자기편집 메모리" 시스템에 결여된 채점 계층이다.

### (6) 적용(Apply) — 운영자 승인 **또는** 정책 자율
라운드의 상태 기계
(`pending → running → evaluating → awaiting_approval → applied`, 그리고
`eval_failed`/`failed`/`aborted`/`reverted` 종료)는 **동일한** 기계 장치에
대해 두 가지 적용 경로를 지원한다:

- **운영자**: 드라이런 라운드가 `awaiting_approval`에 머무르고, 운영자가
  diff를 검토한 뒤 `POST /evolution/rounds/{id}/apply`.
- **자율**(`harness_autonomy.py`): 5분 주기 스케줄러 작업
  (`autonomous_apply_job` → `process_project_autonomy`)이 `autonomous_apply_eligible`이
  **9개의 하드 게이트**를 통과할 때*에만* 자동 적용한다 — 킬 스위치
  (`AGENTED_AUTONOMY=0`), 프로젝트별 정책 활성화, eval `passed` **그리고**
  `score ≥ confidence_threshold`(기본 0.85), 블라스트 반경 ≤
  `max_ops_per_round`, `allowed_kinds`, `block_deletes`, `cooldown_seconds`,
  `rate_limit_per_day`. 기본은 꺼짐이며, 프로젝트별 옵트인
  (`project_autonomy_config`).

자율은 운영자 경로의 *제한된* 격상이지, 별도의 감사되지 않는 코드 경로가
아니다.

### (7) 구체화(Materialize) — `forge_materialization_service.py`
적용된 프리미티브는 프로젝트의 실제 `.claude/` 레이아웃
(commands/rules/hooks + `settings.json`/`mcp.json`/skills)으로 멱등적이고
운영자-보존적으로 투영되며, **라운드당 하나의 git 커밋**으로 커밋된다.
하네스의 진화는 이제 `git log`다.

### (8) 롤백(Rollback) — `harness_evolution_rollback.py`
`apply_patch`는 **before-image 적용 저널(apply-journal)**을 포착한다.
`revert_round`는 라운드가 저널을 가진 `applied` 상태가 아니면 거부하고,
충돌(동일 `{kind, asset_id}`를 건드린 이후 라운드)을 탐지하며, DB 연산을
멱등적으로 역행한 뒤 구체화 커밋을 git revert한다. 부분 실패 또는 git 실패는
라운드를 `revert_error`와 함께 `applied`로 남긴다 — 달성하지 못한
`reverted`를 *주장*하는 일은 결코 없다. 이것이 블로그의
"AuditEval Rollback 축"의 구현이다.

### (9) 전파(Propagate) — `harness_propagation.py`
콘텐츠 **핑거프린트**(`forge_fingerprint.py`, 콘텐츠 필드의 sha256)가
프리미티브에 프로젝트 간 정체성을 부여한다. 적용되고 **eval-PASSED**된 각
라운드는 감쇠된 승격 증거를 기록하며, 어떤 핑거프린트의 시간 감쇠 점수가
`PROMOTION_THRESHOLD = 3.0`을 넘으면 **글로벌 스코프 사본**이 승격되고
(`shared_forge_bindings`) 다른 프로젝트들이 그것을 채택한다
(`adopt_shared_binding`, local-wins 충돌 정책). `_PROPAGATABLE = (rule,
hook, command)`. eval-통과 라운드만 증거에 기여하므로 — 어떤 강제 적용도
공유 계층을 오염시킬 수 없다.

### (10) KG 피드백 — `tesserae_integration.py`
완료된 모든 세션은 프로젝트의 Tesserae 워크스페이스로 자동 임포트된다
(`on_session_complete` → `export_sessions_to_tesserae`); 운영자는 타입이
지정된 지식 그래프(`CodeFile`, `Session`, `SessionTakeaway`,
`SessionDecision`, …)를 컴파일한다. 그 그래프가 (3)단계가 질의하는 기반이다 —
루프를 닫는다.

---

## 3. 무엇이 이것을 감사 가능하게 만드는가 (관통선)

모든 단계는 타임스탬프와 역참조를 가진 행(row)을 방출한다:

- 어떤 동작 → 그것을 만든 **규칙** → 그것을 단조한 **라운드** → 그것을
  채점한 **eval 판정** → 그것을 동기화한 **테이크어웨이/인시던트** → 그것들이
  추출된 **세션** → 영속적 트랜스크립트.
- 학습된 휴리스틱은 ID로 **되돌릴(revert)** 수 있으며, 그것이 비롯된 세션과
  테이크어웨이는 여전히 질의 가능하다.
- 승격된 프리미티브는 자신의 **핑거프린트**와 임계값을 넘은 증거를 지닌다.

이 사슬의 어느 것도 임베딩 블롭에 대한 유사도로 점수화되지 않는다. 이것이
어떤 메모리 벤치마크도 측정하지 않으며 블로그가 가정한 *AuditEval*이 측정할
속성이다.

---

## 4. 블로그가 언급한 아키텍처들과의 비교

솔직한 틀: **이들 대부분은 경쟁자가 아니다 — 다른 축에서 작동한다.**
Mastra/Zep/Mem0/Cognee는 메모리/검색 계층이며, Agented는 그중 하나를 자신의
캡처 기반으로 *사용*할 수도 있다. 진정한 자기변형 이야기를 가진 두 시스템 —
**Letta**(도구를 통한 자기편집 메모리)와 **Hermes Agent**(`skill_manage`,
자율 스킬 생성) — 이 실제 비교 지점이며, 그 대비는 *게이트*다.

| 축 | **Agented 자기개선 하네스** | Letta / MemGPT | Hermes Agent | Mastra | Zep / Graphiti | Mem0 | Cognee |
|---|---|---|---|---|---|---|---|
| 주된 문제 | 자기개선 루프 | 메모리 (LLM-as-OS) | 파일 기반 하네스 상태 + 스킬 생성 | 메모리 계층 | 양시간(bi-temporal) KG 메모리 | 하이브리드 메모리 | RAG-투-그래프 |
| 증거 스트림 | **둘, 비대칭** (실패 분류 + 긍정 테이크어웨이) | 하나 (긍정) | 하나 (긍정) | 하나 | 하나 | 하나 | 하나 |
| 자기변형 | **제안된 diff** (샌드박스 Codex) | 인라인, 에이전트가 도구로 메모리 편집 | 에이전트가 새 스킬을 디스크에 씀 | 해당 없음 (저장소) | 해당 없음 | 해당 없음 | 해당 없음 |
| 적용 전 채점 | **eval 게이트** (정적 + 재현 판정 → 점수 판정) | 없음 | 없음 | 해당 없음 | 해당 없음 | 해당 없음 | 해당 없음 |
| 승인 모델 | **운영자 승인, 또는 정책으로 제한된 자율 (9 게이트)** | 자율 | 자율 | 해당 없음 | 해당 없음 | 해당 없음 | 해당 없음 |
| 디스크 안착 형태 | **라운드당 1 git 커밋** (`.claude/`) | 메모리 행 | 파일 | 저장소 행 | 그래프 | 저장소 | 그래프 |
| 롤백 | **before-image 저널 + git revert, 충돌 인식** | — | — | — | 양시간(과거 뷰) | — | — |
| 프로젝트 간 전파 | **핑거프린트 → 감쇠 증거 → 글로벌 승격 → 채택** | — | — | — | — | — | — |
| 믿음의 출처 | **소스 세션까지의 행-사슬, 임베딩 추측 없음** | 도구-편집 이력 | 파일 이력 | 저장소 메타데이터 | 양시간 엣지 | 추출 로그 | 그래프 계보 |
| 위협 모델 자세 | 기본 "제안 → 승인"; 삭제 차단; 우회 = 점수 0 | 인라인 편집 = 인라인 위험 | **`skill_manage` = 내려받은 의존성** | 저장소 전용 | 저장소 전용 | 저장소 전용 | 저장소 전용 |

### 분명히 말하면

- **vs. Letta / MemGPT** — Letta는 자기편집 메모리를 개척했다; 에이전트가
  도구 호출을 통해 자신의 코어/아카이벌 메모리를 인-프로세스로, 검토 없이
  재작성한다. 우리는 의도적으로 **제안-검토** 변형을 택했다: 모델이 *diff*를
  방출하고, eval 게이트가 그것을 *채점*하며, 운영자(또는 제한된 정책)가
  승인한다. 공개 스킬의 36.8%가 보안 결함을 가진 세상(Snyk ToxicSkills)에서,
  안착-전-diff는 사치가 아니다. 우리는 인라인 편집이 *틀렸다*고 주장하지
  않는다 — 어떤 규제 환경 배포든 이 게이트를 추가하게 될 것이며, 첫날부터
  그것을 중심으로 설계하는 편이 나중에 개조하는 것보다 싸다고 주장한다.
- **vs. Hermes Agent** — Hermes의 `skill_manage`는 에이전트가 자율적으로
  스킬을 디스크에 작성하게 한다. 구조적으로, *스킬을 씀으로써 학습하는
  에이전트는 의존성을 내려받은 것이다.* 우리의 스킬 경로는 기본적으로 운영자
  승인이며(`AGENTED_TAKEAWAY_AUTOAPPLY` 옵트인), 운영자-큐레이트 스킬과의
  diff가 `git status` 한 번 거리에 있도록 **별도의 gitignore된
  `.agented-takeaways/` 디렉터리**에 쓰이고, 적용된 모든 스킬은 자신의
  테이크어웨이 + 세션 + 신뢰도로 역참조된다.
- **vs. Mastra / Mem0 / Cognee** — 순수 메모리/검색 계층. 이들은 LongMemEval을
  이긴다; 회상 축에서 진정으로 훌륭한 엔지니어링이다. 이들에게는 제안/채점/적용/롤백/전파
  루프가 없는데, 그것이 그들의 문제가 아니기 때문이다. Agented는 이들 중
  어느 것 *위에도* 앉을 수 있다.
- **vs. Zep / Graphiti** — *하나의* 축에서 정신적으로 가장 가깝다:
  Graphiti의 양시간 그래프는 이벤트 시각과 수집 시각을 모두 추적하는데, 이는
  **메모리** 계층을 위한 실제 출처 인프라다. 우리는 유사한 작업을 위해
  Tesserae(타입 지정, 오프라인 컴파일, 온라인 질의)를 쓰지만, 우리의
  양시간-등가물은 *하네스-진화* 계층에 있다: 라운드의 적용 저널 + git 이력이
  하네스가 무엇을 언제 믿었는지 정확히 기록하고, 그것을 되돌릴 수 있게 한다.
- **vs. Life-Harness 논문** ([arXiv 2605.22166](https://arxiv.org/abs/2605.22166))
  — 우리는 그 4계층 실패 분류 체계(H2/H3/H4/일반)를 *실패* 증거 스트림으로
  채택하고 일반화한다: 논문은 무엇이 잘못됐는지 분류하고, 우리는 그 분류를
  그것에 따라 행동하는 단조-채점 루프에 배선하며, 긍정 증거 스트림과 짝지어,
  그 결과로 나오는 모든 변경을 되돌릴 수 있고 전파할 수 있게 만든다.

---

## 5. 한 문장 버전

메모리 분야는 사실을 정확히 회상하려 경주하고 있다; 우리는 그 사실들로부터
**하네스가 무엇이 되어야 하는지 결정하는** 계층을 만들었다 — 그리고 그 결정을
*채점되고, 승인되고, 되돌릴 수 있고, 전파될 수 있으며, 종단 간 감사 가능하게*
만들었다. 에이전트가 디스크에 지시문을 씀으로써 자신을 개선하는 순간, 그
속성들 하나하나가 선택사항이기를 멈추기 때문이다.

---

## 소스 맵 (위의 모든 주장은 트리 안의 심볼이다)

| 단계 | 코드 |
|---|---|
| 캡처 | `app/services/harness_snapshot_service.py`, `app/db/session_events.py`, `harness_snapshots` |
| 주석 | `app/services/harness_failure_annotator.py` (`detect_h2/h3/h4`, `_apply_priority_protocol`), `harness_annotations` |
| 추출 | `app/services/harness_takeaway_extractor.py`, `harness_takeaways` (`tk-*`) |
| 수집 | `app/services/harness_evolver.py::gather_inputs`, `app/services/harness_kg_signals.py::gather_kg_signals` |
| 제안 | `harness_evolver.py` (`build_workspace`, `_run_codex_in_workspace`, `parse_patch`, `validate_patch`) |
| 평가 게이트 | `app/services/harness_evolution_eval.py` (`evaluate_patch`, `_static_checks`, `_run_judge`, `_verdict`), `app/models/harness_evolution.py`의 `EvalVerdict` |
| 적용 | `harness_evolver.py::apply_patch`; 라우트는 `app_litestar/routes/harness_evolution.py` |
| 자율 | `app/services/harness_autonomy.py` (`autonomous_apply_eligible`, `process_project_autonomy`), `app_litestar/lifecycle.py`의 `autonomous_apply_job`, `app/models/autonomy_policy.py`, `project_autonomy_config` |
| 구체화 | `app/services/forge_materialization_service.py` |
| 롤백 | `app/services/harness_evolution_rollback.py` (`revert_round`, `reverse_apply_journal`, `_git_revert`); `POST /evolution/rounds/{id}/revert` |
| 전파 | `app/services/harness_propagation.py`, `app/services/forge_fingerprint.py`, `forge_promotion` 리포, `shared_forge_bindings`; `GET /shared-forge`, `POST /projects/{id}/adopt-shared/{sbid}` |
| KG 피드백 | `app/services/tesserae_integration.py` (`on_session_complete`, `export_sessions_to_tesserae`, `ask_tesserae`) |
| 라운드 상태 | `harness_evolution_rounds` CHECK: `pending·running·evaluating·awaiting_approval·applied·eval_failed·failed·aborted·reverted` |

*5개 페이즈에 걸쳐 전달된 아키텍처 (A 증거 · B 단조 · C 평가+롤백 ·
D 자율 · E 전파+KG-소스), 2026-05-31 `main`에 머지됨.*
