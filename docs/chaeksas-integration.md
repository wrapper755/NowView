# NowView ↔ Chaeksas 연계 설계 — SC01을 바깥 Chaeksas에서 돌려도 NowView 전체가 따라온다

- 작성: 2026-10-25 · 상태: **수락**. N1·N4·N2·N6·N3 구현(2026-10-25), N5 구현(2026-10-26), 장면 2 같은 틀(2026-10-27), N7 Pull 전환(2026-10-31 — N6 대체) — 아래 7
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
| 진행 읽기 | 엔진 스냅샷 | 작업 호출이 알려 준 것만 (`{{node_id}}`) | `GET /api/v1/runs/{run_id}/events` 2초 폴링 (N3) |
| NowView 화면 조작 | 된다 | **읽기만** — "Studio에서 답하세요" 배너 | 된다 — 대리 답 (N3). 대리 답용 키가 없으면 503과 사유 |
| 데모 플레이어 각본 | 된다 | 안 된다 | 된다 — 결재에 대리 답으로 답한다 (N3) |
| 누가 기동하나 | 수신 | Studio 시험 실행 | 수신 → `POST /jobs` (N3). 연동용 키가 없으면 기동하지 않고 사유를 남긴다 |
| 어떻게 정하나 | 데모 실행을 만들 때·초기화할 때 고른다(`executor`) — 아래 N2 |||

## 5. NowView 변경 (단계)

### N1. 기록 작업 — 사람 결정 뒤에 서비스 태스크 하나씩

`chaeksas/*.extension.json`의 `operations`와 BPMN에 다음 작업을 더한다. 입력에는 항상 `demo_run_id`,
Chaeksas `run_id`(`{{run_id}}`), 그리고 **답한 사람**이 들어간다. 답한 사람은 결재의 `answered_by_as` 변수로 받는다(R1, §7의 5).

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

**구현에서 정한 것(2026-10-25)** — `engine/app/sc01/center.py`(클라이언트) · `poller.py` · `process.py`의 「Center 실행」

* **기동**: center 데모 실행의 원천 수신이 `POST /jobs {bpm_process_id, target: {type: server_runner}, inputs:
  {데모실행ID, 원천ID}, idempotency_key: 데모실행:원천}`을 부른다. 패키지 id는 `CHAEKSAS_SC01_PACKAGE`(기본
  `nowview.sc01`). 실행이 묶이는 것은 여전히 첫 작업 호출의 `{{run_id}}`다(N2) — 작업 정보에는 실행 id가 없다.
  * 묶인 실행이 보완 대기면 정정본은 `POST /messages {schema: 1, name: 원천정정, correlation: 데모실행ID, …}`로
    같은 실행에 간다. **그래서 BPMN `Wait_Correction`에 상관 키(`데모실행ID`)를 달았다** — Center는 상관 키 없는
    메시지로 기다리는 실행을 찾지 않는다(C12). 그 밖의 정정은 실행을 이력으로 옮기고(N2와 같다) **앞 작업을
    거둔 뒤**(`DELETE /jobs/{id}`, 실패해도 막지 않고 감사 이력에 남김) 새로 기동한다. 초기화도 앞 작업을 거둔다.
  * 앞 작업이 아직 첫 호출 전인데 새 원천이 오면 409 — 늦게 깨어난 앞 실행이 데모 실행을 가로채지 않게.
* **대리 답**: 화면 → 엔진 사전 검사(`check_actor` 403, `check_answer` 409·422 — **Center에 묻기 전에**, 입력을
  지우지 않는다) → `GET /approvals?state=open&assignee=<이름>`에서 이 실행·이 노드의 결재를 찾는다(서버 실행기가
  결재를 올리기까지 최대 30초 기다린다 — 각본이 수신 직후 원천 확인으로 넘어가도 끊기지 않게) → 결재가 보인
  값(`review`)으로 한 번 더 검사 → `POST /approvals/{id}/answer {answer, if_review_digest}`(`X-CHK-On-Behalf-Of`
  = 행위자 이름). Center 거절은 사유를 그대로 낸다(`not_assignee` 403, `already_answered`·`review_changed` 409,
  `answer_invalid` 422). 키가 받아들여지지 않거나 닿지 못하면 503. **업무 효과는 여전히 기록 작업이 낸다** —
  대리 답은 결재를 닫을 뿐이다. 감사 이력에 `answer_relayed`. 답한 사람이 대리 답의 이름이라 Center 결재에는
  실제 사람이 남고, 기록 작업도 그 이름을 `answered_by`로 받는다(R1).
* **진행**: 폴러가 `bpm.state == running`인 center 데모 실행만 2초마다 읽는다(`store.running_external` — 문서를
  다 읽지 않는다). C3 이벤트 → 지나온 노드·토큰 위치(시작했고 안 끝난 노드)·열린 결재(`human_requested` −
  `human_answered`·`human_timeout`·`human_withdrawn`)·끝(`run_finished`). 새로 열린 결재는 대리 답용 키로 읽어
  (SC01은 역할마다 한 사람이라 역할로 담당자를 안다) 검토 자료·폼을 화면 대기에 싣고 **업무를 그때 연다** —
  `opened_late`가 없다. 결재를 못 읽으면 업무는 열지 않는다(계산 id 없이 열면 인계 판정이 틀린다) — 기록 때
  늦게 연다. 읽은 끝(`last_seq`)이 같으면 저장하지 않는다. 바뀌면 기존 notifier로 SSE.
  * 대리 답한 결재는 Center 기록에 `human_answered`가 오기 전까지 대기로 다시 보이지 않는다(`relayed`).
  * 캔버스는 Studio와 달리 시작·게이트웨이도 칠한다 — 실행 기록에 있다.
* **설정이 없을 때**: 조용히 내장으로 돌지 않는다. 수신은 되고(BPM 밖의 일) 「기동하지 않았다」 사유가 배너에
  보인다 — Center 콘솔에서 직접 기동하면 첫 호출로 묶이고 사유는 첫 폴링에서 걷힌다. 화면 답·각본은 503(빠진
  환경변수 이름). 폴러는 연동용 키가 없으면 뜨지 않는다. `/health.center`가 `url`·`integration`·`relay`·
  `polling`을 드러낸다(키 값은 싣지 않는다). 화면은 `answerHere`(엔진이 정한다)로 폼·각본을 켠다.
* **실측(2026-10-25)**: 사용자 Center(:8800)에는 NowView용 키가 없어 쓰지 않았다(키를 지어내지 않는다). 대신
  Chaeksas main 코드로 **빈 Center를 따로 띄워**(:8810, 임시 데이터 폴더·관리자 토큰) 연동용·대리 답용·
  server_runner 키를 발급하고, 서버 실행기 몫은 진짜 Chaeksas 엔진으로 흉내 냈다(실행 기록·결재를 server_runner
  키로 올리고 Center에 적힌 답을 읽어 넣음). 결과:
  * 엔진 프로세스 + 화면(브라우저)에서 원천 확인·비교 계산을 화면으로 대리 답, 나머지를 엔진 API로 대리 답 →
    **인계(`HANDED_OFF`)까지**. Center 결재 8건 모두 담당자 이름 + 대리 답 키 이름으로 닫혔고, 업무 5건은 전부
    폴링 때 열렸다(늦게 연 것 0). 역할이 틀린 답은 Center에 가기 전에 403.
  * `POST /jobs`는 빈 Center라 422 `no_deployment`로 사유가 그대로 보였다. **SC01 패키지 배포·진짜 서버 실행기로
    기동되는 것은 재지 못했다** — 패키지 서명·배포가 필요하다.
  * `POST /messages`는 처음에 422 `input_invalid`였다 — 메시지는 `schema`가 있는 계약(`MessageRequest`)이다.
    고친 뒤 기다리는 실행이 없어 422 `no_receiver`. **기다리는 실행에 메시지가 전달되는 것은 재지 못했다** —
    Center는 실행기의 하트비트(`waiting[]`)로 그것을 안다.

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

**구현에서 정한 것(2026-10-26)** — Chaeksas R7이 ADR-0099(입력의 「값 출처」)로 풀린 뒤 지었다. `engine/processes/sc01-intake.bpmn`,
`process.py`의 「접수 가상 직원」, `components/sc01/intake-card.tsx`.

* **감독자 이름을 그림에 적지 않는다.** 접수 Bot 입력 `감독자`(list, 필수, `source: virtual_worker.supervisors`)를 일괄
  결재가 `assignees: "감독자"`로 받는다. 값은 Center가 가상 직원 등록(CON-13)에서 넣는다 — 감독자를 바꾸면 다음 일괄부터
  따라간다. 필수라서 가상 직원 없이 돌리면 시작하지 않는다(`input_required`). `가상직원`(`virtual_worker.name`)도 받아
  검증·기록 작업의 `processed_by`로 싣는다.
* **일괄 결재는 건별이 아니라 일괄로 승인·반려한다.** 설계는 「승인된 건마다」였지만 두 가지가 막는다. ① 결재 폼에 여러 건을
  고르는 칸이 없다(C14 `bool·number·text·choice`). ② 결재 뒤에 반복할 목록을 다시 만들면 B16 「보여 준 것과 다른 것을
  기동」 경고이고, Center는 B16이 있는 접수 Bot을 가상 직원에 묶지 않는다(`intake_not_gated`). NowView는 수신 한 번에 메시지
  하나를 보내므로 일괄 하나가 대개 원천 하나라 실제로는 건별과 같다. 폼은 `결정`(승인·반려)·`의견`(필수)이다.
* **흐름**: 메시지 시작 `고객계획접수`(본문 `원천목록` = `[{데모실행ID, 원천ID}]`) → 건수 → 원천마다 `screen_source`(반복) →
  `Approve_Batch` → 원천마다 `record_intake_review`(반복) → 승인이면 `Call_SC01`(위임 반복, **함께 돈다** `isSequential=false`
  — SC01은 사람을 며칠 기다린다), 반려면 끝. 위임 실패는 오류 경계 → 사유만 남기고 끝.
* **접수 Bot의 작업은 데모 실행을 바깥 실행에 묶지 않는다**(`Sc01Process._intake_operate`). 접수 Bot 실행은 SC01 실행이
  아니다 — 묶으면 승인 뒤 위임된 SC01의 첫 호출이 「이미 다른 실행에 묶였다」 409가 된다. 묶는 것은 위임된 SC01의 첫
  호출(`validate_source`)이다. center 데모 실행·운영 키에서만 받는다(내장·Studio 키는 409).
* **반려 = SC01을 시작하지 않는다.** `record_intake_review`가 원천을 `NEEDS_INFO`(`fix_opinion` = 의견)로 두고 영업담당의 원천
  확인 업무 TASK-DQ를 **보완 요청(`NEEDS_INFO`)** 상태로 연다. 정정본이 새 일괄로 승인되면 위임된 SC01의 원천 확인 결재가
  같은 업무를 「보완 후 재배정」으로 잇는다(`sync_tasks` — 내장의 보완 경로와 같은 규칙). 승인이면 감사 이력(`intake_reviewed`)만.
* **SC01 입력 `처리자`**(string, 필수 아님, `source: virtual_worker.name`). 일괄이 맡긴 서버 실행이면 Center가 이어받은 가상 직원의
  이름을 넣는다(ADR-0099 §3). 접수 Bot은 넘기지 않는다(넘기면 422). **기록에 남긴다** — `validate_source`의 `processed_by`로
  받아 그 실행에 `processed_by`를 두고 감사 이력 `processed_by_virtual_worker`를 남긴다. 화면은 실행 배너·카드에 「처리자」로
  보인다. 혼자 기동한 SC01·내장은 `None`이라 아무 일도 없다. 확장 정의 **0.7.0**(작업 둘 + `validate_source.processed_by`).
* **엔진**: `CHAEKSAS_INTAKE_WORKER`(가상 직원 id, 예 `nowview-intake`)가 있으면 center 데모 실행의 수신이 `POST /jobs` 대신
  `POST /messages {name: 고객계획접수, virtual_worker, payload: {원천목록}}`(상관 키 없음 = 메시지 시작)을 보낸다. 출처가 있는
  입력(`감독자`·`가상직원`)은 보내지 않는다 — 보내면 422 `input_not_from_caller`. 장부의 작업은 접수 Bot 작업이고
  (`via: intake`, `decision`), 정정·초기화로 대체되면 그것을 거둔다 — 일괄 취소가 위임된 SC01도 취소한다(ADR-0084). 승인 전에
  다른 원천이 오면 409, 반려된 뒤면 새 일괄로 보낸다. 보완 대기 중인 SC01 실행에 가는 정정본 메시지(N3)는 그대로다. 설정이
  없으면 N3처럼 SC01을 바로 기동한다.
* **카드(UI02 「접수 가상 직원」)**: `GET /sc01/intake` → 엔진이 **연동용 키**로 `GET /virtual-workers/{id}`를 읽어 센다 — 오늘
  접수(한국 시각의 실제 날짜, 일괄 수), 승인 대기(열린 일괄 결재), 기동된 SC01(일괄의 자식 수·상태별). 설계의 「대리 답용
  키」가 아니라 연동용 키다 — 대리 답용 키는 감독하는 가상 직원만 보이고 행위자 이름이 필요하다. 승인 대기 일괄은 감독자가 카드에서
  답할 수 있다(`POST /sc01/intake/approvals/{id}/answer`, 대리 답 — 감독자인지는 Center가 대조해 403 `not_assignee`). 일괄
  결재는 SSE가 모르는 Center 쪽 일이라 카드만 10초마다 다시 읽는다.
* **`chaeksas-core`를 `d2e2e46`으로 올렸다**(b421880 이후). 담당자 변수가 `None`이면 결재를 만들 때 실행이 `assignees_missing`
  으로 실패해 멈춘다(예외가 아니라 `run_finished.error_code`) — 시험이 잠갔다.
* **실측(2026-10-26)**: 사용자 Center(:8800)에는 NowView 키가 없어 쓰지 않았다. Chaeksas `d2e2e46` 코드로 **빈 Center(:8810)와
  진짜 서버 실행기**(`chk-server-runner`)를 임시로 띄우고, 확장 정의 0.7.0 등록·주소 덮어쓰기(`http://localhost:3010`)·운영/시험용
  키, 두 패키지(관리자 업로드·승인·배포), 가상 직원 `nowview-intake`(감독자 이도윤)를 놓았다. NowView 엔진 :8078 + 웹 :3010.
  * **가상 직원 등록 201** — Center의 B16 관문(`intake_not_gated`)을 이 그림이 통과했다.
  * 화면 수신 → 메시지 시작 → 실행기가 접수 Bot 기동 → HTTP 어댑터가 `screening` 200 → 일괄 결재가 Center 결재함에
    **담당자 `["이도윤"]`**(그림에 없는 이름 — 등록에서 왔다)으로 올랐다. 카드가 오늘 접수 1·승인 대기 1을 보였고, 카드에서 승인
    → `decision` 200 → SC01 위임 작업(가상 직원 이어받음, `requested_by = server_bot:<접수 실행>`) → 위임된 SC01이 데모 실행을
    묶고 `처리자 = 고객계획 접수 담당`이 NowView에 남았다 → 나머지 결재 8건을 화면 대리 답으로 → **인계(`HANDED_OFF`)**, 접수
    일괄 `success`(자식 1 성공).
  * 반려: EX02 수신 → 카드에서 반려 → 원천 `NEEDS_INFO`·TASK-DQ `NEEDS_INFO`, SC01 작업 0, 일괄 `success`(자식 0).
  * **드러나 고친 것 둘**: ① 실행기가 환경변수 키로 붙으면 Center가 앱 키를 봉해 줄 수 없어 접수 작업을 `not_ready`로 거절했는데
    (Chaeksas 설정 문서대로 — `CHK_SERVER_RUNNER__SVC__NOWVIEW`로 풀었다) NowView 장부는 「승인 대기」로 남아 다음 수신이 영영
    409였다 → 수신 때 앞 작업을 `GET /jobs/{id}`로 읽어 거절·만료·취소·실행 끝이면 `center_job_ended`를 남기고 새로 보낸다.
    ② 초기화하면 원천 번호가 다시 SRC02라 Center 멱등 키(`데모실행:원천`)가 겹쳐 초기화 전의 (거절된) 작업이 그대로
    돌아왔다 — N3의 `/jobs`도 같았다 → 키에 초기화 회차를 넣었다(`_center_key`). 둘 다 시험으로 잠갔다.
  * ~~재지 못한 것: 서명된 패키지(Studio 내보내기)·Center가 봉해 내려 주는 앱 키 경로~~ — 아래 로컬 Center 실측에서 쟀다.
    남은 것은 **운영 Center**와 **로컬 Center에서의 반려 경로**(임시 Center에서만 쟀다)다.
* **로컬 Center 실측(2026-10-27)** — 사용자의 로컬 Chaeksas(docker compose: Center :8800 + 서버 실행기 컨테이너 — compose에 실행기를
  더한 Chaeksas 작업 위)에 정식 경로로 올렸다: CON-07에 정의 0.7.1 등록·외부 앱 키·시험용 키·주소 `http://host.docker.internal:3000`,
  **Studio로 내보낸** 두 패키지 승인·배포(실행기는 **등록 승인**으로 붙어 앱 키를 Center가 봉해 내려 줬다 — `SVC` 환경변수 없음),
  CON-13 가상 직원 `nowview-intake`. NowView는 메인 체크아웃(웹 :3000·엔진 :8077, `engine/.env.local`).
  * 화면 수신 → 메시지 시작 → 접수 Bot `screening` 200(`172.17.0.1:3000` — 컨테이너에서 호스트로) → 일괄 결재(담당자 이도윤) → 카드에서
    승인 → SC01 위임 → 처리자 기록 → 결재 8건을 화면 대리 답(원천 확인·계산·영업 검토·배정·Review 요청·인수 셋) → 실행기가 `handoff` 200
    → **`HANDED_OFF`**, SC01 실행 `success`, 접수 일괄 `success`(자식 1). 오류·거절 0.
  * **가는 길에 드러나 고친 것 둘**(위 §7의 4 후속): ① 실행기가 컨테이너라 `localhost:3000`이 닿지 않았다 → 정의 0.7.1(허용 호스트
    `host.docker.internal`). ② Studio 내보내기의 `requires.extensions`가 비어 실행기가 「서비스 앱 주소를 모른다」로 실패했다 → 두 그림에
    `chk:process.extensions` 선언. 둘 다 임시 Center 실측(실행기를 호스트 프로세스로, 매니페스트를 손으로)에서는 안 보였다.
  * 화면에서 각본(플레이어 「다음 장면」)이 아니라 폼으로 답했다 — 수신을 손으로 했으므로 각본과 섞으면 409다(CLAUDE.md 4.1).

### N6. 시스템 작업의 인증

> **2026-10-31 N7로 대체됐다** — Center가 NowView를 부르지 않으니 받을 키도 없다. 아래는 당시 기록이다.

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

### N7. 일감을 가져간다 — Chaeksas Pull 전환(ADR-0102, C15)에 따라 (2026-10-31)

Chaeksas가 BPM 프로세스에서 바깥 기능을 부르는 길을 모두 Pull로 바꿨다. 서버 실행기·Studio는
`chk:serviceCall`을 **Center에 외부 작업으로 올리고**, 그 토픽(= `app_id`)을 맡은 **일꾼**이 Center에
롱폴링을 걸어 가져가 끝낸다. Center는 외부 앱 키·시험용 키·주소 덮어쓰기(ADR-0094·0097)를 걷었다 —
N6의 키와 R4의 주소가 둘 다 없어졌다.

**선택: 엔진이 직접 일꾼이 된다**(사용자 결정). 다른 길은 Chaeksas 범용 어댑터 일꾼
(`chk-adapter-consumer`)을 NowView 옆에 띄워 지금 HTTP 어댑터 정의 그대로 BFF를 부르게 하는 것이었다 —
NowView 코드는 거의 그대로지만 프로세스가 하나 늘고, HTTP 한 번과 키 검사(N6)가 남는다.

**구현에서 정한 것**

* `engine/app/consumer.py` — `service_kit`의 `Consumer`·`Enrollment`·`Service`를 그대로 쓴다. 토픽 여섯
  (`nowview-sc01`~`sc06`)이 일꾼 하나다. 작업마다 같은 처리기가 `ScNProcess.operate`를 부른다 — 내장
  `_InProcessCalls`와 같은 `run_operation` 길이다.
* **실행 위치 = 일감의 `origin`**(`test` → studio, `run` → center). Center가 올린 쪽을 인증해 붙인다. N2의
  선언 검사(`link_external_run`)는 그대로이고 키 대신 이것을 본다.
* **일감 입력 = 그림의 `chk:serviceCall.input`.** `demo_run_id`로 데모 실행을 찾고, 바깥 실행 id·노드 id는
  멱등 칸에서 온다(`{{run_id}}`·`chaeksas_run_id`가 하던 일).
* **거절은 `fail`에 사유를 싣는다**(`forbidden`·`not_found`·`conflict`·`input_invalid`, 다시 부르지 않음).
  결재가 보이는 `error_message`에 사유가 온다 — 어댑터 때는 상태 코드뿐이었다(N1의 「사유는 감사 이력」).
* **manifest는 확장 정의에서 짓는다**(작업·모드·스키마·`timeout_s`). Center가 작업을 대조하고 출력 필수 칸을
  막는다. 정의는 Center에 계속 등록한다 — 외부 확장 토픽은 등록된 정의가 있어야 일꾼에게 승인된다.
  **정의의 요청 템플릿은 이 길에서 읽지 않는다** — 다시 서명하지 않으려고 고치지 않았다(어댑터 일꾼을
  대신 쓸 때를 위한 것이기도 하다).
* **들이기**: 토큰이 없으면 요청 코드를 로그·`/health.consumer.requestCode`에 보이고, CON-07 「일꾼 승인
  대기」에서 승인하면 봉한 토큰을 `engine/.consumer/`에 둔다. 운영 배포는 그 폴더를 rsync에서 뺀다.
* **멱등 저장소는 메모리다** — 잠금이 지나 다시 온 일감은 저장한 결과를 준다. 엔진이 다시 뜨면 비므로 그 사이의
  재전달은 작업이 **한 번 더 돈다.** 작업마다 두 번 돌아도 안전한지는 확인하지 않았다 — 문서에 저장하는
  멱등 저장소가 후속 거리다.
* 걷은 것: BFF의 `/operations/…`·장면 1 시스템 작업 경로, `auth.py`(N6)·`NOWVIEW_SYSTEM_KEY*`, BFF의
  `Authorization` 전달, BPMN `service_keys`. 그림이 바뀌었으니 **Studio에서 패키지를 다시 내보내야 한다.**
* `chaeksas-core`·`chaeksas-service-kit` 고정 커밋 `554d7fa`.

**Center에 올리는 순서(바뀐 것)** — ① CON-07 확장 정의 `nowview-sc01`~`sc06` 등록(키·주소 없음) ② Studio에서
일곱 그림을 다시 내보내 승인·배포 ③ 엔진에 `CHAEKSAS_CENTER_URL` 등(N3와 같다)을 두고 띄운다 ④ 엔진이 낸 요청
코드를 CON-07 「일꾼 승인 대기」에서 승인(토픽 여섯). 실행기 쪽의 `CHK_SERVER_RUNNER__SVC__NOWVIEW`(N5 실측)는
쓰지 않는다 — 실행기는 Center에 올릴 뿐이다.

**아직 하지 않은 것** — 진짜 Center(C15 판)와 서버 실행기·Studio로 돌려 보지 않았다. 시험은 가짜 Center(일꾼
쪽 엔드포인트)와, 진짜 Chaeksas 엔진이 서비스 태스크를 일감 모양으로 넘기는 흉내(`conftest.C15Calls`)까지다.

## 6. 하지 않는 것

* 내장 BPM을 걷어내지 않는다 — 엔진 시험이 업무 규칙을 같은 프로세스에서 잠그는 데 쓴다. **화면에서는 고르지
  않는다**(2026-10-27 사용자 결정 — 앞으로 BPM은 Studio 시험 실행·Center 서버 실행에서 돈다). 새 데모 실행의 기본은 Center다.
* Center 결재를 NowView DB에 복사하지 않는다. 읽을 때 가져오고, 업무(`TASK-*`)만 NowView 문서에 둔다.
* ~~장면 2 이후는 만들지 않는다(4.7).~~ 장면 2(SC02)는 같은 틀로 붙였다 — 외부 확장 `nowview-sc02`, 같은 키, 같은 실행
  잇기·대리 답·폴링(CLAUDE.md 4.16). 장면 3 이후는 설계·데이터가 나온 뒤다.

## 7. 순서

1. **N1 + N4 — 했다.** Chaeksas 엔진 + HTTP 어댑터 + 로컬 정의로 SC01을 돌려 **인계(`HANDED_OFF`)까지** 갔다
   (서비스 호출 11건 모두 200). 설계와 달리 정한 것:
   * 답한 사람은 폼에 임시 칸을 두지 않고 **그 결재의 담당자로 짐작해 적고 `guessed`로 표시**했다 — 자칭
     이름을 하나 더 만들지 않았다. R1이 와서 짐작은 옛 정의 호환으로만 남았다(아래 5).
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
3. **N3 — 했다.** 위 N3 「구현에서 정한 것」. 그 앞에 N1에서 미룬 **기록 거절 → 같은 결재** 오류 경계를 달았다
   (정의 0.5.0). 남은 것: 진짜 서버 실행기·배포된 패키지로 한 바퀴(기동·정정 메시지 전달), 4xx 본문을
   `error_message`에 싣는 것(Chaeksas 요청 후보).
4. **N5 — 했다** (2026-10-26). 위 N5 「구현에서 정한 것」. 접수 Bot 그림(`sc01-intake.bpmn`), SC01 입력 `처리자`, 수신 →
   메시지 시작, 연동용 키로 가상 직원 읽기, UI02 카드, `chaeksas-core` `d2e2e46`, 확장 정의 0.7.0. 설계와 다르게 정한 것: 일괄
   결재는 **일괄로** 승인·반려(폼에 다중 선택이 없고 B16), 카드는 대리 답용 키가 아니라 **연동용 키**로 읽는다. 임시 Center +
   진짜 서버 실행기로 승인 → 인계, 반려 → 보완 요청까지 쟀다. **Center에 올릴 것**: 정의 0.7.1 서명·등록, `nowview.sc01`·
   `nowview.sc01-intake` 패키지 배포, 가상 직원 `nowview-intake`(감독자 이도윤, 접수 Bot `nowview.sc01-intake`) 등록, 엔진에
   `CHAEKSAS_INTAKE_WORKER=nowview-intake`.
   * **후속(2026-10-27) — 정의 0.7.1.** 사용자 로컬 Center(docker compose)에 실행기가 **컨테이너**로 붙자 주소 덮어쓰기
     `http://localhost:3000`이 닿지 않았다 — 컨테이너 안의 `localhost`는 그 컨테이너다(실측: 실행기 컨테이너에서
     `localhost:3000` 연결 거부, `host.docker.internal:3000` 200). 허용 호스트에 `host.docker.internal`을 더했다.
     위험은 `localhost`와 같은 결이다 — 덮어쓰기는 관리자만 하고, 그 이름은 실행기가 도는 기계의 docker 호스트만
     가리킨다. 실행기를 호스트 프로세스로 띄우면 여전히 `localhost`다. 정의를 올렸으므로 패키지(정의 해시를
     고정한다)도 다시 내보내 배포한다. ← 틀렸다: Studio 내보내기는 해시를 적지 않는다(아래).
   * **후속(2026-10-27) — 그림이 외부 확장을 선언한다.** Studio로 내보낸 패키지가 실행기에서 「서비스 앱 주소를 모른다:
     nowview-sc01」로 첫 호출(`screen_source`)에 실패했다. Studio는 `chk:process.extensions`에 적힌 확장만 `requires.
     extensions`로 옮기고, 실행기는 거기 있는 확장만 Center에서 정의를 받는다 — 우리 그림에 그 칸이 없었다. 임시 Center
     실측은 매니페스트를 손으로 지으며 그 칸을 채워 드러나지 않았다(시험의 빈틈). 두 그림에 `{"id": "nowview-sc01",
     "version": ">=0.7.1,<1"}`을 적었다. 해시는 고정하지 않는다(정의를 올릴 때마다 그림·패키지를 다시 만들지 않게).
5. **R1·R4 반영 — 했다** (Chaeksas `8f0b08d`, wrapper755/Chaeksas#183 · ADR-0096·0097, 정의 0.6.0).
   * **R1 답한 사람.** `chaeksas-core`를 `8f0b08d`로 올렸다. 결재 8개(`Confirm_Calc` 포함)마다
     `answered_by_as`·`answered_via_as`(예: `확인자`·`확인경로`)를 두고, 뒤의 기록 작업과 계산(`compare`)
     입력에 `answered_by`·`answered_via`로 싣는다. 내장 실행도 같은 변수를 탄다(`engine.answer(answered_by=
     행위자)`) — 길이 하나다. 감사 이력에는 대리 답이면 그 키 이름(`answered_via`)을 사람과 따로 남긴다.
   * **마스터 밖의 이름은 422로 거절하지 않고 그 이름 그대로 적는다**(`outside_master`). 근거:
     ① 콘솔 답의 관리자 계정 이름, Studio 케이스 기본값 「시험 케이스」는 **정상 경로에서 온다** — 고장이
     아니다. ② 「담당자만 답한다」는 Center가 이미 막았고(ADR-0081), 이름은 키(N6)로 인증된 호출이 싣고
     온다 — NowView가 다시 막을 근거가 약하다. ③ 거절하면 오류 경계(N1)가 같은 결재로 되돌리는데, **답한
     사람은 자기 이름을 고칠 길이 없다** — 같은 결재가 영영 기록되지 않는 고리가 된다. 대신 업무의 담당자는
     답한 사람이 아니라 **배정 기록이 고른 사람**으로 둔다 — 콘솔 관리자를 담당자로 두면 인계 조건(담당자가
     있는 업무의 최신 run 확인)이 깨진다(실측: `hand_off` 409로 고쳤다).
   * **짐작(`guessed`)은 옛 정의(0.5.0 이하) 호환으로만 남긴다.** 본문에 `answered_by`가 없던 판으로 고정된
     Bot이 남아 있을 수 있다 — 그 판을 422로 끊을 이유가 없고 코드는 몇 줄이다. 그런 Bot이 없어지면 지운다.
   * **R4 정의 한 벌.** `nowview-sc01.local.extension.json`을 지웠다. 정의는 `base_url: https://www.nowview.work`,
     `allowed_hosts: [www.nowview.work, localhost]`(0.7.1에서 `host.docker.internal`을 더했다 — 아래 N5 후속),
     `allow_private_network: true`이고, **로컬 Center만**
     CON-07 「서버 주소」(`PUT /api/v1/resources/extensions/nowview-sc01/address {"base_url":
     "http://localhost:3000"}`)로 덮어쓴다. 운영 Center는 손대지 않는다.
     * 득: 해시가 하나라 고정한 Bot이 두 환경에서 같이 돈다(로컬에서 시험한 그 판이 운영에 간다). 작업 정의를
       두 파일에 맞춰 적는 일이 사라진다 — N1·N3·N6마다 두 파일을 같이 고쳐야 했고, 어긋나면 한쪽 환경에서만
       실행 중에 멈춘다. 이제 `test_extension_definition_matches_the_bpmn_service_calls`가 정의 ↔ BPMN을 잠근다.
     * 실: 운영 정의에서 사설망 허용이 켜진다. 덮어쓰기는 **관리자만** 하고 호스트는 `localhost` **정확히**
       하나로 묶인다(실측: `127.0.0.1`·다른 호스트는 어댑터가 「허용 호스트 밖」으로 거절). 남는 위험은
       ⓐ 운영 Center 관리자가 주소를 `localhost`로 잘못 바꾸면 **그 실행기가 도는 기계 자신**을 부른다 —
       실행기가 NowView 운영 서버에서 돈다면 그 서버의 3000은 Chaeksa라 운영 키가 다른 앱으로 간다. ⓑ `www.nowview.work`의 DNS가 사설 IP를 돌려줘도 막히지
       않는다(우리 Cloudflare DNS다). 둘 다 관리자·DNS 권한이 있어야 생기는 일이라 받아들였다.
   * **실측.** Chaeksas 엔진 + `AdapterCaller` + 이 정의(주소만 `http://localhost:3010`으로 덮어쓰기, 시험용 키)
     로 Studio 데모 실행을 돌려 **인계(`HANDED_OFF`)까지** 갔다. 어댑터는 `[::1]:3010`을 불렀다. 답한 사람
     8건이 짐작 없이 적혔다 — 담당자 6건은 사용자 id, 대리 답 1건은 `answered_via`, 콘솔 관리자 1건은
     `outside_master`. **재지 못한 것**: 진짜 Center에서 「서버 주소」를 바꾸는 단계(이 실측은 Center가 내려 줄
     주소를 `Addresses`로 직접 줬다).
   * Center에 다시 올릴 것: 정의 0.6.0 서명·등록, 로컬 Center에서만 주소 덮어쓰기.

Chaeksas 요청(R1~R6)은 1과 동시에 보냈다. R1·R4는 5에서 반영했다.
