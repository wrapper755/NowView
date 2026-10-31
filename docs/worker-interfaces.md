# NowView 일꾼 · 회사 시스템 · 대시보드 — 인터페이스 (초안, 장면 1)

> 상태: **확정 · 장면 1 구현됨**(2026-10-31 사용자 「초안대로 진행」 — 열린 질문은 제안대로). 회사 시스템 시뮬레이터
> `company-sim/`, 엔진의 회사 클라이언트 `engine/app/company.py`, 장면 1 작업 이름 변경까지 했다. 남은 것은 §6.
> 장면 2~6은 장면 1이 끝난 뒤 같은 틀로 하나씩 옮긴다.

## 0. 정한 것 (2026-10-31 사용자 결정)

* **NowView는 회사 사이트가 아니다.** ① Center에 올린 회사별 BPM 프로세스의 서비스 태스크를 수행하는 **일꾼**, ② N개 회사의
  **운영 현황 대시보드**다. 가상 자동차 부품사(가칭 `autoparts`)는 그 회사 중 하나다.
* **일꾼은 BPM 프로세스 ↔ 회사 시스템 사이의 중계자다.** 회사의 자료와 확정 기록은 회사 시스템에 있고, NowView는 그것을 읽고
  돌려 적는다.
* **규칙 계산은 NowView 몫이다.** 전망 비교·지표·위험 판정·Agent 초안·업무·이슈 관리는 INNONOW 방법론이고 회사가 바뀌어도 같은
  규칙을 쓴다. 회사 시스템은 자료와 확정 기록을 가진다(system of record).
* **가상 회사 시스템은 별도 서버로 돈다.** 엔진 안 어댑터로 시작하지 않는다.

## 0.1 NowView는 고정 패키지다 (2026-10-31 사용자 결정 — 아래 §3.1·§6을 이 결정으로 바꾼다)

* **NowView는 BPM 패키지와 함께 배포되는 고정 프로그램이다.** 일꾼이 제공하는 작업 목록(확장 정의)은 **NowView 판마다 하나**다 —
  확장·토픽 `nowview`. 회사나 장면마다 확장을 만들지 않는다(예전 `nowview-sc02`~`sc06`, 이번의 `autoparts-sc01`을 이것으로 합친다).
  작업 이름은 NowView 전체에서 겹치지 않는 업무 언어다.
* **회사는 BPM 패키지가 정한다.** 회사가 자기 BPM 프로세스(`autoparts.sc01` …)를 만들어 `nowview` 작업을 부른다. 일꾼은 일감에
  실려 오는 **보낸 BPM 프로세스 id**(`caller.bpm_process_id`)로 설정의 「BPM 프로세스 → 회사·업무」 표를 찾아 그 회사 시스템으로
  간다 — 일감 입력에 회사를 싣지 않는다.
* **등록은 설정이다 — 화면·API로 드러내지 않는다.** 회사·회사 시스템 연결·BPM 프로세스 매핑·일꾼 토픽·들이기 상태(요청 코드)는
  공개 대시보드와 공개 API에 나오지 않는다. 공개 대시보드는 회사·업무의 운영 현황만 보인다. 걷어낼 것: `/worker` 화면·
  `/api/engine/worker`, `/companies`의 패키지·토픽·회사 시스템 주소, 회사 운영 현황 화면의 패키지·토픽.
* **바꾸는 일은 NowView 관리자 모드에서 한다** — `/admin`, 관리자 로그인 뒤에만 열리고 공개 화면에는 링크도 두지 않는다. 일꾼 상태·
  요청 코드, 토픽, BPM 프로세스 변경(업무 변경)에 따른 매핑 수정을 여기서 한다.
* **설정은 엔진 DB에 둔다.** 코드를 다시 올려도 설정이 남는다. 키·비밀번호 같은 비밀은 계속 환경 파일(`.env.local`·
  `/etc/nowview.env`)에만 둔다.

이 결정으로 바뀐 것(2026-10-31 구현 — Q6·Q7은 제안대로):

| 지금 | 바뀐 뒤 |
|---|---|
| 확장·토픽 `autoparts-sc01`(장면 1), `nowview-sc02`~`sc06` | 확장·토픽 `nowview` 하나, 판 = NowView 판 |
| 회사 = 토픽(`companies.py` 코드 등록부, `lib/companies.ts` 사본) | 회사 = 설정(엔진 DB) — BPM 프로세스 id로 찾는다 |
| 일꾼이 토픽 → 장면 | 일꾼이 BPM 프로세스 id → 회사·장면, 작업 이름 → 처리기 |
| `/worker`·`/companies` 공개 | `/admin`(로그인) 안으로 |
| 회사 화면 경로를 빌드 때 등록부로 만든다(정적) | 회사가 설정이라 빌드 때 모른다 — 회사 화면은 경로를 런타임에 받는다(아래 Q6) |

새 열린 질문:

* **Q6 회사 화면** — 회사가 DB 설정이라 빌드가 회사를 모른다. `/c/[company]`는 서버에서 엔진을 묻지 않고(엔진이 꺼져도 틀은
  뜬다), 회사 이름·없는 회사 판정은 클라이언트가 공개 목록(`/api/engine/companies`)으로 한다.
* **Q7 관리자 로그인** — 비밀번호 `NOWVIEW_ADMIN_PASSWORD`, 쿠키 서명 `NOWVIEW_ADMIN_SECRET`(웹 환경), 엔진 관리 API 키
  `NOWVIEW_ADMIN_KEY`(웹·엔진 같은 값). 로그인(`POST /api/admin/login`)이 8시간짜리 서명 쿠키를 주고, `/api/admin/*`만 엔진
  `/admin/*`(`X-Admin-Key`)로 중계한다. 공개 BFF는 `/admin`을 중계하지 않는다. 셋 중 하나라도 없으면 관리자 모드는 꺼져 있다.
  틀린 비밀번호는 0.8초 늦출 뿐 횟수 제한은 아직 없다.

**구현 위치** — 엔진: `app/config.py`(설정 모델·`nowview_config` 테이블·기본값) · `app/companies.py`(`Settings`, 공개
`GET /companies`, `/admin/status`·`GET|PUT /admin/config`) · `app/consumer.py`(`routed_by` — 보낸 BPM 프로세스 id → 업무).
웹: `app/admin/page.tsx` · `components/admin/`(상태·설정 JSON 편집) · `app/api/admin/`(로그인·세션·중계) · `lib/admin-session.ts`.
확장: `chaeksas/nowview.extension.json` 0.1.0(장면 1 작업). 설정 편집은 JSON 한 벌을 고치는 모양이다(검사는 엔진이 한다).

## 1. 구성요소와 경계

```
            ① C15 일감(Pull)                       ② 회사 시스템 API(REST)
Center ◀──────────────────────▶ NowView 엔진 ─────────────────────────────▶ 가상 회사 시스템
(BPM 프로세스·결재)   가져가기·끝내기   (일꾼 + 규칙 계산 + 경영 기록)   읽기·쓰기·받은 원천 묻기      (autoparts-sim, 별도 서버)
      ▲                                     ▲
      │ N3: 기동·대리 답·진행 읽기            │ ③ 대시보드 API(BFF 경유)
      └──────────── NowView 엔진 ────────────┘◀──────────── NowView 웹(회사별 운영 현황)
```

| 구성요소 | 가진 것 | 하지 않는 것 |
|---|---|---|
| **Center**(Chaeksas) | 업무 순서·분기·사람 결재·실행 이력 | 숫자 계산, 회사 자료 보관 |
| **NowView 엔진** | 일꾼(C15), 규칙 계산(R01), 계산 run·지표·위험, 검토 전망, 경영 이슈·업무·알림, Agent 초안, 감사 이력, Center 연동(N3) | 회사 마스터·계획·실적·원가의 원본 보관, 회사 확정 기록의 원본 |
| **가상 회사 시스템** | 조직·사용자, 고객·공장·모델, 목표·승인 전망·실적·원가·고정비, 고객 생산계획 수신함, 회사 확정 기록(원천 확인 상태 등), 시연용 세계 시각 | 규칙 계산·위험 판정, BPM |
| **NowView 웹** | 회사 목록, 회사별 운영 현황, 일꾼 화면 | 회사 시스템·Center를 직접 부르지 않는다(엔진만) |

**연결 방향은 늘 NowView에서 나간다.** Center도 회사 시스템도 NowView 주소를 모른다 — Center는 일감을 쌓아 두고(C15), 회사
시스템은 받은 원천을 수신함에 쌓아 둔다(NowView가 묻는다, §3.3). 회사 시스템에 NowView 웹훅을 두지 않는 것은 C15와 같은 이유다
(회사 쪽에 우리 주소·키를 맡기지 않는다).

## 2. 자료의 주인 (장면 1)

| 자료 | 주인 | 지금 위치 | 옮길 곳 |
|---|---|---|---|
| 사용자·역할(영업담당 이도윤 …) | 회사 | `domain.USERS` | 회사 시스템 `GET /company/org/users`(엔진은 아직 `domain.USERS`, §6) |
| 고객·공장·모델 | 회사 | 시드 | 회사 시스템 마스터 |
| 목표 T01 · 승인 전망 F01 · 실적·컷오프 | 회사 | 시드(`plans`·`actuals`) | 회사 시스템 `GET /plans/{version}`·`/actuals` |
| 단가·변동비 C01 · 고정비 FC01 | 회사 | 시드(`costs`·`fixed_costs`) | 회사 시스템 `GET /costs/{version}` |
| 고객 생산계획 원천(CP01·CP02·정정본) | 회사 | 시드 + `domain.FIXTURES`, 문서 `sources` | 회사 시스템 수신함 |
| 원천 확인 상태(VERIFIED·NEEDS_INFO) | 회사 | 문서 `sources[].status` | 회사 시스템에 돌려 적는다 + NowView는 사본 |
| 규칙(임계값 R01) | NowView | 시드 `rules` | NowView(회사별 설정으로 남긴다) |
| 검토 전망 F02 · 계산 run · 지표·위험 | NowView | 문서 | 그대로 — 계산 run이 쓴 회사 자료의 **버전 id**를 남긴다(지금도 `versions`) |
| 경영 이슈·업무·알림·Agent 초안·감사 | NowView | 문서 | 그대로 |
| 시연 세계 시각(가상시계) | NowView가 정하고 회사에 맞춘다 | 문서 `clock` | 그대로 — 시계를 옮기거나 원천을 받을 때 회사 세계 시각을 같은 값으로 맞춘다(`POST /worlds/{w}/clock`). 장면 2~6이 문서 시각을 쓰고 있어 주인을 옮기지 않았다 |

검토 전망 F02는 장면 1에서 승인되지 않는다(`UNDER_REVIEW`) — 회사 시스템에 쓰지 않는다. 공식 전망 갱신(장면 5 FC51)부터
회사 시스템 쓰기가 생긴다.

## 3. 경계별 인터페이스

### 3.1 ① BPM ↔ 일꾼 — C15 일감 (토픽 `nowview`, §0.1)

형식은 그대로다(확장 정의의 작업·입출력 스키마, 실행 위치 = `origin`, 바깥 실행 = 멱등 칸 `run_id`). 바꿀 것은 **작업 목록**이다 —
지금 이름은 NowView 내부 함수를 비춘다(`record_dispatch`). 어댑터 템플릿 때문에 갈라 둔 작업(선택 입력을 못 넣어서
`record_dispatch`·`record_review_request`로 나눴다)도 C15에서는 합칠 수 있다.

| 지금 | 제안 | 하는 일 | 회사 시스템 호출(②) |
|---|---|---|---|
| `validate_source` | `validate_customer_plan` | 원천 자동 검증(UI03-01) | 수신함 원천 읽기 |
| `screen_source` | `screen_customer_plan` | 접수 Bot의 검증 + 변경 요약(N5) | 수신함 원천 + 직전 원천 읽기 |
| `record_intake_review` | `record_intake_decision` | 접수 일괄 승인·반려 | 반려면 원천 상태 NEEDS_INFO 쓰기 |
| `record_dq_review` | `record_plan_review` | 원천 확인 결정 | 원천 상태 VERIFIED·NEEDS_INFO 쓰기 |
| `compare` | `assess_supply_risk` | 검토 전망 생성 · 15행 지표 · 위험 판정 · 이슈 잇기 | T01·F01·실적·C01·FC01 읽기(버전 고정) |
| `request_agent_draft` | `request_review_draft` | Agent 검토 초안 요청(기다리지 않음) | 없음 |
| `record_sales_review` | `record_risk_review` | 영업 검토 의견·근거 | 없음 |
| `record_dispatch` + `record_review_request` | `assign_follow_up` | 현업(생산·자재)·경영관리 배정 — 담당자 이름을 돌려준다 | 사용자·역할 읽기 |
| `record_acceptance` | `record_acceptance` | 인수 | 없음 |
| `hand_off` | `hand_off_case` | 인계 조건 확인 · 인계 기록 | 없음 |

**공통 입력** — 지금은 `demo_run_id`가 일감과 NowView 문서를 잇는다. 회사 시스템이 따로 서면 같은 키가 회사 쪽 「세계」
(§3.2)도 가리켜야 한다. 제안: 입력 이름을 `case_ref`로 바꾸고 값은 지금의 데모 실행 id 그대로 — NowView 문서 = 회사 세계 하나
(아래 열린 질문 Q1).

**실패 코드** — 지금과 같다(`forbidden`·`not_found`·`conflict`·`input_invalid`, `retryable: false`, 글은 업무 규칙의 사유).
더한 것: 회사 시스템이 응답하지 않으면 `fail {code: "dependency_down", retryable: true}`(C15의 재시도 코드) — 업무 규칙
위반이 아니라 Center가 다시 내줄 일이다. 엔진에서는 `CompanyUnavailable`(503)이고, 그 조작은 저장되지 않는다.

**확장 정의** — 외부 확장의 계약(C13)은 HTTP 어댑터 모양이라 주소(`allowed_hosts`)와 작업마다 요청(`request`)이 필수 칸이다.
C15 일꾼만 부르므로 자리만 채웠다(운영계 주소, `path: "/"`, 키 없음) — 범용 어댑터 일꾼으로 부를 길은 열지 않는다. 쓰는
것은 작업 목록·입출력 스키마(일꾼이 Center에 올리는 manifest)다. `assign_follow_up`은 두 결재(현업 배정·Review 요청)를
받는다 — 입력 `node_id`로 가르고 `prod`·`mat`·`fin`은 선택이다.

**공통 입력은 `demo_run_id` 그대로 두었다**(제안한 `case_ref`로 바꾸지 않았다) — 값이 곧 회사 세계 id다.

### 3.2 ② 일꾼 ↔ 회사 시스템 — 회사 시스템 API

가상 회사 시스템(`autoparts-sim`)은 별도 서버다. NowView 엔진만 부른다(키는 엔진만 쥔다 — `COMPANY_AUTOPARTS_URL`,
`COMPANY_AUTOPARTS_KEY`). JSON, 금액은 문자열 DECIMAL(엔진 규칙 그대로), 수량 누락은 `null`(0과 다르다, G13).

**세계(world)** — 시연은 같은 회사를 여러 번 처음부터 돌린다. 회사 시스템은 세계마다 **변하는 기록**(수신함·원천 상태·
시각)을 따로 가진다(지금 데모 실행끼리 서로 보지 않는 것과 같다, DATA-05). `world_id` = NowView 데모 실행 id다(Q1).
**불변 기록**(조직·마스터·버전별 계획·실적·원가)은 세계와 무관하다 — 버전은 지워지지 않으므로 엔진이 한 번 읽어 둔다.
엑셀 원천의 F02(NowView가 계산할 검토 전망 — 기대값)·R01-v1(NowView 규칙)·CP02(나중에 도착할 원천)는 회사 기록이 아니라 내보내지
않는다.

읽기:

```
GET  /company/org/users                             → [{user_id, name, role}]
GET  /company/master                                → {customers, plants, models}
GET  /company/versions                              → T01 · CP01 · F01 · C01 (버전기준 행)
GET  /company/plans/{version}                       → {version, rows:[{customer_id,plant_id,model_id,period,quantity}]}  T01 · F01
GET  /company/actuals                               → {rows:[{…, quantity, cutoff_date}]}
GET  /company/costs/{version}                       → C01 {rows:[{…, unit_price, unit_variable_cost, unit_cm}]}  (문자열 DECIMAL)
GET  /company/fixed-costs/{version}                 → FC01 {rows:[{plant_id, period, total_fixed}]}
GET  /company/customer-plans/CP01                   → 기준 시점에 이미 확인한 원천(변경 비교의 직전 원천)
GET  /worlds/{w}/customer-plans/inbox?after=        → 받은 원천 목록 [{doc_id, seq, fixture_id, customer_plan_id, received_at, corrects, status}]
GET  /worlds/{w}/customer-plans/{doc_id}            → {…, rows:[…]}  (엔진의 SourceRow 모양, 누락은 null)
GET  /worlds/{w}/clock                              → 세계 시각
```

쓰기(회사 확정 기록):

```
POST /worlds/{w}/customer-plans/{doc_id}/status     {status: VERIFIED|NEEDS_INFO, by, opinion, evidence, ref}  → 멱등(ref = BPM 실행·노드)
```

시뮬레이터 조작(시연 전용 — 실제 회사 시스템에는 없다, 플레이어가 엔진을 거쳐 부른다):

```
POST /worlds                                         {world_id, seed}         → 기준 적재(S0, 2027-06-15 18:00)
POST /worlds/{w}/clock                               {at}
POST /worlds/{w}/sim/customer-plans                  {fixture_id}             → 고객이 원천을 보냈다(CP02 · 정정본 · EX 변형)
POST /worlds/{w}/reset                               → S0로
```

**계산 run은 읽은 버전을 남긴다** — 지금처럼 `versions: {target: T01, prior: F01, cost: C01, fixed: FC01, rule: R01-v1}`. 회사
자료가 바뀌어도 지난 run의 숫자는 그 버전으로 다시 낼 수 있어야 한다. 회사 시스템은 버전을 지우지 않는다.

### 3.3 원천 도착 → BPM 기동

지금은 화면의 「수신」이 NowView에서 원천을 만들고 Center를 기동한다. 바뀐 흐름:

```
플레이어「CP02 수신」 → 엔진 → 회사 시스템 POST /worlds/{w}/sim/customer-plans (고객이 보냈다)
   → 엔진이 같은 조작 안에서 GET /worlds/{w}/customer-plans/{doc_id} → NowView 문서에 원천 사본 → Center 기동
   접수 가상 직원이 있으면 메시지 시작(고객계획접수), 없으면 POST /jobs — 지금과 같다(N3·N5)
```

**구현은 「보낸 직후 그 원천을 읽어 들인다」까지다.** 수신함 폴링(회사에 따로 들어온 원천을 엔진이 찾아 들이는 것)은 아직
없다 — 지금은 원천이 늘 플레이어를 거쳐 들어오므로 쓸 일이 없었다. 회사가 스스로 원천을 받는 시나리오가 생기면 Center
진행 폴러와 같은 루프에 붙인다(`inbox?after=`).

### 3.4 ③ 대시보드 ← 엔진

웹은 지금처럼 엔진만 부른다(BFF). 엔진이 회사 자료·BPM 진행·NowView 기록을 엮어 준다.

* 회사 목록 `GET /companies` — 회사·장면별 Center 등록(지금 있음) + 회사 시스템 연결 상태(더할 것).
* 회사 운영 현황 `GET /companies/{c}/overview` — 장면별 최근 데모 실행의 상태(진행 중 노드·열린 업무·위험 최고 수준). 더할 것.
* 장면 화면 — 지금의 `/sc01/demo-runs/{id}`·`/dashboard`. 숫자는 계산 run 기준이고, 계산 전 숫자(T01·F01)는 엔진이 회사
  시스템에서 읽어 캐시한 버전이다.
* 일꾼 `GET /worker` — 지금 있음 + 회사 시스템 호출 최근 기록(더할 것).

## 4. 장면 1 한 바퀴 (바뀐 뒤)

```
1 플레이어 CP02 수신 ─▶ 엔진 ─▶ 회사 POST /sim/customer-plans
2 엔진 수신함 폴링 ─▶ 새 원천 ─▶ Center: 접수 Bot 메시지 시작(autoparts.sc01-intake)
3 Center 일감 screen_customer_plan ─▶ 일꾼 ─▶ 회사 GET 원천·직전 원천 ─▶ 요약 complete
4 감독자 일괄 승인(대리 답) ─▶ 일감 record_intake_decision ─▶ 위임: autoparts.sc01 시작
5 일감 validate_customer_plan ─▶ 회사 GET 원천 ─▶ 검증
6 영업담당 확인(결재) ─▶ 일감 record_plan_review ─▶ 회사 POST status VERIFIED
7 계산 확인(결재) ─▶ 일감 assess_supply_risk ─▶ 회사 GET T01·F01·실적·C01·FC01 ─▶ NowView 계산 run·F02·이슈
8 일감 request_review_draft ─▶ NowView Agent(배경)
9 영업팀장 검토 ─▶ record_risk_review ─▶ assign_follow_up(생산·자재 ∥ 경영관리) ─▶ 인수 ×3 ─▶ hand_off_case
```

## 5. 열린 질문

* **Q1 세계 = 데모 실행?** 데모 실행 하나가 회사 세계 하나라면 `case_ref`(= world id)가 일감·NowView 문서·회사 세계를 다 잇는다.
  아니면 회사 세계는 하나이고 데모 실행이 그 안의 「건」이 되는데, 그러면 초기화·병렬 시연이 서로 섞인다. 제안: 세계 = 데모 실행.
* **Q2 사용자·역할의 주인** — 결재 담당자(BPMN `assignees`)는 사람 이름이고 Center 계정과 맞아야 한다. 회사 시스템의 사용자가
  원본이고 NowView는 읽기만 하는 것으로 제안한다. Center 계정은 지금처럼 사람이 맞춘다.
* **Q3 시뮬레이터 구현** — 제안: `company-sim/`(Python · FastAPI · uv, 포트 8091), 원천은 지금 `engine/seed/`의 원천 시트를 옮긴다
  (파생 시트는 엔진 시험의 기대값으로 남는다). 저장은 SQLite(로컬)/Postgres(compose). 운영계에서는 같은 서버의 systemd 유닛 하나 더.
* **Q4 회사 시스템이 늦거나 죽었을 때** — 일감은 `company_unavailable`(재시도)로 돌려주고 업무를 멈춘다. 대시보드는 마지막 캐시를
  「회사 시스템 연결 안 됨」 표시와 함께 보인다.
* **Q5 장면 2~6의 회사 자료** — 원가 버전 등록(장면 2), 실행과제·예산(장면 4·5), 공식 전망 게시(장면 5) 같은 회사 확정 기록이
  늘어난다. 장면 1 인터페이스는 그 쓰기를 미리 정하지 않는다 — 장면을 옮길 때마다 이 문서에 더한다.

## 6. 진행

1. ✔ 회사 시스템 시뮬레이터 `company-sim/`(FastAPI · SQLite 세계 저장소 · 포트 8091 · 키 `AUTOPARTS_SIM_KEY`) — 시험 4개.
2. ✔ 엔진 회사 클라이언트(`app/company.py`) — 회사 자료를 엑셀 대신 회사에서 읽고(규칙만 엔진 엑셀), 원천을 회사 수신함에서
   들이고, 원천 확인 결정을 회사에 돌려 적는다(저장 직전, 실패하면 저장하지 않음). 세계는 데모 실행을 만들 때·초기화할 때
   함께. 수신함 폴링은 하지 않았다(§3.3).
3. ✔ 장면 1 작업 이름 변경(§3.1) — BPMN 둘·엔진. 확장 정의는 §0.1에 따라 `nowview` 0.1.0으로 냈다.
4. ✔ 시험 — 엔진 시험이 시뮬레이터 앱을 같은 프로세스에 띄워 진짜 회사 API를 지난다(`tests/conftest.py`).
5. ✔ §0.1 — 고정 확장 `nowview`, 설정(엔진 DB)·관리자 모드(`/admin`), 공개 화면·API에서 등록 정보를 걷었다.
6. Center 등록 → 일꾼 승인(`engine/.env.local`의 `NOWVIEW_CONSUMER=off` 줄 삭제 → 관리자 모드의 요청 코드) → 장면 1 실행·수정 반복.
7. 사용자·역할을 회사에서 읽기(Q2) — 지금 시뮬레이터가 같은 명단을 내지만(`seed/org.json`) 엔진은 아직 `domain.USERS`를 쓴다
   (장면 2~6도 쓰고 있어 장면을 옮길 때 함께).
