> 🌐 **Language:** [English](2026-06-13-team-harness-self-improvement-design.md) | 한국어

# v0.8.0 — 팀 하니스 & 자가 개선: 설계 명세

**날짜:** 2026-06-13
**상태:** 승인됨 (설계); `/grd:new-milestone`을 통한 마일스톤 공식화 대기 중
**전달 방식:** GRD 마일스톤, PR 기반 (페이즈당 1개 이상의 PR), 머지 전 codex-review-until-green.

## 1. 목표

모든 Agented 프로젝트가 원클릭으로 다음과 같은 팀 하니스를 부트스트랩할 수 있게 한다:

1. 에이전트(그리고 스케치 패널)가 forge를 통해 **하니스 프리미티브를 생성하고 개선**할 수 있다 — skill, rule, hook, command, subagent.
2. **GRD (GetResearchDone)** 가 모든 슈퍼에이전트 대화의 기본 실행 드라이버가 되고, GRD의 모든 기능(autoresearch, life-harness/자가 개선, tesserae)이 프론트엔드에서 접근 가능하다.
3. 시스템이 **자가 개선**한다: 반복되는 유사한 사용자 요청을 life-harness 메모리 + tesserae로 감지하여 자동으로 스킬화한다(신뢰도 게이트 적용).

### 확정된 제품 결정

| 결정 | 선택 |
|---|---|
| 전달 방식 | GRD 마일스톤 v0.8.0 (`.planning/milestones/v0.8.0/`), 페이즈별 PR |
| GRD 드라이버 기본값 | 기본 켜짐 토글: `driver: grd \| cli_agent \| cliproxy`, 기본값 `grd` |
| 자동 스킬 자율성 | 하이브리드: 고신뢰(≥3회 거의 동일 + 검증된 에피소드)는 자동 생성, 저신뢰는 승인 큐로 |
| 하니스 대상 | 기존 context-renderer/propagation 레이어를 통한 4종 전부 (claude/codex/gemini/opencode) |

## 2. 현재 상태 (정찰 요약)

워크플로 정찰(병렬 에이전트 8개, 2026-06-13)로 확인된 사실:

- **Forge**는 6종의 프리미티브(`rule, skill, hook, command, mcp_server, plugin`)를 `project_forge_bindings`로 프로젝트에 바인딩한다 (`backend/app/db/project_forge_bindings.py:24`; 마이그레이션 121은 스키마 변경 없이 새 kind 추가를 명시적으로 허용). 프리미티브는 두 경로로 하니스에 도달한다: 세션 시작 시 `ContextCompilerService.compile` → 백엔드별 렌더러(claude/codex/gemini/opencode), 그리고 진화 라운드 적용 시 `forge_materialization_service.materialize_primitives`가 영속적인 `.claude/` 프로젝션을 기록. 갭: `subagent` kind 없음; 생성과 바인딩이 별도 호출; `/generate/stream` 엔드포인트는 영속화되지 않는 초안만 출력; `replace_for_project`가 출처 컬럼을 유실 (`project_forge_bindings.py:177-191`); `skill_sets`는 스킬 전용 — 크로스 kind 번들 없음.
- **Sketch** 파이프라인: 생성 → 분류(`SketchRoutingService.classify`, 키워드 → 트라이그램 캐시 → LLM) → 라우팅(`route`, target_type `super_agent | team | none`) → `execute_sketch`. 프리미티브 생성 라우팅 타깃 없음, 프리미티브 개선 경로 없음, 패널은 SA 세션 SSE 결과만 렌더링.
- **슈퍼에이전트**: 모든 채팅 경로가 `run_streaming_response` (`streaming_helper.py:263`)로 모이며 라우팅 규칙은 **불리언** `should_route_via_cli_agent` (`cli_agent_runner_service.py:530`). 채팅에서 GRD는 한 번도 호출되지 않음. 채팅 턴은 상태 없는 일회성 `claude -p` 실행; delegation과 `grd_routes.project_chat`은 `cwd=None`으로 실행. 브리징 선례 존재: `HANDLER_REGISTRY` (`execution_type_handler.py:686`), `GrdEvolveSessionHandler`, `GoalLoopSessionHandler`, `GrdPlanningService.invoke_command`, Ouroboros 브리지 (`super_agents_cluster.py:641`).
- **GRD 연동**: 칸반/플래닝 UI는 47개 중 14개의 `/grd:` 커맨드만 노출; life-harness 라운드와 테이크어웨이는 부분 연동; tesserae 설정은 완전 연동. **GRD 전용 백엔드 라우트 16개가 프론트엔드 연동 전무** (health, think, dead-ends, genome, verify-mechanical, reflections, verdict-counts, evolve 표면); 라운드 revert, 자율성 정책, shared-forge 채택은 UI 없음; **autoresearch (`gd research` v2: 스레드, 가설 원장, 포트폴리오)는 전혀 연동되지 않음**.
- **GRD 패키지** `@jokerized/getresearchdone` 0.4.4 (`~/Developer/Projects/GetResearchDone`): 약 95개의 결정적 `gd` 도구 커맨드, 에이전트 커맨드, autoresearch v2 (`gd research`), 리서치 KB(ingest/synthesize/retrieve), TesseraeClient KG 동기화, 0.4.4의 collective/upstream 레이어(이미 **크로스 프로젝트 발생 횟수 카운팅** 수행), 그리고 `grd-mcp-server`.
- **원클릭 선례**: ProjectDashboard 액션 행에 이미 Load Harness(`HarnessLoaderService`), Deploy Harness, Run Setup(`InteractiveSetup.vue` SSE)이 있음; 프로젝트 생성은 `grd_init_status` 백그라운드+폴링으로 GRD 초기화를 자동 실행 — 새 버튼의 템플릿.
- **Life-harness 메모리**: 세션 완료 이벤트 버스(`execution_events.py:38`, 세션 5종), `_apply_to_skill`을 갖춘 테이크어웨이 추출기(SKILL.md 기록 + `add_project_skill`, `AGENTED_TAKEAWAY_AUTOAPPLY` 뒤에서 ≥0.85 자동 적용), Codex 진화 라운드(평가 게이트, 저널링 롤백), 10중 게이트 자율성, 크로스 프로젝트 승격. **반복 요청 감지는 존재하지 않음**: kg_signals에는 발생 횟수 카운터가 없고 가중치가 시간에 따라 *감쇠*; 원시 사용자 요청 텍스트의 정규 저장소 없음; 임베딩은 `memory_messages`에만 존재; tesserae 내보내기는 `project_session`/`workflow`/`team_session`을 건너뜀; 진화기 프롬프트는 `_create_skill`이 구현되어 있음에도 스킬을 읽기 전용이라 주장.
- **Hermes 리서치** (Nous Research Hermes 에이전트 + Voyager/ACE/Anthropic skill-creator 선행 연구): 에피소드 수준 LLM 판단 생성 트리거; 스테이징 게이트(`write_approval` 보류 디렉터리); 점진적 공개 스킬 인덱스; 생성보다 패치 우선 중복 제거; 원본 해시 출처 추적; 자가 작성 콘텐츠 보안 스캔; Voyager식 임베딩 유사도 검색; ACE식 델타 업데이트; Anthropic식 trigger/non-trigger A/B 평가.

## 3. 페이즈별 설계

### Phase 1 — Forge 생성 표면 (백엔드 기반)

**새 `subagent` kind.** 새 `subagents` 테이블(id `subag-` 접두사, name, description, content = frontmatter 포함 `.claude/agents/*.md` 전문, enabled, project_id, source_path, 타임스탬프), `rules_plugins_hooks_commands.py`를 본뜬 CRUD 라우트, `VALID_KINDS`에 `subagent` 추가, `forge_materialization_service`에서 `.claude/agents/<name>.md`로 물질화, 그리고 컨텍스트 컴파일러 지원(claude 렌더러: `agents/` 디렉터리 오버레이; codex/gemini/opencode: 기존 렌더러 동작과 일관된 최근접 등가물 또는 프롬프트 프리픽스 폴백).

**원자적 생성+바인딩+물질화.** `POST /admin/projects/{project_id}/forge/create` 바디 `{kind, payload, bind: true, materialize: true}` → 자산 행 생성, 바인딩 추가(멱등 upsert), 저장소 프로젝션 물질화를 실패 시 보상 정리가 있는 단일 흐름으로 수행. `replace_for_project`가 `source_scope/source_shared_binding_id/fingerprint/conflict_policy`를 보존하도록 수정.

**크로스 kind 번들.** `forge_bundles` (+ `forge_bundle_items(kind, asset_id, position)`)와 모든 항목을 바인딩하는 `POST /admin/projects/{id}/forge/bundles/{bundle_id}/bind`. `skill_sets`는 그대로 유지(스킬 전용 레거시).

**Forge-creator 번들 ("번들 스킬").** 5개의 크리에이터 스킬을 글로벌 스코프 forge 자산으로 제공하고 기본 번들 `forge-creator`로 구성: `skill-creator`, `rule-creator`, `hook-creator`, `command-creator`, `subagent-creator`. 각각 agentskills.io 호환 SKILL.md (When to Use / Procedure / Pitfalls / Verification)로, 세션 내 에이전트가 프리미티브를 **프로젝트의 `.claude/` 트리 아래 파일로** 스캐폴딩하도록 안내(세션 내 API 인증 표면 없음). 새 세션 완료 핸들러(`execution_events.register_session_handler`)가 `.claude/`를 forge 매니페스트와 비교(diff)하여 신규/변경 프리미티브를 `HarnessLoaderService` + 원자적 생성/바인딩 API로 자동 임포트하고, 출처(원본 콘텐츠 해시, 소스 세션 id)를 기록.

**테스트:** 새 테이블의 저장소 레이어 테스트; 원자적 생성 라우트 테스트(성공 + 보상 정리); `.claude/agents/` 포함 물질화 골든 파일 테스트; 픽스처 `.claude/` 트리에 대한 임포트 핸들러 테스트.

### Phase 2 — 스케치 → 프리미티브 생성/개선 라우팅

**분류.** `SketchRoutingService`에 `action` 차원 추가 (`sketch_routing_service.py:98/:132/:225-234`): `create_skill | create_rule | create_hook | create_command | create_subagent | improve_primitive | none` — 키워드 단계(새 키워드 사전)와 LLM 프롬프트/JSON 스키마 양쪽 모두. 신뢰도 의미론은 변경 없음.

**라우팅.** `route` (`:298`)에서 분류가 신뢰도 ≥ 0.6의 프리미티브 액션을 담고 있으면 SA/팀 해석 전에 새 `target_type: "primitive_generator"` (target_id = 프리미티브 kind)를 반환. 라우트 핸들러(`leaf_crud_g.py:165`)는 새 `PrimitiveForgeService`로 디스패치:

- *생성:* 기존 kind별 생성 서비스를 완성된 초안까지 구동한 뒤, Phase 1의 원자적 API로 영속화+바인딩+물질화. 스킬은 대화형 플로의 preview-finalize 내부를 재사용.
- *개선:* 프로젝트에 바인딩된 프리미티브에서 퍼지 이름 매칭으로 대상 해석; ACE식 old→new 델타 패치 생성; 업데이트로 적용 + 재물질화. 모호한 참조 → 스케치 상태 `collaborating`으로 명확화 질문.

**프론트엔드.** `useSketchChat`/`SketchRouting.vue`에 세 번째 결과 분기: "프리미티브 생성됨/업데이트됨" 카드(kind, 이름, 설명, diff 뷰, 바인딩된 프로젝트 목록, 원클릭 실행 취소 = 언바인드+삭제 또는 업데이트 되돌리기). `SketchStatus` enum에 누락된 `collaborating`도 수정.

**테스트:** 액션별 분류기 단위 테스트(키워드 + LLM 모킹); `primitive_generator` 우선순위 라우팅 테스트; PrimitiveForgeService 생성/개선 테스트; 결과 카드 컴포넌트 테스트. 도그푸드: 완료 선언 전 실제 스케치 ≥3건을 라이브 파이프라인에 통과시킬 것.

### Phase 3 — GRD를 기본 실행 드라이버로

**드라이버 추상화.** `cli_agent_runner_service.py`의 불리언을 `resolve_execution_driver(...) -> "cliproxy" | "cli_agent" | "grd"`로 교체하고, 단일 퍼널 `run_streaming_response` (`streaming_helper.py:263`)에서 준수. 해석 우선순위: 턴별 오버라이드 → `SuperAgent.config_json.driver` → `project_sa_instances.driver` → 프로젝트 기본값(`projects.default_driver`) → 글로벌 기본값 **`grd`**. `grd`는 `grd_cli_service`가 바이너리 불가용을 보고하거나 프로젝트에 워크스페이스가 없으면 조용히 `cli_agent`로 강등.

**GRD 드라이버 의미론.** 경량 턴 분류기(스케치 키워드 단계 재사용 + 저비용 LLM 폴백)가 턴을 *작업형* vs *대화형*으로 분리:

- 작업형 → `HANDLER_REGISTRY`에 등록되는 새 `GrdChatSessionHandler`(패턴: `system_prompt_override` + forge 번들 + `super_agent_id` 연계를 이미 지원하는 `GoalLoopSessionHandler`)를 통해 프로젝트 워크스페이스에서 `/grd:quick "<task>"` (리서치/플래닝 분류 턴은 `/grd:research`, `/grd:plan-phase` 등으로 매핑)를 실행하는 ProjectSessionManager 세션 생성. PSM 출력 이벤트는 채팅 SSE `state_delta` 프로토콜(content_delta/tool_use/finish/error)로 브리징 — Ouroboros 브리지의 대화형 진화.
- 대화형 → 기존 cliproxy 경로 그대로.

**cwd 수정.** `execute_delegate`, `_scan_mentions_and_notify`, `grd_routes.project_chat`이 `cwd=None` 대신 프로젝트 워크스페이스를 해석하고, `project_chat`의 `backend='claude'` 하드코딩 제거.

**프론트엔드.** 슈퍼에이전트 설정 + 프로젝트 설정에 드라이버 셀렉터(기본 GRD); 채팅 트랜스크립트에 GRD 세션 연계 렌더링(프로젝트 세션/플래닝 패널 링크).

**테스트:** 해석기 우선순위 매트릭스 테스트; 가짜 PSM을 사용한 핸들러 테스트; SSE 브리지 테스트(델타 순서, 오류 전파); cliproxy 대화형 경로 무변경 회귀 테스트; delegation cwd 테스트.

### Phase 4 — GRD 기능 전체의 프론트엔드 연동

**Autoresearch.** `gd research`를 감싸는 새 백엔드 라우트(start/status/resume/report/portfolio + `.planning/research/threads/<id>/`를 읽는 스레드 브라우저)와 장기 실행 루프를 위한 `grd_research` 실행 타입 핸들러(PSM 세션 + SSE, `grd_evolve`와 동일). 새 "Research" 페이지: 질문 입력, 상태/반복 횟수가 있는 스레드 목록, 가설 원장 뷰, 리포트 뷰어, 포트폴리오 실행.

**Life-harness 완성.** UI 추가: 자율성 정책 편집기(`GET/PUT /admin/projects/{id}/autonomy`), 라운드 revert, shared-forge 브라우저 + 채택(`GET /admin/shared-forge`, `POST .../adopt-shared/{id}`), 그리고 미연동 GRD 라우트 16개(health, think, dead-ends, genome + 스냅샷, verify-mechanical, reflections, verdict-counts, evolve 표면)의 패널을 ActivityPage/GRD 페이지에.

**커맨드 표면.** PlanningCommandBar를 14개에서 지원되는 `/grd:` 커맨드 전체로 확장, 그룹화(Plan / Execute / Verify / Research / Harness / Misc), 선언적 커맨드 매니페스트 기반.

**i18n:** 모든 새 표면은 4개 로케일 키 동일 제공.

**테스트:** 새 래퍼별 라우트 테스트; 패널별 컴포넌트 테스트; 리서치 스트리밍 SSE 테스트; 프론트엔드 신규 실패 없음 게이트.

### Phase 5 — 원클릭 팀 하니스 셋업

**진입점.** ProjectDashboard 액션 행(`ProjectDashboard.vue:507-541`)의 "Setup Team Harness" 버튼, `grd_init_status` 패턴 준수: 새 `projects.harness_setup_status` (`none/running/ready/failed`) + InteractiveSetup SSE 러너를 통한 단계별 진행 상황.

**오케스트레이션.** 새 `TeamHarnessSetupService.setup(project_id)`가 멱등 단계들을 실행하며, 이미 충족된 단계는 건너뜀:

1. 클론 + GRD 초기화 보장 (`grd_init_status != ready`면 `auto_init_project`).
2. 기본 팀 토폴로지 + 슈퍼에이전트 생성(팀당 팀 리더 SA, `driver=grd`) — `team_topology_config` 또는 기본 템플릿 기반.
3. `forge-creator` 번들 + 기본 rule/hook 번들 바인딩 — 프로젝트의 map-codebase 출력으로 **맞춤화**(언어/프레임워크 조건부 rule 선택).
4. 프로젝트에 tesserae 활성화(기존 `POST /admin/system/memory/tesserae/projects/{id}` 경로 + MCP 자동 바인딩).
5. 기본 정책 설정: 진화 라운드 자율성은 보수적으로(enabled=false, 신뢰도 0.85, skill ∈ allowed_kinds, 삭제 차단); 테이크어웨이 자동 적용은 프로젝트별 정책 켜짐, 반복 기반 스킬 생성으로 한정(Phase 6).
6. `.claude/` 프로젝션 물질화 + 4종 하니스 전부에 대한 백엔드별 렌더러 컴파일 검증(스모크 체크로 백엔드별 `forge-context/preview` 컴파일).

재실행은 중복 대신 조정(매니페스트/핑거프린트 비교). 실패 시 단계 로그와 `failed` 상태를 남기고, 각 단계는 독립적으로 재시도 가능.

**테스트:** 서비스 단계 테스트(신규, 부분, 전체 재실행); 라우트 + SSE 테스트; 대시보드 컴포넌트 테스트; 실제 프로젝트 대상 라이브 도그푸드 1회.

### Phase 6 — 반복 요청 감지 → 자동 스킬

**시그널 저장소.** `repeated_request_signals`: `signal_id` (PK), `project_id`, `canonical_text`, `embedding` (BLOB), `occurrence_count`, `example_session_ids` (JSON, 상한 있음), `first_seen_at`, `last_seen_at`, `verified_success_count`, `skill_created` 플래그. UPSERT는 `first_seen_at`을 보존하되(패턴: `db/harness_kg_signals.record_signal`) **카운트를 증가** — 반복과 함께 중요도가 커짐(kg_signals 감쇠의 역).

**감지 핸들러.** annotator/extractor/exporter와 나란히 세션 완료 버스에 등록(`lifecycle.py:454-485`), 세션 5종 전부 대상:

1. `_FETCHERS` 트랜스크립트 레이어(`harness_failure_annotator.py:304-315`) + `parse_claude_stream`으로 사용자 요청 턴 추출.
2. `embedding_service`로 임베딩; 코사인 ≥ 0.83으로 기존 시그널과 매칭; 최적 매치에 병합하거나 신규 삽입.
3. 세션에 증거 원장의 통과된 검증 레코드가 있으면 `verified_success` 기록.
4. 시그널 저장소 이전의 과거 발생을 tesserae(`ask_tesserae`)로 교차 확인.

**스킬 합성 게이트** (확정된 하이브리드 결정 기준):

- **자동 경로:** 30일 내 `occurrence_count ≥ 3` **그리고** `verified_success_count ≥ 1` **그리고** 보안 스캔 통과(프롬프트 인젝션/유출 패턴, 비가시 유니코드) → `session_takeaways` 행 삽입(kind `discovered_procedure`, `suggested_target='skill'`, 신뢰도 0.9, 증거 = 예시 세션들) → 기존 자동 적용 머신이 SKILL.md (When to Use / Procedure / Pitfalls / Verification) 물질화 + `add_project_skill`. 테이크어웨이 자동 적용 게이트는 글로벌 `AGENTED_TAKEAWAY_AUTOAPPLY` 환경 변수에서 프로젝트별 정책으로 승격되며, 반복 기반 스킬 생성은 **기본 활성화**(이는 보수적으로 유지되는 진화 라운드 자율성과 별개 — Phase 5의 5단계 참조).
- **제안 경로:** 2회 발생, 또는 미검증, 또는 스캔 플래그 → 같은 테이크어웨이를 신뢰도 0.65로, HarnessTakeawaysCard에서 운영자 승인 대기 큐.
- **생성보다 패치:** 생성 전 프로젝트의 바인딩된 스킬 인덱스(이름+설명 임베딩 매치)와 비교; 준중복이면 기존 스킬에 대한 업데이트 제안(델타 패치)으로 전환.
- **출처 추적:** 생성 시 원본 콘텐츠 해시 기록; 정제 패스는 운영자가 수정한 스킬을 절대 덮어쓰지 않음(해시 불일치 → 적용 대신 제안).

**함께 반영되는 일관성 수정:** 진화기 `_DESIGN_GUIDE`/`_PROMPT_TEMPLATE`을 스킬이 쓰기 가능함을 반영하도록 갱신; `tesserae_integration._build_harness_session`을 `project_session`/`workflow`/`team_session` kind도 정규화하도록 확장하여 감지와 KG 시그널이 모든 세션을 보게 함.

**테스트:** 시그널 저장소 upsert/감쇠 테스트; 픽스처 트랜스크립트 대상 감지 핸들러 테스트; 게이트 매트릭스 테스트(자동 vs 제안 vs 거부); 보안 스캔 테스트; **라이브 도그푸드: 완료 선언 전 실제 세션 트랜스크립트 ≥3건을 감지기에 리플레이** (하우스 규칙).

## 4. 공통 사항

- **4종 백엔드 규칙:** 모든 LLM 호출 추가 기능은 `{backend_kind, model_override?}`를 받음; 렌더러 작업은 claude/codex/gemini/opencode를 커버.
- **i18n:** 모든 새 UI 문자열은 en/ko/ja/zh 키 동일; 본 명세도 `.ko.md` 자매 문서와 함께 제공.
- **검증 게이트 (하우스):** `just build`; 12분 워치독 절차 하의 백엔드 pytest (알려진 행이 발생하면 표적 대체를 공개); 프론트엔드 `npm run test:run` 신규 실패 없음.
- **워크플로:** 페이즈(또는 서브 페이즈)당 PR, 머지 전 codex-review-until-green.
- **보안:** 자동 작성된 스킬/메모리 콘텐츠는 4종 하니스로 증폭되는 시스템 프롬프트 인젝션 벡터 — 수용 전 스캔(Phase 6), 자율성의 스테이징 게이트 기본 켜짐(Phase 5의 5단계).

## 5. 리스크 & 완화

| 리스크 | 완화 |
|---|---|
| GRD 드라이버가 채팅에 지연/무게 추가 | 턴 분류기가 대화형 턴을 cliproxy에 유지; SA/프로젝트별 옵트아웃; GRD 불가용 시 조용한 강등 |
| 스케치 오분류로 원치 않는 프리미티브 생성 | 액션 신뢰도 ≥ 0.6 게이트; 원클릭 실행 취소가 있는 결과 카드; 개선 경로는 모호 시 질문 |
| 정크 스킬 축적 | 하이브리드 게이트, 생성보다 패치 중복 제거, 출처 해시, 테이크어웨이 dismiss, 스킬 비활성화 |
| 원클릭 셋업이 기존 프로젝트를 파괴적으로 변경 | 단계별 멱등 조정; 매니페스트 비교; 단계별 재시도; 셋업에서 삭제 없음 |
| 자동 임포트가 클론된 저장소의 악성 `.claude/` 콘텐츠를 끌어옴 | 임포트 핸들러는 Agented 주도 세션에서 생성된 프리미티브만 자동 바인딩(세션 id 출처); 그 외는 검토 큐로 |
| 백엔드 테스트 스위트 행이 회귀를 가림 | 알려진 이슈 워치독 절차, PR별 표적 스위트 공개 |

## 6. 의존성 순서

Phase 1 → Phase 2; Phase 1+3 → Phase 5; Phase 4는 3 이후 독립(드라이버 배관 공유); Phase 6은 1 이후 독립(스킬 생성 경로 사용). 권장 실행 순서: 1, 2, 3, 4, 5, 6.
