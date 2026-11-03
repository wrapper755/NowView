# NowView 일꾼 · 회사 시스템 · 대시보드 — 인터페이스

지금 구조만 적는다. Center 등록 절차와 실행 중 동작은 [chaeksas-integration.md](chaeksas-integration.md)에 있다.
지금 회사 이름으로 옮긴 업무는 장면 1(고객 생산계획 변경 대응)·장면 2(외주 단가 인상 검토)·장면 3(수익성 통합 분석과 수시
경영검토)·장면 4(수익성 개선 대응안 검토와 실행 승인)·장면 5(결정 실행과 계획 갱신)·장면 6(과제 완료와 성과 실현 검토)·장면 7(실제 경험을 관리모델 개선으로 연결)이다.

## 1. NowView가 하는 일

* **NowView는 회사 사이트가 아니다.** 두 가지다.
  * **워커(Worker, 일꾼)** — Center에 올린 회사별 BPM 프로세스의 서비스 태스크(External Service 일감)를 가져가 수행한다.
  * **대시보드(Dashboard)** — N개 회사의 운영 현황을 그 회사의 BPM 진행 위에서 보여 준다. **NowView의 본체는 대시보드다** — 워커는
    대시보드가 보일 운영 기록을 BPM 진행에서 받아 오는 몫이다.
* **일꾼은 BPM 프로세스와 회사 시스템을 잇는다.** 회사의 자료와 확정 기록은 회사 시스템에 있고, NowView는 그것을 읽어 계산하고
  결정을 돌려 적는다.
* **규칙 계산은 NowView 몫이다.** 전망 비교·지표·위험 판정·Agent 초안·경영 이슈·업무는 INNONOW 방법론이고 회사가 바뀌어도 같은
  규칙을 쓴다. 회사 시스템은 자료와 확정 기록의 원본(system of record)이다.
* **NowView는 고정 프로그램이다.** 일꾼이 제공하는 작업은 기본 확장 `external`(BPM 서비스 태스크의 External Service) 하나에 모여 있고 NowView 판과 함께 바뀐다. 회사나 업무마다
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

**장면 2**

| 자료 | 주인 | 어디서 |
|---|---|---|
| 부품·공급사·부품 구성(소요량)·현행 구매 단가 C01 | 회사 | `GET /company/purchase/master` — 엔진은 엑셀의 같은 칸 대신 쓴다(`seed.with_company`). 외주비가 엑셀 C01과 다르면 409 |
| 공급사 단가 인상 요청 원문 | 회사 | 세계 구매 수신함 — NowView 문서에 사본(`request.company_doc_id`) |
| 요청 원문 확인 상태(VERIFIED·NEEDS_INFO) | 회사 | 원문 확인 기록 때 회사에 적는다(`POST …/price-requests/{doc}/status`) |
| 원가 버전 C02-APP01(승인 단가, 적용 예정·적용 중) | 회사 | 원가 등록 기록 때 회사에 등록한다(`POST /worlds/{w}/cost-versions`) |
| 물량·원가 행(2027 = 장면 1 회사 자료, 2028 내부가정)·고정비·임계값·승인권한표 | NowView | 엔진 엑셀(`SYN-SC02-v0.2`) — 2028은 경영관리의 분석 가정이지 회사 확정 계획이 아니다 |
| 보고·협상·단가안·기안·결재 결정·분석 run·위험·인계 | NowView | 데모 실행 문서 |

**장면 3**

| 자료 | 주인 | 어디서 |
|---|---|---|
| 승인 원가 버전 C02-APP01(승인 단가·적용일) | 회사 | 시작 때 `GET /worlds/{w}/cost-versions`로 읽어 장면 2 기록과 대조한다(없거나 다르면 409). 시계를 옮기면 회사 세계 시각도 옮긴다(적용 예정 → 적용 중) |
| 받은 고객계획·원천 확인(장면 1) | 회사 | 장면 1이 이미 들였다 — 장면 3은 장면 1 계산 run을 잇는다 |
| 통합 손익·부족·정합 검증·부서 확인·쟁점·보고·회의·후보·분석과제·인계 | NowView | 데모 실행 문서 — 회사에 적지 않는다(경영 기록) |

## 4. 경계별 인터페이스

### 4.1 ① BPM ↔ 일꾼 — 일감 (토픽 `external`)

* **확장 정의** `chaeksas/external.extension.json`의 작업·입출력 스키마가 계약이다. 일꾼은 이것으로 Center에 manifest를 올리고, Center는
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
| `record_plan_review` | 원천 확인 결정 기록 | 원천 상태 VERIFIED·NEEDS_INFO |
| `assess_supply_risk` | 검토 전망 생성 · 15행 지표 · 위험 판정 · 이슈 잇기 | T01·F01·실적·C01·FC01 읽기(불변 버전 — 한 번 읽어 둔다) |
| `request_review_draft` | Agent 검토 초안 요청(기다리지 않음) | — |
| `record_risk_review` | 영업 검토 의견·근거 기록 | — |
| `assign_follow_up` | 현업(생산·자재, `Approve_Dispatch`) 또는 경영관리(`Approve_Review`) 배정 — 담당자 이름을 돌려준다 | — |
| `record_acceptance` | 인수 기록 | — |
| `hand_off_case` | 인계 조건 확인 · 인계 기록 | — |

장면 2 작업(BPM 프로세스 `company1.sc02` 0.2.0 — 확장 `>=0.2.0`):

| 작업 | 하는 일 | 회사 시스템 호출(②) |
|---|---|---|
| `screen_price_request` | 요청 자동 검사(CT21) — 필수값·KRW·VAT 제외·월초 적용·품목 매핑·기존가 = 회사 C01 단가 | — (마스터는 한 번 읽어 둔다) |
| `record_price_request_review` | 요청 원문 확인 기록 | 요청 상태 VERIFIED·NEEDS_INFO |
| `record_purchase_report` | 팀장 구두보고 기록 | — |
| `analyze_price_request` · `analyze_price_negotiation` | 요청안·내부제시안 · 협상안 영향분석 run | — |
| `request_price_review_draft` | Agent 검토 초안(AG21·22·24) | — |
| `record_price_negotiation` | 1차 협상 결과 | — |
| `submit_price_proposal` | 기안 상신(기안 버전·분석 run) | — |
| `record_price_decision` · `judge_price_authority` | 결재 결정 · 대표 대상 판단 | — |
| `register_cost_version` | 승인 조건 대조 · 원가 버전 등록 | 원가 버전 C02-APP01 등록 |
| `hand_off_cost_review` · `accept_cost_review` | 경영관리 인계 요청 · 인수 | — |

장면 3 작업(BPM 프로세스 `company1.sc03` 0.3.0 — 확장 `>=0.3.0`). 회사 시스템 호출은 없다 — 원가 버전은 시작(화면 명령) 때 읽는다:

| 작업 | 하는 일 |
|---|---|
| `open_profit_review` | 착수된 검토건 MR-2706-01 열기(S31) |
| `analyze_profit_impact` · `correct_profit_calculation` | 통합 분석 실행·정합 검증(CT31~33) · 계산 정정(E33) |
| `request_profit_explanation_draft` | Agent 통합 손익 설명 초안(AG30) |
| `request_department_confirmation` · `record_department_confirmation` · `revise_profit_report` | 부서 확인 요청 · 영업/구매/생산 확인 · 이견 보완(새 초안 버전) |
| `record_target_gap` · `judge_open_questions` | 기존 목표 부족 확인 · 쟁점(Q31·Q32) 판단 |
| `freeze_profit_report` · `distribute_profit_report` | 보고 자료 확정 · 배포 |
| `open_review_meeting` · `record_review_conclusion` · `confirm_meeting_minutes` | 수시회의 보고 · 결론·후보 판단 · 회의록 확정 |
| `assign_analysis_tasks` · `accept_analysis_task` · `reassign_analysis_task` | 분석과제 배정 · 책임자 인수·반려 · 재배정 |
| `hand_off_profit_review` | 완료 조건 재검증 · HANDOFF31(장면 4 MT41 연결) |

**장면 4**

| 자료 | 주인 | 어디서 |
|---|---|---|
| 분석 결과·효과 검증·우선 실행안·보고본·회의 기록·판단본·대표 결정·승인서·회의록·실행과제·조건·지시·인수·인계 | NowView | 데모 실행 문서 — 회사에 적지 않는다(경영 기록). 실제 실행 품의·예산 거래는 장면 5 범위(구현명세 SC04 v0.2 — 장면 4의 예산 위임은 정책 조회뿐) |
| 회사 세계 시각 | 회사 | 시계를 옮기면(각본·바깥 답이 따라갈 때 포함) `set_clock`으로 함께 옮긴다 |

장면 4 작업(BPM 프로세스 `company1.sc04` 0.4.0 — 확장 `>=0.4.0`). 회사 시스템 호출은 없다:

| 작업 | 하는 일 |
|---|---|
| `open_improvement_review` | 착수된 검토건 열기 — HANDOFF31·AT31~34 연결(S01) |
| `submit_analysis_result` · `confirm_analysis_result` | 분석 결과 제출(부서 책임자) · 담당 임원 확인·보완 요청 |
| `verify_improvement_effects` · `correct_improvement_effects` | 효과 계산·회피 비용·중복 검증 · 검증이 막으면 담당 임원 보완 |
| `request_improvement_draft` | Agent 검증 요약 초안(AG41) |
| `recommend_priority_actions` · `freeze_improvement_report` | 우선 실행안 2~3개 공동 제안 · 보고본 REP41 확정·배포 |
| `open_monthly_meeting` | 대표 주재 월간회의 MT41 보고 |
| `draft_decision_report` · `confirm_decision_report` | 판단 초안(가정 변경·조건·지원) · 판단본 DEC41 확정 |
| `record_ceo_decision` | 대표의 과제별 결정(승인·조건부·보류·반려)·추가 발굴 지시 |
| `draft_execution_approval` · `finalize_execution_approval` | 승인서·회의록 초안 · APR41·MIN41 확정(누락이면 422) |
| `register_execution_actions` · `accept_execution_assignment` · `revise_execution_assignment` | 실행과제·조건·지시 등록 · 책임자 인수·반려 · 반려 보완(새 배정버전) |
| `hand_off_execution_plan` | 종료 요건 재검증 · HANDOFF41(장면 5 상세 실행계획 연결) |

**장면 5**

| 자료 | 주인 | 어디서 |
|---|---|---|
| 실행 품의(상신·현업 승인·예산 승인·반려 — 상태 이력) | 회사 | `POST/GET /worlds/{w}/execution-requests` — 저장 직전에 아직 적지 않은 상태 칸을 적는다(`ref` 멱등) |
| 예산 원장(약정 COMMIT·정산 SETTLE)과 범위별 합계 | 회사 | `POST/GET /worlds/{w}/budget-ledger` — 거래 id 멱등, 같은 id 다른 내용 409 |
| 공식 전망 게시(FC50 → FC51)와 지금 공식본 | 회사 | `POST/GET /worlds/{w}/forecasts` — 판 id 멱등, 같은 id 다른 내용 409. 목표는 바꾸지 않는다 |
| 실행 계획·변경·조건·지원·착수·변경 대응·발주 기록·초기 결과·운영계획·전망 작성·확인·인계 | NowView | 데모 실행 문서 — 경영 기록. 고객 변경 원문(CP51·CP52)·구매 주문 60건·근거는 아직 NowView 시드(배경 원천, `catch_up`) |
| 회사 세계 시각 | 회사 | 시계를 옮기면(각본·바깥 답이 따라갈 때 포함) `set_clock`으로 함께 옮긴다 |

회사에 적는 것은 BPM 기록 작업이 아니라 **저장 직전의 대조**(`Sc05Process._sync_company`)다 — 결재 기록 작업이 만든 품의·약정·
게시뿐 아니라 가상시계가 들인 배경 행(ACT41·43 품의, 정산 거래, 9/6 FC50)도 같은 길로 간다. 적은 것은 `company_synced`에 남고
회사가 받지 못하면 그 조작은 저장되지 않는다(503). 장면 5 초기화는 회사의 장면 5 기록만 지운다(`POST /worlds/{w}/execution/reset`).

장면 5 작업(BPM 프로세스 `company1.sc05` 0.5.0 — 확장 `>=0.5.0`):

| 작업 | 하는 일 | 회사 시스템(저장 직전) |
|---|---|---|
| `open_execution_plan` | 착수된 장면 열기 — HANDOFF41·APR41-v1 연결(S01) | — |
| `draft_execution_plan` · `coordinate_execution_plan` · `confirm_execution_plan` · `verify_execution_plan` | 상세 계획 초안 · 생산 협조 · 구매 임원 확정 · 경영관리 확인(변경안에도 같은 작업) | — |
| `request_plan_change` | 승인 범위 안 변경 요청(범위 이탈이면 시행 보류) | — |
| `submit_condition_evidence` · `coordinate_condition_readiness` · `confirm_condition` | CON41·SUP41 근거 · 준비 확인 · 충족·이행 확인 | — |
| `submit_execution_request` · `approve_execution_request` | 품의 상신 · 현업/예산 승인(예산 승인과 약정이 한 저장) | 품의 상태 · 원장 약정 |
| `start_action_operation` | 운영 적용 착수(요건 미충족 422, 9/1 전 불가) | — |
| `receive_production_change` · `share_production_change` · `acknowledge_production_change` · `respond_production_change` | 고객 변경 접수 · 생산 공유 · 구매 확인 · 정상 대응/긴급 기안 | — |
| `approve_urgent_purchase` · `record_purchase_order` | 긴급 예외 전결 · 발주·처리 기록 | — |
| `confirm_initial_results` · `confirm_operating_plan` · `verify_operating_plan` | 9월 초기 결과 확인 · OPL51~53 확정 · 경영관리 확인 | — |
| `draft_rolling_forecast` · `confirm_rolling_forecast` · `submit_rolling_forecast` · `approve_rolling_forecast` · `publish_rolling_forecast` | RUN·검토안 작성·대사 · 부서 가정 확인 · 대표 승인 요청 · 대표 승인 · 공식본 게시 | 게시 → 공식 전망 |
| `hand_off_follow_up` | 종료 요건 재검증 · HANDOFF51 | — |

**장면 6**

| 자료 | 주인 | 어디서 |
|---|---|---|
| 지금 공식 전망(FC51 — 4분기 기대 효과의 기준) | 회사 | `GET /worlds/{w}/forecasts` — 적재 때 읽어 장면 5 기록과 연간·월 손익을 대조한다(공식본이 FC51이 아니거나 다르면 409) |
| 4분기 구매 거래 180건·운영비·완료 근거·Agent 기록 | NowView 시드 | 통합가상데이터 v0.6 SC06 원천 — 장면 5의 구매 주문처럼 아직 회사로 옮기지 않았다 |
| 기대 대비 확인 효과·원인·완료 판단·확인 기록(CF61-*)·보고본 RPT61-v1·후속 조치(FUP61·PROP61·FUP62) | NowView | 데모 실행 문서 — 계산과 경영 기록이라 회사에 적지 않는다 |
| 회사 세계 시각 | 회사 | 확인 기록이 시계를 일정으로 옮기면 `set_clock`으로 함께 옮긴다 |

장면 6 작업(BPM 프로세스 `company1.sc06` 0.6.0 — 확장 `>=0.6.0`). 회사 시스템 호출은 없다 — 공식 전망은 적재(화면 명령) 때 읽는다:

| 작업 | 하는 일 |
|---|---|
| `open_performance_review` | 착수된 검토건 RV61 열기 — 보고 버전·산정 버전을 돌려준다 |
| `confirm_performance_evidence` | 담당 임원 성과 근거 확인(생산 CF61-P · 구매 CF61-B — 같은 작업, `record_id`로 가른다) |
| `review_performance_summary` | 경영관리 종합 확인 CF61-F(재확인 요청이면 두 확인을 이력으로 옮긴다) |
| `draft_performance_conclusion` | 보고 결론 TXT61 |
| `finalize_performance_report` | 보고본 확정 CF61-R + 남는 사항 NOTE61(결론 숫자 ↔ 산정, 아니면 422 REPORT_INVALID) · 보완 요청 |
| `report_performance_to_ceo` | 대표 월간 보고 CF61-M — 보고 확정은 발의의 실행·예산 승인이 아니다 |

**장면 7**

| 자료 | 주인 | 어디서 |
|---|---|---|
| 장면 6 보고본·AG62 초안과 사람 보정·대표 사례(CH61-1103·PO61-1103·E61-1103) | NowView | 장면 6 문서 스냅샷 — 비교 화면에만 쓰고 바꾸지 않는다(지문으로 TC707) |
| 대행 위임·확인 로그·공급 조건(EV71~74)·검증 입력 IN71~75 | NowView 시드 | 통합가상데이터 v0.7 SC07 원천 — 회사로 옮기지 않았다(2026-11-02 결정, 합성 사례 IN73·74는 실제 이력에 넣지 않는다) |
| 검증 결과(TS71-v1)·확인 기록 CF71·CF72·운영 설정 CFG71·후속 점검 | NowView | 데모 실행 문서 — 개선 Agent의 설정은 NowView 기록이다 |
| 회사 세계 시각 | 회사 | 확인 기록이 시계를 일정으로 옮기면 `set_clock`으로 함께 옮긴다 |

장면 7 작업(BPM 프로세스 `company1.sc07` 0.7.0 — 확장 `>=0.7.0`). 회사 시스템 호출은 없다:

| 작업 | 하는 일 |
|---|---|
| `open_improvement` | 착수된 개선건 IMP71 열기 — 대상 Agent 버전·검증 세트를 돌려준다 |
| `verify_improvement_version` | 검증 세트 TS71-v1 실행(TC701~708 관측값을 규칙으로 다시 계산) — `result` PASS·FAIL |
| `confirm_improvement_version` | 업무 확인(구매 임원 CF71 · 경영관리 임원 CF72 — 같은 작업, `record_id`로 가른다). 대상 버전이 아니면 422, 보완 요청 |
| `apply_agent_setting` | 운영 설정 반영 CFG71 — active_version·범위·증적 유형(SETTINGS_SNAPSHOT·RESERVED) |
| `check_agent_setting` | 설정 반영 확인 — 「일치」는 버전·범위·스냅샷이 맞아야 한다(아니면 422 SETTING_MISMATCH), 「불일치」면 다시 반영 |
| `schedule_follow_up_check` | 후속 점검 연결(2/11 10:00 경영관리 담당) — 운영 실행은 미확인으로 남는다 |

**실패** — 업무 규칙 위반은 `forbidden`·`not_found`·`conflict`·`input_invalid`(재시도 없음, 글은 사유). 회사 시스템이 응답하지 않으면
`dependency_down`(재시도) — 엔진 안에서는 `CompanyUnavailable`(503)이고 그 조작은 저장되지 않는다. 설정에 없는 BPM 프로세스의 일감은
`not_found`.

### 4.2 ② 일꾼 ↔ 회사 시스템 — 회사 시스템 API

가상 자동차 부품사의 회사 시스템은 별도 리포 Company1의 기간계다(`legacy/`, :8191 — `../Company1`에서 `scripts/stack.sh start`). 엔진 시험은 같은 계약의 쌍둥이(`engine/tests/company_twin/`)를 쓴다. NowView 엔진만 부른다 — 주소는 설정, 키는 엔진 환경
(`COMPANY_COMPANY1_KEY`, Bearer). JSON, 금액은 문자열 DECIMAL, 수량 누락은 `null`(0과 다르다).

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

장면 2(구매):

```
GET  /company/purchase/master                       → {parts, suppliers, bom:[{model_id, part_id, supplier_id, qty_per, outsource, residual_outsource}], prices}
GET  /worlds/{w}/price-requests/inbox?after=        → 받은 요청 [{doc_id, seq, fixture_id, request_id, supplier_id, received_at, corrects, status}]
GET  /worlds/{w}/price-requests/{doc_id}            → {…, supplier_name, source_doc_id, text, items:[{part_id, old_price, requested_price, effective_date, …}]}
GET  /worlds/{w}/price-requests/status-log · /worlds/{w}/cost-versions
POST /worlds/{w}/price-requests/{doc_id}/status     {status, by, opinion, evidence, ref}   (멱등 — 위와 같다)
POST /worlds/{w}/cost-versions                      {cost_version_id, parent_cost_version, part_id, supplier_id, old_price, new_price,
                                                     effective_from, models, approved_proposal, request_doc_id, registered_by, note, ref}
                                                     같은 버전·같은 내용이면 기존 등록, 다른 내용이면 409. 상태는 세계 시각으로
                                                     REGISTERED_FUTURE·EFFECTIVE
POST /worlds/{w}/sim/price-requests  {fixture_id}   (시연) 공급사가 요청을 보냈다 — REQ-2706-01 · REQ-2706-01-MISSING
POST /worlds/{w}/purchase/reset                     (시연) 장면 2 기록만 처음으로 — 장면 1 수신함·원천 상태는 그대로
```

장면 5(실행 품의·예산 원장·공식 전망):

```
GET  /worlds/{w}/execution-requests                 → [{request_id, seq, version, task_id, scope, amount, reason, approval_ref, state,
                                                       history:[{ref, version, state, by, at, note, recorded_at}]}]
POST /worlds/{w}/execution-requests                 {request_id, version, task_id, scope, amount, reason, approval_ref, state, by, at, note, ref}
                                                     상태 한 칸 — ref 멱등, 지난 판(version)이면 409
GET  /worlds/{w}/budget-ledger                      → {transactions:[…], totals:{scope:{committed, paid, pnl_cost}}}
POST /worlds/{w}/budget-ledger                      {txn_id, task_id, scope, request_ref, at, type: COMMIT|SETTLE, commitment_delta,
                                                     paid_delta, pnl_cost, evidence, ref}   같은 거래·같은 내용이면 기존 줄, 다른 내용 409
GET  /worlds/{w}/forecasts                          → {official, forecasts:[…]}
POST /worlds/{w}/forecasts                          {forecast_id, run_id, parent_official, cutoff, annual, months:[{month, profit}],
                                                     approved_at, approved_by, published_at, published_by, ref}   공식본을 이 판으로
POST /worlds/{w}/execution/reset                    (시연) 장면 5 기록만 처음으로
```

경영 기록(2026-11-03, `docs/role-split.md` §3 — **봉투는 공통, 본문은 종류별 스키마** `docs/records/`):

```
POST /worlds/{w}/records          {kind, record_id, version, scene, state, at, by, title, body, ref}
                                   같은 ref·같은 내용 → 기존 판(recorded: false), 같은 ref·다른 내용 → 409.
                                   새 판(version이 더 크다)이면 앞 판을 history로 옮긴다(지우지 않는다).
                                   지난 판·같은 판에 다른 ref → 409. 기록 시각(recorded_at)은 세계 시각
GET  /worlds/{w}/records?scene=&kind=&state=     → 각 기록의 최신 판(처음 적은 순서, history_count)
GET  /worlds/{w}/records/{kind}/{record_id}      → 최신 판 + history
POST /worlds/{w}/records/reset {scene}           (시연) 그 장면 기록만 처음으로. 세계 초기화는 기록도 비운다
```

* 장면 1이 적는 종류는 `scene`·`source`·`forecast`·`calc_run`·`issue`·`task`·`review`·`agent_draft`·`handoff`·`dashboard`다
  (`engine/app/sc01/records.py`). 본문은 NowView 장면 1 화면이 읽는 모양 그대로다(2026-11-03 사용자 결정). 바뀐 기록만 새 판으로
  적고(문서의 `company_records`에 판·본문 해시), ref = `데모실행:종류/id:v판`이다. 회사 사이트는 이 기록만 읽어 업무 화면을 그린다.
* **기간계는 봉투만 검사한다** — 본문의 주인은 NowView다. 엔진 시험(`test_sc01_records.py`)이 적은 모든 판을 스키마로 검사하고, 사이트
  시험(Company1 `site-api/tests/test_work.py`)이 같은 예시(`docs/records/sc01/examples/base-end.json`)로 읽기를 검사한다.

NowView는 이 쓰기를 **데모 실행 문서를 저장하기 직전에** 한다 — 회사가 받지 못하면 그 조작 전체가 저장되지 않는다.

시연 조작(시연 전용 — 실제 회사 시스템에는 없다). **세계를 만들고 초기화하고 시계를 옮기는 쪽은 회사 사이트다**(2026-11-03,
`docs/role-split.md` §5) — NowView는 읽기만 한다(엔진 시험만 엔진이 쓴다, `app.company.engine_drives`):

```
POST /worlds                                        {world_id, case_id="BASE", origin}  → 세계(이미 있으면 그대로), 시각 S0 = 2027-06-15 18:00
                                                     origin = site면 NowView 일꾼이 데모 실행으로 들인다(그 밖은 들이지 않는다)
GET  /worlds · /worlds/{w}                          → {world_id, case_id, generation, reset_at, clock, received, price_requests,
                                                       pending_commands, …}   NowView 일꾼이 2초마다 읽는다(app/follower.py)
POST /worlds/{w}/clock                              {at}             (사이트)
POST /worlds/{w}/sim/customer-plans                 {fixture_id}     → 고객이 원천을 보냈다(CP02 · CP03 · EX01·02·04·05)
POST /worlds/{w}/sim/price-requests                 {fixture_id}     → 공급사가 단가 인상 요청을 보냈다(장면 2)
POST /worlds/{w}/reset                              {case_id?}       → 세계를 S0로, 초기화 회차(generation) +1, 명령을 비운다
POST /worlds/{w}/commands                           {scene, kind, actor, body, ref}   (사이트) 결재가 아닌 업무 행위 → PENDING
GET  /worlds/{w}/commands?state=&after= · /commands/{id}
POST /worlds/{w}/commands/{id}/result               {state: DONE|REJECTED, status, reason, result}   (NowView) — 한 번만
POST /worlds/{w}/worker-log                         {scene, operation, node_id, approval_node, run_id, ok, reason, ref}   (NowView)
GET  /worlds/{w}/worker-log?after=                  → 일감 기록 — 사이트 자동 모드가 답한 결재의 기록이 왔는지 본다
```

명령 종류(`open`·`start`·`record`·`agent`·`adopt`·`review`·…)와 몸통은 `docs/role-split.md` §5.2다.

**원천 도착** — 사이트가 회사 시스템에 원천을 보내면(`sim/customer-plans`·`sim/price-requests`) 일꾼이 수신함을 읽어 데모 실행
문서에 사본으로 들이고 Center에서 업무를 시작한다(`app/follower.py` → `Sc01Process.receive_inbox`·`Sc02Process.receive_inbox`).
장면 2 문서가 아직 없으면(사이트가 `open`하기 전) 단가 요청은 수신함에 둔다. 엔진 시험은 예전처럼 엔진이 보내고 같은 조작 안에서
들인다(`receive(fixture_id)`).

**세계 시각** — 일꾼은 세계 시각이 장면 문서보다 앞이면 장면마다 따라가고(기한 초과 알림 · 장면 5 배경 원천), 일감·명령·수신을
처리하기 전에도 그 세계의 시각을 먼저 읽는다(`follower.Synced`). 엔진은 기간계 시계를 쓰지 않는다 — 각본 시각으로 옮기는 것도
사이트 몫이다(결재 화면 「각본 시각으로 옮기고 답하기」·자동 모드).

**직원 명단** — 엔진 사용자 마스터(`domain.USERS`)는 `GET /company/org/users`로 채운다(`CompanyClient.ensure_roster`, 기준 자료를
읽을 때·세계를 따라갈 때). 엔진에 남은 것은 자기 행위자 시연관리자(`u-demo`)뿐이다.

### 4.3 ③ 웹 ↔ 엔진

* **공개** — 장면 화면 API(`/api/engine/sc01`~`sc07/…`)와 회사 목록 `GET /api/engine/companies`(`{id, name, description, scenes}` —
  이름·설명·업무 번호뿐). BPM 프로세스 id·토픽·회사 시스템 주소·일꾼 상태는 공개하지 않는다.
* **관리** — `/admin` 화면이 로그인 뒤 `/api/admin/*`를 부르고, 웹 서버가 세션을 확인한 뒤 엔진 `/admin/*`에 관리 키(`X-Admin-Key`)를
  실어 보낸다. 엔진 관리 API:

```
GET  /admin/status    → 일꾼(상태·토픽·최근 일감) · Center 연결 · 회사 시스템 연결 · 재시작 필요 여부
GET  /admin/config    → 설정 · 업무 번호 목록 · 고정 확장의 작업 목록(읽기만)
PUT  /admin/config    → 설정 저장(검사 실패 422 + 사유)
```

## 5. 설정

엔진 DB(`nowview_config`)에 한 벌 있고 관리자 모드에서만 고친다. 키·비밀번호는 설정에 두지 않는다(환경 파일).

```json
{
  "companies": [{"id": "company1", "name": "가상 자동차 부품사", "description": "…", "system_url": "http://localhost:8191"}],
  "processes": [
    {"bpm_process_id": "company1.sc01", "company": "company1", "scene": 1},
    {"bpm_process_id": "company1.sc02", "company": "company1", "scene": 2}
  ],
  "topics": ["external"]
}
```

* 처음 뜰 때 설정이 없으면 이 모양의 기본값을 적는다(장면 1~7 `company1.sc0N` → 업무 N, 토픽은 기본 확장 `external` 하나).
* 검사: 회사 id·BPM 프로세스·토픽이 겹치지 않을 것, 매핑의 회사가 있을 것, 업무 번호가 NowView에 있는 것(1~6)일 것, NowView에 업무
  코드가 있는 회사일 것.
* 매핑·회사 시스템 주소는 저장하면 바로 쓰인다. 토픽은 일꾼 파일(`worker.consumer.json`)을 다시 지어 Center와 엔진을 다시 띄워야 한다(Center는 그 파일의 토픽만 내준다).

## 6. 장면 1 한 바퀴

```
1 플레이어 「CP02 수신」 ─▶ 엔진 ─▶ 회사 POST /worlds/{w}/sim/customer-plans ─▶ GET 원천 ─▶ 문서에 사본
2 엔진 ─▶ Center: POST /jobs (company1.sc01 시작)
3 일감 validate_customer_plan ─▶ 일꾼 ─▶ 검증 ─▶ complete
4 영업담당 확인(결재) ─▶ 일감 record_plan_review ─▶ 회사 POST status VERIFIED
5 계산 확인(결재) ─▶ 일감 assess_supply_risk ─▶ 회사 자료(T01·F01·실적·C01·FC01) ─▶ 계산 run·F02·이슈
6 일감 request_review_draft ─▶ Agent 초안(배경)
7 영업팀장 검토 ─▶ record_risk_review ─▶ assign_follow_up(생산·자재 ∥ 경영관리) ─▶ 인수 ×3 ─▶ hand_off_case
```

## 7. 아직 아닌 것

* 엔진이 회사 시스템의 사용자 명단을 읽지 않는다 — 기간계가 사원 명단을 내지만 엔진은 `domain.USERS`를
  쓴다. 장면 2~6도 쓰고 있어 업무를 옮길 때 함께 바꾼다. 결재 담당자 이름(BPMN `assignees`)은 Center 계정과 사람이 맞춘다.
* 장면 5는 실행 품의·예산 원장·공식 전망을 회사에 적고, 장면 6은 그 공식 전망을 기준으로 읽기만 한다 — 고객 변경 원문(CP51·CP52)·
  구매 주문(장면 5 60건·장면 6 4분기 180건)·근거는 아직 NowView 시드다(회사 수신함·구매 시스템으로 옮길지는 아직이다). 장면 3의 회의·분석과제,
  장면 4의 승인서·실행과제는 경영 기록이라 NowView에만 둔다. 장면 2의 협상·기안·결재
  기록은 NowView 문서에만 있다 — 회사 전자결재 기록으로 옮길지는 아직 정하지 않았다.
* 회사 시스템이 죽으면 업무가 멈추고 일감은 재시도로 돌아간다. 공개 대시보드에는 「회사 시스템 연결 안 됨」 표시가 아직 없다(관리자
  화면에만 있다).
