# NowView ↔ Chaeksas 연계 — 현재 구조와 등록 절차

지금 구조만 적는다. 바뀐 과정은 git 이력에 있다. NowView의 역할 정의와 회사 시스템 인터페이스는
[worker-interfaces.md](worker-interfaces.md), 화면·API 세부는 CLAUDE.md 4.3·4.5에 있다.

## 1. 구성

```
                 Chaeksas                                   NowView                          회사
┌──────────────────────────────────┐        ┌──────────────────────────────────┐     ┌──────────────────┐
│ Studio(시험 실행)                 │        │ 엔진 :8077                        │     │ 회사 시스템        │
│ 서버 실행기 ── 일감 올리기 ─▶ Center│◀───────│  · C15 일꾼(토픽 nowview)          │────▶│ (가상 자동차 부품사 │
│ :8800      ◀─ 결재·실행 기록 ──    │ 가져가기 │  · Center 클라이언트(기동·대리 답·  │ 읽기 │  기간계 :8191)    │
│            가상 직원·패키지·키      │ 기동·답  │    진행 폴링)                     │ 쓰기 └──────────────────┘
└──────────────────────────────────┘        │  · 규칙 계산·경영 기록·설정(DB)     │
                                            ├──────────────────────────────────┤
                                            │ 웹 :3000 — 회사별 대시보드 · /admin │
                                            └──────────────────────────────────┘
```

* **연결은 늘 NowView에서 나간다.** Center도 회사 시스템도 NowView 주소·키를 모른다.
* **NowView는 고정 프로그램이다.** 일꾼이 제공하는 작업 목록은 확장 하나(`nowview`)이고 NowView 판과 함께 바뀐다. 어느 회사의 어느 BPM
  프로세스를 맡는지는 NowView **설정**(엔진 DB, 관리자 화면 `/admin`)이다.
* **업무 흐름은 BPMN 하나다**(`engine/processes/*.bpmn` — 원본은 autopart1 리포의 `bpm/`, `scripts/sync-bpm.sh`로 가져온다). 같은 그림을 Studio·서버 실행기·엔진 내장 실행기(시험용)가 돈다.
* **숫자는 NowView 규칙 계산이 만든다.** Chaeksas는 순서·사람 결재·분기·인계를 쥐고, 회사 시스템은 자료와 확정 기록을 쥔다.

## 2. 무엇이 어디에 등록되나

| 무엇 | 어디서 (Center 콘솔 http://localhost:8501 의 왼쪽 메뉴) | 값 |
|---|---|---|
| 확장 정의(일꾼 작업 목록) | 배포·자원 › **리소스** › 「기능 추가 (외부)」 | 파일 `chaeksas/nowview.extension.json` (id `nowview`, 0.1.0) |
| BPM 패키지 둘 | Studio 「파일 › Center로 올리기」 → 운영 현황 › **BPM 프로세스 현황**에서 승인 → 배포·자원 › **배포** | `autopart1.sc01`(`engine/processes/sc01.bpmn`), `autopart1.sc01-intake`(`engine/processes/sc01-intake.bpmn`) |
| 가상 직원 | 업무 › **가상 직원** › 「새 가상 직원」 | id `autopart1-intake`, 감독자 `이도윤`, 접수 BPM 프로세스 `autopart1.sc01-intake` |
| Center 키 둘 | 관리 › **Center API 키** › 「새 키...」 | 종류 「연동용」 하나, 「대리 답용」 하나 → `engine/.env.local` |
| 일꾼(NowView 엔진) | 배포·자원 › **리소스** › 「일꾼 승인 대기」 | NowView `/admin`에 보이는 요청 코드 |
| BPM 프로세스 → 회사·업무 | NowView `/admin` 설정 | 기본값에 이미 있다 — 손댈 것 없음 |

장면 2~6은 아직 옮기기 전이다 — 예전 확장 `nowview-sc02`~`sc06`, 패키지 `autopart1.sc02`~`sc06`로 돈다.

## 3. 등록 순서 (로컬 Center)

**준비**
* NowView: `npm run stack:start`(회사 시스템 → 엔진 → 웹). `engine/.env.local`에 `NOWVIEW_CONSUMER=off`가 있어 일꾼은 꺼져 있다.
* Center 콘솔 `http://localhost:8501`에 **관리자 계정**으로 들어간다(등록·승인은 관리자만 된다).
* Studio를 띄우고 이 Center에 연결해 둔다(Studio의 「Center로 올리기」가 그 연결로 올린다).

**1. 확장 정의 등록** (Center 콘솔)
1. 왼쪽 메뉴 **배포·자원 › 리소스**.
2. 아래 「기능 추가 (외부)」에서 「확장 정의 파일 (extension.json)」에 `chaeksas/nowview.extension.json`을 고르고 **등록**.
3. 「기능을 등록했습니다.」가 나오고 기능 목록에 `nowview`가 보이면 된다. 키·주소는 넣지 않는다.

**2. BPM 패키지 올리기·승인·배포** (Studio → Center 콘솔) — 두 그림 모두 같은 순서다.
1. Studio에서 `engine/processes/sc01.bpmn`을 연다 → 메뉴 **파일 › Center로 올리기**.
2. Center 콘솔 **운영 현황 › BPM 프로세스 현황**에서 `autopart1.sc01` 줄의 「승인」 칸에서 **승인**.
3. **배포·자원 › 배포** › **새 배포...** → 「BPM 프로세스@버전 (승인된 것)」에서 `autopart1.sc01@…`를 고르고 **고르기** → 실행기를
   고르고 **배포**.
4. `engine/processes/sc01-intake.bpmn`(`autopart1.sc01-intake`)도 1~3을 한다.

**3. 가상 직원 등록** (Center 콘솔)
1. **업무 › 가상 직원** 아래 「새 가상 직원」.
2. id `autopart1-intake`, 이름 `고객계획 접수 담당`, 감독자 `이도윤`, 접수 BPM 프로세스 `autopart1.sc01-intake` → **등록**.
   (id는 `engine/.env.local`의 `CHAEKSAS_INTAKE_WORKER`와 같아야 한다 — 이미 `autopart1-intake`로 적혀 있다.)

**4. Center 키 발급** (Center 콘솔 → NowView)
1. **관리 › Center API 키** › **새 키...** → 이름 `nowview-integration`, 종류 **연동용** → **발급**. 한 번만 보이는 원문을 복사해
   `engine/.env.local`의 `CHAEKSAS_INTEGRATION_KEY=` 뒤에 붙인다.
2. 한 번 더 **새 키...** → 이름 `nowview-relay`, 종류 **대리 답용** → **발급** → `CHAEKSAS_RELAY_KEY=` 뒤에 붙인다.

**5. 일꾼 켜기** (NowView)
1. `engine/.env.local`에서 `NOWVIEW_CONSUMER=off` 줄을 지운다.
2. `npm run stack:restart engine`.

**6. 일꾼 승인** (NowView → Center 콘솔)
1. NowView `http://localhost:3000/admin`에 로그인한다(비밀번호는 저장소 루트 `.env.local`의 `NOWVIEW_ADMIN_PASSWORD`). 「일꾼」 카드에
   요청 코드(예 `ABCD-1234`)가 보인다.
2. Center 콘솔 **배포·자원 › 리소스** 맨 위 「일꾼 승인 대기」에서 **요청 코드가 같은 줄**의 **승인...** → 이름(예 `NowView 엔진`)·
   토픽(`nowview`, `nowview-sc02`~`sc06`) 확인 → **승인**.
3. NowView `/admin`의 일꾼 상태가 「일감을 가져가는 중」이 되면 된다(5초마다 새로 읽는다).

**7. 확인** (NowView)
1. `/admin` 「연결」에서 Center 연동용 키·대리 답용 키가 「있음」, 회사 시스템이 「응답함」인지 본다.
2. 회사 화면 `http://localhost:3000/c/autopart1/sc01`의 데모 플레이어에서 실행 위치 **Center**로 초기화하고 장면 1을 돌린다.

**다시 처음부터** — 승인 전 요청을 버리려면 `engine/.consumer/`를 지우고 엔진을 다시 띄운다(새 요청 코드가 나온다). Center에 남은
옛 요청은 「일꾼 승인 대기」에서 **거절...** 한다. NowView에서는 Center의 요청을 지울 수 없다(Center 관리자 권한).

## 4. NowView 환경과 설정

**환경 파일**(비밀 — git에 넣지 않는다)

| 파일 | 값 | 쓰임 |
|---|---|---|
| `engine/.env.local` | `CHAEKSAS_CENTER_URL` | Center 주소(일꾼·기동·대리 답 모두) |
| | `CHAEKSAS_INTEGRATION_KEY` | 연동용 키 — 기동(`POST /jobs`·`/messages`), 진행 읽기, 가상 직원 읽기, 작업 거두기 |
| | `CHAEKSAS_RELAY_KEY` | 대리 답용 키 — 결재 읽기·답(`X-CHK-On-Behalf-Of` = 행위자 이름) |
| | `CHAEKSAS_INTAKE_WORKER` | 접수 가상 직원 id. 있으면 원천 수신이 접수 Bot을 메시지로 깨운다. 없으면 SC01을 바로 기동한다 |
| | `CHAEKSAS_SC01_PACKAGE` | 장면 1 패키지 id(기본 `autopart1.sc01`) |
| | `NOWVIEW_CONSUMER=off` | 일꾼을 끈다(들이기 요청을 내지 않는다) |
| | `COMPANY_AUTOPART1_URL`·`COMPANY_AUTOPART1_KEY` | 회사 시스템 주소(설정의 기본값)·키 |
| | `NOWVIEW_ADMIN_KEY` | 관리 API 키 — 웹과 같은 값 |
| autopart1 `legacy/.env.local` | `AUTOPART1_LEGACY_KEY` | 회사 시스템 키 — 엔진 `COMPANY_AUTOPART1_KEY`와 같은 값 |
| `.env.local`(저장소 루트, 웹) | `NOWVIEW_ADMIN_PASSWORD` | 관리자 로그인 비밀번호 |
| | `NOWVIEW_ADMIN_SECRET` | 관리자 세션 쿠키 서명 |
| | `NOWVIEW_ADMIN_KEY` | 관리 API 키 — 엔진과 같은 값 |

운영계는 이 값들이 전부 `/etc/nowview.env` 하나에 있다(5장).

**NowView 설정**(엔진 DB, `/admin`에서만 고친다) — 회사(이름·설명·회사 시스템 주소), BPM 프로세스 → 회사·업무, 일꾼 토픽. 처음
뜰 때 기본값(가상 자동차 부품사, 장면 1~6 매핑, 토픽 `nowview`·`nowview-sc02`~`sc06`)을 적는다. 매핑·주소는 고치면 바로 쓰이고,
토픽은 엔진을 다시 띄워야 한다(승인된 일꾼이면 Center 쪽 토픽도 바꾼다). 공개 화면·API에는 나오지 않는다.

## 5. 실행 중에 일어나는 일

**실행 위치는 데모 실행마다 하나다**(`bpm.executor`). 만들 때·초기화할 때 데모 플레이어에서 고른다.

| | Center 서버 실행 (기본) | Studio 시험 실행 | 내장 (엔진 시험용 — 화면에서 고르지 않는다) |
|---|---|---|---|
| 누가 BPMN을 도나 | 서버 실행기 | Studio | 엔진 `chaeksas-core` |
| 누가 시작하나 | NowView — 원천 수신 때 `POST /jobs` 또는 접수 Bot 메시지 | 사람이 Studio에서 | 원천 수신 |
| 결재 답 | NowView 화면(대리 답) 또는 Center 결재함 | Studio 대화상자 — NowView 화면은 읽기만 | NowView 화면 |
| 진행을 NowView가 아는 방법 | 실행 기록 2초 폴링 | 일감이 알려 준 노드만 | 엔진 스냅샷 |
| 데모 플레이어 각본 | 된다(대리 답) | 안 된다 | 된다 |

**서비스 태스크(일감)** — 실행기·Studio가 Center에 일감을 올리면 엔진의 일꾼이 가져가 처리하고 결과를 돌려준다.

* 일꾼은 일감을 보낸 BPM 프로세스 id로 설정에서 업무를 찾는다. 매핑에 없으면 `not_found`로 거절한다.
* 일감의 `origin`(`run` = 서버 실행, `test` = Studio)이 실행 위치다. 데모 실행의 실행 위치와 다르면 `conflict`로 거절하고 묶지 않는다.
* 데모 실행은 입력 `demo_run_id`로, 바깥 실행은 첫 일감의 실행 id로 묶인다. 다른 실행이 오면 거절한다(정정본 뒤의 새 실행은 예외 —
  앞 실행을 이력으로 옮긴다).
* 업무 규칙 위반은 사유와 함께 `fail`이다(`forbidden`·`not_found`·`conflict`·`input_invalid`, 재시도 없음). 회사 시스템이 응답하지
  않으면 `dependency_down`(재시도)이다.
* 같은 일감이 다시 와도 결과를 다시 준다(멱등 저장소). 저장소는 메모리라 엔진이 다시 뜨면 빈다.

**사람 결재**

* 결재 담당자는 BPMN `chk:approval.assignees`의 **사람 이름**이다 — Center가 「담당자만 답한다」를 그것으로 막는다. 인수 결재는 배정
  기록이 돌려준 이름 변수를 쓴다.
* 결재의 업무 효과는 결재 바로 뒤의 **기록 서비스 태스크**가 낸다(`record_plan_review`·`record_risk_review`·`assign_follow_up`·
  `record_acceptance`). 화면에서 답하든 Center 콘솔에서 답하든 같은 길이다. 답한 사람은 결재 변수(`answered_by_as`)로 실려 온다.
* **화면 답 = 대리 답** — NowView가 먼저 검사하고(역할 403, 규칙 409·422 — 입력은 지우지 않는다), Center에서 그 결재를 찾아(최대
  30초) 행위자 이름으로 답한다.
* **기록이 거절되면 같은 결재로 돌아간다**(기록 태스크마다 오류 경계). 결재 폼에 사유(`error_message`)가 보이고 감사 이력에
  `answer_rejected`가 남는다. 거절된 답은 기록·업무를 남기지 않는다.
* 업무(`TASK-*`)는 폴러가 결재를 처음 볼 때 연다(대리 답이 먼저면 그때). Studio 실행은 기록 때 연다.

**고객계획 접수 가상 직원**

```
NowView 원천 수신 ──메시지 「고객계획접수」──▶ 접수 Bot autopart1.sc01-intake
                                              ├─ 원천마다 screen_customer_plan
                                              ├─ 감독자 일괄 결재(승인·반려, 의견 필수)
                                              ├─ 원천마다 record_intake_decision
                                              └─ 승인이면 원천마다 autopart1.sc01 위임 / 반려면 끝(원천 보완 요청)
```

* 감독자 이름은 그림에 없다 — 가상 직원 등록(업무 › 가상 직원)의 감독자가 입력 `감독자`로 들어온다. 가상 직원 없이 돌리면 시작하지 않는다.
* 접수 Bot의 일감은 데모 실행을 묶지 않는다. 묶는 것은 위임된 SC01의 첫 일감이다.
* 고객계획 화면의 「접수 가상 직원」 카드가 오늘 접수·승인 대기·기동된 SC01을 보이고, 감독자가 거기서 일괄 결재에 답할 수 있다.
* 데모 플레이어 각본은 일괄을 감독자로 대리 승인하고 진행한다(장면 1 각본·장면 2 이후 시작). 화면에서 손으로 할 때는 사람이 승인한다.

**원천 정정** — 보완 대기 중이면 정정본이 같은 실행에 메시지(`원천정정`, 상관 키 = 데모 실행 id)로 간다. 그 밖이면 앞 실행을 이력으로
옮기고 앞 작업을 거둔 뒤 새로 기동한다. 초기화도 앞 작업을 거둔다. Center 멱등 키에는 초기화 회차가 들어간다.

## 6. 그림을 고칠 때 지킬 것

* 서비스 호출의 `app_id`는 `nowview`, 프로세스에 `chk:process.extensions: [{"id": "nowview", "version": ">=0.1.0,<1"}]`를 둔다 — 빠지면
  Center가 그 실행의 일감을 받지 않는다. 정의를 1.0으로 올리면 이 범위도 올린다.
* 작업을 더하거나 입출력을 바꾸면 `chaeksas/nowview.extension.json`을 고치고 판을 올려 다시 서명·등록한다(같은 판·다른 내용은 거절).
  엔진 시험(`test_extension_definition_matches_the_bpmn_service_calls`, `test_manifest_covers_every_service_call_of_the_drawings`)이
  그림 ↔ 정의를 잠근다.
* 결재마다 `assignees`(사람 이름)와 `answered_by_as`·`answered_via_as`를 둔다. 역할표(`domain.NODE_ROLES`)와 어긋나면 시험이 잡는다.
* 결재 뒤 기록 태스크에는 오류 경계(`TASK_FAILED` → 같은 결재)를 단다.
* 그림을 바꾸면 Studio에서 패키지를 다시 내보내 배포한다. TS 토폴로지 사본(`tests/fixtures/sc0N-process.json`)은 엔진 시험이 다시
  만드는 명령을 알려 준다.

## 7. 운영계에 올릴 때

운영 서버(`www.nowview.work`)에도 같은 서버에 Chaeksas Center(127.0.0.1:8800)와 서버 실행기가 있다.

1. 운영 Chaeksas가 C15 판(Pull)이어야 한다 — 옛 판은 일감을 쌓지 않는다.
2. `scripts/deploy.sh --bootstrap` — `/etc/nowview.env`에 빠진 관리자 비밀(`NOWVIEW_ADMIN_PASSWORD`·`SECRET`·`KEY`)을 더한다.
3. 회사 시스템 시뮬레이터를 서버에 올린다 — **아직 배포 스크립트·systemd 유닛이 없다**(남은 일).
4. `scripts/deploy.sh`로 NowView를 올린다.
5. 운영 Center 콘솔에서 3장 1~4를 한다. `/etc/nowview.env`에 `CHAEKSAS_*`·`COMPANY_AUTOPART1_*`를 넣고 `systemctl restart nowview-engine`.
6. `/admin`(운영 비밀번호는 `/etc/nowview.env`)에서 요청 코드를 보고 운영 Center 콘솔 「일꾼 승인 대기」에서 승인한다.

## 8. 남은 일

* 실제 C15 판 Center + 서버 실행기 + Studio로 장면 1을 돌려 보지 않았다 — 3장을 마치면 한다.
* 일꾼 멱등 저장소가 메모리다 — 엔진이 다시 뜨는 사이 다시 온 일감은 한 번 더 돈다.
* 회사 시스템의 사용자 명단을 엔진이 아직 읽지 않는다(엔진 `domain.USERS`를 쓴다).
* 회사 시스템 시뮬레이터의 운영 배포.
* 관리자 로그인에 시도 횟수 제한이 없다.
* 장면 2~6을 `nowview` 확장·회사 이름 패키지로 옮기기.
