# 튜토리얼: 하네스가 스스로 개선되는 과정 보기 (위키형 메모리와 함께)

**언어:** [English](/self-improving-harness-tutorial) · 한국어 (현재)

*직접 해보는 워크스루입니다. 약 30분 동안 에이전트 세션을 몇 개 실행하고,
Agented가 그것을 타입이 있는 메모리로 바꾸는 과정을 지켜보고, 그 메모리를
탐색 가능한 **LLM-위키**로 컴파일한 뒤, 하네스가 **자신의 규칙**에 대한
변경을 제안·채점·적용하고 (원한다면) 되돌리는 과정을 — 새 규칙에서 그것을
유발한 세션까지 거슬러 올라가는 출처(provenance) 체인과 함께 — 지켜봅니다.*

> 이 문서는 두 개의 레퍼런스 문서에 대한 *직접 보여주는* 동반 문서입니다.
> "왜"와 "무엇"이 궁금하면 그쪽을 읽으세요:
> - **[자기개선 하네스: 아키텍처](/ko/self-improving-harness-architecture)** — 닫힌 루프를 단계별로, 실제 심볼에 매핑.
> - **[블로그: 당신의 에이전트는 메모리 문제가 아니다. 출처 문제다.](https://github.com/ca1773130n/Agented/blob/main/BLOG-self-improving-harness.ko.md)** — 이 시스템이 따라 나오는 논증.

---

## 무엇에 대한 감을 잡게 되는가

서로 다른 두 계층, 그리고 그 둘이 서로를 먹이는 방식:

1. **위키형 메모리** — 완료된 모든 세션은 타입이 있는 지식 그래프(Tesserae)로
   컴파일되고 **탐색 가능한 위키 / Obsidian 볼트**로 투영됩니다. 사람은 위키처럼
   읽고, 에이전트는 그래프처럼 질의합니다.
2. **자기개선 루프** — 하네스는 그 메모리와 실패/성공 증거 스트림을 읽어,
   **자신의 프리미티브**(규칙, 훅, 커맨드, 스킬, MCP 바인딩)에 대한 **diff를
   제안**하고, **채점**하고, **하나의 git 커밋**으로 **적용**하며, 그것을
   **되돌리거나** **전파**할 수 있습니다.

마지막에 보게 될 핵심: 루프가 *생산하는* 그래프가 곧 루프가 *소비하는*
기질(substrate)입니다. 바로 그 간선이 이것을 파이프라인이 아니라 루프로
만듭니다.

---

## 0. 사전 준비

```bash
# 리포지토리 루트에서
just deploy            # 백엔드(:20000), 사이드카(:20001), 프론트엔드(:3000) 빌드 + 시작
# …또는 반복 작업용:
just dev-backend &     # :20000
just dev-frontend      # :3000
```

운영자 콘솔을 `http://localhost:3000` 에서 엽니다.

또한 **Tesserae** CLI + MCP(에이전트 메모리 시스템)가 있어야 합니다.
확인:

```bash
tesserae --version
```

콘솔에서 **프로젝트**를 고르거나 만듭니다 — Projects → New. 아래 내용은 모두
하나의 프로젝트로 스코프됩니다.

> **내부적으로:** 프로젝트, 제품, 팀, 에이전트는 접두사 ID 행입니다
> (`proj-…`, `agent-…`). 백엔드는 모든 하네스를 `subprocess.Popen`으로 구동하고
> 출력을 콘솔로 SSE 스트리밍합니다.

---

## 1. 프로젝트에 위키형 메모리 켜기

콘솔에서: **Settings → Memory System →** 이 프로젝트에 대해 Tesserae를
활성화하고 워크스페이스 경로를 지정합니다. (선호한다면 동등한 SQL:
`UPDATE projects SET tesserae_project_root = '/abs/path' WHERE id = 'proj-…';`)

활성화되면 **완료된 모든 세션이 자동으로 임포트**됩니다 — 세션마다 따로
배선할 것이 없습니다.

> **내부적으로:** `app/services/tesserae_integration.py`
> (`on_session_complete → export_sessions_to_tesserae`). 루프의 **(10)**
> 단계입니다.

---

## 2. 증거 만들기 (세션 몇 개 실행)

에이전트가 무언가를 *해야* 루프가 배울 게 생깁니다. 신호가 생기도록 실제
작업 3~5개를 실행하세요 — 성공과 실패가 섞이면 이상적입니다(시스템은 **둘 다**,
비대칭적으로 포착합니다; 4단계 참조).

콘솔에서 평범한 작업을 시작하면 됩니다: 트리거 실행, 슈퍼 에이전트 실행, 팀
실행, 또는 워크플로우. 예를 들어 작은 버그를 에이전트가 고치게 하고, 다른
에이전트에게는 처음에 *틀릴* 만한 일(오래된 경로, 누락된 환경변수)을 시켜보세요.
둘 다 유용합니다.

> **내부적으로:** **모든** 완료 세션마다 — "봇"만이 아니라 — 해결된 하네스
> 번들의 스냅샷이 원시 이벤트 스트림과 함께 영속화됩니다
> (`harness_snapshot_service.py`, `session_events.py`). 이것이 **(1) 캡처**
> 단계 — 출처 원장의 입력 계층입니다.

---

## 3. 메모리가 형성되는 모습: 두 개의 비대칭 스트림

프로젝트의 **Activity** 대시보드 레인을 엽니다. 방금 실행한 세션들로부터
쌓이는 것을 보게 됩니다:

- **테이크어웨이(Takeaways)** (긍정 신호) — 사용자 선호, 발견된 절차, 도구
  패턴, 제약, 도메인 사실, 근본 원인, 성공 패턴. 각각 안정적인 `tk-…` ID를
  가지며 출처 세션을 역참조합니다.
- **실패 인시던트(Failure incidents)** (부정 신호) — 4계층 분류 체계
  (인터페이스 → 환경 계약 → 트래젝토리 → 일반)로 타입화됩니다.

**비대칭이 핵심**입니다: 실패는 *규칙과 훅*을, 성공은 *스킬과 커맨드*를
원합니다. 대부분의 메모리 시스템은 한 방향만 포착하고 신호의 절반을 잃습니다.

> **내부적으로:** `harness_takeaway_extractor.py` → `harness_takeaways`
> (2단계, 긍정) 및 `harness_failure_annotator.py`
> (`detect_h2/h3/h4`) → `harness_annotations` (2단계, 부정). 둘 다 같은
> `session_complete` 채널에서 팬아웃됩니다.

---

## 4. 위키 컴파일 — 그리고 프로젝트의 메모리를 위키처럼 읽기

이것이 **LLM-위키** 순간입니다. 누적된 세션·문서·코드를 타입이 있는 그래프로
컴파일한 뒤, 탐색 가능한 사이트로 투영합니다:

```bash
tesserae status                 # 점검: 노드/간선/세션 수, 마지막 컴파일
tesserae project compile        # 타입 그래프 추출 + 볼트 + 사이트 산출물 작성
tesserae build-site             # 정적 위키 렌더링
tesserae serve                  # 로컬에서 탐색
```

서빙된 사이트를 엽니다. 이제 당신은 **프로젝트 메모리의 위키**를 읽고
있습니다 — 코드 파일, 세션, 결정, 테이크어웨이, 개념에 대한 페이지가 타입이
있는 간선으로 상호 링크되어 있습니다. 세션에서 그것이 만든 결정으로, 다시
그것이 건드린 코드로 클릭해 이동하세요.

자연어로 질문하세요 (CLI 또는 번들된 MCP 도구):

```bash
tesserae ask "재시도/백오프에 대해 우리가 무엇을 결정했지?"
tesserae ask "어떤 세션이 cost 대시보드를 건드렸고, 무엇이 깨졌지?"
```

에디터에서 보고 싶나요? 볼트를 Obsidian으로 동기화:

```bash
tesserae obsidian-sync
```

> **내부적으로:** 그래프 타입은 `CodeFile`, `Session`, `SessionTakeaway`,
> `SessionDecision`, … 입니다. MCP 표면(`tesserae_ask`, `search_facts`,
> `graph_ppr`, `wiki_page`, `find_session_findings`)은 *에이전트*가 작업 도중
> 바로 이 메모리를 읽는 방법입니다 — `CLAUDE.md`의 Tesserae 섹션 참조. 큰
> 변경 후에는 `tesserae refresh`로 갱신하세요.

---

## 5. 에볼루션 라운드 실행 (드라이런): 제안 → 채점

이제 루프입니다. 콘솔에서 프로젝트의 **Harness Evolution** 카드(Activity
레인)를 열고 **드라이런** 라운드를 시작합니다. (API 동등:
`POST /projects/{project_id}/evolution/dry-run`.)

세 가지가 순서대로 일어나며, 라운드 상태 기계는
`pending → running → evaluating → awaiting_approval`을 걷습니다:

1. **수집(Gather)** — 라운드는 입력을 모읍니다: 현재 바인딩된 프리미티브,
   최근 트래젝토리 + 그 인시던트, 최근 테이크어웨이, **그리고 방금 컴파일한
   위키에서 되질의한 KG 신호**(≤3개의 한정된 발견 질문). 메모리가 제안자를
   먹입니다.
2. **제안(Propose)** — 입력이 임시 워크스페이스에 작성되고 **Codex가 샌드박스에서
   실행**됩니다. 그것은 **diff를 내놓습니다**; 라이브 프리미티브를 인프로세스로
   편집하는 일은 결코 없습니다.
3. **평가 게이트(Eval-gate)** — 무엇이든 적용되기 전에, 패치는 **`EvalVerdict`**
   (`passed`, `score ∈ [0,1]`, per-check 결과)로 채점됩니다: 정적 검사
   (스키마/프론트매터/no-op/앵커) **그리고** 대표 세션을 *패치된* 프리미티브에
   대해 재생하는 회귀-리플레이 심판.

카드는 **제안된 diff**와 **평결**을 보여줍니다. 게이트 실패는 즉시 차단합니다 —
아무것도 적용되지 않습니다.

> **내부적으로:** `harness_evolver.py` (`gather_inputs`, `build_workspace`,
> `_run_codex_in_workspace`, `parse_patch`, `validate_patch`),
> `harness_kg_signals.py::gather_kg_signals`, 그리고
> `harness_evolution_eval.py` (`evaluate_patch`, `_static_checks`, `_run_judge`,
> `_verdict`). 게이트 *오류*는 score 0.0의 기록된 바이패스 평결과 함께
> 실패-닫힘(fail closed)합니다 — 바이패스가 진짜 통과와 구별 불가능해지는 일은
> 없습니다.

---

## 6. 적용, 그리고 그것이 git 커밋이 되는 모습

diff가 마음에 드나요? **승인**하세요 (라운드는 `awaiting_approval`에 머물러
있고, 승인은 `POST /evolution/rounds/{id}/apply`).

적용 시, 프리미티브는 프로젝트의 실제 `.claude/` 레이아웃
(커맨드/규칙/훅 + `settings.json`/`mcp.json`/스킬)으로 **구체화(materialize)**되며,
멱등적이고 운영자-보존적으로, 그리고 **라운드당 하나의 git 커밋**으로
커밋됩니다. 확인:

```bash
git -C <project_root> log --oneline -1     # 라운드의 구체화 커밋
git -C <project_root> status               # 어떤 .claude/ 프리미티브가 바뀌었는지
```

하네스의 진화는 이제 말 그대로 `git log`입니다.

> **내부적으로:** `forge_materialization_service.py`. 라운드는 `applied`로
> 전이합니다.

---

## 7. 출처 추적하기 (어떤 메모리 벤치마크도 측정하지 않는 부분)

방금 안착한 규칙을 골라 거꾸로 따라가세요. 모든 홉은 타임스탬프와 역포인터를
가진 행입니다:

```
어떤 행동
  → 그것을 만든 규칙(RULE)
    → 그것을 단조한 라운드(ROUND)             (harness_evolution_rounds)
      → 그것을 채점한 평가 평결(EVAL VERDICT)  (EvalVerdict)
        → 테이크어웨이 / 인시던트              (tk-… / harness_annotations)
          → 그것들이 나온 세션(SESSIONS)        (영속 트랜스크립트)
```

이 체인의 어떤 것도 임베딩 블롭에 대한 유사도 점수가 아닙니다. "*왜 하네스가
이것을 믿으며, 무엇이 그것을 채점했는가?*"를 추측이 아니라 ID로 답할 수
있습니다. 이것이 블로그의 가상 *AuditEval*이 시험할 속성입니다.

---

## 8. 되돌리기

마음이 바뀌었나요? 라운드를 되돌리세요 (`POST /evolution/rounds/{id}/revert`):

```bash
# 콘솔의 Harness Evolution 카드에서, 또는 API로
```

롤백은 **이전 이미지 저널(before-image journal)**을 포착하고, 라운드가 저널을
가진 `applied` 상태가 아니면 거부하며, 충돌(같은 `{kind, asset_id}`을 건드린
이후 라운드)을 감지하고, DB 연산을 멱등적으로 역순 수행한 뒤, 구체화 커밋을
**git-revert** 합니다. git 또는 부분 단계가 실패하면 라운드는 `revert_error`와
함께 `applied`로 남습니다 — 달성하지 못한 `reverted`를 *주장*하는 일은 결코
없습니다.

> **내부적으로:** `harness_evolution_rollback.py` (`revert_round`,
> `reverse_apply_journal`, `_git_revert`).

---

## 9. (선택) 자율 적용하게 두기 — 아홉 개의 게이트 뒤에서

운영자 승인이 기본값입니다. 검증된 변경이 스스로 적용되게 하려면, 프로젝트를
자율 모드로 옵트인하세요 (**Settings → … → Autonomy**, 또는
`PUT /projects/{id}/autonomy`). 5분 스케줄러 잡은 `autonomous_apply_eligible`이
**아홉 개의 하드 게이트**를 통과할 때**만** 자동 적용합니다:

1. 킬 스위치 off (`AGENTED_AUTONOMY` ≠ `0`)
2. 프로젝트별 정책 활성화
3. 평가 `passed`
4. `score ≥ confidence_threshold` (기본 **0.85**)
5. 폭발 반경 ≤ `max_ops_per_round`
6. `allowed_kinds`
7. `block_deletes`
8. `cooldown_seconds`
9. `rate_limit_per_day`

기본은 off이며, 이는 별도의 비감사 코드 경로가 아니라 *운영자 경로의 한정된
에스컬레이션*입니다. 전역 킬 스위치:

```bash
export AGENTED_AUTONOMY=0      # 모든 자율 적용을 하드 정지
```

> **내부적으로:** `harness_autonomy.py`
> (`autonomous_apply_eligible`, `process_project_autonomy`),
> `lifecycle.py`의 `autonomous_apply_job`, `project_autonomy_config`.

---

## 10. (선택) 검증된 프리미티브가 프로젝트 간 전파되는 모습 보기

두 번째 프로젝트에서 루프를 돌립니다. 프리미티브의 콘텐츠 **지문(fingerprint)**이
충분히 감쇠된 **eval-passed** 승격 증거를 누적하면
(`score ≥ PROMOTION_THRESHOLD = 3.0`), 전역 스코프 사본이 승격되고 다른
프로젝트가 그것을 **채택(adopt)**할 수 있습니다
(`POST /projects/{id}/adopt-shared/{sbid}`; 로컬 우선 충돌 정책). `rule`, `hook`,
`command`만 전파되며, eval-passed 라운드만 기여합니다 — 어떤 강제 적용도 공유
계층을 오염시킬 수 없습니다.

> **내부적으로:** `harness_propagation.py`, `forge_fingerprint.py`,
> `shared_forge_bindings`; `GET /shared-forge`.

---

## 루프가 닫혔다

`tesserae project compile`을 다시 실행하세요. *바로 이 워크스루*의 세션들 —
에볼루션 라운드를 포함 — 이 이제 위키의 노드입니다. 다음 드라이런의 **수집**
단계(5.1)가 그것들을 질의할 것입니다. 루프가 생산한 그래프가 이제 루프를
시드합니다.

```
 세션 ──► 테이크어웨이 + 인시던트 ──► 수집(KG 시드) ──► 제안(Codex)
   ▲                                                         │
   │                                                         ▼
 KG 피드백 ◄── git 커밋 ◄── 구체화 ◄── 적용 ◄── 평가 게이트(채점됨)
 (Tesserae 위키)                          │
                                          └─ 되돌리기 / 전파
```

---

## 문제 해결 & 어디에 무엇이 있는가

| 증상 | 확인 위치 |
|---|---|
| 세션 후 테이크어웨이/인시던트 없음 | 세션이 *완료*되었는지 확인; Activity 레인; `harness_takeaways` / `harness_annotations` 행 |
| 위키가 비어 있음 / 오래됨 | `tesserae status`, 그 다음 `tesserae project compile` (또는 `tesserae refresh`) |
| 드라이런이 아무것도 제안 안 함 | 최근 증거 필요; 세션 더 실행. no-op은 `_static_checks`가 잡음 |
| 라운드가 `awaiting_approval`에 멈춤 | 그게 게이트입니다 — 승인하거나 자율 활성화(§9) |
| 라운드가 되돌려지지 않음 | 저널을 가진 `applied` 라운드만 되돌려짐; 충돌하는 이후 라운드 확인 |
| 자율이 절대 작동 안 함 | 아홉 게이트(§9) 점검; `AGENTED_AUTONOMY` ≠ `0` 및 `score ≥ 0.85` 확인 |

전체 심볼 맵: [아키텍처 문서](/ko/self-improving-harness-architecture)의
**Source map** 표.

---

## 다음 단계

- Letta/MemGPT, Hermes Agent, Mastra, Zep/Graphiti, Mem0, Cognee와의 정직한
  비교는 **[아키텍처](/ko/self-improving-harness-architecture)**를 읽으세요.
- Tesserae MCP 도구를 에이전트에 배선해 재유도 대신 작업 도중 위키를 *질의*하게
  하세요 — `tesserae_ask`, `find_session_findings`, `graph_ppr`, `wiki_page`.
- 위험이 낮은 프로젝트 하나에 자율을 켜고 일주일치 `git log`가 스스로 쓰이는
  것을 지켜보세요 — 모든 커밋은 되돌릴 수 있고, 모든 믿음은 세션으로 추적
  가능합니다.
