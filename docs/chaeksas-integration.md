# NowView ↔ Chaeksas 연계 설계 — SC01을 바깥 Chaeksas에서 돌려도 NowView 전체가 따라온다

- 작성: 2026-10-25 · 상태: **수락**. N1·N4·N2·N6 구현(2026-10-25), 나머지는 아래 7의 순서
- 관련: CLAUDE.md 4.3(API·외부 확장)·4.5(BPM)·4.6(화면), Chaeksas ADR-0079~0085(가상 직원·결재 담당자·대리 답),
  Chaeksas에 보낼 요청서 [handoff/chaeksas-nowview-integration.md](handoff/chaeksas-nowview-integration.md)

## 1. 원하는 것

SC01 BPMN이 **Studio 시험 실행**이나 **Center 서버 Bot**에서 돌 때도 NowView 화면 전체가 그 실행을 따라간다.
고객계획, 위험 검토, 업무, 인계, BPM 흐름 화면이 모두 포함되고, 감사 이력과 SSE도 내장 BPM으로 돌릴 때와 같아야 한다.
사람 결재는 NowView 화면에서 답하든 Center 콘솔(CON-04)에서 답하든 **한 번만 닫히고**, NowView에 남는 기록도 같아야 한다.
고객계획 접수는 Center의 **가상 직원**이 맡고, 사람 감독자가 승인한 건만 SC01로 기동된다.

## 2. 지금 왜 안 되나 (2026-10-25 실측)

Studio에서 `nowview.sc01`을 돌렸더니 `validate_source`는 200이었다. 그러나 다음 두 단계가 막혔다.

* **사람 결정의 업무 효과가 내장 BPM 전용 훅에 있다**(`process._before_answer`). 원천 확인 완료(`verify_source`),
  보완 요청, 업무 완료·인수 표시, 영업 검토 의견 저장, 배정 검사가 전부 그 훅에서 일어난다. 그런데 바깥 실행에서는 결재 답이
  NowView를 지나지 않는다. 그래서 Studio에서 「확인완료」를 해도 원천은 `RECEIVED` 그대로이고, `compare`가 409를 낸다.
  인계(`hand_off`)도 같은 이유로 409가 난다. 인수 기록이 없기 때문이다.
* **화면의 대기·노드 상태가 내장 엔진 스냅샷에서 나온다.** 바깥 실행이 어디까지 갔는지 NowView는 모른다.
* **업무(`TASK-*`)는 내장 엔진이 사람 대기를 만들 때 생긴다.** 바깥 실행에서는 업무 화면이 비어 있다.

## 3. 원칙

1. **지도는 BPMN 하나다.** 같은 `sc01.bpmn`을 내장 실행기와 바깥 Chaeksas가 함께 돈다. 실행 위치마다 그림을 따로 두지 않는다.
2. **사람 결정의 업무 효과는 결재 뒤의 「기록」 서비스 태스크가 낸다.** 답을 어디서 했든 같은 길로 NowView에 적힌다.
   내장 실행기도 그 태스크를 `_InProcessCalls`로 똑같이 돈다. 그래서 `_before_answer`에 있던 부수 효과는 이 작업으로
   옮긴다. 내장 경로에는 **부수 효과 없는 사전 검사**만 남긴다. 거절해도 입력이 지워지지 않게 하려는 것이다(4.6).
3. **NowView는 바깥 실행의 상태를 저장하지 않고 읽는다.** 노드 상태는 Center 실행 기록(C3 `node_state`)에서 파생한다.
   지금 `process-layout.ts`가 하는 방식과 같다.
4. **숫자는 여전히 NowView 규칙 계산이 만든다**(AG-01). Chaeksas는 순서·대기·분기·인계만 쥔다.
5. **역할 검사는 결재 담당자(`assignees`)로 옮긴다.** Center가 대리 답을 담당자와 대조하므로(ADR-0081),
   「담당자만 인수」라는 규칙이 Center 안에서도 지켜진다.

## 4. 실행 위치 세 가지

| | 내장 (지금) | Studio 시험 실행 | Center 서버 Bot |
|---|---|---|---|
| 누가 BPMN을 도나 | 엔진 `chaeksas-core` | Studio | 서버 실행기 |
| 결재는 어디서 답하나 | NowView 화면 | Studio 시험 대화상자 | Center 결재함 — 콘솔, 또는 **NowView 화면(대리 답용 키)** |
| NowView 기록 | 기록 작업 (같은 프로세스) | 기록 작업 (HTTP 어댑터) | 기록 작업 (HTTP 어댑터) |
| 진행 읽기 | 엔진 스냅샷 | 작업 호출이 알려 준 것만 (`{{node_id}}`) | `GET /api/v1/runs/{run_id}/events` (N3) — 그 전에는 Studio와 같다 |
| NowView 화면 조작 | 된다 | **읽기만** — "Studio에서 답하세요" 배너 | 된다 (대리 답, N3) — 그 전에는 읽기만 |
| 데모 플레이어 각본 | 된다 | 안 된다 | 된다 — 결재에 대리 답으로 답한다 (N3) — 그 전에는 안 된다 |
| 어떻게 정하나 | 데모 실행을 만들 때·초기화할 때 고른다(`executor`) — 아래 N2 |||

## 5. NowView 변경 (단계)

### N1. 기록 작업 — 사람 결정 뒤에 서비스 태스크 하나씩

`chaeksas/*.extension.json`의 `operations`와 BPMN에 다음 작업을 더한다. 입력에는 항상 `demo_run_id`,
Chaeksas `run_id`(`{{run_id}}`), 그리고 **답한 사람**이 들어간다. 답한 사람은 요청서 R1이 해결돼야 받을 수 있다.

| 결재 뒤 | 작업 | 하는 일 (지금 `_before_answer`에서 옮긴다) |
|---|---|---|
| `Approve_DQ` | `record_dq_review` | 확인완료면 `verify_source`, 보완요청이면 `request_fix`, 그리고 `TASK-DQ` 완료 |
| `Confirm_Calc` | (없음) | 감사 기록은 `compare`가 남긴다. 결재로 바꾸어 담당자를 둔다(N4) |
| `Approve_Sales` | `record_sales_review` | 의견·근거 저장, AI 초안 id(AG-03), `TASK-SALES` 완료 |
| `Approve_Dispatch` · `Approve_Review` | `record_assignment` | 배정한 사람이 그 역할인지 검사하고 감사 기록 |
| `Accept_*` | `record_acceptance` | `TASK-*` 인수와 최신 run 확인(`acks`) |

* **업무 규칙 위반**(예: 검증 오류가 남은 원천의 확인완료)이면 409·422를 돌려준다. 그림에서는 오류 경계로 받아
  **같은 결재로 되돌아간다.** R2는 거절됐다 — 이 고리가 그대로 남는다. **구현(2026-10-25)**:
  * 기록 태스크 7개마다 오류 경계(`Bnd_Record_*`, `Err_record` = `TASK_FAILED`)와 결재로 돌아가는 흐름
    (`Flow_*_rejected`). 결재의 `show`에 `error_message`를 더했다.
  * **그 `error_message`에는 사유가 없다.** HTTP 어댑터는 4xx의 본문을 버리고 「nowview-sc01.record_dq_review이
    409를 돌려줬다」만 남긴다(`http_adapter.AdapterCaller.call`). 사유는 NowView 감사 이력의 `answer_rejected`
    (`node_id`·`status`·`reason`)에 있다. 거절된 답은 「기록」도 업무도 남기지 않는다 — 검사가 부수 효과보다 먼저다.
    Chaeksas가 4xx 본문의 `detail`을 `error_message`에 실어 주면 그대로 보인다(요청 후보).
  * 기록이 성공하면 출력 `error_message: null`로 **직전 사유를 비운다** — 다음 결재에 낡은 사유가 보이지 않게.
    그래서 정의가 0.5.0이 됐다(기록 작업 응답에 `error_message`).
  * 캔버스는 경계도 결재에 접고, 접은 뒤의 자기 고리는 그리지 않는다.
* **업무(`TASK-*`)는 대기가 열릴 때 만든다.** 바깥 실행에서는 Center 결재(`approval_created`)를 읽어서 만들고,
  내장 실행에서는 지금처럼 만든다. 같은 함수를 쓴다.
* 내장 경로는 **같은 작업을 같은 프로세스에서** 부른다. `_before_answer`는 사전 검사만 하는 함수로 줄인다.
  기존 테스트(EV01~EV07, EX03·EX07)가 그대로 통과해야 한다.

### N2. 데모 실행 ↔ 바깥 실행 잇기

* 문서에 `bpm.executor`(`embedded` | `studio` | `center`)와 `bpm.external_run_id`를 둔다.
  바깥 실행이면 내장 엔진은 그 문서에서 `step`하지 않는다.
* 바깥 실행을 처음 아는 시점은 **첫 작업 호출**이다. 그 호출에 실린 `{{run_id}}`로 데모 실행과 바깥 실행을 묶는다.
  같은 데모 실행에 다른 `run_id`가 오면 409를 낸다. 단, 정정(EX03)으로 새 실행을 시작한 경우는 예외로 이력에 남긴다.
* 실행 위치(Studio인지 서버인지)는 작업 입력만으로는 알 수 없다. 요청서 R5다.

**구현에서 정한 것(2026-10-25)**

* **실행 위치는 데모 실행을 만들 때·초기화할 때 사람이 고른다**(`POST /demo-runs {executor}`, `…/reset
  {executor}`, 데모 플레이어의 실행 위치 선택). 근거:
  * 템플릿으로 알 길이 없다 — Chaeksas가 R5를 거절했다. 템플릿 값은 부르는 쪽이 스스로 하는 주장이라
    인증된 구분이 아니라는 이유다.
  * 인증된 구분은 N6의 키다 — Studio에는 시험용 키만, 현장(Bot UI·서버 실행기)에는 운영 키만 간다
    (R6 답, Chaeksas ADR-0094 §7). N6이 그 검사를 붙였다(아래).
  * **화면이 읽기 전용인지는 첫 작업 호출 전에 정해져야 한다.** 수신 직후, 바깥 실행이 아직 시작되지
    않았을 때부터 "Studio에서 답하세요"와 Studio에 넣을 입력(데모실행ID·원천ID)을 보여야 한다. 첫 호출로
    알아내는 방식은 그 자리를 비운다.
  * **내장 데모 실행이 바깥 호출을 받아 바깥으로 바뀌게 두지 않는다.** 그러면 내장 BPM이 이미 시작된
    문서에 바깥 실행이 겹친다 — 고치려던 바로 그 상태다. 내장 데모 실행에 바깥 호출이 오면 409다.
  * N6은 키로 선언을 검사한다: 시험용 키로 온 호출이 `center` 데모 실행에, 운영 키로 온 호출이
    `studio` 데모 실행에 오면 409. 선언은 남는다 — 위 셋째 이유 때문이다.
* 문서: `bpm`은 바깥 실행이면 처음부터 있다 — `{executor, external_run_id, run_id, state, snapshot: null,
  visited, position: []}`. `state`는 `not_started` → 첫 호출에 `running` → 인계가 성립하면 `done`이다.
  내장은 지금처럼 시작 때 생기고 `executor: "embedded"`다. 이전 문서는 `upgrade`가 내장으로 채운다.
* **모든 작업 본문에 `chaeksas_run_id: {{run_id}}`, `chaeksas_node_id: {{node_id}}`**(정의 0.3.0).
  `run_id`라는 이름은 작업 입력에서 이미 계산 id다. 실행 id가 없는 호출(0.2.0 정의)은 422다.
* 바깥 데모 실행에서 `receive`는 원천만 등록한다. 화면 답(`actions`)과 각본(`script`)은 409이고, 사유가
  어디서 답하는지 말한다. 원천 수신·시계·Agent 재생성·채택은 BPM 밖의 일이라 그대로 된다.
* **정정(EX03)**: 묶인 실행이 있을 때 정정본이 오면, 직전 원천이 보완 요청(`NEEDS_INFO`) 상태면 같은
  실행이 받는다(Studio에서 「원천정정」 메시지를 보낸다). 그 밖이면 실행을 `bpm_history`로 옮긴다
  (`state: superseded`). 그 실행의 남은 호출은 409이고 다음 새 실행이 묶인다(`external_run_linked`가 감사
  이력에 둘 남는다). 바깥 실행은 NowView가 취소할 수 없으므로 이것이 내장의 cancel에 해당한다.
* 진행: 작업을 부른 노드와, 기록 작업이면 그 앞의 결재(계산이면 `Confirm_Calc`)를 `visited`에 쌓는다.
  **토큰 위치는 비워 둔다** — 호출이 끝나면 토큰은 이미 다음으로 갔다. 캔버스는 바깥 실행이 끝나도 알려
  주지 않은 노드(시작·게이트웨이·메시지 대기)를 미실행으로 칠하지 않는다 — 모르는 것이다.
* 업무: 바깥 결재의 대기 id를 (실행, 결재, 원천·계산)으로 지어 `sync_tasks`에 넘긴다. 정정 뒤 새 실행이
  같은 결재에 오면 인수한 업무에 재확인이, 끝난 업무에 재검토 업무가 생긴다 — 내장과 같은 규칙이다.

### N3. Center 연동 (엔진 안의 클라이언트, 비밀은 환경변수)

| 환경변수 | 쓰임 |
|---|---|
| `CHAEKSAS_CENTER_URL` | Center 주소 |
| `CHAEKSAS_INTEGRATION_KEY` | 연동용 키: `POST /jobs`(SC01 기동), `POST /messages`(정정본 EX03), `GET /runs/{id}/events`(진행) |
| `CHAEKSAS_RELAY_KEY` | 대리 답용 키: `GET /approvals?assignee=`, `POST /approvals/{id}/answer` (`X-CHK-On-Behalf-Of` = 행위자 이름) |

* **결재 답은 NowView가 검사한 뒤 Center로 보낸다.** 화면 → BFF → 엔진(사전 검사, 403·409·422) → Center 대리 답 순서다.
  콘솔에서 바로 답한 것은 사전 검사를 거치지 않으므로, N1의 기록 작업이 마지막 관문이다.
* **진행은 폴링으로 받는다**(2초, 열린 데모 실행만). 바뀌면 기존 `notifier`로 SSE를 낸다. 요청서 R3이 생기면 push로 바꾼다.
* BFF는 지금처럼 경로를 그대로 중계한다. 키는 엔진만 쥐고, 브라우저와 BFF에는 두지 않는다.

### N4. 결재 담당자 — 역할을 이름으로

* BPMN `chk:approval.assignees`에 사람 이름을 적는다. `Approve_DQ`·`Confirm_Calc`는 `["이도윤"]`,
  `Approve_Sales`·`Approve_Dispatch`·`Approve_Review`는 `["박서진"]`, `Accept_*`는 배정 변수(`생산담당자` 등)다.
  배정 변수에는 사용자 id가 아니라 **이름**이 들어가야 하므로 폼 값 → 이름 변환이 필요하다.
* `Confirm_Calc`는 `manualTask`(확인)라 담당자를 둘 수 없다(C14 B12 경고). 그래서 `userTask` 결재로 바꾼다.
* `NODE_ROLES`와 BPMN `assignees`가 어긋나지 않게 테스트를 둔다. `test_every_user_task_has_a_role`과 같은 방식이다.

### N5. 가상 직원 — 「고객계획 접수 가상 직원」

기획안 1단계(데이터 수집·이상 징후 감지는 Agent, 승인은 사람)를 Chaeksas 가상 직원으로 옮긴다.

```
NowView 원천 수신 ──POST /messages──▶ 접수 Bot nowview.sc01-intake (server)
                                        ├─ 원천마다 validate_source (반복)
                                        ├─ 일괄 결재 — 감독자 이도윤(영업담당), show: 원천ID·고객계획·검증 결과·변경 요약
                                        └─ 승인된 건마다 SC01 위임 (Call Activity 반복 + 위임, ADR-0082)
```

* Center 자원: `virtual_worker` id는 `nowview-intake`, 이름은 「고객계획 접수 담당」, `supervisors`는 `["이도윤"]`,
  `intake`는 `nowview.sc01-intake`다. 결재 없이 기동하는 그림은 묶이지 않는다(B16).
* NowView 고객계획 화면(UI02)에 「접수 가상 직원」 카드를 둔다. 오늘 접수한 건수, 승인 대기, 기동된 SC01 실행을 보인다.
  출처는 `GET /virtual-workers/nowview-intake`(대리 답용 키, 감독자 이름)다.
* **반려된 건은 SC01을 시작하지 않는다.** 원천은 `NEEDS_INFO`로 남고, 업무 화면에 보완 요청으로 보인다.
* NowView의 AI Agent(AG-01~03, 검토 초안)는 가상 직원이 아니다. 서비스 태스크가 부르는 규칙 검증된 초안이고, 그대로 둔다.
* SC01은 위임 대상이므로 **서버 Bot 패키지**로 배포돼야 한다. Studio는 위임하지 않으므로(B14), 가상 직원 경로는 Center에서만 돈다.

### N6. 시스템 작업의 인증

지금 시스템 작업 네 개는 **인증 없이 열려 있다.** 운영계는 인터넷에 노출돼 있다. 연계를 붙이기 전에
확장 정의에 `auth: {type: bearer}`를 두고, 엔진이 키를 검사하게 한다. 키를 어떻게 받는지는 요청서 R6이다.

**지금 정의 두 벌은 최신 Chaeksas에서 거절된다**(2026-10-25 확인). ADR-0091 이후로는 `requires_keys: [{purpose: run}]`가
있는데 `auth`가 없으면 E3 `adapter_invalid`다. NowView 엔진에 고정된 `chaeksas-core`는 그 이전 판이라 통과했고,
Studio도 그래서 돌았다. 바로잡는 길은 두 가지다. ① `auth: bearer`를 두는 것이 N6의 방향이다.
② `requires_keys`를 빼면 키를 받지 않는 앱이 된다. (N1에서 ②로 임시로 바로잡았고 N6에서 ①로 갔다.)

**구현에서 정한 것(2026-10-25)** — Chaeksas R6 답을 그대로 따랐다.

* 정의 0.4.0 / 0.4.0-local: `auth: {type: bearer}` + `requires_keys: [{purpose: run}]`. 키 참조는 BPMN
  `service_keys`의 `nowview`. 최신 계약 검사 위반 0건, `takes_key` 참.
* **키 둘을 NowView가 짓는다.** 운영 키 `NOWVIEW_SYSTEM_KEY` → Center 「외부 앱 키」(서버 실행기·Bot UI),
  시험용 키 `NOWVIEW_SYSTEM_KEY_TEST` → 「시험용 키」(Studio만). 엔진은 상수 시간 비교로 둘 다 대 보고
  어느 쪽인지 가린다(`engine/app/sc01/auth.py`). 원문을 환경에 둔다 — 해시만 두는 것은 이득이 적다
  (같은 서버의 `/etc/nowview.env` 0600, DB 비밀번호와 같은 자리다).
* **어느 키인지가 실행 위치다** — 시험용 키면 `studio`, 운영 키면 `center`. 데모 실행의 선언과 어긋나면
  409, 묶이지 않는다. 키가 없거나 틀리면 401.
* **키가 하나도 없으면 503이다(fail closed).** 운영계는 인터넷에 열려 있다 — 환경 파일이 빠진 채
  올라가면 조용히 열린다. 끄는 것은 `NOWVIEW_SYSTEM_AUTH=off`로 명시한다(로컬·시험). 두 키가 같아도
  503이다 — 시험용 키가 운영을 여는 셈이다. `/health.systemAuth.mode`가 `keys`·`off`·`unconfigured`.
* BFF는 `Authorization`을 그대로 넘기고 검사하지 않는다 — 키는 엔진만 쥔다.
* 배포: `deploy/bootstrap.sh`가 **파일이 이미 있어도 빠진 키만** 지어 더한다(있는 값은 그대로 — 바꾸면
  Center에 넣은 키와 어긋난다). 값은 출력하지 않는다. 로컬은 `engine/.env.local`을 `stack.sh`가 읽는다.
* 내장 경로(`_InProcessCalls`)는 HTTP를 타지 않아 키와 무관하다.

## 6. 하지 않는 것

* 내장 BPM을 걷어내지 않는다. 시연·CI·오프라인에서 그대로 쓴다. 바깥 실행은 데모 실행마다 고르는 옵션이다.
* Center 결재를 NowView DB에 복사하지 않는다. 읽을 때 가져오고, 업무(`TASK-*`)만 NowView 문서에 둔다.
* 장면 2 이후는 만들지 않는다(4.7).

## 7. 순서

1. **N1 + N4 — 했다.** Chaeksas 엔진 + HTTP 어댑터 + 로컬 정의로 SC01을 돌려 **인계(`HANDED_OFF`)까지** 갔다
   (서비스 호출 11건 모두 200). 설계와 달리 정한 것:
   * 답한 사람은 폼에 임시 칸을 두지 않고 **그 결재의 담당자로 짐작해 적고 `guessed`로 표시**한다 — 자칭
     이름을 하나 더 만들지 않는다. R1이 오면 본문에 `answered_by`를 더한다.
   * 배정 기록을 `record_dispatch`·`record_review_request` 둘로 나눴다 — 어댑터는 본문 템플릿의 입력이
     없으면 실패한다.
   * 업무(`TASK-*`)는 바깥 실행에서 **기록 때 늦게 연다**(`opened_late`). Studio에는 결재가 열리는 신호가 없다.
   * 결재 뒤 기록이 거절될 때 같은 결재로 되돌아가는 오류 경계는 N1에서 미뤘다가 **N3 앞에서 달았다**(위 N1).
     Center 콘솔 답으로 검증 오류 원천을 확인완료해도 실행이 실패로 끝나지 않고 같은 결재가 다시 열린다.
   * 캔버스는 기록 태스크를 결재 노드에 접는다. 확장 정의는 `0.2.0`(로컬 `0.2.0-local`), `requires_keys`를 뺐다.
2. **N2 — 했다.** Studio 실행용 데모 실행(`executor: studio`)을 만들고 Chaeksas 엔진 + HTTP 어댑터 + 로컬
   정의(0.3.0-local)로 돌려 인계(`HANDED_OFF`)까지 갔다(호출 11건 모두 200). 내장 BPM은 돌지 않았다(대기·
   스냅샷 없음, 업무 5건 모두 늦게 열림). 이미 묶인 데모 실행에 다른 실행을 붙이면 첫 호출이 409로 실패하고,
   내장 데모 실행에 붙여도 409다. 화면은 배너·읽기 전용 폼·각본 비활성·캔버스 진행을 브라우저에서 봤다.
   설계와 다르게 정한 것은 위 N2 「구현에서 정한 것」에 적었다 — 실행 위치는 선언, 토큰 위치는 비움.
   **N6 — 했다.** 같은 방식으로 키를 실어 돌렸다: Studio 데모 실행 + 시험용 키, Center 데모 실행 + 운영 키는
   인계까지(각 11건 200), 엇갈린 짝은 첫 호출 409로 실패·묶이지 않음, BFF 경유 키 없음·틀린 키는 401.
   **운영계에 올리려면** `scripts/deploy.sh --bootstrap`(키 생성) → Center CON-07에 두 키 입력 → 0.5.0 정의(지금 판)
   서명·등록 순서다. 운영계는 아직 이전 구현이다(CLAUDE.md 5.4).
3. **N3** — Center 서버 Bot과 NowView 화면 대리 답, 폴링 SSE.
4. **N5** — 가상 직원. 접수 Bot 그림, Center 등록, UI02 카드.

Chaeksas 요청(R1~R6)은 1과 동시에 보낸다. R1이 오면 1의 임시 칸을 걷는다.
