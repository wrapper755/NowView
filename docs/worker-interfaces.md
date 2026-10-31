# NowView 일꾼 · 회사 시스템 · 대시보드 — 인터페이스

지금 구조만 적는다. Center 등록 절차와 실행 중 동작은 [chaeksas-integration.md](chaeksas-integration.md)에 있다.
지금 회사 이름으로 옮긴 업무는 장면 1(고객 생산계획 변경 대응)뿐이다 — 장면 2~6은 옮길 때마다 이 문서에 더한다.

## 1. NowView가 하는 일

* **NowView는 회사 사이트가 아니다.** 두 가지다.
  * **일꾼** — Center에 올린 회사별 BPM 프로세스의 서비스 태스크(일감)를 가져가 수행한다.
  * **대시보드** — N개 회사의 운영 현황을 그 회사의 BPM 진행 위에서 보여 준다.
* **일꾼은 BPM 프로세스와 회사 시스템을 잇는다.** 회사의 자료와 확정 기록은 회사 시스템에 있고, NowView는 그것을 읽어 계산하고
  결정을 돌려 적는다.
* **규칙 계산은 NowView 몫이다.** 전망 비교·지표·위험 판정·Agent 초안·경영 이슈·업무는 INNONOW 방법론이고 회사가 바뀌어도 같은
  규칙을 쓴다. 회사 시스템은 자료와 확정 기록의 원본(system of record)이다.
* **NowView는 고정 프로그램이다.** 일꾼이 제공하는 작업은 확장 `nowview` 하나에 모여 있고 NowView 판과 함께 바뀐다. 회사나 업무마다
  확장을 만들지 않는다. 어느 회사의 어느 BPM 프로세스를 맡는지는 **설정**이다(§5).
* **연결은 늘 NowView에서 나간다.** Center는 일감을 쌓아 두고, 회사 시스템은 받은 원천을 수신함에 쌓아 둔다. 어느 쪽도 NowView
  주소·키를 모른다.

## 2. 구성요소

```
            ① 일감(C15 Pull)                       ② 회사 시스템 API(REST)
Center ◀──────────────────────▶ NowView 엔진 ─────────────────────────────▶ 회사 시스템
(BPM 프로세스·결재)   가져가기·끝내기   (일꾼 · 규칙 계산 · 경영 기록 · 설정)   읽기·쓰기          (가상 자동차 부품사 시뮬레이터)
      ▲                                     ▲
      │ 기동·대리 답·진행 읽기                │ ③ 공개 API · 관리 API(BFF 경유)
      └──────────── NowView 엔진 ────────────┘◀──────────── NowView 웹(회사별 운영 현황 · /admin)
```

| 구성요소 | 가진 것 | 하지 않는 것 |
|---|---|---|
| **Center**(Chaeksas) | 업무 순서·분기·사람 결재·실행 이력 | 숫자 계산, 회사 자료 보관 |
| **NowView 엔진** | 일꾼, 규칙 계산(R01), 계산 run·지표·위험, 검토 전망, 경영 이슈·업무·알림, Agent 초안, 감사 이력, 설정 | 회사 자료·확정 기록의 원본 |
| **회사 시스템** | 조직·사용자, 고객·공장·모델, 목표·승인 전망·실적·원가·고정비, 고객 생산계획 수신함, 원천 확인 상태 | 규칙 계산, BPM |
| **NowView 웹** | 회사 목록, 회사별 운영 현황(장면 화면), 관리자 모드 `/admin` | 회사 시스템·Center를 직접 부르지 않는다(엔진만) |

## 3. 자료의 주인 (장면 1)

| 자료 | 주인 | 어디서 |
|---|---|---|
| 사용자·역할(영업담당 이도윤 …) | 회사 | 회사 시스템 `GET /company/org/users` — 엔진은 아직 자기 명단(`domain.USERS`)을 쓴다(§7) |
| 고객·공장·모델 | 회사 | 회사 시스템 `GET /company/master` |
| 목표 T01 · 승인 전망 F01 · 실적·컷오프 | 회사 | 회사 시스템 `GET /company/plans/{version}`·`/company/actuals` |
| 단가·변동비 C01 · 고정비 FC01 | 회사 | 회사 시스템 `GET /company/costs/C01`·`/company/fixed-costs/FC01` |
| 고객 생산계획 원천 | 회사 | 기준 원천 CP01은 `GET /company/customer-plans/CP01`, 이후 원천은 세계 수신함 — NowView 문서에 사본 |
| 원천 확인 상태(VERIFIED·NEEDS_INFO) | 회사 | NowView가 결정 때 회사에 적는다(`POST …/status`) |
| 규칙(임계값 R01) | NowView | 엔진 엑셀(`engine/seed`, `load_rules`) |
| 검토 전망 F02 · 계산 run · 지표·위험 | NowView | 데모 실행 문서 — 계산 run은 읽은 회사 자료의 버전 id(`versions`)를 남긴다 |
| 경영 이슈·업무·알림·Agent 초안·감사 | NowView | 데모 실행 문서 |
| 시연 시각(가상시계) | NowView | 데모 실행 문서 — 시계를 옮기거나 원천을 받을 때 회사 세계 시각을 같은 값으로 맞춘다 |

검토 전망 F02는 장면 1에서 승인되지 않는다(`UNDER_REVIEW`) — 회사 시스템에 쓰지 않는다.

## 4. 경계별 인터페이스

### 4.1 ① BPM ↔ 일꾼 — 일감 (토픽 `nowview`)

* **확장 정의** `chaeksas/nowview.extension.json`의 작업·입출력 스키마가 계약이다. 일꾼은 이것으로 Center에 manifest를 올리고, Center는
  일감의 작업을 대조하고 출력 필수 칸을 막는다.
  * 외부 확장 계약(C13)이 HTTP 어댑터 모양이라 주소(`allowed_hosts`)와 작업마다 요청(`request`)이 필수 칸이다. NowView 일꾼만 부르므로
    자리만 채웠다(운영계 주소, `path: "/"`, 키 없음) — 범용 어댑터 일꾼으로는 부를 수 없다.
* **회사·업무는 일감을 보낸 BPM 프로세스 id로 찾는다**(`caller.bpm_process_id` → 설정의 매핑). 일감 입력에 회사를 싣지 않는다.
* **실행 위치는 일감의 `origin`**(`run` = Center 서버 실행, `test` = Studio)이고, 데모 실행은 입력 `demo_run_id`(= 회사 세계 id),
  바깥 실행은 멱등 칸의 `run_id`로 묶는다.

장면 1 작업:

| 작업 | 하는 일 | 회사 시스템 호출(②) |
|---|---|---|
| `validate_customer_plan` | 원천 자동 검증(UI03-01) | — (원천은 수신 때 들였다) |
| `screen_customer_plan` | 접수 Bot의 검증 + 직전 원천 대비 변경 요약 | — |
| `record_intake_decision` | 접수 일괄 승인·반려 기록 | 반려면 원천 상태 NEEDS_INFO |
| `record_plan_review` | 원천 확인 결정 기록 | 원천 상태 VERIFIED·NEEDS_INFO |
| `assess_supply_risk` | 검토 전망 생성 · 15행 지표 · 위험 판정 · 이슈 잇기 | T01·F01·실적·C01·FC01 읽기(불변 버전 — 한 번 읽어 둔다) |
| `request_review_draft` | Agent 검토 초안 요청(기다리지 않음) | — |
| `record_risk_review` | 영업 검토 의견·근거 기록 | — |
| `assign_follow_up` | 현업(생산·자재, `Approve_Dispatch`) 또는 경영관리(`Approve_Review`) 배정 — 담당자 이름을 돌려준다 | — |
| `record_acceptance` | 인수 기록 | — |
| `hand_off_case` | 인계 조건 확인 · 인계 기록 | — |

**실패** — 업무 규칙 위반은 `forbidden`·`not_found`·`conflict`·`input_invalid`(재시도 없음, 글은 사유). 회사 시스템이 응답하지 않으면
`dependency_down`(재시도) — 엔진 안에서는 `CompanyUnavailable`(503)이고 그 조작은 저장되지 않는다. 설정에 없는 BPM 프로세스의 일감은
`not_found`.

### 4.2 ② 일꾼 ↔ 회사 시스템 — 회사 시스템 API

가상 자동차 부품사의 회사 시스템은 별도 리포 autopart1의 기간계다(`legacy/`, :8191 — `../autopart1`에서 `scripts/stack.sh start`). 엔진 시험은 같은 계약의 쌍둥이(`engine/tests/company_twin/`)를 쓴다. NowView 엔진만 부른다 — 주소는 설정, 키는 엔진 환경
(`COMPANY_AUTOPART1_KEY`, Bearer). JSON, 금액은 문자열 DECIMAL, 수량 누락은 `null`(0과 다르다).

**세계(world)** — 시연은 같은 회사를 여러 번 처음부터 돌린다. 회사 시스템은 세계마다 **변하는 기록**(수신함·원천 상태·시각)을 따로
가진다. 세계 id = NowView 데모 실행 id다 — 데모 실행을 만들 때 세계도 만들고, 초기화하면 세계도 처음으로 돌린다. **불변 기록**
(조직·마스터·버전별 계획·실적·원가)은 세계와 무관하다.

읽기:

```
GET  /company/org/users                             → [{user_id, name, role}]
GET  /company/master                                → {customers, plants, models}
GET  /company/versions                              → T01 · CP01 · F01 · C01
GET  /company/plans/{version}                       → {version, rows:[{customer_id, plant_id, model_id, period, quantity}]}   T01 · F01
GET  /company/actuals                               → {rows:[{…, quantity, cutoff_date}]}
GET  /company/costs/{version}                       → {rows:[{…, unit_price, unit_variable_cost, unit_cm}]}   C01
GET  /company/fixed-costs/{version}                 → {rows:[{plant_id, period, total_fixed}]}   FC01
GET  /company/customer-plans/CP01                   → 기준 시점에 이미 확인한 원천(변경 비교의 직전 원천)
GET  /worlds/{w}/customer-plans/inbox?after=        → 받은 원천 [{doc_id, seq, fixture_id, customer_plan_id, received_at, corrects, status}]
GET  /worlds/{w}/customer-plans/{doc_id}            → {…, rows:[…]}
GET  /worlds/{w}/clock                              → 세계 시각
```

쓰기(회사 확정 기록):

```
POST /worlds/{w}/customer-plans/{doc_id}/status     {status: VERIFIED|NEEDS_INFO, by, opinion, evidence, ref}
                                                     ref가 같으면 다시 적지 않는다(멱등). 같은 ref·다른 결정은 409
```

NowView는 이 쓰기를 **데모 실행 문서를 저장하기 직전에** 한다 — 회사가 받지 못하면 그 조작 전체가 저장되지 않는다.

시뮬레이터 조작(시연 전용 — 실제 회사 시스템에는 없다):

```
POST /worlds                                        {world_id}       → 세계를 만든다(이미 있으면 그대로), 시각 S0 = 2027-06-15 18:00
POST /worlds/{w}/clock                              {at}
POST /worlds/{w}/sim/customer-plans                 {fixture_id}     → 고객이 원천을 보냈다(CP02 · CP03 · EX01·02·04·05)
POST /worlds/{w}/reset                              → 세계를 S0로
```

**원천 도착** — 플레이어의 「수신」이 회사 시스템에 고객 원천을 보내고(`sim/customer-plans`), 엔진이 같은 조작 안에서 그 원천을 읽어
데모 실행 문서에 사본으로 들인 뒤 Center에서 업무를 시작한다. 회사에 따로 들어온 원천을 엔진이 찾아 들이는 수신함 폴링은 없다.

### 4.3 ③ 웹 ↔ 엔진

* **공개** — 장면 화면 API(`/api/engine/sc01`~`sc06/…`)와 회사 목록 `GET /api/engine/companies`(`{id, name, description, scenes}` —
  이름·설명·업무 번호뿐). BPM 프로세스 id·토픽·회사 시스템 주소·일꾼 상태는 공개하지 않는다.
* **관리** — `/admin` 화면이 로그인 뒤 `/api/admin/*`를 부르고, 웹 서버가 세션을 확인한 뒤 엔진 `/admin/*`에 관리 키(`X-Admin-Key`)를
  실어 보낸다. 엔진 관리 API:

```
GET  /admin/status    → 일꾼(상태·토픽·요청 코드·최근 일감) · Center 연결 · 회사 시스템 연결 · 재시작 필요 여부
GET  /admin/config    → 설정 · 업무 번호 목록 · 고정 확장의 작업 목록(읽기만)
PUT  /admin/config    → 설정 저장(검사 실패 422 + 사유)
```

## 5. 설정

엔진 DB(`nowview_config`)에 한 벌 있고 관리자 모드에서만 고친다. 키·비밀번호는 설정에 두지 않는다(환경 파일).

```json
{
  "companies": [{"id": "autopart1", "name": "가상 자동차 부품사", "description": "…", "system_url": "http://localhost:8191"}],
  "processes": [
    {"bpm_process_id": "autopart1.sc01",        "company": "autopart1", "scene": 1},
    {"bpm_process_id": "autopart1.sc01-intake", "company": "autopart1", "scene": 1},
    {"bpm_process_id": "autopart1.sc02",          "company": "autopart1", "scene": 2}
  ],
  "topics": ["nowview", "nowview-sc02", "nowview-sc03", "nowview-sc04", "nowview-sc05", "nowview-sc06"]
}
```

* 처음 뜰 때 설정이 없으면 이 모양의 기본값을 적는다(장면 2~6은 옮기기 전 이름 `nowview.sc0N`·토픽 `nowview-sc0N`).
* 검사: 회사 id·BPM 프로세스·토픽이 겹치지 않을 것, 매핑의 회사가 있을 것, 업무 번호가 NowView에 있는 것(1~6)일 것, NowView에 업무
  코드가 있는 회사일 것.
* 매핑·회사 시스템 주소는 저장하면 바로 쓰인다. 토픽은 엔진을 다시 띄워야 한다(일꾼이 들이기 때 Center에 알린다).

## 6. 장면 1 한 바퀴

```
1 플레이어 「CP02 수신」 ─▶ 엔진 ─▶ 회사 POST /worlds/{w}/sim/customer-plans ─▶ GET 원천 ─▶ 문서에 사본
2 엔진 ─▶ Center: 접수 Bot 메시지 시작(autopart1.sc01-intake)
3 일감 screen_customer_plan ─▶ 일꾼 ─▶ 검증·변경 요약 ─▶ complete
4 감독자 일괄 승인(대리 답) ─▶ 일감 record_intake_decision ─▶ 위임: autopart1.sc01 시작
5 일감 validate_customer_plan ─▶ 검증
6 영업담당 확인(결재) ─▶ 일감 record_plan_review ─▶ 회사 POST status VERIFIED
7 계산 확인(결재) ─▶ 일감 assess_supply_risk ─▶ 회사 자료(T01·F01·실적·C01·FC01) ─▶ 계산 run·F02·이슈
8 일감 request_review_draft ─▶ Agent 초안(배경)
9 영업팀장 검토 ─▶ record_risk_review ─▶ assign_follow_up(생산·자재 ∥ 경영관리) ─▶ 인수 ×3 ─▶ hand_off_case
```

## 7. 아직 아닌 것

* 엔진이 회사 시스템의 사용자 명단을 읽지 않는다 — 기간계가 사원 명단을 내지만 엔진은 `domain.USERS`를
  쓴다. 장면 2~6도 쓰고 있어 업무를 옮길 때 함께 바꾼다. 결재 담당자 이름(BPMN `assignees`)은 Center 계정과 사람이 맞춘다.
* 장면 2~6이 회사 시스템에 쓸 기록(원가 버전·실행과제·예산·공식 전망 게시)은 그 업무를 옮길 때 정한다.
* 회사 시스템이 죽으면 업무가 멈추고 일감은 재시도로 돌아간다. 공개 대시보드에는 「회사 시스템 연결 안 됨」 표시가 아직 없다(관리자
  화면에만 있다).
