# 하네스 샌드박싱 및 이그레스 제어

**Languages:** [English](./sandboxing.md) · 한국어 (현재)

Phase 24는 모든 하네스 `subprocess.Popen`을 OS 샌드박스에 가두고, 그 아웃바운드
네트워크를 기본-차단(deny-by-default) 이그레스 프록시로 라우팅하며, 이를 Phase-23의
`enforce_sandbox` 정책으로 게이트합니다. 이 런북은 모델, 운영 방법, v1 한계선,
검증 게이트를 다룹니다.

## 1. 샌드박스 모델

단일 빌더 `app/services/sandbox_wrap.py:build_sandbox_prefix(cmd, workspace, *,
net=False, proxy_url=None)`는 argv **프리픽스**와 `sandboxed: bool`을 반환합니다 —
이는 `stdbuf`와 똑같이 앞에 붙으므로 기존 `Popen`은 그대로 유지됩니다(두 번째 런처
없음).

- **Linux** → [`bwrap`](https://github.com/containers/bubblewrap) (bubblewrap):
  워크스페이스는 `--bind`로 읽기-쓰기, 나머지는 전부 `--ro-bind`로 읽기 전용이며,
  `--unshare-all --share-net`(pid/ipc/uts 네임스페이스는 격리하되 네트워크는 공유하여
  자식이 로컬 프록시에 도달 가능) 및 `--die-with-parent`를 사용합니다.
- **macOS** → `sandbox-exec -p <SBPL>`: `(deny default)`인 seatbelt 프로파일로,
  읽기는 폭넓게 허용하고 쓰기는 워크스페이스 내부(+ `TMPDIR` + `/dev`)로만
  제한하며, 이그레스 프록시를 제외한 네트워크를 거부합니다.

**워크스페이스 전용 쓰기.** 워크스페이스 외부로의 쓰기는 거부됩니다("Operation not
permitted"). 워크스페이스 내부 쓰기는 성공합니다 — 이것은 전면 차단이 아니라
경계(boundary)입니다.

**가용성 및 우아한 저하(degrade).** `sandbox_available()` = `shutil.which(tool)`
**그리고** 캐시된 런타임 프로브(Linux에서는 `bwrap`이 존재하지만 사용 불가한
`kernel.unprivileged_userns_clone=0` 상황을 포착)입니다. 사용 가능한 샌드박스가
없으면 `build_sandbox_prefix`는 **제자리에서** `(cmd, sandboxed=False)`로 저하되고
경고를 한 번만 로깅합니다 — 절대 예외를 던지지 않습니다. 이후 `enforce_sandbox`
게이트가 실행-vs-거부를 결정합니다(§3 참조).

**기능 플래그.** 하네스 실행 지점에서의 실제 래핑은 `AGENTED_SANDBOX`(기본 off)로
옵트인합니다. off일 때 `wrap_harness_command`는 아무 동작도 하지 않는 통과(pass-through)
이므로, 운영자가 활성화하기 전까지 정상 동작은 바뀌지 않습니다. 플래그가 off인 상태에서
`enforce_sandbox`를 요구하는 정책은 모든 실행을 거부합니다(fail closed) — 이를
충족하려면 플래그를 켜십시오.

## 2. 이그레스 제어

`app/services/egress_proxy.py`는 임시 루프백 포트에서 동작하는 아주 작은 stdlib-`asyncio`
**기본-차단** 포워드 프록시입니다. 평문 `CONNECT` 호스트(TLS SNI 호스트는 MITM 없이도
보임)와 평문-HTTP `Host:`/absolute-form 라인을 기준으로 필터링합니다:

- 실행별 allowlist에 있는 호스트 → `200 Connection Established` + 양방향 바이트 펌프;
- allowlist에 **없는** 호스트 → `403 Forbidden` + 구조화된 거부 로그
  `{session_id, host, port, action: "deny"}`.

**실행별 allowlist.** `AGENTED_EGRESS_ALLOWLIST`(쉼표로 구분한 호스트)로 재정의합니다.
설정하지 않으면 보수적인 필수 집합은 `github.com`, `api.github.com`,
`api.anthropic.com`입니다. **빈** allowlist는 모든 것을 차단합니다 — 자율/자동-구현
실행에 올바른 기본-차단 자세입니다.

**환경변수 주입.** `proxy_env(handle)`는 `HTTPS_PROXY`/`HTTP_PROXY` = 프록시 url과
**우회 불가한** `NO_PROXY`(`127.0.0.1,localhost` — 절대 `*` 아님)를 산출합니다.
`execution_runner.build_subprocess_env(..., proxy_url=...)`가 이를 병합하여 자식의
HTTP(S) 클라이언트가 프록시를 통과하고 샌드박스의 이그레스 규칙과 일치하도록 합니다.

## 3. `enforce_sandbox` 게이트 (Phase 23)

실행 경계에서 `execution_service._apply_sandbox_and_enforce`가 명령을 래핑한 뒤,
`Popen` **이전에** `PolicyService.enforce_launch(..., sandboxed=<실제 플래그>)`를
호출합니다. `enforce_sandbox` 빌트인은 정책이 샌드박스를 요구하는데 실행이 샌드박스되지
않은 경우 **거부(deny)**합니다:

- 샌드박스 저하 / 비활성화 ⇒ `sandboxed=False` ⇒ **`PolicyDenied` 발생, 프로세스는
  절대 시작되지 않음**(fail closed);
- 실제 샌드박스 작동 ⇒ `sandboxed=True` ⇒ 실행 진행.

정책은 `PolicyService.create_policy(scope=..., kind="enforce_sandbox",
effect="deny", params={"require_sandbox": True})`로 작성합니다.

## 4. 선택적 클라우드 러너 (E2B / Modal)

가장 위험도가 높은 두 완전-자율 소비자 — 경쟁 인텔리전스 자동-구현
(`competitor_strategy_service.start_autoimplement`)과 라이프-하네스 자율성
(`harness_autonomy.process_project_autonomy`) — 에 대해
`cloud_sandbox_runner.select_runner(risk, config)`가 오프보드 샌드박스를 선택합니다:

- 기본 → `LocalRunner`(위의 로컬 OS 샌드박스);
- `E2BRunner` — `E2B_API_KEY`가 설정되고 실행이 최고 위험도일 때;
- `ModalRunner` — `MODAL_TOKEN_ID` + `MODAL_TOKEN_SECRET`가 설정되고 최고 위험도일 때.

**우아한 건너뛰기.** 자격증명이 없으면 로그를 남기며 `LocalRunner`로 저하됩니다 —
절대 크래시하지 않습니다. `e2b`/`modal` SDK는 어댑터 내부에서 **지연(lazy)** 임포트
되므로 클라우드가 없는 설치에서도 `ImportError`가 발생하지 않습니다. 이들은 선택적
extras로 고정됩니다: `pip install '.[cloud-sandbox]'`.

## 5. 한계선 및 업그레이드 경로

**v1 이그레스는 환경변수 + 프록시 BEST-EFFORT입니다.** `bwrap`은 `--share-net`(호스트
네트워크 네임스페이스)을 유지하고 `HTTPS_PROXY`/`HTTP_PROXY`만 주입하므로, 악의적인
자식은 이를 해제하거나 생 IP로 접속할 수 있습니다. 이스케이프 테스트는 구성된 경계가
**협조적인** 클라이언트에 대해 유지됨을 증명할 뿐, 악의적 프로세스가 환경변수를
우회할 수 없음을 증명하지는 않습니다.

- **우회 불가(airtight) 이그레스** → 비특권 네트워크 네임스페이스(`--unshare-net`으로
  프록시를 그 안에 바인딩) + 모든 이그레스를 프록시 포트로 강제하는 `nftables`.
  이후 웨이브로 연기됨.
- **URL-경로 / 본문 필터링** → `mitmproxy` 애드온(샌드박스 CA 번들에 인증서 주입).
  연기됨; 자체 제작 CONNECT 프록시가 의도적인 v1 선택입니다(TLS 인터셉트 없음, 인증서
  저장소 없음, 추가 의존성 없음).

우회 불가한 강제를 주장하지 **마십시오** — 한계선을 정직하게 문서화하십시오.

## 6. 하우스-게이트 런북

이 계층을 건드리는 변경을 배포하기 전에:

1. `just build` (vue-tsc 타입 검사 + vite 빌드).
2. `cd backend && uv run pytest`를 ~12분 워치독 하에 실행. 전체 직렬 스위트는 ~40–48%
   에서 알려진 행(hang)이 있습니다; 행이 발생하면 종료하고 포괄적인 대상 집합 — 샌드박스
   스위트 + execution/streaming/harness 회귀 — 를 실행합니다:
   ```bash
   uv run pytest tests/test_sandbox_wrap.py tests/test_egress_proxy.py \
     tests/test_cloud_sandbox_runner.py tests/test_sandbox_escape.py \
     tests/test_enforce_sandbox_gate.py tests/test_sandbox_wiring.py \
     tests/test_policy_harness_gates_23.py tests/test_execution_service.py -q
   ```
   PR에 대체를 명시하십시오; 대상 실행을 전체 스위트로 제시하지 마십시오.
3. `cd frontend && npm run test:run` — 게이트는 **신규 실패 없음**(베이스라인에 알려진
   기존 실패 7건 포함).

`test_sandbox_escape.py`는 `@skipif(not sandbox_available())`입니다: 사용 가능한
`bwrap`/`sandbox-exec`가 있는 호스트에서 실행되어(FS + 이그레스 경계가 유지됨을 증명)
둘 다 없는 곳에서는 깔끔하게 건너뜁니다.
