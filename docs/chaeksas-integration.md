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
│            패키지·키               │ 기동·답  │    진행 폴링)                     │ 쓰기 └──────────────────┘
└──────────────────────────────────┘        │  · 규칙 계산·경영 기록·설정(DB)     │
                                            ├──────────────────────────────────┤
                                            │ 웹 :3000 — 회사별 대시보드 · /admin │
                                            └──────────────────────────────────┘
```

* **연결은 늘 NowView에서 나간다.** Center도 회사 시스템도 NowView 주소·키를 모른다.
* **NowView는 고정 프로그램이다.** 일꾼이 제공하는 작업 목록은 기본 확장 하나(`external` — BPM 서비스 태스크의 External Service)이고 NowView 판과 함께 바뀐다. 어느 회사의 어느 BPM
  프로세스를 맡는지는 NowView **설정**(엔진 DB, 관리자 화면 `/admin`)이다.
* **업무 흐름은 BPMN 하나다**(`engine/processes/*.bpmn` — 원본은 Company1 리포의 `bpm/`, `scripts/sync-bpm.sh`로 가져온다). 같은 그림을 Studio·서버 실행기·엔진 내장 실행기(시험용)가 돈다.
* **숫자는 NowView 규칙 계산이 만든다.** Chaeksas는 순서·사람 결재·분기·인계를 쥐고, 회사 시스템은 자료와 확정 기록을 쥔다.

## 2. 무엇이 어디에 등록되나

| 무엇 | 어디서 (Center 콘솔 http://localhost:8501 의 왼쪽 메뉴) | 값 |
|---|---|---|
| 일꾼 | **콘솔이 아니다** — Center 일꾼 폴더에 일꾼 파일을 두고 Center를 다시 띄운다(Chaeksas ADR-0121) | `worker.consumer.json`(이름 `worker`·토픽 `external`·토큰 해시) |
| 기본 확장 `external`(일꾼 작업 목록) | **콘솔이 아니다** — 일꾼이 뜰 때 올린다(`PUT /consumers/self/extension`) | `chaeksas/external.extension.json` 0.7.0(장면 1~7) |
| BPM 패키지 | Studio 「파일 › Center로 올리기」 → 운영 현황 › **BPM 프로세스 현황**에서 승인 → 배포·자원 › **배포** | `company1.sc01`~`company1.sc07` — 그림 원본은 Company1 리포 `bpm/company1/` |
| Center 키 둘 | 관리 › **Center API 키** › 「새 키...」 | 종류 「연동용」 하나, 「대리 답용」 하나 → `engine/.env.local` |
| BPM 프로세스 → 회사·업무 | NowView `/admin` 설정 | 기본값에 이미 있다 — 손댈 것 없음 |

장면 1~6 모두 `external`로 옮겼다(장면 2는 `company1.sc02` 0.2.0 — 확장 `>=0.2.0`, 장면 3은 `company1.sc03` 0.3.0 — `>=0.3.0`,
장면 4는 `company1.sc04` 0.4.0 — `>=0.4.0`, 장면 5는 `company1.sc05` 0.5.0 — `>=0.5.0`, 장면 6은 `company1.sc06` 0.6.0 — `>=0.6.0`). 장면 7은 처음부터 `external`이다(`company1.sc07` 0.7.0 — `>=0.7.0`).
업무별 옛 확장(`nowview-scN`)은 하나도 남지 않았다.

## 3. 등록 순서 (로컬 Center)

**준비**
* 회사 시스템: Company1 리포에서 `scripts/stack.sh start`. NowView: `npm run stack:start`(엔진 → 웹).
* Center 콘솔 `http://localhost:8501`에 **관리자 계정**으로 들어간다(패키지 승인은 관리자만 된다).
* Studio를 띄우고 이 Center에 연결해 둔다(Studio의 「Center로 올리기」가 그 연결로 올린다).

**1. NowView 키를 Center 폴더로** (NowView → Center) — 콘솔 발급·요청 코드 승인이 없다(Chaeksas ADR-0122)

NowView가 Center에 쓰는 키는 셋이다 — 일꾼(일감 가져가기·끝내기)·연동용(실행 기동·메시지·진행 읽기)·대리 답용(결재 읽기·답).
**셋 다 설치가 짓는다** — Center를 띄운 뒤 콘솔에서 발급받아 옮겨 적지 않는다(2026-11-01 사용자 결정). 원문은 엔진만 아는 보관
파일(`engine/.consumer/keys.json`, gitignore, 0600)에 있고, Center 폴더에는 해시만 간다.

1. 키를 짓고 Center 폴더에 해시 파일을 쓴다 — 로컬 compose의 Center는 **그 compose 파일 옆의** `deploy/consumers/`가 그 폴더다
   (`CHK_CENTER__CONSUMERS_DIR`, 다른 곳이면 `CHK_CENTER__CONSUMERS_HOST_DIR`). 지금 로컬 Center는 Chaeksas worktree
   `.claude/worktrees/local-center`에서 돈다:
   `cd engine && uv run python -m app.worker_file ~/Workspace/Chaeksas/.claude/worktrees/local-center/deploy/consumers`.
   없는 키만 짓는다(다시 돌려도 키는 그대로, 새로 지으려면 `--rotate`). 생기는 파일:
   `worker.consumer.json`(이름 `worker`·토픽 `external`·토큰 해시) · `nowview-integration.key.json` · `nowview-relay.key.json`
   (이름·키 종류·토큰 해시).
2. Center를 다시 띄운다. 콘솔 **배포·자원 › 리소스**의 「일꾼 폴더」에 일꾼 `worker`와 두 키가 보이면 된다. 확장 정의 `external`은
   3에서 엔진(일꾼)이 뜰 때 올린다. 빼려면 파일을 지우고 Center를 다시 띄운다(그 키가 폐기된다).

> **Chaeksas 쪽이 아직이다**(2026-11-01) — 지금 Center는 `*.consumer.json`(일꾼)만 읽고 `*.key.json`(연동용·대리 답용)은 읽지
> 않는다. Chaeksas에 요청했고, 그 판이 오기 전에는 콘솔 **관리 › Center API 키**로 발급한 키를 `engine/.env.local`의
> `CHAEKSAS_INTEGRATION_KEY`·`CHAEKSAS_RELAY_KEY`에 둔다(환경 변수가 보관 파일을 이긴다).

**2. BPM 패키지 올리기·승인·배포** (Studio → Center 콘솔)
1. Studio에서 Company1 리포의 `bpm/company1/company1.sc01/process/sc01.bpmn`을 연다 → 메뉴 **파일 › Center로 올리기**.
2. Center 콘솔 **운영 현황 › BPM 프로세스 현황**에서 `company1.sc01` 줄의 「승인」 칸에서 **승인**.
3. **배포·자원 › 배포** › **새 배포...** → 「BPM 프로세스@버전 (승인된 것)」에서 `company1.sc01@…`를 고르고 **고르기** → 실행기를
   고르고 **배포**.
**3. 일꾼 켜기** (NowView)
1. `engine/.env.local`에 `CHAEKSAS_CENTER_URL`이 있고 `WORKER_CONSUMER=off` 줄이 없어야 한다.
2. `npm run stack:restart engine`. 엔진 로그(`npm run stack:logs engine`)에 「확장 external 0.1.2판을 올렸다」·「일꾼이 토픽 external를
   가져간다」가 나오면 된다 — 승인 단계는 없다.

**4. 확인** (NowView)
1. `/admin`(비밀번호는 저장소 루트 `.env.local`의 `NOWVIEW_ADMIN_PASSWORD`)에서 일꾼이 「일감을 가져가는 중」, 「연결」의 Center
   연동용 키·대리 답용 키가 「있음」, 회사 시스템이 「응답함」인지 본다.
2. 회사 화면 `http://localhost:3000/c/company1/sc01`의 데모 플레이어에서 실행 위치 **Center**로 초기화하고 장면 1을 돌린다.

**키·토픽을 바꿀 때** — 1의 명령(키를 바꾸려면 `--rotate`)으로 파일을 다시 짓고 Center와 엔진을 다시 띄운다. 확장 정의를 고치면 판을 올린다(같은 판·
다른 내용은 Center가 409로 거절한다). Center는 해시가 바뀌면 옛 토큰을 폐기하고,
폐기된 토큰은 되살아나지 않는다.

## 4. NowView 환경과 설정

**환경 파일**(비밀 — git에 넣지 않는다)

| 파일 | 값 | 쓰임 |
|---|---|---|
| `engine/.env.local` | `CHAEKSAS_CENTER_URL` | Center 주소(일꾼·기동·대리 답 모두) |
| | `CHAEKSAS_SC01_PACKAGE` | 장면 1 패키지 id(기본 `company1.sc01`) |
| | `WORKER_CONSUMER_TOKEN`·`CHAEKSAS_INTEGRATION_KEY`·`CHAEKSAS_RELAY_KEY` | 두지 않는다 — 키는 보관 파일에 있다. 있으면 보관 파일을 이긴다(콘솔 발급 키를 쓸 때) |
| | `WORKER_CONSUMER=off` | 일꾼을 끈다 |
| | `COMPANY_COMPANY1_URL`·`COMPANY_COMPANY1_KEY` | 회사 시스템 주소(설정의 기본값)·키 |
| | `NOWVIEW_ADMIN_KEY` | 관리 API 키 — 웹과 같은 값 |
| `engine/.consumer/keys.json` | `worker`·`integration`·`relay` | 설치(`python -m app.worker_file`)가 지은 키 원문(0600). 일꾼 — 일감 가져가기·끝내기 · 연동용 — 기동(`POST /jobs`·`/messages`)·진행 읽기·작업 거두기 · 대리 답용 — 결재 읽기·답(`X-BPM-On-Behalf-Of` = 행위자 이름, 옛 Center를 위해 `X-CHK-`도 싣는다) |
| company1 `legacy/.env.local` | `COMPANY1_LEGACY_KEY` | 회사 시스템 키 — 엔진 `COMPANY_COMPANY1_KEY`와 같은 값 |
| `.env.local`(저장소 루트, 웹) | `NOWVIEW_ADMIN_PASSWORD` | 관리자 로그인 비밀번호 |
| | `NOWVIEW_ADMIN_SECRET` | 관리자 세션 쿠키 서명 |
| | `NOWVIEW_ADMIN_KEY` | 관리 API 키 — 엔진과 같은 값 |

운영계는 이 값들이 전부 `/etc/nowview.env` 하나에 있다(5장).

**NowView 설정**(엔진 DB, `/admin`에서만 고친다) — 회사(이름·설명·회사 시스템 주소), BPM 프로세스 → 회사·업무, 일꾼 토픽. 처음
뜰 때 기본값(가상 자동차 부품사, 장면 1~7 매핑, 토픽 `external` 하나)을 적는다. 매핑·주소는 고치면 바로 쓰이고,
토픽은 엔진을 다시 띄워야 한다(승인된 일꾼이면 Center 쪽 토픽도 바꾼다). 공개 화면·API에는 나오지 않는다.
**기본값은 설정이 없을 때만 적힌다** — 새 업무가 더해진 판(장면 7)을 이미 설정이 저장된 DB에 올리면 매핑이 없어 그 업무의 일감이
`not_found`로 거절된다. `/admin`(또는 `PUT /admin/config`)에서 `company1.sc07 → 7`을 더한다.

## 5. 실행 중에 일어나는 일

**실행 위치는 데모 실행마다 하나다**(`bpm.executor`). 만들 때·초기화할 때 데모 플레이어에서 고른다.

| | Center 서버 실행 (기본) | Studio 시험 실행 | 내장 (엔진 시험용 — 화면에서 고르지 않는다) |
|---|---|---|---|
| 누가 BPMN을 도나 | 서버 실행기 | Studio | 엔진 `chaeksas-core` |
| 누가 시작하나 | NowView — 원천 수신 때 `POST /jobs` | 사람이 Studio에서 | 원천 수신 |
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

**가상 직원(접수 Bot)은 없다**(2026-11-01 사용자 결정) — 원천을 받으면 NowView가 `company1.sc01`을 바로 기동하고, 그림은 원천 자동
검증부터 한다. 예전의 접수 Bot(`company1.sc01-intake`)·감독자 일괄 결재·「접수 가상 직원」 카드는 걷었다.

**원천 정정** — 보완 대기 중이면 정정본이 같은 실행에 메시지(`원천정정`, 상관 키 = 데모 실행 id)로 간다. 그 밖이면 앞 실행을 이력으로
옮기고 앞 작업을 거둔 뒤 새로 기동한다. 초기화도 앞 작업을 거둔다. Center 멱등 키에는 초기화 회차가 들어간다.

## 6. 그림을 고칠 때 지킬 것

* 서비스 호출의 `app_id`는 `external`, 프로세스에 `chk:process.extensions: [{"id": "external", "version": ">=0.1.0,<1"}]`를 둔다 — 빠지면
  Center가 그 실행의 일감을 받지 않는다. 정의를 1.0으로 올리면 이 범위도 올린다.
* 작업을 더하거나 입출력을 바꾸면 `chaeksas/external.extension.json`을 고치고 판을 올려 다시 서명·등록한다(같은 판·다른 내용은 거절).
  엔진 시험(`test_extension_definition_matches_the_bpmn_service_calls`, `test_manifest_covers_every_service_call_of_the_drawings`)이
  그림 ↔ 정의를 잠근다.
* 결재마다 `assignees`(사람 이름)와 `answered_by_as`·`answered_via_as`를 둔다. 역할표(`domain.NODE_ROLES`)와 어긋나면 시험이 잡는다.
* 결재 뒤 기록 태스크에는 오류 경계(`TASK_FAILED` → 같은 결재)를 단다.
* 그림을 바꾸면 Studio에서 패키지를 다시 내보내 배포한다(원본은 Company1 `bpm/`, 엔진 사본은 `scripts/sync-bpm.sh`).

## 7. 운영계에 올릴 때

운영 서버(`www.nowview.work`)에도 같은 서버에 Chaeksas Center(127.0.0.1:8800)와 서버 실행기가 있다.

1. 운영 Chaeksas가 C15 판(Pull)이고 일꾼 폴더(ADR-0121)가 있는 판이어야 한다 — 옛 판은 일감을 쌓지 않고 폴더를 읽지 않는다.
2. `scripts/deploy.sh --bootstrap` — `/etc/nowview.env`에 빠진 관리자 비밀(`NOWVIEW_ADMIN_PASSWORD`·`SECRET`·`KEY`)을 더한다.
3. 회사 시스템 시뮬레이터를 서버에 올린다 — **아직 배포 스크립트·systemd 유닛이 없다**(남은 일).
4. `scripts/deploy.sh`로 NowView를 올린다.
5. 서버에서 3장 1의 명령으로 키를 짓고 운영 Center 폴더에 파일을 쓴 뒤 Center를 다시 띄운다(보관 파일은 서버의
   `engine/.consumer/` — 배포 rsync가 빼는 자리다. 배포 스크립트에 아직 이 단계가 없다 — 남은 일).
6. 운영 Center 콘솔에서 3장 2를 한다. `/etc/nowview.env`에 `CHAEKSAS_CENTER_URL`·`COMPANY_COMPANY1_*`를
   넣고 `systemctl restart nowview-engine`.

## 8. 남은 일

* 실제 C15 판 Center + 서버 실행기 + Studio로 장면 1을 돌려 보지 않았다 — 3장을 마치면 한다.
* 일꾼 멱등 저장소가 메모리다 — 엔진이 다시 뜨는 사이 다시 온 일감은 한 번 더 돈다.
* 회사 시스템의 사용자 명단을 엔진이 아직 읽지 않는다(엔진 `domain.USERS`를 쓴다).
* 회사 시스템 시뮬레이터의 운영 배포.
* `scripts/deploy.sh`가 일꾼 파일을 짓고 Center를 다시 띄우는 단계(지금은 3장 1을 손으로 한다).
* 장면 2~6을 `external`로 옮기기 전까지 그 장면들의 Center 실행은 서비스 태스크에서 멈춘다(일꾼이 옛 토픽을 맡지 않는다).
* 관리자 로그인에 시도 횟수 제한이 없다.
* 장면 2~6을 `external` 확장·회사 이름 패키지로 옮기기.
