# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
npm run dev        # 개발 서버 (Turbopack)
npm run build      # 프로덕션 빌드 — TypeScript 타입 검사를 포함한다
npm run lint       # eslint (flat config: eslint.config.mjs)
npm run test       # Vitest 1회 실행
npm run test:watch # Vitest 감시 모드
npm run start      # 빌드 산출물 실행
```

**단일 테스트 실행**

```bash
npx vitest run tests/dashboard.test.ts             # 파일 하나
npx vitest run tests/dashboard.test.ts -t "미산출"   # 이름으로 하나만
```

**BPM 엔진 (Python · `engine/`)**

```bash
cd engine
uv sync
uv run uvicorn app.main:app --port 8077 --reload   # http://localhost:8077/docs  (키: --env-file .env.local)
uv run pytest                                      # SQLite만, LLM 제외 (Postgres 시험은 skip)
uv run pytest -m llm                               # ollama 실호출 (OLLAMA_URL 필요, 약 100초)
uv run ruff check .
```

**가상 회사 시스템 (Company1 리포)** — 가상 자동차 부품사의 회사 시스템(기간계 :8191 · 사이트 API :8190 · 웹 :3100)과
업무 BPMN 원본(`bpm/`)은 별도 리포 `../Company1`에 있다. 거기서 `scripts/stack.sh start`로 띄운다. 엔진은 기간계를 부른다
(`engine/.env.local`의 `COMPANY_COMPANY1_URL`·`COMPANY_COMPANY1_KEY` = company1 `legacy/.env.local`의 `COMPANY1_LEGACY_KEY`).

```bash
scripts/sync-bpm.sh         # company1 bpm/의 BPMN을 engine/processes/로 가져온다
scripts/sync-scenarios.sh   # company1 scenarios/의 각본을 engine/scenarios/로 가져온다 (엔진 시험 전용 각본 실행기가 읽는다)
```

**시연은 회사 사이트가 몬다**(2026-11-03, `docs/role-split.md` §5) — 세계(= 데모 실행) 만들기·초기화·시계·원천 보내기·결재·
명령(착수·회의 기록·Agent 요청 …)·자동 모드는 Company1 사이트(:3100 `/demo`·직원 결재 화면)에서 한다. 업무 화면(`/work/{회차}/sc0N`)도
사이트에 있다. NowView 웹은 회사 목록·회사 대시보드·관리자뿐이고(2026-11-03 4단계 — 장면 화면을 걷었다),
엔진은 기간계를 2초마다 읽어 따라간다(`engine/app/follower.py`). 엔진의 장면 쓰기 HTTP 경로는 **엔진 시험 전용**이다
(`NOWVIEW_TEST_INPUTS=1` — `tests/conftest.py`가 켠다. 아니면 405).

**로컬 프로세스 제어 (웹 · 엔진 · DB)**

```bash
npm run stack:start            # 엔진 → 웹 순서로 띄운다 (회사 시스템은 Company1 리포에서) (db는 별도: stack:start db)
npm run stack:status
npm run stack:restart engine
npm run stack:stop             # 시작과 반대 순서로 내린다
npm run stack:logs engine 80
```

`scripts/stack.sh`가 그 일을 한다. **수동으로 띄우고 죽이다가 두 번 망가뜨려서 만든 것이다:**

* **`start`는 멱등이다.** 포트가 이미 잡혀 있으면 두 번째를 띄우지 않는다 — 실제로 중복
  기동으로 프로세스가 연결이 쌓인 채(`Recv-Q`) 먹통이 됐다.
* **종료는 리스닝 포트로 PID를 찾는다.** `pkill -f "uvicorn app.main:app"`은 **자기 셸의
  명령줄까지 매치**해 스스로를 죽인다(exit 143/144). 실제로 그랬다.
* **소유는 PID가 아니라 프로세스 그룹으로 판정한다.** `setsid`로 띄우면 기록되는 것은
  래퍼(`uv run`)의 PID인데 포트를 쥐는 것은 그 아래 uvicorn 워커다 — PID로 비교하면
  우리가 띄운 것도 "외부"로 오판한다. 종료도 그룹째 보낸다(`--reload`는 reloader와 워커가
  따로 있어 부모만 죽이면 자식이 포트를 쥐고 남는다).
* **우리가 띄우지 않은 프로세스는 건드리지 않는다.** IDE 프리뷰가 3000을 쓰고 있을 수
  있다 — `--force`가 있어야 내린다.
* **`start engine`은 `--timeout-graceful-shutdown 3`을 준다.** 브라우저가 SSE로 붙어 있으면 uvicorn이
  그 연결을 기다리며 **reload가 끝나지 않았다** — 엔진이 응답 없이 멈춘 것처럼 보였고 TERM에도 안 죽어
  KILL됐다. 운영 유닛(5.4)과 같은 이유다. `.claude/launch.json`도 같다.
* `start engine`은 **기본이 `--reload`다.** 없이 띄워 두고 코드를 고쳐 "왜 반영이 안 되나"를
  두 번 헤맸다.

**함정**: `wait_until 15 ! port_open 8077`처럼 쓸 수 없다. `!`는 예약어라서 소스 텍스트에서만
부정으로 동작하고, 확장된 인자로 넘기면 `!`라는 **명령**을 찾는다 — 대기가 절대 성공하지
않아 매번 KILL로 넘어가고 포트가 이미 비었는데도 실패로 보고했다. `port_closed` 헬퍼를 뒀다.

**전체 스택 (앱 · 엔진 · Postgres)**

```bash
docker compose up --build   # 앱 :3000 · 엔진 :8077 · Postgres :55432
```

* `docker compose`는 **Postgres 백엔드**로 돈다. 로컬 `uv run`은 기본이 SQLite다.
* **포트가 이미 쓰이고 있으면 컨테이너가 포트 매핑 없이 만들어질 수 있다.** 그 상태로
  `up`을 다시 해도 compose가 기존 컨테이너를 재사용해 계속 접속이 안 된다 —
  `docker compose down` 후 다시 올려야 한다. 실제로 dev 서버가 3000을 잡고 있어 겪었다.
* 두 백엔드를 모두 검증하려면:
  `TEST_DATABASE_URL=postgresql://nowview:nowview@localhost:55432/nowview uv run pytest` (869개)

* **`--reload`를 빼면 코드 수정이 반영되지 않는다.** 실제로 그 때문에 Pydantic 별칭
  변경이 적용되지 않아 422를 받고 원인을 한참 찾았다.
* 앱과 엔진은 별개 프로세스다. `.claude/launch.json`에 `nowview-engine`으로 등록해 두었다.
* `npm run test`는 TS만 돈다 — 엔진 테스트는 별도다(CI에서는 둘 다 돈다).

* **타입 검사 단독 실행**: `npx tsc --noEmit`. `npm run build`가 타입 검사를 겸하므로 별도 `typecheck` 스크립트는 두지 않았다. `tsconfig.json`의 `include`가 `**/*.ts`라 테스트도 함께 검사된다.
* **Shadcn 컴포넌트 추가**: `npx shadcn@latest add <component>` → `components/ui/`에 생성된다.

## Scaffolding Notes (한 번만 읽으면 되는 함정)

* **`package.json`의 `name`은 `nowview`** 다. 디렉토리명 `NowView`는 npm 명명 규칙(대문자 불가) 위반이라 `create-next-app .`이 거부한다. 재스캐폴딩이 필요하면 소문자 하위 디렉토리에 생성한 뒤 내용을 올려야 한다.
* **`AGENTS.md`는 `next dev`가 자동 생성·재삽입한다.** Next.js 16 자체 에이전트 규칙 블록이며, 지워도 되살아난다. 커밋에 포함시켜 트리를 깨끗하게 유지한다. 이 프로젝트의 지침은 `AGENTS.md`가 아니라 이 파일이다.
* **Tailwind v4에는 `tailwind.config.ts`가 없다.** 테마는 `app/globals.css`의 `@theme`/CSS 변수로 설정한다. Shadcn도 `components.json`에서 `tailwind.config: ""`로 이를 반영한다.
* **React Flow·Recharts·Zustand는 걷었다**(2026-11-03 4단계 — 장면 화면과 함께). 캔버스(`markerEnd`의 CSS 변수, 숨겨진
  패널에서 측정이 끝나지 않음)·차트(커스텀 `shape` + 애니메이션 `height: 0`, `<Cell radius>`, 커스텀 `tick`)의 함정은 git 이력의
  이 절에 있다(`79f6ea9` 이전). 다시 들이면 그 함정부터 본다.
* **테마 의존 UI를 `useState`+`useEffect`(mounted 플래그)로 그리면 lint가 막는다** —
  `react-hooks/set-state-in-effect`. 적용 테마를 렌더 결과에 반영하는 대신 `dark:` 변형(CSS)으로
  전환하면 마크업이 양쪽 테마에서 동일해져 hydration 불일치도 같이 사라진다.
  `components/theme-toggle.tsx`가 그 패턴이다(`resolvedTheme`은 클릭 시점에만 읽는다).

---

## 1. Project Overview
* **Project Name**: NowView (INNONOW Management Reference Model Pilot Web Platform)
* **Description**: 매출 약 1조원 규모 가상 자동차 부품사를 대상으로, 체계화된 Management Framework 및 BPM 프로세스 위에서 사람과 AI Agent가 협업하는 경영 운영 플랫폼 프로토타입.
* **NowView의 역할**(2026-10-31 사용자 정의): **회사 사이트가 아니다.** 둘이다 — ① **워커(Worker)**: Chaeksas Center에 올린 **회사별 BPM
  프로세스의 서비스 태스크(External Service)를 수행한다**(C15, `engine/app/consumer.py`), ② **대시보드(Dashboard)**: **N개 회사의 운영
  현황**(`/` 회사 목록 → `/c/{회사}`). **NowView의 본체는 대시보드다** — 워커는 대시보드가 보일 운영 기록을 BPM 진행에서 받아 오는 몫이다.
  가상 자동차 부품사(가칭, id `company1`)는 그 회사들 중 하나이고, 그 회사의 업무(장면 1~7)를 BPM 프로세스로 정의해 대시보드로
  운영 현황을 보인다. **NowView는 BPM 패키지와 함께 배포되는 고정 프로그램이다**(2026-10-31 결정, `docs/worker-interfaces.md`
  §1) — 워커의 작업 목록은 **기본 확장 `external` 하나**(파일 `chaeksas/external.extension.json`, 토픽도 `external`, NowView 판과 함께 바뀐다 —
  BPM 서비스 태스크의 External Service다. 일꾼이 뜰 때 Center에 올리는 기본 확장이라 Center 콘솔에서 등록·해제하지 않는다)이고, 어느 회사의 어느 BPM
  프로세스를 맡는지는 **설정**(엔진 DB `nowview_config`, `app/config.py`)이다. 일꾼은 일감을 보낸 BPM 프로세스 id(`company1.sc01`)로
  설정에서 회사·업무를 찾는다. **등록은 공개하지 않는다** — 공개 화면·API(`/api/engine/companies`)는 회사 이름·설명·업무 번호뿐이고,
  BPM 프로세스 매핑·토픽·회사 시스템 주소·일꾼 상태(요청 코드)는 **관리자 모드 `/admin`**(로그인)에만 있다. 업무(장면) 목록은
  코드다(`lib/companies.ts`의 `SCENES` = 엔진 `SCENE_WORKS`). **장면은 하나씩 옮겼다** — 장면 1~6 모두 `external` 확장이다(2026-11-02 장면 6을 마지막으로
  옮겼다). 장면 7은 처음부터 `external`(0.7.0)로 만들었다(2026-11-03). 옮길 때마다 그 장면을 Center에 다시 등록하고 실행·시험·수정을 반복했다.
* **세 서버로 나눈다**(2026-11-03 사용자 결정, `docs/role-split.md`) — BPM 서버(Center)는 흐름·결재, NowView는 일꾼·외부 서비스
  연계·N개 회사 대시보드·관리자, 회사 사이트(Company1)는 **업무에 관한 것 전부**(직원 업무함·결재·업무 판단 화면·회사 자료·업무 설명·
  시연 조작). **경영 기록의 원본은 회사 시스템(기간계)이다** — 아래 10-31의 「경영 기록은 NowView 몫」을 바꿨다(규칙 계산은 그대로
  NowView). 회사 사이트는 NowView를 부르지 않는다. NowView의 장면 화면·플레이어·해설은 걷었다(4단계, 그 문서 §4) — NowView 웹에는
  회사 목록·**회사 대시보드**(업무별 BPM 진행·일꾼 일감·핵심 지표, 사이트 업무 화면으로 링크 — 4.6)·관리자만 있다.
* **일꾼은 BPM 프로세스 ↔ 회사 시스템의 중계자다**(2026-10-31 확정, `docs/worker-interfaces.md`). 회사의 자료·확정 기록(조직·
  계획·실적·원가·고객계획 원천·원천 확인 상태)은 **회사 시스템**에 있고, **규칙 계산·경영 기록(이슈·업무·검토·Agent)은 NowView**
  몫이다. 가상 자동차 부품사의 회사 시스템은 **별도 리포 Company1의 기간계**(:8191)이고 엔진이 `app/company.py`로 읽고 적는다.
  연결은 늘 NowView에서 나간다(Center도 회사도 NowView 주소를 모른다). 지금 장면 1·2가 이 길이다(장면 2는 구매 마스터·
  단가 인상 요청 수신함·요청 확인 상태·원가 버전 C02-APP01, 2026-11-01).
* **지금 구현된 것**: 대표 시나리오 1의 **장면 1(SC01)** — 고객 생산계획 변경을 감지해 현업 통제와 Management Review로 인계하기까지. 업무 흐름은 **Chaeksas BPM**이 BPMN을 해석해 돌린다(4.5). 원천을 받으면 SC01이 바로 시작된다 — 예전의 고객계획 접수 가상 직원(접수 Bot·감독자 일괄 결재)은 2026-11-01에 걷었다(4.5).
  **장면 2(SC02)** — 외주 공통부품 단가 인상 요청을 접수·분석·1차 협상·기안·순차 승인(팀장 → 임원 → 금액 기준 대표)하고 원가 버전을 등록해, 장면 1 물량 감소와 함께 경영관리에 인계하기까지(4.16). 장면 1과 **같은 데모 실행**을 잇는다. **Studio 시험 실행·Center 서버 실행**에서 돈다(기본 확장 `external` 0.2.0, 2026-11-01 옮김).
  **장면 3(SC03)** — 장면 1 물량 감소와 장면 2 승인 단가를 한 수익성 검토건(MR-2706-01)에 잇고, 통합 분석 → 영업·구매·생산
  확인 → 쟁점 판단 → 자료 확정 → 경영관리 임원 주재 수시회의(결론·후보 포함/제외) → 분석과제 AT31~34 배정·인수 → 장면 4 인계
  (HANDOFF31)까지(4.17). 같은 데모 실행을 잇고 **Studio·Center 실행**에서 돈다(기본 확장 `external` 0.3.0, 2026-11-02 옮김).
  **장면 4(SC04)** — 장면 3 분석과제 AT31~34의 결과를 받아 비용·중복을 검증하고, 담당 임원들이 우선 실행안 3개를 공동 제안하고,
  대표 주재 월간회의(MT41)의 질의로 판단본(DEC41-v2)을 확정한 뒤 대표가 책임·예산 한도·두 기한·조건을 포괄 승인(APR41-v1)하고,
  전체·개별 책임자가 실행과제 ACT41~43·조건·지시를 인수하면 장면 5로 인계(HANDOFF41)까지(4.18). 같은 데모 실행을 잇고 **Studio·
  Center 실행**에서 돈다(기본 확장 `external` 0.4.0, 2026-11-02 옮김).
  **장면 5(SC05)** — 장면 4가 조건부 승인한 ACT42(긴급구매 축소)를 상세 실행계획(PL51-v1 → 범위 내 변경 v2)으로 확정·확인하고,
  CON41·SUP41 이행 확인과 품의(REQ51·OP51) 뒤 9/1 운영 적용, 생산 변경 공유·구매 대응(정상 CH51 · 긴급 CH52), 9월 초기 결과,
  월간 Rolling 운영계획(OPL51~53)과 공식 Forecast(FC50 → FC51) 작성·부서 확인·대표 승인·게시를 거쳐 후속 책임을 넘기기까지
  (HANDOFF51, 4.19). ACT41·43은 요약만 한다. 같은 데모 실행을 잇고 **Studio·Center 실행**에서 돈다(기본 확장 `external` 0.5.0, 2026-11-02 옮김 — 실행 품의·예산 원장·공식 전망은 회사 기록).
  **장면 6(SC06)** — 과제 완료 후 차 분기(2027 Q4)의 완료·성과 검토. Q4 자료를 적재하고(숫자는 규칙 계산), **확인 절차**(담당 임원
  성과 근거 확인 생산 ∥ 구매 → 경영관리 종합 확인 → 보고 결론 → 보고본 확정 → 대표 보고)를 BPM으로 돌린 뒤, 확인된 보고본 RPT61-v1을
  2028-01-14 11:00에 **조회**한다(U601 요약 → ACT42 차이 상세 → U602 보고 요약, 두 화면·세 동작). Q4 기대 91.8 → 확인 87.0백만원
  (−4.8), ACT42 30.6 → 25.8, 운영 보완 FUP61·추가 검토 발의 PROP61까지(4.20). 같은 데모 실행을 잇고 **Studio·Center 실행**에서 돈다
  (기본 확장 `external` 0.6.0, 2026-11-02 옮김 — 2026-10-28 사용자 요청으로 확인 절차를 BPM으로 돌렸다. 기대 효과의 기준인 공식
  전망 FC51은 회사 기록이라 적재 때 회사에서 읽어 대조한다).
  **장면 7(SC07)** — 실제 경험을 관리모델 개선으로 연결(Management Evolution). 장면 6에서 사람이 바로잡은 원인 판단(AG62 → PO61-1103,
  주담당 공란이지만 유효 대행이 10:00 확인 · 정상 공급 11/16 > 요구 11/14)을 개선건 IMP71로 적재하고, **확인·적용 절차**(검증 TS71-v1 → 구매
  임원 확인 CF71 → 경영관리 임원 확인 CF72 → 운영담당 설정 반영 CFG71 → 경영관리 담당 설정 확인 → 후속 점검)를 BPM으로 돌린 뒤 U701
  한 화면 두 동작(개선 전후 → 검증·적용)을 **조회**한다. 끝은 「운영 설정 반영 확인 · 운영 실행 미확인」(ST707)이다(4.21). 같은 데모
  실행을 잇고 **Studio·Center 실행**에서 돈다(기본 확장 `external` 0.7.0 — 회사 시스템에 적는 것은 없다).
  **시나리오 2(납기·OTD) 장면 1** — 공통 플랫폼(`docs/platform.md` — 업무설계서 v0.3·화면시연·데이터기본설계 v0.2.2)의 첫 업무.
  구매 입고예정 개정 하나 = BPM 실행 하나(`company1.s2.sc01`, 결재 없음): Y01 경보 판정 → **공통 BPM `platform.case-intake` 호출**
  (Case 연결 → A01 영향 분석(S 90분·R 150분) → 장면 2 N03A 인계, `docs/platform.md` §5)(`docs/s2/sc01.md`, 2026-11-04 · 호출 구조 11-05). 업무 번호 **21**(시나리오 2 장면 N = 20 + N), 공통 기록 종류(`event`·`alert`·`case`·
  `analysis`·`handoff`·`dashboard`)를 기간계에 적고, 납기 상황판(UI-D01)은 NowView 대시보드, Case 화면(UI-B02)은 회사 사이트다.
  **시나리오 2 장면 2(정형통제 실행과 주문별 분기)** — 장면 1 인계(HAND-01)에서 사이트 「장면 열기」로 `company1.s2.sc02`를 기동:
  **공통 BPM `platform.case-plan` 호출**(A03 수행계획 제안 → Y01 위임·필수 확인 검사 → 적용, 구성 승인 없음) → A02 변경안 →
  **생산관리 책임자(H03) 확인 결재 한 번** → 기간계 생산계획 저장소에 주문 행마다 실행키로 반영 → 저장소 재조회 대조(미반영 확인분만
  다시) → 주문별 재평가(S +60분 관찰 · R −30분 운송 확인) → HAND-02(장면 3 N09)(`docs/s2/sc02.md`, 2026-11-05). 업무 번호 **22**,
  데이터는 장면 1~4가 같은 `SYN-S2-SC04-v0.4`(앞 22개 시트는 v0.3과, 앞 15개는 v0.2와, 앞 7개는 v0.1과 셀 단위로 같다).
  **시나리오 2 장면 3(잔여 납기 위험의 경영검토와 대응 합의)** — 장면 2 인계(HAND-02, COM-R만)에서 「장면 열기」로 `company1.s2.sc03`:
  **같은 공통 BPM `platform.case-plan`을 다시 호출**(수행계획 v2 — v1 완료 항목 보존 + U06 기존 운송 문의 참조 · 조건부 U07) → 출하팀의
  **기존 운송 문의(기간계 원업무 W-TRAN-R)를 참조로 연결**(새 문의 0건) → 회신·고객 확인이 없으면 메시지 「사건근거」 대기(세계 따라가기가
  기간계의 새 근거를 보면 보낸다, `no_receiver`면 폴러가 다시) → A01 전량 대안 비교(정기차 −30분·0원 / 긴급 3대 +15분·120만원) →
  **담당 팀장(H03) 권고·재보고** 결재(한도 100만원 초과 20만원 → ESC-03·U07, 같으면 전결 범위로 끝) → **생산총괄 임원(H05) 결정** 결재
  (근거가 바뀌었으면 다시 비교) → **출하 담당자(H04) 과제 인수** 결재 → HAND-03(`docs/s2/sc03.md`, 2026-11-05). 업무 번호 **23**.
  사람 결재 셋은 공통 BPM에 두지 않았다 — BPM 서버 실행기가 호출 활동 안의 결재를 Center에 올리지 않는다.
  **시나리오 2 장면 4(실행 결과 확인과 관리기준 개선)** — 장면 3 인계(HAND-03)에서 「장면 열기」로 `company1.s2.sc04`(공통 BPM 호출 없음 —
  기준 개선은 별도 개선 건 U09라 사건 수행계획을 바꾸지 않는다): 회사 시스템의 **실행 증빙**(예약 BOOK-R·고객 인수 POD-S·POD-R·정산
  SET-S·SET-R, 기간계 `sim/execution-evidence`)을 결정과 대조(OUT-04, 정시 전량 2 · R 실제 120만원, 부족하면 메시지 「실행증빙」 대기) →
  **관리 기준 책임자(H06) 개선 착수** → 11/4 09:00 자료 재현(SNAP-0900 8건 — R만 −30분 후보, 변경 접수 마감 = 기점 출발 − 24시간 09:10) →
  **출하 담당자(H04) 요청 확인·송신**(모의 — 외부 송신 0건) → 모의 접수증 09:05·수락 회신 09:08 → **H04 타 고객 영향 확인** → 조정 정규편
  채택(+15분·0원·조건부 회피 120만원) → 시험 01~09·8개 회신 분기(표본 1·1·7) → **Agent 운영 담당자(H07) 시험 판정** → **H06 적용 확인**
  (APP-04, 효력 11/9 00:00) → **H07 위임 설정**(CFG-04 — CASE-NEXT-01은 KRI-CTL-v2, CASE-S2-01은 기존 버전)(`docs/s2/sc04.md`, 2026-11-06).
  업무 번호 **24**.
  **시나리오 3 장면 1(결산조정 업무 착수)** — 시나리오 3(2026 연말결산, 공통 설계 `docs/s3/common.md` — 결산 건·조정항목·입력 버전·
  체크리스트)의 첫 업무. 결산 건 S3-CLOSE-01 하나 = BPM 실행 하나(`company1.s3.sc01`): 자료 연결 확인 → 다음 점검 항목(규칙) →
  **회계담당자의 「점검 실행」 결재 둘**(감가상각비·대손충당금 — 승인이 아니다) → 규칙 점검(공통 C-01~03 · DEP-01~05 · ALW-01~08,
  원 단위 대사) → 보완 필요만 남으면 메시지 「결산자료보완」 대기 → 둘 다 준비면 장면 2 인계(HAND-S3-01). 입력은 기간계의 입력 버전
  (IN-26-01 …, 허용 7개 시트)이고 그 항목이 쓰는 칸이 바뀐 항목만 재점검이다(`docs/s3/sc01.md`, 2026-11-06). 업무 번호 **31**
  (시나리오 3 장면 N = 30 + N). 끝은 준비 2/2 · 승인 0/2 · 상신 0건이다.
  **시나리오 3 장면 2(결산조정 계산 및 담당자 검토)** — 장면 1 인계(HAND-S3-01)에서 「장면 열기」로 `company1.s3.sc02`(진입·실행·상신
  직전에 장면 1 준비·최신 입력을 다시 본다): 지시 열기 → **회계담당자 [분석 실행]**(실행 RUN-S3-nn — 연속 클릭 1건) → 계산(전이율·누적
  PD·집합/개별·정액법 월할, 원 단위 대사) → **계산근거 Excel 생성·결산 건 첨부**(견본 v0.1 시트 구성 + 수식, 기간계 `close-attachments`,
  다시 열리는지 확인) → **검토 둘**(충당금·상각비, 결과 버전에 묶임) → **[상신]** 한 번(보고 REP-S3-01 · 인계 HAND-S3-02)(`docs/s3/sc02.md`,
  2026-11-06). 업무 번호 **32**. **연계 PC는 모의다**(`execution_mode: simulated` — 일꾼이 같은 계산·같은 시트의 .xlsx를 만든다). PC
  미응답(→ [상태 조회])·전송 실패(→ 첨부 대기·[첨부 재시도], 같은 파일)는 기간계 시연 스위치로만 난다. 입력이 바뀌면 결과가 낡아
  다시 실행(새 실행·결과·파일 버전)하고 입력·금액이 같은 항목의 검토는 승계한다. 끝은 상각비 50 추가 계상 · 충당금 30 추가 설정 ·
  승인 대기 2행 · 상신 1건 · 승인 0건(견본 v0.1과 같다 — 전기 대비 +80·+10과 다른 칸).
  **시나리오 3 장면 3(팀장 보고 및 승인)** — 장면 2 상신(HAND-S3-02)에서 「장면 열기」로 `company1.s3.sc03`(열 때 상신본 REP-S3-01 v1을
  결과·첨부·검토와 함께 읽어 둔다 — 다시 계산하지 않는다): 보고 열기(열람은 결정 0건) → **회계팀장 결정 한 번**(승인 또는 대상·사유 있는
  보완 요청 — 결정 직전에 지정 결재자·현재 상신 버전·결과 버전 일치·첨부 접근(기간계에서 다시 읽어 지문 대조)을 다시 보고 어긋나면 사유·복구
  담당을 남겨 보류, 버전마다 유효 결정 하나 — 재전송은 같은 DEC-S3-nn) → 승인이면 **후속 업무 인계**(전표 반영 `u-posting`·주석 취합
  `u-notes` 두 경로를 기간계 `close-followups`에 등록 — 기존 등록을 먼저 조회, 실패 경로만 [인계 재시도], 인계 HAND-S3-03), 보완이면
  **회계담당자 보완 처리**(참조 보강 재상신 · 입력 반영 재계산(장면 2와 같은 계산 기능, 번호는 장면 2에 이어진다) → 영향 항목 재검토 → 재상신,
  같은 보고 ID의 새 버전 `REP-S3-01:v{n}`)(`docs/s3/sc03.md`, 2026-11-06). 업무 번호 **33**. 끝은 승인 2/2 · 승인 보고 1건 · 전표 반영 0/2 ·
  주석 취합 0/2다(완료 처리는 후속 업무의 몫 — 이 판에 없다). 장애(첨부 접근 실패·경로 등록 실패·응답 유실)는 기간계 시연 스위치로만 난다.
  **화면은 내장 BPM을 고르지 않는다**(2026-10-27 결정) — 새 데모 실행의 기본은 Center다. 내장 실행기는 엔진 시험용으로 남았다.
* **Core Philosophy**:
  * **Target vs. Forecast vs. Plan**: 목표(Target)는 임의로 변경하지 않으며, 실행 결과와 최신 가정을 반영한 전망(Forecast)과 실행계획(Plan)을 Rolling 방식으로 갱신하고 잔여 Gap을 명시적으로 관리한다.
  * **Human-in-the-Loop**: AI Agent는 데이터 수집, 이상 징후 감지, 원인 분석, 대안 초안을 지원하고, 최종 판단과 승인은 사람이 책임진다.
  * **Deterministic BPM + Rule Calculation + Probabilistic AI**: 업무 흐름은 결정론적 BPM(Chaeksas)이, 지표·위험 판정은 규칙 계산이, 해석·설명은 Agent가 맡는다. **숫자는 규칙 계산만 만든다**(구현명세 AG-01).

---

## 2. Business Context & Virtual Company Spec

기준 문서(리포 밖, 사용자 Downloads/INNONOW): 기획안 v0.5 · SC01 설계서 v0.5 · SC01 구현명세 v0.2 ·
통합 가상 데이터 설계 v0.2(→ `engine/seed/`) · 설계 Template v0.5. 기획안 v0.1은 v0.5의 1~4장과 같다.
장면 2(Downloads/INNONOW_S02): SC02 설계서 v0.5 · 업무설계표 v0.2 · 화면구성·시연순서 v0.2 · 구현명세 v0.2 ·
SC01_SC02 통합가상데이터 v0.2(→ `engine/seed/SYN-SC02-v0.2.xlsx`).
장면 3(Downloads/장면3): SC03 설계서(자료 목록) · 경영이야기와장면범위 v0.2 · 업무설계표 v0.2 · 화면구성·시연순서 v0.2 ·
구현명세 v0.2 · SC01_SC02_SC03 통합가상데이터 v0.3(→ `engine/seed/SYN-SC03-v0.3.xlsx`).
장면 4(Downloads/장면4): 경영이야기와 범위 v0.2 · 업무설계표 v0.2 · 화면구성·시연순서 v0.2 · 구현명세 v0.2 ·
SC01_SC02_SC03_SC04 통합가상데이터 v0.4 2026-10-23 수정본(→ `engine/seed/SYN-SC04-v0.4.xlsx`).
장면 5(Downloads/장면5): 경영이야기·장면범위 v0.2 · 업무설계표 v0.2 · 화면구성·시연순서 v0.2 · 구현명세 v0.2 ·
SC01~SC05 통합가상데이터 v0.5(→ `engine/seed/SYN-SC05-v0.5.xlsx`).
장면 6(Downloads/장면6): 경영이야기·장면범위 v0.2 · 업무설계표 v0.2 · 화면구성·시연순서 v0.2 · 구현명세 v0.2 ·
SC01~SC06 통합가상데이터 v0.6(→ `engine/seed/SYN-SC06-v0.6.xlsx`).
장면 7(Downloads/장면7): 경영이야기·장면범위 v0.2 · 업무설계표 v0.2 · 화면구성·시연순서 v0.2 · 구현명세 v0.2 ·
SC01~SC07 통합가상데이터 v0.7(→ `engine/seed/SYN-SC07-v0.7.xlsx`).
**문서의 요구사항 ID(UI01-xx, CALC-xx, WF-xx, AT-xx, EX-xx, D-xx, T4xx·T5xx, CT4xx·CT5xx, X5xx)를 코드 주석·테스트 이름에 그대로 쓴다.**

### 2.1 가상 고객사와 범위

* 매출 약 1조원의 가상 자동차 부품사. 현대·기아차가 주요 고객. 전사 1조원은 **배경**이고 상세 데이터와
  억지로 맞추지 않는다(D02).
* **기존사업 A제품**(배기 시스템 특성 참고) · **울산공장(ULS)** — 1차 상세 범위. a~e 5개 모델.
  a = 고급차종(고단가·소량), b = 소형차종(저단가·다량·외주 비중 높음). 모델별 수익성 우열을 미리 정하지 않는다.
* **신사업 B제품**(안테나·액추에이터 참고) · **평택공장** — 배경에만 있고 상세는 확장 단계.
* 가상 고객군 `CUS-HK`(현대·기아 합산). 고객계획은 **이미 당사 배정·월 전체 물량**이다 — 공급 점유율
  40%를 모델·공장 물량에 다시 곱하지 않는다(G10).
* 가상 시점 2027년. 실적 컷오프 6/15, 사건은 6/16 09:00 수신한 CP02의 **7월 b모델 9,500 → 8,800대분**.
* 고객 시연용 회사·인물은 전부 가상이다. 벤치마킹한 실제 회사명은 **앱 코드에 넣지 않는다**(5.4).

### 2.2 경영 작동모델 6단계 루프 (기획안 3.1)

1. **목표 대비 성과·전망 모니터링 · Risk 감지** — 현재 성과 변동과 선행 Risk 시그널, 관측과 가정을 구분.
2. **Operation Control** — 권한 안의 현업 통제. 부서 간 조정·경영 선택이 필요하면 Review로.
3. **Management Review (Human-in-the-Loop)** — 원인·영향 분석, 대안 비교, 의사결정.
4. **Management Action** — 책임자·기한·기대 효과가 있는 실행과제.
5. **Rolling Plan Update** — 승인 시 예상 효과, 실행 후 실현 효과로 전망·계획 갱신. 잔여 차이 유지.
6. **Management Evolution** — Framework · Process · Agent 개선.

**SC01은 1·2단계와 3단계 "연결"까지다.** **SC02**(단가 인상 검토)도 같은 범위다 — 위험을 해소하지 않고
장면 3 손익 검토로 넘긴다. **SC03**은 3단계(Management Review)의 **분석 검토와 분석 지시**까지다 — 대안 선택·실행 승인·
Rolling은 하지 않고 장면 4(대표 주재 월간회의 MT41)로 넘긴다. **SC04**는 3단계의 대안 결정과 4단계(Management Action)의 **실행 승인·
책임 인수**까지다 — 상세 실행계획은 장면 5이고, 승인 효과는 예상치일 뿐 Rolling·공식 Forecast 갱신을 하지 않는다. **SC05**는 4단계의
상세 계획·착수·초기 실행과 5단계(Rolling Plan Update)의 운영계획·**공식 Forecast 갱신**까지다 — 연간 효과의 최종 실현 검증과
Management Evolution(6단계 공식 개선)은 하지 않는다. **SC06**은 4·5단계의 **실현 검증**(과제 완료 후 차 분기의 기대 대비
확인 효과)과 그 결과를 운영 보완·추가 과제 발의로 잇는 데까지다 — 발의의 효과·예산은 미산정이고, Target·공식 Forecast를 바꾸지 않으며,
Management Evolution 상세는 범위 밖이다. **SC07**은 6단계(Management Evolution)의 **한 건**이다 — 사람이 보정한 경험을 Agent의 근거
연결·원인 후보 방식과 기존 지표의 측정·해석 기준에 반영해 검증하고 다음 운영 설정에 적용하기까지. 새 KPI·KRI·Control·임계값·효과 산식은
없고, 장기 효과(시간 절감·정확도·재무 효과)는 측정하지 않으며, 운영 실행은 미확인으로 남는다. 기획안의 100억 → 85억 → 97억은 **설명용 예시**이고 데이터의 손익
(공장관리손익 목표 34.77억)과 다르다(D18).

---

## 3. Tech Stack

* **Frontend**: Next.js 16.3.6 (App Router, Turbopack), React 19.2, TypeScript 5, Tailwind CSS v4, Shadcn/UI (`radix-nova` 프리셋 / Radix 기반 / Lucide 아이콘)
* **화면**: 회사 목록 · 회사 대시보드 · 관리자뿐이다(4.6). 캔버스(React Flow)·차트(Recharts)·스토어(Zustand)는 장면 화면과 함께
  걷었다(2026-11-03) — 업무 화면은 회사 사이트(Company1)에 있다
* **Backend / API**: Next Route Handler 하나가 엔진을 프록시한다(BFF, 4.3)
* **BPM**: **Chaeksas BPM** (`chaeksas-core`, BPMN 2.0 해석기 — git 커밋 고정 의존성으로 임베드)
* **Engine**: Python 3.12 · FastAPI · uv
* **Database**: PostgreSQL(운영·compose·CI) / SQLite(로컬 기본). 시드는 엑셀(`engine/seed/`)

### 3.1 확정된 기술 선택 (Decided — 재검토 불필요)

| 영역 | 선택 | 배제한 대안 | 사유 |
|---|---|---|---|
| BPM | **Chaeksas BPM** (`chaeksas-core` 라이브러리 임베드) | LangGraph StateGraph(이전 선택), Camunda 8, Chaeksas Center 연동 | 2026-10-19 사용자 결정. BPMN 2.0을 그대로 해석하므로 업무 흐름이 **BPMN 파일 하나**에 있고 Chaeksas Studio로 열 수 있다. Camunda는 Zeebe 브로커 운영이 과중했다. Center·서버 실행기 경유는 정의마다 서명·배포가 필요하고 결재 응답이 관리자 토큰 전용이며 작업 결과 값을 돌려주지 않아 배제했다(4.5). |
| 차트 | Recharts(지금은 차트가 없어 의존성을 뺐다) | Apache ECharts | Shadcn/UI·Tailwind와의 컴포지션이 자연스럽다. 차트 라이브러리는 하나만 쓴다 — 두 개를 섞으면 테마·툴팁·반응형 동작이 갈라진다. 대시보드에 차트를 다시 두면 이것을 쓴다. |
| Shadcn 프리미티브 | Radix (`-b radix`) | Base UI, React Aria | 기존 shadcn/ui 문서·스니펫이 Radix 기반이라 이식 비용이 가장 낮다. |
| 테마 전환 | next-themes (`attribute="class"`) | 직접 구현 | 초기 렌더에 잘못된 테마가 번쩍이는(FOUC) 문제를 직접 처리하지 않아도 된다. `.dark` 클래스 방식이 Tailwind v4 `@custom-variant dark`와 `globals.css`의 `.dark .viz-root`를 동시에 만족시켜, UI 토큰과 차트 색이 항상 함께 전환된다. |

**토폴로지의 원천은 BPMN 파일**(`engine/processes/*.bpmn`)이다. 엔진은 `GET /scN/process`로 내지만 그것을 그리던 캔버스는
걷었다 — 대시보드는 그림의 결재 수만 센다(4.6). 실행 상세는 Center 콘솔이다.

---

## 4. Project Directory Structure

아래는 **실제 구조**다(목표 설계가 아니라 파일 시스템 기준). 구조를 바꾸면 이 트리를 갱신한다.

```text
NowView/
├── CLAUDE.md
├── AGENTS.md                     # next dev 자동 생성 (Next.js 에이전트 규칙)
├── components.json               # Shadcn 설정
├── .claude/launch.json           # preview 서버 설정 (nowview-dev, nowview-engine)
├── scripts/
│   ├── stack.sh                  # 로컬 프로세스 제어 (start/stop/restart/status/logs)
│   ├── sync-bpm.sh               # company1 bpm/ → engine/processes/ (BPMN 원본은 company1에 있다)
│   ├── sync-scenarios.sh         # company1 scenarios/ → engine/scenarios/ (각본 원본은 company1에 있다)
│   ├── deploy.sh                 # 운영계 배포 (rsync → 빌드 → systemd 재시작) — 5.4
│   └── validate_palette.js       # 차트 팔레트 검증기 (dataviz 스킬에서 들여옴)
├── deploy/                       # 운영계 자산 (5.4) — bootstrap.sh · systemd 유닛 2개
├── chaeksas/                     # Center에 올릴 외부 확장 정의 — NowView 기본 확장 external.extension.json(장면 1~7)
├── docs/                         # platform.md(공통 플랫폼 — 세 영역 ↔ 세 서버·M01~M29 원본·공통 기록·업무 번호) · s2/sc01.md~sc04.md(시나리오 2 장면 1~4) · s3/common.md(시나리오 3 공통 — 결산 건·조정항목·입력 버전)·s3/sc01.md·s3/sc02.md·s3/sc03.md · role-split.md(세 서버 역할 분담·전환 단계) · records/(경영 기록 봉투·종류별 JSON 스키마·예시) · chaeksas-integration.md(Chaeksas 연계 — 현재 구조·등록 순서) · worker-interfaces.md(일꾼·회사 시스템 인터페이스) · handoff/(Chaeksas 요청서)
├── app/
│   ├── layout.tsx                # 뼈대(html·body·테마)만 — 공통 줄은 화면마다(`components/shared/top-bar.tsx`)
│   ├── globals.css               # 테마 토큰 + --viz-* 시각화 팔레트(지금 차트는 없다 — 4.4)
│   ├── page.tsx                  # 회사 목록 — INNONOW 브랜드 영역 + 공개 회사 목록(이름·설명·업무)
│   ├── admin/page.tsx            # 관리자 모드 — 로그인 · 일꾼 상태(요청 코드·토픽·최근 일감) · 연결 · 설정 편집(공개 화면에 링크 없음)
│   ├── c/[company]/page.tsx      # 회사 대시보드(4.6) — 회사는 설정이라 서버가 묻지 않고 클라이언트가 읽는다
│   ├── api/engine/[scene]/[[...path]]/route.ts  # 엔진 프록시(BFF) — `companies`·`companies/{회사}/dashboard`(GET)만. 장면 경로는 404
│   └── api/admin/                # 관리자 — login(비밀번호 → 서명 쿠키)·session·[...path](세션이 있으면 엔진 /admin/*로, X-Admin-Key)
├── components/
│   ├── ui/                       # Shadcn 원시 컴포넌트
│   ├── shared/                   # top-bar(공통 줄) · brand-hero(첫 화면 머리 — Center 로그인 상단과 같은 INNONOW 로고·문구,
│   │                             #   로고는 `public/brand/`)
│   ├── admin/                    # 관리자 모드 — admin-console(로그인·설정 JSON 편집) · status-panel(일꾼·연결·최근 일감)
│   ├── companies/company-list.tsx # 공개 회사 목록 · 회사 대시보드(회차 선택 · 업무 카드 — 진행·열린 결재·지표·일감·사이트 링크)
│   ├── theme-provider.tsx
│   └── theme-toggle.tsx
├── lib/
│   ├── utils.ts                  # cn()
│   ├── companies.ts              # 업무 목록 SCENES(엔진 SCENE_WORKS와 시험이 대조) · useCompanies(공개 목록)
│   ├── dashboard.ts              # 대시보드 응답 모양 · 표기(억·만·미산출·KST 시각) · 회사 사이트 업무 화면 주소
│   └── admin-session.ts          # 관리자 세션(서버 전용) — 비밀번호 대조·서명 쿠키
├── tests/dashboard.test.ts       # Vitest — 대시보드 표기·사이트 주소
└── engine/                       # Python BPM 엔진 (별도 프로세스)
    ├── pyproject.toml            # uv · chaeksas-core(git 커밋 고정)
    ├── scenarios/sc0{1..7}.json  # 각본 사본 — 원본은 Company1 scenarios/(scripts/sync-scenarios.sh)
    ├── processes/sc01.bpmn       # SC01 업무 흐름 — 사본(원본은 Company1 bpm/)
    ├── processes/sc02.bpmn       # SC02 업무 흐름 — Studio·Center 실행(4.16)
    ├── processes/sc03.bpmn       # SC03 업무 흐름 — Studio·Center 실행(4.17)
    ├── processes/sc04.bpmn       # SC04 업무 흐름 — Studio·Center 실행(4.18)
    ├── processes/sc05.bpmn       # SC05 업무 흐름 — Studio·Center 실행(4.19)
    ├── processes/sc06.bpmn       # SC06 확인 절차 — Studio·Center 실행(4.20)
    ├── processes/sc07.bpmn       # SC07 확인·적용 절차 — Studio·Center 실행(4.21)
    ├── processes/s2-sc01.bpmn    # 시나리오 2 장면 1 — 개정 하나 = 실행 하나, 결재 없음(docs/s2/sc01.md)
    ├── processes/case-intake.bpmn # 공통 BPM platform.case-intake — 업무 그림이 호출 활동으로 부른다(사본, 원본 Company1 bpm/platform/)
    ├── processes/s2-sc02.bpmn    # 시나리오 2 장면 2 — 수행계획 호출 → 변경안 → H03 확인 → 반영·재조회 → 재평가 → 인계(docs/s2/sc02.md)
    ├── processes/case-plan.bpmn  # 공통 BPM platform.case-plan — A03 제안 → Y01 검사 → 적용(사본)
    ├── processes/s2-sc03.bpmn    # 시나리오 2 장면 3 — 수행계획 v2 호출 → 원업무 연결·근거 메시지 대기 → 비교 → 팀장 권고 → H05 결정 → H04 인수(docs/s2/sc03.md)
    ├── processes/s2-sc04.bpmn    # 시나리오 2 장면 4 — 결과 대조·증빙 메시지 대기 → H06 착수 → 재현 → H04 송신·영향 → 시험 → H07 판정 → H06 적용 → H07 설정(docs/s2/sc04.md)
    ├── processes/s3-sc01.bpmn    # 시나리오 3 장면 1 — 연결 확인 → 다음 항목 → 회계담당 점검 둘 → 보완 대기(메시지) → 인계(docs/s3/sc01.md)
    ├── processes/s3-sc02.bpmn    # 시나리오 3 장면 2 — 지시 → 회계담당 분석 실행 → 계산(PC 미응답 → 상태 조회) → Excel 첨부(실패 → 재시도) → 검토 둘 → 상신(docs/s3/sc02.md)
    ├── processes/s3-sc03.bpmn    # 시나리오 3 장면 3 — 보고 열기 → 회계팀장 결정(보류 → 같은 결재) → 승인: 후속 인계(인계 대기 → 재시도) / 보완: 회계담당 보완 처리 → 재검토 → 재상신(docs/s3/sc03.md)
    ├── seed/S3-INPUT-v0.1.xlsx   # 시나리오 3 입력자료 명세·대표 사건 v0.1 — 입력 7개 시트가 원천(기간계 `s3.py`), 앞 4개 시트는 설계·기대값
    ├── seed/S3-WORKPAPERS-v0.1.xlsx # 시나리오 3 결산조정 계산근거 견본 v0.1 — 장면 2의 기대값(시험만 대조한다 — 엔진은 읽지 않는다)
    ├── seed/SYN-S2-SC04-v0.4.xlsx # 시나리오 2 장면 1~4 통합가상데이터 v0.4(앞 22개 시트 = v0.3) — 원천은 기간계(`s2.py`), 파생 칸은 시험이 대조
    ├── seed/SYN-SC01-v0.2.xlsx   # 통합 가상 데이터 설계 — 원천 시트=시드, 파생 시트=기대값
    ├── seed/SYN-SC02-v0.2.xlsx   # SC01_SC02 통합가상데이터 v0.2 — 같은 원칙(2027 행은 SC01 시드와 같다)
    ├── seed/SYN-SC03-v0.3.xlsx   # SC01_SC02_SC03 v0.3 — 숫자 시트는 v0.2와 같다, SC03 시트는 종료 시점 완성 레코드(기대값)
    ├── seed/SYN-SC04-v0.4.xlsx   # SC01~SC04 v0.4 수정본 — 숫자·SC03 시트는 v0.3과 같다, SC04가정이 원천, 나머지 SC04 시트는 기대값
    ├── seed/SYN-SC07-v0.7.xlsx   # SC01~SC07 v0.7 — 앞 92개 시트는 v0.6과 같다(값·수식), SC07 원천(개선·기준·버전·검증입력·근거·확인이력·적용)
    ├── seed/SYN-SC06-v0.6.xlsx   # SC01~SC06 v0.6 — 기존 71개 시트는 v0.5와 같다, SC06 원천(기준·실적·거래 180·변경·판단·후속·근거·Agent·보고)을 한 번에 적재
    ├── seed/SYN-SC05-v0.5.xlsx   # SC01~SC05 v0.5 — 기존 45개 시트는 v0.4와 같다, SC05 원천(설정·활동·고객계획·변경·구매·원장·근거)은 시각대로 들인다
    ├── app/
    │   ├── main.py               # FastAPI — health + /sc01 ~ /sc07 라우터 + C15 일꾼 기동
    │   ├── worker_file.py        # 설치가 Center 키 셋(일꾼·연동용·대리 답용)을 짓고 Center 폴더에 해시 파일을 쓴다(ADR-0122) · center_key
    │   ├── config.py             # NowView 설정 — 회사·회사 시스템 주소·BPM 프로세스 → 회사·업무·토픽(엔진 DB nowview_config, 기본값)
    │   ├── companies.py          # Settings · 업무 목록 SCENE_WORKS · 공개 GET /companies·/companies/{회사}/dashboard · 관리 /admin/status·config(X-Admin-Key)
    │   ├── dashboard.py          # 회사 대시보드 — 업무별 BPM 진행·열린 결재·핵심 지표(경영 기록에서 고른다)·일꾼 일감(회사 일감 기록)
    │   ├── records.py            # 경영 기록 공통 — 바뀐 판만 골라 한 번에 적기(batch)·장면 기록 처음으로·`SC0N:` 접두(장면마다 sc0N/records.py)
    │   ├── company.py            # 회사 시스템 클라이언트 — 회사 자료 읽기(→ Seed)·원천 수신·원천 상태 쓰기·세계, 503 = CompanyUnavailable
    │   ├── consumer.py           # C15 일꾼 — Center에서 서비스 태스크 일감을 가져가 장면 N operate (4.3)
    │   ├── follower.py           # 세계 따라가기 — 기간계의 세계·회차·시각·수신함·명령을 읽어 데모 실행을 만들고·초기화하고·따라간다(role-split §5). 사이트가 지운 세계는 데모 실행(장면 1~7)을 거둔다(`_sweep`, 2026-11-04). 사이트가 「장면 N부터 다시」 하면 기간계가 남긴 `rewind` 명령으로 N 이상 데모 실행을 거두고 Center 작업을 취소한다(`_rewind`). 시나리오 1(`scenario_id: s1`) 회차만 들인다(`SCENARIO`)
    │   ├── scenarios.py          # 각본 사본(engine/scenarios/) → 장면 Step — 시험 전용 각본 실행기의 BASE
    │   ├── store.py              # 백엔드 선택 (SQLite 파일 / Postgres 풀)
    │   ├── events.py · notify.py # SSE 허브 · 프로세스 경계 전파
    │   ├── preparation.py        # 장면 2~6 시작의 배경 진행 · 준비 상태(4.3)
    │   ├── script_wait.py        # Center 실행의 각본이 앞 결재의 기록 작업을 기다린다(장면 3~5, 4.17)
    │   └── sc01/                 # seed · calc · domain · process · store · demo · view · api · auth
    │                             #   · center(Center 클라이언트) · poller(진행 폴링) — N3 · records(회사에 적는 경영 기록)
    │   └── sc02/                 # seed · calc · domain · agent · process(내장·Studio·Center) · demo · view · api (저장은 sc01/store의 `sc02_*`)
    │   └── sc03/                 # seed · calc(장면 2 월별 계산 재사용) · domain · agent · process · demo · view · api (`sc03_*`)
    │   └── sc04/                 # seed · calc(효과·중복·검증·잔여 부족, 기준은 장면 3 계산) · domain · agent · process · demo · view · api (`sc04_*`)
    │   └── sc05/                 # seed · calc(관측·예산·과제 효과·월 손익·FC50 대비 대사) · domain(배경 원천 catch_up) · agent · process · demo · view · api (`sc05_*`)
    │   └── sc06/                 # seed · calc(Q4 기대 대비 확인 효과·원인·운영지표·보조 손익) · domain(적재 검증·판단·조회·재적재)
    │                             #   · confirm(확인 절차 — 결재 검사·기록·업무) · process(내장·Studio·Center) · demo(D601~D607) · view · api (`sc06_*`)
    │   ├── platform/catalog.py   # 공통 플랫폼 카탈로그 — 역할 H01~H07·A01~A03·Y01, 업무 단위 U01~U09, 위임 A/B/C, 실행 방식, 상태 어휘
    │   ├── s2/sc01/              # 시나리오 2 장면 1 — calc(Y01 판정·배정·A01 분석·OTD) · process(수신→Center 기동·일감 넷) · records(공통 기록)
    │   ├── s2/sc02/              # 시나리오 2 장면 2 — calc(A03 제안·Y01 검사·A02 변경안·반영본 대조·재평가) · process(열기→Center 기동·일감 아홉·
    │   │                         #   기간계 생산계획 반영) · records(case_plan·production_change·confirmation·production_plan·assessment·handoff)
    │   ├── s2/sc03/              # 시나리오 2 장면 3 — calc(수행계획 v2·원업무 회신 상태·전량 대안 비교·재보고 기준·결정 뒤 재보고) · process(열기→Center
    │   │                         #   기동·일감 여덟·근거 메시지) · records(case_plan·work_link·comparison·escalation·decision·action·handoff)
    │   ├── s2/sc04/              # 시나리오 2 장면 4 — calc(결과 대조·SNAP-0900 선별·접수 마감·회신 분기 채택·시험 01~09·적용 버전) · process(열기→
    │   │                         #   Center 기동·일감 열·증빙 메시지) · records(outcome·improvement·replay·verification·confirmation·config)
    │   ├── s3/sc01/              # 시나리오 3 장면 1 — calc(공통·감가상각비·충당금 점검, 항목별 입력 지문, 기한) · process(결산 건 → Center
    │   │                         #   기동·다음 항목·점검·보완 메시지·재점검 실행) · records(close_case·close_item·input_check·fix_request·handoff·dashboard)
    │   ├── s3/sc02/              # 시나리오 3 장면 2 — calc(전이율·누적 PD·충당금·상각비·대사·규칙 문안) · workpaper(계산근거 .xlsx — 견본 시트 + 수식,
    │   │                         #   같은 결과는 같은 바이트) · process(열기 → Center 기동·실행 접수·모의 PC 작업·첨부·검토·상신, 장애 스위치)
    │   │                         #   · records(analysis_run·close_result·attachment·item_review·close_report·handoff·dashboard S3-CLOSE-01:SC02)
    │   ├── s3/sc03/              # 시나리오 3 장면 3 — process(열기 → Center 기동·결정 재확인·보류·후속 경로 등록·보완 처리(장면 2 계산 기능으로
    │   │                         #   재계산)·재검토) · records(report_version·approval_decision·report_revision·followup·handoff·dashboard S3-CLOSE-01:SC03)
    │   └── sc07/                 # seed · calc(대행 확인·소요시간·원인 후보·Agent 입력 투영·검증 TS71-v1·적용 상태 ST703~707) · domain(적재 검사·조회)
    │                             #   · confirm(확인·적용 절차) · process(내장·Studio·Center) · demo(D701~D705) · view · api (`sc07_*`)
    └── tests/                    # pytest — test_sc01_calc · _process · _api · _agent · _exceptions · _center · _records,
                                  #   test_sc02_calc · _process · _external, test_sc03_calc · _process · _external,
                                  #   test_sc04_calc · _process · _external, test_sc05_calc · _process · _external,
                                  #   test_sc06_calc · _process · _external, test_sc07_calc · _process · _external,
                                  #   test_events · _notify · test_preparation · test_consumer · test_follower · test_companies · test_dashboard,
                                  #   test_records_sc02~sc07(+ records_contract · records_chain)
```

**디렉토리 규칙**
* 웹은 화면 셋(회사 목록·회사 대시보드·관리자)뿐이다. **장면별 화면을 NowView에 다시 만들지 않는다** — 업무 화면은 회사 사이트
  (Company1 `web/app/work/[world]/sc0N`)가 경영 기록으로 그린다(`docs/role-split.md`).
* `components/shared/` — 두 화면 이상이 쓰는 조각만 둔다.
* `engine/app/sc01/`~`sc07/` — 업무 규칙. 화면(TS)은 규칙을 다시 구현하지 않는다(4.3).

### 4.1 각본 실행기 (엔진 시험 전용)

> 화면의 데모 플레이어·결재 폼·시작 카드는 2026-11-03에 걷었고(2단계, `docs/role-split.md` §5), 장면 화면 자체도 같은 날 걷었다
> (4단계). 시연은 Company1 사이트(`/demo` 시연 조작·자동 모드·직원 결재 화면)가 몬다. 각본 실행(`demo.run_step`)·`_follow_script`·
> `_clock_to_script`·대리 답(`_relay`)은 **엔진 시험 전용**으로 남았다(`app.company.engine_drives`). 아래는 그 실행기의 규칙이다.

각본(누가·언제·무엇을)은 Company1 `scenarios/sc0N.json`의 사본(`engine/scenarios/`)을 장면마다 `app/sc0N/demo.py`가 단계로 읽는다.

* **실행은 실제로 한다.** `POST …/script/{i}`는 그 단계까지 역할 검사·업무 규칙을 그대로 탄다(지름길 없음). "초기화"만 데모 실행을
  S0로 되돌린다.
* **바깥에서 답해도 각본이 따라간다**(2026-11-01). 회사 사이트·Center 콘솔에서 결재에 답하면 기록 작업(원천 확인은 계산 요청)의
  효과가 각본 지점(`script_index`·`step`)을 옮긴다(`process._follow_script` — `script_follow.ahead`·`pending`, 병렬 인수는 순서가
  바뀌어도 된다). 각본과 다른 답(예: 다른 담당자 배정)은 각본 지점을 옮기지 않는다 — 기록이 거절되면 같은 결재가 다시 열린다.
  **시계도 따라간다** — 엔진 시험에서 바깥 답이 각본의 다음 단계를 지나가면 그 효과를 내기 전에 가상시계를 그 단계 시각으로
  옮긴다(뒤로는 안 간다, `_clock_to_script`). 운영·로컬 기동에서는 시계의 원본이 기간계이고 엔진은 읽기만 한다(follower).

### 4.2 상태 영속화

NowView 웹은 브라우저에 아무것도 저장하지 않는다 — 장면 스토어(`lib/store/*`, localStorage `persist`·`skipHydration`)는 장면
화면과 함께 걷었다(2026-11-03). 대시보드의 회차 선택은 화면 상태이고, 새로고침하면 엔진이 고른 기본 회차로 돌아간다(4.6).

### 4.3 API 계층

```
브라우저 ──/api/engine/companies[/{회사}/dashboard]──▶ Next Route Handler(BFF, GET만 중계) ──/companies…──▶ 엔진(127.0.0.1:8077)

GET  /companies                            → 공개 회사 목록(이름·설명·업무 번호·회사 사이트 주소)
GET  /companies/{회사}/dashboard?world=     → 회사 대시보드(4.6) — 따라가는 세계 목록 + 고른 세계의 업무별 진행·지표·일감

     아래 장면 경로는 BFF가 중계하지 않는다(2026-11-03 4단계 — 화면을 걷었다). 엔진 시험과 기록 대조(기록 본문 = 화면 응답,
     role-split §4)가 쓴다. 쓰기 경로는 NOWVIEW_TEST_INPUTS=1일 때만 열린다(role-split §5.5).

GET  /sc01/process · /users · /rules · /script · /customer-plans/{id}
POST /sc01/demo-runs  {caseId, executor}   → 새 데모 실행(S0). executor = embedded|studio|center (N2)
GET  /sc01/demo-runs/{id}                  → 문서 뷰 (BPM 대기·업무·이슈·인계 조건)
GET  /sc01/demo-runs/{id}/dashboard?period=&month=&seq=   → UI01 집계 (seq = 지난 시점)
GET  /sc01/demo-runs/{id}/history · /history/{seq}         → 지난 시점(읽기 전용)
POST /sc01/demo-runs/{id}/sources/receive  {fixtureId}     → 시연 원천 수신
POST /sc01/demo-runs/{id}/actions/{nodeId} {answer}        → BPM 사람 대기에 응답
POST /sc01/demo-runs/{id}/clock {at} · /script/{i} · /reset {caseId, executor}
GET  /sc01/demo-runs/{id}/events           → SSE
     시스템 작업(서비스 태스크)은 HTTP 경로가 없다 — 엔진의 C15 일꾼이 Center에서 일감을 가져간다(아래)

     장면 2(4.16) — 데모 실행 id는 장면 1과 같다
GET  /sc02/process · /cases · /rules · /parts · /script?case_id=
POST /sc02/demo-runs  {sc01DemoRunId?, caseId, executor=center|studio}  → 장면 2 시작(D00). 장면 1이 인계 전이면 각본으로 인계까지 실행
GET  /sc02/demo-runs/{id} · /history · /history/{seq} · /events(SSE, 채널 sc02:{id})
POST /sc02/demo-runs/{id}/requests/receive {fixtureId}        → 요청 접수 = BPM 시작
POST /sc02/demo-runs/{id}/actions/{nodeId} {answer, expect}   → 사람 대기에 응답. expect = {proposal}·{bundle}
POST /sc02/demo-runs/{id}/negotiation-due {due, reason}        → 외부 협상기한 변경(이력 보존)
POST /sc02/demo-runs/{id}/agent-outputs/{oid}/adopt · /clock {at} · /script/{i} · /reset {executor?}
     시스템 작업 13개(토픽 external — screen_price_request … accept_cost_review) — C15 일꾼이 가져간다(HTTP 경로 없음)

     장면 3(4.17) — 데모 실행 id는 장면 1·2와 같다
GET  /sc03/process · /cases · /script?case_id=
POST /sc03/demo-runs  {sc01DemoRunId?, caseId, executor=center|studio}  → 장면 3 시작(D30). 장면 2가 인수 전이면 각본으로 인수까지
GET  /sc03/demo-runs/{id} · /history · /history/{seq} · /events(SSE, 채널 sc03:{id})
POST /sc03/demo-runs/{id}/start                         → S31 착수 = BPM 시작(내장)·SC03 기동(Center)·착수만(Studio). 재착수는 같은 결과
POST /sc03/demo-runs/{id}/actions/{nodeId} {answer, expect}  → 사람 대기에 응답. expect = {report}·{assignment}
                                                          Complete_Scene 조건 미충족 → 422 {message, error_code, blocking_items}
POST /sc03/demo-runs/{id}/meetings/MT31/records {type, subject, content, related}  → 회의 질의·답변·설명(참석자만)
POST /sc03/demo-runs/{id}/agent-drafts {kind}  · /agent-outputs/{oid}/adopt          → AG31 회의 요약(경영관리 담당)
POST /sc03/demo-runs/{id}/tasks/{taskId}/draft {changes, reason}                      → 배정 전 과제 초안 수정(전후값)
POST /sc03/demo-runs/{id}/forecast-revisions {reason}   → E34 새 전망 버전(E34 사례 실행에서만)
POST /sc03/demo-runs/{id}/clock {at} · /script/{i} · /reset {executor?}
     시스템 작업 18개(토픽 external — open_profit_review … hand_off_profit_review) — C15 일꾼이 가져간다(HTTP 경로 없음)

     장면 4(4.18) — 데모 실행 id는 장면 1~3과 같다
GET  /sc04/process · /cases · /script?case_id=
POST /sc04/demo-runs  {sc01DemoRunId?, caseId, executor=center|studio}  → 장면 4 시작(D400). 장면 3이 완료 전이면 각본으로 완료까지
GET  /sc04/demo-runs/{id} · /history · /history/{seq} · /events(SSE, 채널 sc04:{id})
POST /sc04/demo-runs/{id}/start                         → S01 착수(HANDOFF31·AT31~34 연결) = BPM 시작(내장)·SC04 기동(Center)·착수만(Studio)
POST /sc04/demo-runs/{id}/actions/{nodeId} {answer, expect}  → 사람 대기에 응답. expect = {report}(판단본)·{approval}(승인 초안)·{assignment}
                                                          승인서 누락 → 422 APPROVAL_INCOMPLETE · 종료 요건 미충족 → 422 COMPLETION_BLOCKED (blocking_items)
POST /sc04/demo-runs/{id}/meetings/MT41/records {type, subject, content, related}  → 대표 질의·지시(대표)·현업 답변(임원)
POST /sc04/demo-runs/{id}/agent-drafts {kind}  · /agent-outputs/{oid}/adopt          → AG42 질의 후보·AG43 회의록·승인서 초안(경영관리)
POST /sc04/demo-runs/{id}/budget-policy {kind: transfer|total, …}  → 예산 위임 조회(E407) — 규칙만, 거래·이력 없음
POST /sc04/demo-runs/{id}/clock {at} · /script/{i} · /reset {executor?}
     시스템 작업 18개(토픽 external — open_improvement_review … hand_off_execution_plan) — C15 일꾼이 가져간다(HTTP 경로 없음)

     장면 5(4.19) — 데모 실행 id는 장면 1~4와 같다
GET  /sc05/process · /cases · /script?case_id=
POST /sc05/demo-runs  {sc01DemoRunId?, caseId, executor=center|studio}  → 장면 5 시작(D500). 장면 4가 완료 전이면 각본으로 완료까지
GET  /sc05/demo-runs/{id} · /history · /history/{seq} · /events(SSE, 채널 sc05:{id})
GET  /sc05/demo-runs/{id}/start-check · /completion-check   → 착수 요건(M502)·종료 요건(CT513) — 계산만, 상태 변경 없음
POST /sc05/demo-runs/{id}/start                         → S01 착수(HANDOFF41 연결) = BPM 시작(내장)·SC05 기동(Center)·착수만(Studio)
POST /sc05/demo-runs/{id}/actions/{nodeId} {answer, expect}  → 사람 대기에 응답. expect = {plan}·{forecast, run}
                                                          422 PLAN_INCOMPLETE·START_BLOCKED·BUDGET_EXCEEDED·RESULT_INCOMPLETE·
                                                          FORECAST_INVALID·COMPLETION_BLOCKED (blocking_items) — 착수·제출·완료는 대기가 아니어도 요건부터
POST /sc05/demo-runs/{id}/agent-drafts {kind} · /agent-outputs/{oid}/review {note}  → AG51~AG58 초안·제안 검토 기록(업무 역할)
POST /sc05/demo-runs/{id}/clock {at} · /script/{i} · /reset {executor?}   → 시계 이동이 그 시각까지의 배경 원천을 들인다
     시스템 작업 27개(토픽 external — open_execution_plan … hand_off_follow_up) — C15 일꾼이 가져간다(HTTP 경로 없음)

     장면 6(4.20) — 데모 실행 id는 장면 1~5와 같다. 조회 넷은 멱등이고, 쓰기는 적재와 확인 절차(BPM)다
GET  /sc06/process · /script
POST /sc06/demo-runs  {sc01DemoRunId?, executor=center|studio}  → RV61 적재(확인 전). 장면 5가 완료 전이면 각본으로 HANDOFF51까지. 이미 있으면 그대로
GET  /sc06/demo-runs/{id} · /history · /history/{seq} · /events(SSE, 채널 sc06:{id})  → 머리(보고본·산정·FC51·적재 묶음·확인 절차). 없으면 404
POST /sc06/demo-runs/{id}/start                         → 확인 착수(경영관리 담당) = BPM 시작(내장)·SC06 기동(Center)·착수만(Studio)
POST /sc06/demo-runs/{id}/actions/{nodeId} {answer}     → 결재 답(담당만). 확정의 요건 미충족 → 422 REPORT_INVALID (blocking_items)
POST /sc06/demo-runs/{id}/script/{i} · /reset {executor?}   → 각본 D601~D607 · 확인 절차만 확인 전으로(적재는 그대로)
     시스템 작업 6개(토픽 external — open_performance_review … report_performance_to_ceo) — C15 일꾼이 가져간다(HTTP 경로 없음)
GET  /sc06/demo-runs/{id}/reviews/RV61/summary?report_version=          → U601 요약(3과제·합계·완료 판단·Agent)
GET  /sc06/demo-runs/{id}/reviews/RV61/tasks/ACT42/variance?report_version=  → 원인별 건수·실제 긴급비, PO61-1103, AG62
GET  /sc06/demo-runs/{id}/evidence/{evidenceId}?report_version=           → 근거 본문·작성/확인 이력(가상 증빙)
GET  /sc06/demo-runs/{id}/reports/RPT61-v1                → U602 결론·FUP61·PROP61·FUP62·RISK61·확인 다섯 단계·다음 보고
     모든 조회 응답: review_id · report_version · calculation_version · as_of · data_status. X-Demo-Actor가 검토건 참여자가 아니면
     403 ACCESS_DENIED · 다른 보고 버전 409 VERSION_MISMATCH · 없음 404 NOT_FOUND(`detail.error_code`)

     장면 7(4.21) — 데모 실행 id는 장면 1~6과 같다. 조회 넷은 멱등이고, 쓰기는 적재와 확인·적용 절차(BPM)다
GET  /sc07/process · /script · /cases
POST /sc07/demo-runs  {sc01DemoRunId?, executor=center|studio}  → IMP71 적재(확인 전). 장면 6이 대표 보고 전이면 각본으로 끝까지. 이미 있으면 그대로
GET  /sc07/demo-runs/{id} · /history · /history/{seq} · /events(SSE, 채널 sc07:{id})  → 머리(개선건·버전 묶음·확인·적용 절차·상태 배지)
POST /sc07/demo-runs/{id}/start                         → 확인 착수(경영관리 담당) = BPM 시작(내장)·SC07 기동(Center)·착수만(Studio)
POST /sc07/demo-runs/{id}/actions/{nodeId} {answer}     → 결재 답(담당만). 다른 대상 버전 422 · 설정 「일치」가 레코드와 어긋나면 422 SETTING_MISMATCH
POST /sc07/demo-runs/{id}/script/{i} · /reset {executor?}   → 각본 D701~D705 · 확인·적용 절차만 확인 전으로(적재는 그대로)
     시스템 작업 6개(토픽 external — open_improvement · verify_improvement_version · confirm_improvement_version · apply_agent_setting ·
     check_agent_setting · schedule_follow_up_check) — C15 일꾼이 가져간다(HTTP 경로 없음)
GET  /sc07/demo-runs/{id}/improvements/IMP71?dataset_version=          → U701 A — 개선 사유·기존 검토(AG62 원본·제한 입력)·개선한 검토 방식(IN71)·기준·절차
GET  /sc07/demo-runs/{id}/improvements/IMP71/verification?dataset_version=  → TC701 상세 · TC702~708 요약(미실행이면 NOT_RUN)
GET  /sc07/demo-runs/{id}/applications/AP71?dataset_version=           → 범위·버전·확인 이력·설정 반영·다섯 조건·운영 실행(NOT_CONFIRMED)·후속 점검
GET  /sc07/demo-runs/{id}/evidence/{evidenceId}           → SC07근거 EV71~78 · 대표 사례 E61-1103(화면 조회 — Agent 입력이 아니다)
     모든 조회 응답: dataset_version · improvement_id · version_bundle · as_of. 403 ACCESS_DENIED(본문·사유 없음) · 다른 데이터
     버전 409 VERSION_MISMATCH · 없음 404 NOT_FOUND · 적재 검사 실패 422 DATA_INVALID(`detail.error_code`)
```

* **회사 시스템**(`app/company.py` ↔ Company1 기간계 :8191, `docs/worker-interfaces.md` §4.2) — 장면 1의 회사 자료(T01·F01·실적·C01·FC01·
  CP01)는 엔진 엑셀이 아니라 회사에서 읽는다(불변 버전이라 한 번 읽어 둔다, 규칙 R01만 엔진 엑셀 `load_rules`). 「수신」은 회사에
  고객 원천을 보내고(`POST /worlds/{w}/sim/customer-plans`) 그 원천을 들인다(`company_doc_id`). 원천 확인 결정(VERIFIED·NEEDS_INFO)은
  저장 직전에 회사에 적는다(`_company_writes` → `_commit`, `ref` 멱등) — 회사가 받지 못하면 그 조작은 저장되지 않는다(503). 일꾼은
  503을 C15 `dependency_down`(재시도)으로 돌려준다. 데모 실행을 만들 때·초기화·시계 이동 때 회사 세계도 함께 바뀐다. 설정
  `COMPANY_COMPANY1_URL`·`COMPANY_COMPANY1_KEY`(엔진) = `COMPANY1_LEGACY_KEY`(company1 `legacy/.env.local`). **설정이 없으면
  엑셀로 되돌아가지 않고 503이다.** 엔진 시험은 기간계 계약의 시험용 쌍둥이(`tests/company_twin/`)를 같은 프로세스에 띄운다
  (`tests/conftest.py`) — company1 없이 돈다. `/health.companies`·`/companies[].system.reachable`이 연결을 드러낸다.
  **회사와 오간 것은 문서에 따로 남는다**(`doc.company_log`, 뷰 `companyLog`, 2026-11-01) — 기준 자료 읽기(만들 때·초기화)·
  고객계획 받기(`in`)·원천 확인 결과 적기(`out`, `_commit`에서 회사가 받은 뒤). 감사 이력에 섞여 BPM ↔ 회사 연계가 화면에서 보이지
  않았다. 장면 1 고객계획·BPM 흐름 화면의 「회사 시스템과 오간 것」 카드가 보이고, 회사 설정의 공개 `site_url`(비우면 환경
  `COMPANY_{ID}_SITE_URL`, 로컬 `http://localhost:3100`)이 있으면 회사 사이트의 그 문서(`/legacy/worlds/{데모실행}/docs/{doc}`)로
  링크한다. 이 기록 전에 만든 데모 실행은 빈 목록이다(초기화하면 생긴다).
* **경영 기록은 회사에 적는다**(2026-11-03, `docs/role-split.md` §3 — 1단계 장면 1 파일럿). `app/sc01/records.py`가 화면이 읽는
  모양 그대로(`view.view`·`view.dashboard_all`) 기록 열 종류(`scene`·`source`·`forecast`·`calc_run`·`issue`·`task`·`review`·
  `agent_draft`·`handoff`·`dashboard`)를 짓고, `Sc01Process._write_records`가 **바뀐 것만 새 판으로** 기간계 `POST /worlds/{w}/records`에
  적는다 — `_commit`(원천 확인 상태 쓰기 바로 뒤)·생성·Agent 초안 저장 직전이고, 회사가 받지 못하면 그 조작은 저장되지 않는다(503).
  판·해시는 문서의 `company_records`, ref = `데모실행:종류/id:v판`. 본문 스키마의 주인은 NowView(`docs/records/` — 봉투 + 종류별)이고
  기간계는 봉투만 본다. 회사 사이트(Company1 `/work/{회차}/sc01`)가 이것만 읽어 업무 화면 다섯을 그린다. 화면이 하던 뺄셈(목표 부족액·
  사건 영향)은 `dashboard.gaps`로 옮겼다.
  **장면 2~7도 적는다**(2026-11-03, role-split §4 3단계) — `app/sc0N/records.py`가 그 장면 view의 칸 그대로 기록을 짓고(장면 6·7은
  문서 머리 + 조회 넷을 경영관리 담당이 보는 응답 그대로), 각 `_commit`·생성이 저장 직전에 `app/records.py`로 적는다. 공통 규칙:
  * **한 조작의 판은 `POST /worlds/{w}/records/batch`로 한 번에**(전부 적거나 하나도 안 적는다) — 기간계는 세계를 JSON 문서 하나로
    두어 판마다 문서 전체를 다시 썼다(쌍둥이 실측 판 하나 약 0.1초, 장면 4 각본 약 48초 → 묶은 뒤 18초). 그래서 기록도 세계
    문서 밖(기간계 기록 테이블)으로 뺐다 — 18초 → 3.5초. 쌍둥이(`tests/company_twin/`)도 같다.
  * **장면 2~7 record_id는 `SC0N:` 접두**(`SC02:TASK-VERIFY`) — 기간계 키가 kind/record_id인데 업무 id가 장면마다 겹친다.
  * **감사 이력은 한 줄이 기록 하나(`audit`)** — 인계 본문에 넣으면 조작마다 이력 전체가 새 판이 되어 기록이 제곱으로 불었다.
  * **초기화·새로 열기는 그 장면 기록을 처음으로**(`records.restart` → `POST /worlds/{w}/records/reset {scene}`).
  * **스키마는 기본 시연의 모든 판에서 뽑았다**(`tests/records_contract.py`, `NOWVIEW_WRITE_RECORD_SCHEMAS=1`) — 손으로 쓴 장면 1과
    다르다. 있던 칸을 빼거나 종류를 바꾸면 막고, 새 칸은 막지 않는다. 예시는 `NOWVIEW_WRITE_RECORD_EXAMPLES=1`.
  회사 사이트는 `/work/{회차}/sc0N`(site-api `work.scene_bundle` — 종류별로 묶기만 한다)으로 그린다.
* **장면 2~6 시작은 오래 걸리면 202다**(`app/preparation.py`, 2026-10-27). 시작은 앞 장면을 각본으로 끝까지 실제로 실행한다 —
  Center 실행이면 장면 3 시작이 약 7분이라 BFF의 `fetch`(undici 응답 헤더 기본 300초)가 503을 냈다(엔진은 끝까지 갔다). 운영계는
  Cloudflare가 약 100초에 끊는다(4.15) — 시간 늘리기로는 안 된다.
  * `POST /scN/demo-runs`는 **20초**(`NOWVIEW_PREPARE_WAIT_S`)까지 기다린다. 그 안에 끝나면(문서가 이미 있거나 내장) 지금처럼 201,
    거절이면 그 상태 코드 그대로다. 아니면 **202 `{preparing, demoRunId, state, startedAt, progress}`**를 돌려주고 배경 스레드가 잇는다.
    `GET /scN/demo-runs/{id}/preparation` → `running`(앞 장면들의 지금 단계 `progress`) · `done` · `failed`(사유·상태 코드).
  * 데모 실행 id가 없으면 **장면 1 실행을 먼저 만든다** — 화면이 준비를 물을 id가 있어야 한다. 같은 장면·실행의 시작이 겹치면
    진행 중인 것을 함께 기다린다(두 번 돌리지 않는다).
  * **준비 상태는 엔진 메모리에만 있다** — 운영 엔진은 워커 하나다. 엔진이 다시 뜨면 조회가 404이고 배경 진행도 멈춘다. 다시
    시작하면 앞 장면의 남은 단계부터 잇는다(각본은 지난 단계를 건너뛴다). 개발 중 `--reload`가 진행 중인 준비를 끊는다.
  * 이 길은 엔진 시험 전용이다 — 운영에서는 사이트의 `open` 명령이 앞 장면을 돌리지 않는다(앞 장면이 끝나지 않았으면 409,
    role-split §5.2). 그것을 기다리던 화면(`lib/preparation.ts`·`preparation-note.tsx`)은 장면 화면과 함께 걷었다.
* **시스템 작업은 Center에 쌓인 일감을 엔진이 가져간다**(Pull, 2026-10-31 — Chaeksas ADR-0102, 계약 C15).
  `engine/app/consumer.py`. 서버 실행기·Studio가 서비스 태스크를 **Center에 외부 작업으로 올리면**, 토픽
  (= BPMN `app_id`, 설정 `topics` — 기본 확장 `external` 하나, 장면 1~7)을 맡은 엔진 안의 일꾼이 롱폴링으로 가져가 `ScNProcess.operate`를 부르고
  `complete`·`fail`로 알린다. 연결은 늘 엔진 → Center다 — **Center는 NowView 주소도 키도 모른다.**
  내장 BPM의 `_InProcessCalls`와 일꾼이 **같은 함수**(`process.run_operation`)를 써서 출력 모양이 같다.
  예전(Push)에는 Center 쪽 HTTP 어댑터가 BFF의 `/operations/…`를 키로 찔렀다 — 그 경로·키 검사(N6,
  `auth.py`)·로컬 Center의 주소 덮어쓰기는 걷었다.
  ```
  서버 실행기·Studio ─올리기─▶ Center(외부 작업) ◀─가져가기·끝내기─ 엔진 일꾼 ─▶ 장면 N operate
  ```
  * **실행 위치는 일감의 `origin`이다** — Studio 시험 실행은 `test`, 서버 실행은 `run`. Center가 올린 쪽을
    인증해 붙이는 값이라(Studio는 `test_…` 실행만 올린다) 지어낼 수 없다. 시험용 키 ↔ 운영 키가 하던 일이다.
    데모 실행의 선언(`executor`)과 어긋나면 409(`domain.link_external_run`)이고 묶이지 않는다.
  * **일감의 입력이 그림의 `chk:serviceCall.input` 그대로다.** 데모 실행은 `demo_run_id`, 바깥 실행 id·노드 id는
    멱등 칸(`run_id`·`node_id`)이다 — 템플릿 `{{run_id}}`·`chaeksas_run_id`가 하던 일이다. 선택 입력이
    빠져도 호출이 멈추지 않는다(어댑터는 `{{input.x}}`가 없으면 실패시켰다).
  * **거절 사유가 그대로 간다** — 업무 규칙 위반(`DomainError`)은 `fail` `{code: forbidden·not_found·conflict·
    input_invalid, message: 사유, retryable: false}`다. 결재가 보이는 `error_message`에 이제 사유가 실린다
    (어댑터 때는 「…이 409를 돌려줬다」뿐이었다).
  * **최소 한 번 실행이다**(C15) — 잠금이 지나 같은 일감이 다시 오면 `service_kit`의 멱등 저장소가 저장한
    결과를 다시 준다(같은 칸·다른 본문은 `idempotency_conflict`). 저장소는 **메모리**다 — 엔진이 다시 뜨면 빈다.
  * **승인 없는 일꾼이다**(2026-10-31 사용자 결정, Chaeksas ADR-0121). 배포가 Center의 일꾼 폴더
    (`CHK_CENTER__CONSUMERS_DIR`)에 일꾼 파일 `worker.consumer.json`(이름 `worker`·토픽·토큰 **해시**)을 두면 Center가 뜰 때
    들인다 — 요청 코드 승인이 없다. 파일은 `engine/app/worker_file.py`가 짓는다 — **연동용·대리 답용 키도 같은 명령이 짓는다**
    (2026-11-01 사용자 결정: 설치가 키를 짓고 Center는 해시 파일 `nowview-{integration,relay}.key.json`으로 들인다, 콘솔 발급·옮겨
    적기 없음). 원문은 `engine/.consumer/keys.json`(0600)에만 있고 엔진은 `center_key`로 읽는다 — 같은 이름의 환경 변수가 이긴다.
    Center가 `*.key.json`을 읽는 판은 Chaeksas에 요청 중이다(그 전에는 콘솔 발급 키를 env에 둔다). **확장 정의는 일꾼이 올린다** — 엔진이 뜨면 토픽마다 `chaeksas/{topic}.extension.json`을
    `PUT /consumers/self/extension`으로 올리고(409는 판을 올리라는 경고만) manifest를 올린 뒤 가져가기를 시작한다. 콘솔 등록·
    해제는 없다. 토큰이 없으면 꺼진 채 사유를 남긴다. **기본 토픽은 `external` 하나다** — 장면 6의 옛 토픽은 맡지 않아,
    옮길 때까지 그 장면의 Center 실행은 서비스 태스크에서 멈춘다. **지켜볼 것은 로그다** — 엔진 로그 `nowview.consumer`와 Center 로그(일꾼·일감·토픽·작업·오류 코드).
    `/health.consumer.state`는 `off`·`starting`(확장 정의 올리는 중)·`running`이다.
  * **manifest는 확장 정의에서 짓는다**(`manifest_of`) — 작업·모드·입출력 스키마·`timeout_s`. 일꾼이 뜰 때
    `PUT …/consumers/self/manifest`로 올리고, Center가 일감의 작업을 대조하고 출력 필수 칸을 막는다(422
    `output_invalid`). 그래서 **확장 정의를 먼저 올린다**.
    정의 위치는 `NOWVIEW_EXTENSIONS_DIR`(기본 리포 `chaeksas/`, 도커 이미지는 `additional_contexts`로 복사).
  * **기본 확장(`external`)은 요청 템플릿을 자리만 채운다**(운영계 주소·`path: "/"`·키 없음) — C13이 HTTP 어댑터 모양을
    요구해서다. 작업 이름도 업무 언어로 바꿨다(`assess_supply_risk`·`record_plan_review`·`assign_follow_up` …,
    `docs/worker-interfaces.md` §4.1). 장면 2도 옮기며 이름을 바꿨다(`screen_price_request`·`record_price_decision`·
    `register_cost_version` …). 장면 3도 옮기며 이름을 바꿨다(`analyze_profit_impact`·`record_department_confirmation`·`assign_analysis_tasks` …). 장면 4도 옮기며 이름을 바꿨다(`submit_analysis_result`·`record_ceo_decision`·`accept_execution_assignment` …). 장면 5도 옮기며 이름을 바꿨다(`draft_execution_plan`·`approve_execution_request`·`publish_rolling_forecast` …). 장면 6 정의는 아래처럼 옛 템플릿이 남아 있다.
  * **확장 정의의 요청 템플릿(`path`·`body`·`allowed_hosts`·`auth`)은 이 길에서 쓰지 않는다.** Chaeksas 범용
    어댑터 일꾼(`chk-adapter-consumer`)을 대신 돌릴 때만 읽힌다. 고치면 다시 서명해야 해서 그대로 뒀다 —
    `test_extension_definition_matches_the_bpmn_service_calls`가 여전히 템플릿 ↔ 그림을 잠근다.
  * **확장 id에는 점을 쓸 수 없다**(C13 `^[a-z][a-z0-9-]{1,49}$`). 토픽(서비스 앱 id)은 기본 확장 `external`, BPM
    프로세스(패키지) id는 회사가 짓는다(`company1.sc01`). 장면 1을 옮기며 정의를 새 id로 다시 냈다(`chaeksas/external.extension.json`
    0.1.0 — 예전 `nowview-sc01` 0.7.1을 이었다). **철회된 판은 되살아나지 않는다**(C2) — 일꾼 파일을 폴더에서 빼면 Center가
    그 일꾼만 맡던 확장을 철회하므로, 다시 들일 때는 판을 올린다(0.1.0이 그렇게 철회돼 0.1.1, 2026-11-01). BPMN 범위는 `<1`이라 그대로다.
    같은 날 접수 작업 둘을 빼며 0.1.2, 장면 2 작업 13개를 더하며 0.2.0, 장면 3 작업 18개로 0.3.0, 장면 4 작업 18개로 0.4.0, 장면 5 작업 27개로 0.5.0, 장면 6 작업 6개로 0.6.0, 장면 7 작업 6개로 0.7.0이다(그림 `company1.sc0N`은 `>=0.N.0`을 선언한다).
  * **관리자 모드 `/admin`**(로그인)이 일꾼 상태·맡은 토픽·최근 일감 50건(엔진 메모리)을 보인다 — 공개 화면·API에는 없다
    (`/health`도 일꾼 상태만 싣는다). **토픽을 바꾸면 일꾼 파일을 다시 지어 Center·엔진을 다시 띄운다** — Center는 그 파일의
    토픽만 내준다(밖이면 403 `topic_not_granted`).
  * **BPMN은 `chk:process.extensions`에 `nowview-scN`을 선언한다** — Studio가 이것을 패키지
    `requires.extensions`로 옮기고, Center는 그 줄로 「이 실행이 이 토픽에 올려도 되나」를 본다(C15
    `topic_not_required`). `service_keys`·`key_ref`는 걷었다(ADR-0102 — 쓰는 곳이 없다, B7이 경고한다).
    **그래서 그림이 바뀌었다 — Studio에서 패키지를 다시 내보내 승인·배포해야 한다.**
  * `chaeksas-core`·`chaeksas-service-kit`은 같은 커밋(`d479226`, 2026-10-31 로컬 Center와 같은 판)에 고정한다(`engine/pyproject.toml`).
* **반대 방향 — 엔진이 Center를 부른다**(N3, `engine/app/sc01/center.py`). 키는 **엔진만** 쥔다(BFF·브라우저에
  없다 — 원문은 설치가 지은 보관 파일 `engine/.consumer/keys.json`, 위 「승인 없는 일꾼」). `CHAEKSAS_CENTER_URL` · `CHAEKSAS_INTEGRATION_KEY`(연동용 — `POST /jobs` 기동, `POST /messages` 정정본,
  `GET /runs/{id}/events` 진행, `DELETE /jobs/{id}` 대체된 작업 거두기, `GET /jobs/{id}` 앞 작업 상태) ·
  `CHAEKSAS_RELAY_KEY`(대리 답용 — 결재 읽기·답, `X-BPM-On-Behalf-Of` =
  행위자 이름) · `CHAEKSAS_SC01_PACKAGE`(기본 `company1.sc01`). 키가 둘인 것은
  Chaeksas 권한표 그대로다 — 대리 답용 키는 결재만, 연동용 키는 결재를 못 읽는다. `/health.center`가 설정·폴링
  여부를 드러낸다(값은 싣지 않는다). C15 일꾼 토큰과는 다른 키다(일꾼 토큰은 가져가기·끝내기만 연다).
  * **메시지는 `schema: 1`이 있어야 한다**(`MessageRequest`) — 없으면 422 `input_invalid`(실측). 작업(`/jobs`)은
    `schema`가 없는 계약이다.
  * **Center 멱등 키에는 초기화 회차가 들어간다**(`_center_key`). 초기화하면 원천 번호가 다시 SRC02라
    `데모실행:원천`만으로는 초기화 전의 작업이 그대로 돌아왔다(N5 실측 — 거절된 작업이 돌아와 새 접수가 안 됐다).
    장면 2~7 문서는 회차 초기화·「장면부터 다시」 때 **지우고 새로 만들어** 초기화 회차가 늘 0이다 — 문서마다 다른
    `center_epoch`(`domain.new_demo_run`)를 키에 넣는다. 없을 때는 거둔 옛 작업(취소됨)이 같은 키로 돌아와 새 실행이 서지
    않았다(2026-11-04 로컬 실측, 사이트 「장면 2부터 다시」).
  * **앞 작업이 NowView를 부르기 전에 끝났으면 기다리지 않는다.** 수신 때 `GET /jobs/{id}`로 읽어 거절·만료·취소·
    실행 끝이면 `center_job_ended`를 남기고 새로 보낸다. 읽지 못하면 막는다(모르면 막는 쪽). 실행기가 `not_ready`로
    거절한 접수 작업 때문에 다음 수신이 영영 409였다(N5 실측).
  * **선택 입력을 본문 템플릿에 넣지 않는다.** 어댑터는 `{{input.x}}`의 `x`가 없으면 호출을 실패시킨다 —
    그래서 배정 기록이 생산·자재(`record_dispatch`)와 경영관리(`record_review_request`)로 갈렸다.
    `answered_via`는 대리 답이 아니면 `null`이지만 **변수는 늘 있다**(결재가 `answered_via_as`를 채운다) —
    없는 것과 `null`은 다르다. 값 하나뿐인 템플릿은 JSON 값 그대로 실린다.
  * **모든 작업 본문에 `{{run_id}}`·`{{node_id}}`를 싣는다**(0.3.0, N2). 이름이 `chaeksas_run_id`인 것은
    작업 입력의 `run_id`가 이미 **계산** id라서다. 실행 id가 없는 호출(0.2.0 정의)은 422다 — 묶을 수 없다.

* **BFF는 `companies`(목록)와 `companies/{회사}/dashboard`의 GET만 중계한다**(2026-11-03 4단계). 장면 경로(`sc01`~`sc07`)는
  404다 — 화면을 걷었고, 업무 화면은 회사 사이트가 기간계의 경영 기록으로 그린다. 관리 API는 `/api/admin/*`(관리자 세션)만 중계한다.
  목록 밖은 404 — 엔진의 다른 경로(`/health` 등)를 열지 않는다. 쓰기는 405다. 바깥 Chaeksas가 BFF를 부르는 길은 없다(C15 일꾼).
  업무 규칙(권한 403 · 없음 404 · 상태 충돌 409 · 입력 422 — API-03)은 전부 엔진에 있다.
* **화면은 규칙을 다시 구현하지 않는다.** 금액은 엔진이 문자열 DECIMAL로 주고 화면은 단위만 바꾼다(`lib/dashboard.ts`).
* **화면은 서버에서 엔진을 부르지 않는다.** `/`·`/admin`은 정적 프리렌더(`○`)이고, `/c/[company]`는 회사가 설정이라 `ƒ`지만
  서버 쪽은 틀만 그린다 — 데이터는 클라이언트가 받는다. 서버에서 엔진을 부르면 엔진이 꺼졌을 때 페이지가 깨진다.
* **엔진이 꺼져 있는 것은 고장이 아니라 상태다.** 클라이언트는 throw하지 않고 화면이 배너로 말한다. 회사 시스템에 닿지
  않으면 대시보드는 200에 세계 없이 사유(`problem`)를 싣는다.

### 4.4 데이터 시각화 규칙

> **지금 NowView에는 차트가 없다**(2026-11-03 — 장면 화면과 함께 걷었다, Recharts 의존성도 뺐다). `--viz-*` 팔레트와 검증기는
> 대시보드에 차트를 다시 둘 때를 위해 남겼다. 아래 규칙은 그때 그대로 쓴다.

차트 색은 `app/globals.css`의 **`--viz-*` 변수만** 사용한다. 이유와 제약:

* **shadcn nova 프리셋의 `--chart-1~5`는 무채색 그레이스케일**(`oklch(… 0 0)`)이다. 계열 식별에 쓰면
  chroma floor를 통과하지 못하므로 차트에 쓰지 않는다.
* 역할을 섞지 않는다: `favorable`/`unfavorable`은 극성(개선/악화), `series-1|2`는 엔티티 식별,
  `status-*`는 상태 전용이다. 계열색을 상태색으로, 상태색을 계열색으로 재사용하지 않는다.
* 계열색은 **엔티티에 고정 배정**한다. 목록 순서나 순위에 따라 다시 칠하면 안 된다.
* 상태는 색 단독으로 전달하지 않는다 — `SeverityTag`(아이콘+한글 라벨)를 항상 동반한다.
  라이트 서피스에서 warning/serious는 대비 3:1 미만이라 이 조합이 유일한 완화 수단이다.
* 색을 바꾸면 **눈으로 판단하지 말고 검증기를 돌린다** — `scripts/validate_palette.js`.
  서피스는 **카드 배경**이다(라이트 `#ffffff`, 다크 `#171717`). 페이지 배경(`#f4f4f4` /
  `#0a0a0a`)이 아니다 — 차트는 카드 안에 있다. 실행 명령 네 줄은 `globals.css`의
  `.viz-root` 주석에 그대로 적어 두었고, 현재 값은 양쪽 모드에서 전부 PASS다.
  검사 항목은 lightness band · chroma floor · CVD 분리(protan/deutan) · 정상시야 분리 ·
  서피스 대비이며, 하나라도 FAIL이면 종료코드 1이다.
* **단위가 다른 두 계열을 한 차트에 겹치지 않는다.** 축이 둘이면 없는 상관관계를 만들어낸다.
  (예전 SC01 손익 추이는 모두 원 단위라 한 축이었고, 물량(대분)은 표로 뒀다.)
* 모든 차트에는 표 뷰를 둔다(값이 툴팁에만 갇히면 접근성 위반).

### 4.5 BPM — Chaeksas 위의 SC01 (엔진)

```
engine/processes/sc01.bpmn ──read_process──▶ Chaeksas Engine (step·pendings·answer·deliver)
                                              │ chk:serviceCall nowview.sc01
                                              ▼
                          app/sc01/process.py _InProcessCalls → domain.py / calc.py
                                              │ 문서 1개 + BPM 스냅샷을 한 번에 저장
                                              ▼
                          sc01_demo_run(row_version) · sc01_history → notifier → SSE
```

**경계**

* **BPM이 쥐는 것: 순서·사람 대기·분기·인계. 숫자는 모른다.** 계산·원천 검증·이슈 갱신은 서비스
  태스크가 부르는 `nowview.sc01` 앱이 한다 — 네트워크가 아니라 같은 프로세스의 어댑터다.
* **Chaeksas는 라이브러리로만 쓴다**(`chaeksas-core`, git 커밋 고정 — `rev`를 바꾸고 `uv lock`해야
  올라간다). Center·서버 실행기는 쓰지 않는다 — 정의 변경마다 서명·배포, 결재 응답은 관리자 토큰
  전용, 작업 결과 값 미반환이라 화면이 결과를 읽을 길이 없다. 대신 **우리가 붙인 것**: SSE(기존
  허브·notifier), 지난 시점(Chaeksas 스냅샷은 현재 하나뿐이라 `sc01_history`에 매번 문서 전체),
  폼이 못 거는 업무 규칙(의견·근거 필수, 담당자만 인수 — `process.check_answer`).
* **운영 데모 실행은 내장을 쓰지 않는다**(2026-10-27). 세계 따라가기(`follower.py`)가 만드는 데모 실행은 Center이고, API 기본
  (`POST /demo-runs`의 `executor`)도 `center`다. 엔진의 내장 경로·`Sc01Process.create()`의 기본값(내장)은 시험이 업무 규칙을 같은
  프로세스에서 잠그는 데 쓴다.
* **사람 결정의 업무 효과는 결재 뒤의 「… 기록」 서비스 태스크가 낸다**(`Record_*` → `record_*` 작업,
  `docs/chaeksas-integration.md` §5). 결재를 내장·Studio·Center 어디서 닫았든 같은 길이다 — 예전에는
  내장 실행기의 답 훅에만 있어 Studio 실행에서 원천이 확인되지 않고 계산이 409였다(2026-10-25 실측).
  내장 경로는 답을 넣기 전에 `check_answer`로 **부수 효과 없이** 거절해 입력을 지키고(4.6), 기록 작업이
  같은 검사를 다시 한다(콘솔 답은 앞 검사를 거치지 않는다).
  * **답한 사람은 결재 변수로 온다**(R1, ADR-0096). 결재마다 `answered_by_as`·`answered_via_as`(`확인자`·
    `확인경로` …)를 두고 뒤의 기록 작업·계산 입력에 `answered_by`·`answered_via`로 싣는다. 내장도 같은
    변수다(`engine.answer(answered_by=행위자)`). **사용자 마스터에 없는 이름(콘솔 관리자 · Studio 「시험
    케이스」)은 거절하지 않고 그 이름 그대로 적는다**(`outside_master`) — 정상 경로에서 오는 이름이고, 422로
    거절하면 오류 경계가 같은 결재로 되돌리는데 답한 사람은 고칠 길이 없다. 인수 업무의 담당자는 답한
    사람이 아니라 **배정 기록이 고른 사람**이다 — 관리자를 담당자로 두면 인계 조건이 깨진다(실측 409).
    짐작(`guessed`)은 `answered_by`가 없던 옛 정의(0.5.0 이하) 호환으로만 남았다.
    **`chaeksas-core`가 `8f0b08d` 이전이면 변수가 생기지 않아** 기록 작업 입력이 「모르는 이름」으로 멈춘다.
  * **업무가 없으면 기록 때 연다**(`opened_late`). 바깥 실행에서는 대기가 열리는 순간을 모른다 — 기한
    판정이 그만큼 느슨하다(Studio). Center 실행은 폴링이 결재를 읽을 때 연다(N3, 아래) — 대리 답이 폴러보다
    먼저 결재를 찾으면 대리 답 때 연다(장면 1~6 `_relay`, 5.10 — 장면 1은 운영 Center 각본에서 DQ·SALES 2건, 장면 2는 9/12건으로 드러났다).
  * (걷은 캔버스는 기록 태스크를 결재 노드에 접어 그렸다 — 토폴로지의 `recordOf`. 그대로 두면 노드가 20 → 27개가 되어
    글자가 읽히지 않았다. 대시보드는 결재(`userTask`)만 센다.)
  * **기록이 거절되면 같은 결재로 되돌아간다** — 기록 태스크마다 오류 경계(`Bnd_Record_*`, `TASK_FAILED`).
    Center 콘솔 답은 사전 검사를 거치지 않아 예전에는 실행이 실패로 끝났다. 결재 `show`의 `error_message`에는
    **사유가 없다** — HTTP 어댑터가 4xx 본문을 버리고 「…이 409를 돌려줬다」만 남긴다. 사유는 감사 이력
    `answer_rejected`에 있다. 검사가 부수 효과보다 먼저라 거절된 답은 기록·업무를 남기지 않고, 성공한 기록은
    `error_message: null`을 돌려줘 낡은 사유를 비운다. 캔버스는 경계도 결재에 접는다.
* **실행 위치는 데모 실행마다 하나다**(`bpm.executor` = `embedded`|`studio`|`center`, N2). 만들 때·초기화할
  때 고른다(`POST /demo-runs {executor}` — 세계 따라가기는 늘 Center). 바깥이면 **내장 엔진은 그 문서에서
  step하지 않는다** — 수신은 원천만 등록하고, 화면 답·각본은 409, 진행은 작업 호출이 알려 준 노드뿐이다.
  예전에는 수신이 내장 BPM을 늘 시작해서 바깥 실행과 한 문서에서 함께 돌았다(내장 쪽이 Approve_DQ에 멈춘
  채 남았다, 2026-10-25 실측).
  * **첫 작업 호출의 `{{run_id}}`가 묶는다**(`bpm.external_run_id`). 같은 데모 실행에 다른 실행이 오면 409,
    내장 데모 실행에 바깥 호출이 와도 409다. 예외는 정정(EX03): 묶인 실행이 있는데 보완 대기가 아닌 때
    정정본이 오면 그 실행을 `bpm_history`(`superseded`)로 옮긴다 — 그 실행의 남은 호출은 409이고 다음
    새 실행이 묶인다. 바깥 실행은 취소할 수 없으니 이것이 내장의 cancel에 해당한다.
  * **Studio인지 Center인지는 선언하고, 일감의 `origin`으로 검사한다**(C15, 4.3). 예전에는 시험용 키 ↔ 운영
    키(N6)였다. 선언을 남긴 것은 화면이 첫 호출 전부터 읽기 전용이어야 해서다
    (`docs/chaeksas-integration.md` §5).
  * 바깥 실행의 업무는 대기 id를 (실행, 결재, 원천·계산)으로 지어 `sync_tasks`에 넘긴다 — 정정 뒤의 새
    실행이 같은 결재에 오면 인수한 업무에 재확인, 끝난 업무에 재검토 업무가 생긴다(내장과 같은 규칙).
  * 바깥 실행은 작업 호출이 없는 노드(시작·게이트웨이)를 지나왔어도 모른다 — `visited`에 없다. 그래서 대시보드는 지나온
    **결재** 수만 센다(결재는 기록 작업이 알려 준다). 토큰 위치도 비워 둔다(호출이 끝나면 토큰은 이미 갔다).
  * **보완 대기인지는 바로 앞 원천으로 본다**(`receive_external`). `corrects`는 같은 고객계획의 첫 원천을
    가리켜, 보완 → 정정 → 확인 뒤의 또 다른 정정본을 보완 대기로 오인했다(N3 시험에서 드러남).
* **Center 실행(`center`)은 NowView가 기동하고, 화면 답이 대리 답이며, 진행을 폴링한다**(N3,
  `docs/chaeksas-integration.md` §5).
  * 수신 → `POST /jobs`. 묶인 실행이 보완 대기면 정정본은 `POST /messages`(상관 키 = 데모실행ID — 그래서
    `Wait_Correction`에 `correlation`이 있다. Center는 상관 키 없는 메시지로 기다리는 실행을 찾지 않는다).
    대체·초기화 때는 앞 작업을 거둔다.
  * 화면 답(`act`)·각본 → **사전 검사가 Center보다 먼저**(403·409·422, 입력 보존) → 열린 결재 찾기(최대 30초 —
    실행기가 결재를 올리는 동안) → 대리 답(`if_review_digest`). 업무 효과는 여전히 기록 작업이 낸다.
  * **대리 답 헤더는 `X-BPM-On-Behalf-Of`다**(Chaeksas ADR-0126 — 옛 `X-CHK-`는 무시한다). 옛 Center를 위해 둘 다 싣는다 —
    0126 판 로컬 Center에서 `on_behalf_required`로 막혔다(2026-11-01).
  * **Center 각본은 그 결재의 기록과 다음 결재를 기다린다**(`demo._await_own_record` → `_await_next_approval`, 다음 결재는 그림에서
    찾는다). 기다리지 않으면 시계가 먼저 가서 원천 확인이 10:10, 인수가 다음 단계 시각에 적히고 업무가 한 단계 늦게 열렸다(로컬
    Center 실측 2026-11-01) — 고친 뒤 업무 다섯 건의 열림·인수·완료·기한이 내장 실행과 같다(시험이 잠근다).
  * 폴러(`poller.py`, 2초)는 `bpm.state == running`인 center 데모 실행만 읽는다(`store.running_external`).
    C3 → 지나온 노드·토큰 위치·열린 결재·끝. 새 결재는 대리 답용 키로 읽어 검토 자료·폼을 싣고 **업무를 그때
    연다**(늦게 열지 않는다). 대리 답한 결재는 `human_answered`가 오기 전까지 다시 보이지 않는다(`relayed`).
  * **설정이 없으면 조용히 내장으로 돌지 않는다** — 수신은 되고 「기동하지 않았다」 사유가 배너에 남는다
    (첫 폴링에서 걷힌다). 화면 답·각본은 503. 화면은 엔진이 정한 `answerHere`로 폼·각본을 켠다.
  * 시험은 가짜 Center(`test_sc01_center.py`)와 **따로 띄운 빈 Center**(실측)로 했다. 진짜 서버 실행기·배포된
    패키지로는 아직 돌려 보지 않았다(기동·메시지 전달이 남았다).
* **고객계획 접수 가상 직원(N5)은 걷었다**(2026-11-01 사용자 결정 — 사용자에게 효용이 없는 억지 기능이었다). 원천 수신은
  `company1.sc01`을 `POST /jobs`로 바로 기동하고 그림은 원천 자동 검증부터 한다. 걷은 것: 접수 Bot 그림 `sc01-intake.bpmn`(Company1
  `bpm/company1/company1.sc01-intake`도), 감독자 일괄 결재와 대리 답(`/sc01/intake`), 「접수 가상 직원」 카드, 작업
  `screen_customer_plan`·`record_intake_decision`(확장 `external` 0.1.2), SC01 입력 `처리자`(출처 `virtual_worker.name`)·
  `processed_by`, `CHAEKSAS_INTAKE_WORKER`. 장면 2~6 시작의 각본도 감독자 대리 승인 없이 장면 1을 인계까지 돈다. Center 쪽
  가상 직원 자원은 Chaeksas가 「직원」(ADR-0125)으로 바꾸는 중이다 — 업무를 직원에 할당하는 모양은 그 구현 뒤에 다시 정한다.
* **한 데모 실행 = 문서 하나.** 계산 결과·이슈 갱신·BPM 스냅샷이 한 번의 쓰기라 API-04의 원자성이
  저절로 성립한다. 워커 사이는 `row_version`(낙관적 잠금, 409)이 막는다. 데모 실행끼리는 서로
  보지 않는다(DATA-05).
* **엑셀이 기준 시드이자 기대값이다.** `seed.py`는 원천 시트만 읽고(행 번호가 아니라 영문 헤더로),
  테스트가 파생 시트(월분기연간·SC01검증)를 따로 읽어 대조한다 — 숫자를 테스트에 옮겨 적지 않는다.
  엑셀을 고치면 `engine/seed/`의 파일을 바꾸고 `pytest`를 돌린다.
* **역할 배정은 코드에 있다**(`domain.NODE_ROLES`). `chk:approval`에 역할 칸이 없다. BPMN에 사람
  노드를 더하고 표를 빠뜨리면 `test_every_user_task_has_a_role`이 잡는다.
* **결재 담당자(`chk:approval.assignees`)는 사람 이름이다**(N4) — 바깥 Chaeksas가 「담당자만 답한다」를
  그것으로 막는다(ADR-0081). 인수 결재는 배정 기록이 돌려준 `…담당자명` 변수를 쓴다(폼은 id를 고른다).
  `NODE_ROLES`와 어긋나면 `test_every_approval_names_assignees_matching_the_role_table`이 잡는다.
  확인(`manualTask`)에는 담당자를 둘 수 없어 `Confirm_Calc`는 결재(`userTask`)다.
* **행위자는 `X-Demo-Actor` 헤더다 — 신뢰 경계가 아니다.** 구현명세는 세션에서 꺼내라고 하지만 인증이
  없다(5.4). 서버는 "그 사용자가 그 역할·담당인가"까지 검사하고(403), 인증이 붙으면 헤더만 세션으로
  바꾸면 된다.
* **저장 백엔드는 `DATABASE_URL` 유무로 갈린다** — 있으면 Postgres, 없으면 파일 SQLite. **연결 실패를
  SQLite로 조용히 되돌리지 않는다** — 운영에서 DB가 안 붙었다면 즉시 드러나야 한다. `/health`의
  `storage`가 어느 쪽인지 알려 준다.

**흐름(BPMN)** — (각 결재 뒤에 기록 태스크가 있다 — 생략) S01·S02 자동 검증 → `Approve_DQ`(영업담당, 보완이면 정정본 메시지 대기) →
`Confirm_Calc` → 전망 생성·지표 계산 → `Approve_Sales`(영업팀장) → **포함 게이트웨이**: 현업 배정(항상)
∥ Review 요청(`위험수준 == 'CRITICAL' or 경영검토요청`) → PROD·MAT(병렬)·FIN 인수 → 인계 기록.
장면 완료는 **후속 업무 인수**이지 위험 해소·전망 승인이 아니다 — 끝나도 F02는 `UNDER_REVIEW`,
ISSUE-B07은 열린 중요다.

**노드 상태는 저장하지 않는다.** 엔진이 주는 것은 지나온 노드(`visited` — 조작마다 RunLog가 새로 열리므로 문서에 누적한다),
사람 대기(`waiting`), 토큰 위치다. 걷은 캔버스는 거기서 노드 상태를 파생했다(실행 중에는 안 간 분기를 미실행으로 칠하지
않는다 — 게이트웨이가 돌기 전에는 갈 수도 있다). 대시보드의 「지나온 결재 / 그림의 결재」도 같은 이유로 완료율이 아니다 —
갈래가 있는 그림은 끝나도 모든 결재를 지나지 않는다.

**만들며 드러난 것**

* **폼 없는 `manualTask`는 `decision`(승인/반려)을 요구한다.** "비교 계산 실행"에 승인을 넣는 꼴이라
  선택 칸(메모)을 하나 뒀다.
* **`chk:serviceCall`은 키 참조가 없으면 검사(B7)에서 막힌다.** 같은 프로세스 어댑터라 키가 필요
  없지만 `service_keys`에 이름만 둔다.
* **SQLite 연결을 잠금 없이 나눠 쓰자 SSE가 죽었다.** 쓰는 도중의 읽기가 빈 행을 받아
  `json.loads(None)`. SC01 저장소는 같은 파일에 **자기 연결**을 열고 잠금으로 줄 세운다. 잠금을 끄면
  회귀 테스트가 3회 중 3회 실패하는 것을 확인했다.
* **`python:3.12-slim`에 git이 없다** — git 의존성이 깔리지 않는다. 엔진 Dockerfile에 git과
  `processes/`·`seed/` 복사를 넣었다. 운영 서버에는 git이 있다.
* **변수 이름 가림**: `_commit(…, event)` 안에서 루프 변수를 `event`로 써 이력 테이블에 RunEvent가
  들어갈 뻔했다(SQLite 바인딩 오류로 드러났다).
* **S0에서 8·9월 관심 평가를 이슈로 만들지 않는다**(UI01-04). 이슈는 7월 a·b 둘뿐이고, 계산은 같은
  키의 열린 이슈에 run을 잇는다(B07: 관심→중요, 새 이슈 없음).

**Agent 검토 지원**(`app/sc01/agent.py`, AG-01~03)

* BPMN의 `Task_AgentRequest`는 **요청만 남기고 기다리지 않는다** — 곧바로 영업 검토로 간다. 초안은
  저장이 끝난 뒤 **잠금 밖의 스레드 풀**에서 만들고, 결과는 다시 잠금을 잡아 기록한다(StaleWrite면
  다시 읽어 얹는다). LLM을 노드 안에서 기다리면 같은 실행의 조작이 모두 멈추고 프록시가 100초에 끊는다.
* **검증이 핵심이다.** 형식, 근거 ID가 `evidence_catalog`에 있는지, **본문의 숫자가 규칙 결과(입력)에
  있는 값인지**를 본다. 하나라도 어긋나면 한 번 자동 재시도하고, 그래도 안 되면 실패로 남긴다.
  실패한 응답은 `rejected`에만 두고 화면에는 사유만 보낸다. 31 이하 정수는 날짜·월로 보고 허용한다.
* 러너: `mock`(결정론, 기본) · `llm`(ollama — `NOWVIEW_AGENT_MODE=llm`, `OLLAMA_URL`, `OLLAMA_MODEL`) ·
  `fail`(EX08 시연 사례). mock도 같은 검증을 통과해야 한다.
* **기록에 누가·어느 판·어느 실행인지를 싣는다**(2026-11-07, Company1 시나리오 1 검토 v0.1 §5) — `agent_id`·`agent_version`·
  `execution_id`(AGX-…, 산출물 번호 AGT-001과 다르다 — 자동 재시도 둘은 한 실행)·`model_called`(러너의 `calls_model` — mock·fail은
  false). 이 칸 전에 만든 기록에는 없다(사이트 「기록 없음」). **초안 글의 금액은 백만원**(「14백만원」, 백만원 미만은 원 — 사이트
  표기)이고 지시문은 `sc01-review-v3`다. 검증은 백만·만·억 단위를 다 읽는다.
* 30초(실제 시간)를 넘기면 "지연"으로 보인다. 자동 요청은 같은 입력 해시의 성공한 초안을 재사용하고,
  담당자의 재생성은 항상 새로 만든다(이전 초안 보존). 채택은 원본을 건드리지 않고 기록만 남긴다.
* **실제 모델(kimi-k3:cloud)로 돌려 본 것**: 첫 응답을 검증이 10건 거절했다 — 전부 입력의 비율값을
  그대로 인용한 것(0.07368421, 임계값 0.05)이었다. 같은 값이므로 허용하도록 고쳤고(테스트로 잠갔다),
  "M01 700"처럼 코드로 말해서 지표 이름·표기 규칙을 입력·프롬프트에 넣었다(`sc01-review-v2`). 그 뒤
  검증을 통과했고 응답에 **약 100초**가 걸렸다 — 배경 실행이 아니면 프록시가 끊었을 길이다.

**정정(EX03) · 기한(EX07) · 멱등(AT13)**

* **정정본이 계산 뒤·인계 뒤에 오면 이전 BPM 실행을 이력으로 옮기고(`bpm_history`) 새 실행을 시작한다.**
  진행 중이면 취소한다 — Chaeksas의 취소는 상태가 FAILED라 이력에는 `cancelled`로 적는다. 끝난 인계는
  `handoff_history`로 가고 장면은 다시 ACTIVE다(WF-03). 보완 대기 중의 정정본은 같은 실행에 메시지로 간다.
* **업무는 지우지도 다시 쓰지도 않는다.** 완료된 업무에 같은 종류의 대기가 또 오면 연결된 재검토 업무
  (`TASK-DQ-2`, `reopens`)를 만든다. 인수한 업무에는 새 근거를 붙이고 `reconfirm`을 켠다 — 인계 판정은
  **최신 run에 대한 확인(`acks`)**을 본다. 이전 확인도 남는다(WF-02).
* 가상시계가 기한을 넘기면 담당자와 기능별 검토자(`REVIEWER`)에게 화면 내 알림을 만든다. 같은 업무·
  기한에는 한 번만. 진행 중이어도 미완료면 알린다(UI05-03 — 지연은 상태와 독립).
* `Idempotency-Key` 헤더: 같은 키 + 같은 본문이면 다시 실행하지 않고 지금 상태를 돌려주고, 다른 본문이면
  409다. 화면의 폼은 같은 입력의 재시도에 같은 키를 쓰고 입력을 고치면 새 키를 쓴다.
* **이전 형식 문서는 읽을 때 채운다**(`domain.upgrade`). 저장된 데모 실행을 버리지 않는다.

**순서는 저장 순서에 기대지 않는다 — Postgres JSONB가 객체 키를 (길이, 바이트) 순으로 다시 놓는다.**
운영계 배포 뒤에 드러났다: 업무 목록이 DQ·FIN·MAT·PROD·SALES로 나왔다(SQLite는 넣은 순서라 로컬과
CI의 SQLite 테스트로는 안 보였고, Postgres 테스트는 순서를 보지 않았다). "마지막이 최신"을 쓰는 곳
(최신 계산·최신 원천·활성 업무·재검토 업무)이 우연히 맞고 있었을 뿐이다. 그래서:

* 원천·전망·계산·업무·Agent 초안은 만들 때 **`seq`**를 받고, 순서가 필요한 곳은 전부
  `domain.ordered()`로 읽는다. 한 번에 생기는 업무(생산·자재)와 화면의 사람 대기 목록은 BPMN 노드
  순서다(`NODE_ROLES`).
* 테스트의 `JsonbLikeStore`가 읽을 때 키를 JSONB처럼 섞는다 — Postgres 없이도 순서 의존을 잡는다.
  넣자마자 기한 초과 알림 순서가 같은 이유로 틀린 것을 하나 더 잡았다.
* `seq` 이전에 저장된 문서는 `upgrade`가 id의 숫자·배정 시각으로 순서를 되살린다.

### 4.6 회사 대시보드 (`/c/{회사}`)

2026-11-03 4단계(`docs/role-split.md`) — 장면 화면 48개(UI01~06·U21~U27·U31~U37·U401~U408·U501~U508·U601·U602·U701, 장면별 BPM
흐름 캔버스)와 플레이어·해설·업무 사이드바·섹션 탭·역할 선택을 걷고, 회사 화면을 이것 하나로 바꿨다. **업무 판단 화면이 아니다** —
업무 화면·해설·업무 설명은 회사 사이트(Company1 `/work/{회차}/sc0N`, `/scenario`)에 있고, 실행 상세는 Center 콘솔이다.

| 칸 | 어디서 | 메모 |
|---|---|---|
| 시연 회차 | 회사 시스템 `GET /worlds` 중 엔진이 따라가는 것(장면 1 문서가 있다) | 사이트가 만든 세계(`origin: site`)를 최근 초기화 순으로 앞에 둔다 — 기간계는 id 순이다. 기본은 맨 앞 |
| BPM 진행 | 장면 문서의 `bpm.state`·`visited`, 그림의 결재(`userTask`) 수 | 「지나온 결재 n / 그림의 결재 m」 — 갈래가 있는 그림은 끝나도 m에 못 미친다. 완료율로 읽지 않게 수를 쓴다 |
| 열린 결재 | 문서의 `bpm.waiting`(Center 폴러가 채운다) | 제목만 — 결재는 사이트에서 한다 |
| 핵심 지표 | 그 장면 `records_of(doc)`(회사에 적는 경영 기록)에서 고른다(`app/dashboard.py` `METRICS`) | 사이트와 같은 숫자. 없으면 `null` → 「미산출」(0이 아니다) |
| 일꾼 일감 | 회사 시스템 `GET /worlds/{w}/worker-log`의 그 장면 줄 | 건수·실패·최근 5건(작업 이름·세계 시각). 엔진 메모리의 최근 일감(관리자 모드)은 토픽·실행 id까지 있어 공개하지 않는다 |
| 사이트 링크 | 회사 설정의 공개 `site_url` + `/work/{회차}/sc0N` | `site_url`이 없으면(환경 `COMPANY_{ID}_SITE_URL`도 없으면) 링크하지 않는다 |

장면마다 고른 지표(기본 시연 끝 = 통합가상데이터, `tests/test_dashboard.py`가 잠근다): 1 연간 공장관리손익 F02 33.09억 · 목표 대비
−1.68억 · 사건 영향 −1,400만, 2 12개월 원가 증가 18,817,440 · 협상 감소 12,544,960, 3 통합 손익 3,299,986,680 · 부족 177,303,320,
4 개선 효과 127,800,000 · 남는 부족 49,503,320(인계 전이면 최신 효과 계산), 5 전망 손익 3,428,986,680 · 남는 부족 48,303,320,
6 Q4 기대 91.8 · 확인 87.0 · 차이 −4.8백만원, 7 적용 상태 「운영 설정 반영 확인」(ST707).

* **지표를 새로 계산하지 않는다.** 대시보드가 view를 다시 뺄셈하면 사이트와 다른 숫자가 생길 수 있다 — 회사에 적는 기록의 칸만
  고른다. 그래서 고른 칸이 기록에서 빠지면(스키마 시험이 막는다) 지표도 「미산출」이 된다. 한 장면의 기록을 짓다 실패하면 그 장면
  지표만 비고 로그(`nowview.dashboard`)에 남는다.
* **10초마다 다시 읽는다** — SSE를 걷었다. 일꾼이 세계를 2초마다 따라가므로 그보다 촘촘할 까닭이 없다.
* 화면 머리·카드 글에는 「장면 N」 대신 업무 이름을 쓴다(`SCENE_WORKS`). 장면 번호는 카드 앞 숫자뿐이다.
* 걷은 장면 화면의 규칙(상태를 칩 하나로 뭉치지 않는다 · 고객 원천 비교와 전망 비교를 섞지 않는다 · AI 초안과 담당자 의견은
  다른 카드 · 판단에 쓸 숫자를 먼저 · 오독을 막는 문구는 접지 않는다)은 회사 사이트 업무 화면이 이어받는다. 걷기 전의 화면 설명은
  git 이력(`79f6ea9`)의 이 절에 있다.

### 4.7 숫자와 가상 데이터의 규칙

* **화면이 보여 주는 숫자는 전부 엔진의 규칙 계산이다.** 연간 공장관리손익 T01 34.77억 · F01 33.23억 ·
  F02 33.09억, b모델 7월 700대분 · 7.37% · 1,400만원 · 12% · 중요가 엑셀(SC01검증·월분기연간 시트)과
  같아야 한다 — 엔진 테스트가 잠근다.
* **목표 부족액과 사건 영향을 구분한다**(AT07). 연간 T01 − F02 = 1억 6,794만원, 이 중 이번 사건분
  F02 − F01 = −1,400만원. 하나만 보이면 사건이 목표 차이 전부를 만든 것처럼 읽힌다.
* **누락은 0이 아니고, 판정 보류는 정상이 아니다**(G13·CALC-03). 화면도 "누락"·"판정 보류"·"미산출"로
  따로 쓴다.
* **비율은 소수 8자리로 반올림한 뒤 판정한다**(CALC-02) — 엑셀과 경계에서 같은 결과를 낸다. 화면은
  소수 둘째 자리, 원 단위 값은 `title`·표에서 다시 볼 수 있다.
* **공장관리손익은 전사 영업이익이 아니다.** 상시 표기한다. 고정비는 공장·월에 한 번만 차감하고 모델별
  배부 손익은 만들지 않는다(D11).
* **후속 장면의 숫자를 지어내지 않는다.** 단가 인상·대안 효과·Rolling 결과는 설계표·데이터가 나온 뒤
  만든다. 지어내면 화면이 주장하는 것을 데이터가 배반한다(4.15의 교훈).
* 시연 원천 변형(EX01·02·04·05, CP03)은 `domain.FIXTURES`에 있고 기본 데이터에 섞지 않는다(ERR-01).

### 4.8 테스트

| 위치 | 무엇을 잠그는가 |
|---|---|
| `engine/tests/test_sc01_calc.py` | **엑셀 파생 시트와 대조** — SC01검증 15행 전부, 월분기연간 17행 전부, 경계값(AT06), EX01~06, 목표 부족액 ≠ 사건 감소액 |
| `engine/tests/test_sc01_process.py` | Chaeksas 위의 기본 시연 EV01~EV07(AT01~AT09), 권한 403, 멱등, stale write 409, 시계, 초기화, 보완 경로 — **SQLite·Postgres 양쪽** |
| `engine/tests/test_sc01_agent.py` | Agent 계약 검증(틀린 금액·비율·물량, 없는 근거, 빠진 항목), EX08, 실패 응답 비노출, 재생성·채택·지연, **잠금 밖 실행**, `-m llm` 실호출 |
| `engine/tests/test_sc01_exceptions.py` | EX03 정정(이력 보존·재검토 업무·재확인·최신 run 인계), EX07 알림(중복 없음), 멱등키, 이전 형식 문서 |
| `engine/tests/test_sc01_api.py` | HTTP 오류 코드(API-03), 대시보드 노출(F02는 계산 후), 지난 시점, 동시 읽기·쓰기 회귀 |
| `engine/tests/test_sc01_records.py` | 경영 기록 — 기본 시연 동안 적은 **모든 판**(최신·지난 판)이 봉투·종류별 스키마(`docs/records/`)를 통과, 회사 기록 = 엔진 문서(B07 중요·b 7월 M01 700·M03 −1,400만·완료 조건·대시보드 기간), 바뀌지 않은 기록은 판 하나, 회사가 못 받으면 저장 안 함 → 다시 하면 이어짐, 사이트 예시(`docs/records/sc01/examples/base-end.json`)가 스키마를 통과하고 지금 적는 기록 목록과 같다(다시 만들기 `NOWVIEW_WRITE_RECORD_EXAMPLES=1`) — **SQLite·Postgres 양쪽** |
| `engine/tests/test_records_sc02.py`~`sc07.py` | 장면 2~7 경영 기록 — 기본 시연(장면 2는 X01도)의 **모든 판**이 봉투·종류별 스키마(`docs/records/sc0N/`, `records_contract.py`)를 통과, `SC0N:` 접두, 회사 기록 = 엔진 화면 응답(분석·효과·전망·조회 응답·업무 수), 회사가 못 받으면 저장 안 함 → 다시 하면 이어짐, 사이트 예시가 최신(장면 잇기는 `records_chain.py`) — SQLite |
| `engine/tests/test_sc01_center.py` | N3 — 가짜 Center(C3·C5·C6·C12 계약 그대로) + 진짜 Chaeksas 엔진의 실행기 흉내로 각본 끝까지(대리 답), 사전 검사가 Center보다 먼저, Center 거절 사유, 설정 없음 503, 정정 메시지·대체, **바깥 답(회사 사이트 흉내)이 각본 지점을 옮김**(병렬 인수 순서 바뀜·플레이어와 섞기) — **SQLite·Postgres 양쪽** |
| `engine/tests/test_sc02_calc.py` | **통합가상데이터 v0.2 파생 시트와 대조** — 단가안비교 5안 전부, 통합손익 17행 전부, Q3 모델별, 정합성검증 V05·V06·V09·V16·V17, 2027 행 = SC01 시드, 2028 = F01×97%(엑셀 ROUND), X02~X10 경계·기간·누락·중복 |
| `engine/tests/test_sc02_process.py` | Chaeksas 위의 기본 시연 D00~D12(T21~T30), 권한·순서·버전 403/409, 멱등, X01·X02·X04~X07·X09·X10, 기한·알림·시계·초기화, BPMN ↔ 역할표, HTTP — **SQLite·Postgres 양쪽** |
| `engine/tests/test_sc02_external.py` | 기본 확장 `external` ↔ BPMN(본문 입력·답한 사람·오류 경계·확장 선언), Studio 흉내(진짜 엔진 + `origin: test` 일감)로 인계까지, 기록 거절 → 같은 결재, `origin` ↔ 실행 위치 409, 가짜 Center + 실행기 흉내로 각본 끝까지(대리 답·폴링·도달한 종료), 사전 검사가 Center보다 먼저, 설정 없음 사유·503, 초기화가 작업을 거둠 |
| `engine/tests/test_sc03_calc.py` | **통합가상데이터 v0.3 파생 시트와 대조** — 통합손익(연간·Q3·잔여·12개월), 통합모델손익 a~e, SC03검증 V31·V32·V39·V40, 숫자 원천 = v0.2, 구매 증가 156,812개·18,817,440원, E33 정합 실패, E34 −1,988,000원, 엑셀 시각 KST·초 반올림 |
| `engine/tests/test_sc03_process.py` | Chaeksas 위의 기본 시연 D30~D41 — **끝난 문서 = SC03 시트**(사실확인·쟁점·후보·과제·인계·이벤트 시각), T31 재착수, T33 무응답 차단, T34 담당·기한 필수, 차단 → 재분석, T35 제외 사유 누락 시 전체 미저장, T36 C32·C33 → AT32, T37 3/4 완료 422·타부서 403, E35-M 책임자 NULL 전건 보류, T38 구버전 인수 409, 멱등, E31·E33·E34·E36·E37, 화면 답이 각본 지점을 옮김(병렬 순서 바뀜·조회 건너뜀), BPMN ↔ 역할표, HTTP — **SQLite·Postgres 양쪽** |
| `engine/tests/test_sc04_calc.py` | **통합가상데이터 v0.4 파생 시트와 대조** — SC04월효과 36행 전부(보고·판단), SC04월손익 월·연간·Q3·Q4·잔여, SC04비교 대안별 효과·정상 연간, SC04검증, 숫자 시트 = v0.3, T403(2,900 → 124.8M)·E401 감가상각 회피 차단·E402 중복 180만원·E403 승인 범위 121.6M, 입력 한도(전망·원가·긴급 역전·일회성비), E407 위임 조회 |
| `engine/tests/test_sc04_process.py` | Chaeksas 위의 기본 시연 D401~D413 — **끝난 문서 = SC04 시트**(예산과제·조건지시·인계·이벤트 23건 시각·행위자·회의 기록), T401 재착수·재등록, T402 보고본/판단본 분리, 작성자 ≠ 확인자·AT33 제외·Q31·Q32 이력, 다른 부서 403, 보완 요청 새 버전, E401·E402 검증 차단 → 담당 임원 보완, 추천 2~3개·우선순위, 회의 기록 역할, 판단 변경 사유·임원 확인, T403, 대표만 결정·판단본 409, T407 승인서 누락 422 무저장, T406 보류 과제 미생성, T408 2/3 종료 422·타인 403, T409 반려·보완·구버전 409, T411·T412·T413, 시계·초기화·각본, **바깥 답(회사 사이트·화면)이 각본 지점·시계를 옮김**(순서 바뀜·제 단계 시각·폼 기본값), BPMN ↔ 역할표, HTTP — **SQLite·Postgres 양쪽** |
| `engine/tests/test_sc04_external.py` | 기본 확장 `external` ↔ BPMN(입력·출력·답한 사람·오류 경계), Studio 흉내로 완료까지(늦게 연 업무·같은 숫자), 기록 거절 → 같은 결재, `origin` ↔ 실행 위치 409, 가짜 Center + 실행기 흉내로 각본 끝까지(대리 답·책임자 이름 결재), 사전 검사가 Center보다 먼저, 설정 없음 사유·503, 초기화가 작업을 거둠 |
| `engine/tests/test_sc05_calc.py` | **통합가상데이터 v0.5 파생 시트와 대조** — v0.4 45개 시트 그대로, 기초 손익 = SC05모델손익 60행, FC50 = 장면 4 판단 가정 손익, SC05월효과 18행, SC05월손익 월·연간·마감·전망·Q3, 모델별 효과, 변경 대사(9월 −1.2M · 11~12월 +2.4M · 차이 0), X506 재가산 대사 실패, X508 3,427,786,680, SC05초기지표, 임계값 같으면 정상·NULL 미확인, X509 중복·비용 NULL, 납기·품질 미수집, SC05예산(정산 이중 차감 없음), 고객계획 a~e 월합계 0 |
| `engine/tests/test_sc05_process.py` | Chaeksas 위의 기본 시연 D501~D518 — **끝난 문서 = SC05 시트**(계획·활동·조건품의·예산원장·변경공유·구매표본 60건·운영계획·전망버전·인계·이벤트 시각·사람·Agent 상태), SC05착수조건 GT51~55, T501~T532(X501 착수 422·T506 9/1 전 READY·T502 권한·T503 누락 저장·확정 422·T504 v1 유지·T507/X502 범위 이탈·T509 예산 초과·T512/X504·T513 전결 경계·대행 확인·T516/X509·T518·T521/X506·T522·T523/X505·T524/X507·T525/X508·T526 새 RUN·T527 게시 멱등·T528 시계만으로 승인 없음·T530 Agent 실패·T531), BPMN ↔ 역할표, HTTP — **SQLite·Postgres 양쪽** |
| `engine/tests/test_sc05_external.py` | 기본 확장 `external` ↔ BPMN, Studio 흉내로 완료까지(늦게 연 업무·같은 숫자), 기록 거절 → 같은 결재, `origin` ↔ 실행 위치 409, 가짜 Center + 실행기 흉내로 각본 끝까지(대리 답·구매 확인 대행 담당자), 사전 검사가 Center보다 먼저, 설정 없음 사유·503, 초기화가 작업을 거둠 |
| `engine/tests/test_sc06_calc.py` | **통합가상데이터 v0.6 파생 시트와 대조** — 기존 71개 시트 = v0.5, BASE61 = 장면 5 FC51 산정본(어긋나면 409), 과제성과·월효과 9행·원인집계·운영지표·분기손익·SC06요약·검증 17항목(계산값), 보고 결론 숫자 ↔ 산정, X61-01 비용 null 산정 보류·확인 소계, X61-02 판단 보류, X61-03 중복 대사 대기, X61-04 Agent 후보, AT61-06/X61-05 재적재 새 산정·확인 재수행 대상·같은 입력 되돌림, X61-06 미산정 ≠ 0, X61-07 원인 비용 + 미달 대사 오류, X61-08 검토 가능, 오류값 422·쉼표 문자열, 연결 누락·승인 전 발주, 고정비 절감 거절, AT61-12·14 |
| `engine/tests/test_sc06_process.py` | 장면 5 완료까지 각본 실행 후 적재(확인 전 DRAFT · 새 실행·도중 실행), 다시 열어도 재적재 없음, **확인 절차 각본 끝의 기록 일곱 건 = SC06보고 시트**(행위자·시각·상태·글·근거)·보고본이 CALC61-v1에 묶임, 담당만 답함 403, 결론 숫자가 다르면 확정 422 REPORT_INVALID → 보완 요청 → 다시 결론·확정, 재확인 요청 → 두 확인 이력·다시 열림, 초기화는 확인만 되돌림, BPMN ↔ 역할표·담당 이름, HTTP 착수·결재·각본·폼 기본값, 조회 계약 4개(문맥 칸·3과제·원인·PO61-1103·AG62·근거·확인 다섯 단계·후속·연간 FC51 그대로), 403 ACCESS_DENIED(오류에 금액·근거 없음)·409 VERSION_MISMATCH·404, **조회가 문서·이력·감사를 바꾸지 않는다**, Studio 장면 5 409 — **SQLite·Postgres 양쪽** |
| `engine/tests/test_sc06_external.py` | 기본 확장 `external` ↔ BPMN(계약 검사·입력·출력·답한 사람·오류 경계), Studio 흉내로 대표 보고까지(늦게 연 업무·같은 기록), 결론 숫자 틀린 확정 → 기록 거절 → 같은 결재(남은 항목은 감사 이력), `origin` ↔ 실행 위치 409, 착수 전 열기 409, 가짜 Center + 실행기 흉내로 각본 끝까지(대리 답·담당 이름 결재), 사전 검사가 Center보다 먼저, 설정 없음 사유·503, 초기화가 작업을 거둠, **Center 각본이 자기 기록을 기다려 사이트가 먼저 답한 결재를 다시 대리 답하지 않음** |
| `engine/tests/test_sc03_external.py` | 기본 확장 `external` ↔ BPMN(입력·출력·답한 사람·오류 경계), Studio 흉내로 완료까지(늦게 연 업무·같은 숫자), 기록 거절 → 같은 결재, `origin` ↔ 실행 위치 409, 가짜 Center + 실행기 흉내로 각본 끝까지(대리 답·과제 책임자 이름 결재), 사전 검사가 Center보다 먼저, 설정 없음 사유·503, 초기화가 작업을 거둠, **콘솔 답 거절 → 같은 업무에 잇고 사유가 폼에·반영 중(`inflight`)·화면 답이 각본 지점을 옮김**, 회신기한 형식 사전 검사 |
| `engine/tests/test_consumer.py` | C15 일꾼 — manifest가 여섯 장면 그림의 서비스 호출·입력·출력을 다 덮는다, 가짜 Center와 들이기(요청 코드 → 승인 → 봉한 토큰) → manifest → 가져가기 → `complete`, `origin`이 선언과 다르면 사유와 함께 `fail`(conflict), 같은 멱등 칸 다른 본문 `idempotency_conflict`, Center 없으면 꺼짐. 장면별 바깥 실행 시험의 Studio·서버 실행기 흉내도 이 수행기를 지난다(`conftest.C15Calls` — Center처럼 출력 필수 칸을 본다) |
| `engine/tests/test_companies.py` | NowView 설정·회사 — 업무 목록 = 화면 사본, 설정 기본값·저장·검사(겹침·없는 회사·없는 업무), 공개 목록에 등록 정보 없음·`/worker` 없음, 관리 API 키(401·503)·설정 편집(토픽 바꾸면 재시작 필요), 일꾼이 보낸 BPM 프로세스 id로 업무를 찾음(없으면 `not_found`) |
| `engine/tests/test_dashboard.py` | 회사 대시보드 — 장면 1→7 기본 시연 끝의 업무별 지표 = 통합가상데이터 숫자(경영 기록에서 고른다), 결재 진행(지나온 ≤ 그림), 시작 전 업무, 일감 기록은 그 장면 것만·새것이 앞, 따라가는 세계만·사이트 세계가 앞, 따라가지 않는 세계를 고르면 사유, 회사 시스템이 없으면 200 + 사유 |
| `engine/tests/test_s2_sc02.py` | 시나리오 2 장면 2 — **통합가상데이터 v0.2 파생 칸과 대조**(SC02생산안 제안 착수·종료, SC02반영본 대조, SC02납기판정 준비·정기차·도착·여유·경로, SC02수행계획·SC02확인·SC02인계·SC02요약), 구현명세 T01~T09(U03 없는 조합 차단·원계획 불변·H03만·중복 확인·확인 후 원계획 변경 → 새 판 재확인·보완 요청·라인 충돌·응답 유실 재처리·저장 수량 불일치 보류·마감 경계·차량 누락·같은 판정 재인계 없음), 진짜 엔진 + 공통 BPM 호출, 일감의 실행 신원, 세계 따라가기의 「장면 열기」, 대시보드 업무 22, 공통 기록 스키마(`docs/records/s2/sc02/`) |
| `engine/tests/test_s2_sc01.py` | 시나리오 2 장면 1 — **통합가상데이터 v0.1 파생 칸과 대조**(입고개정 판정·주문영향 배정·상황판·모델별), 구현명세 T01~T09(15분 경계·1개 부족·3영업일 창·재수신·배경·차량 마감 누락·A01 실패 재시도·인계), 진짜 엔진 + C15 수행기로 그림 끝까지, 실행·실행 위치 409, Center 설정 없음 사유, 세계 따라가기(만들기·수신·초기화·거두기), 대시보드 상황판, 공통 기록 스키마(`docs/records/s2/sc01/`) |
| `engine/tests/test_s2_sc03.py` | 시나리오 2 장면 3 — **통합가상데이터 v0.3과 대조**(SC03대안비교 두 안 전부, SC03결정인계·SC03인계·SC03요약, SC03업무연결의 사람 시각), 구현명세 T01~T09(재진입·같은 문의 링크 하나·중복 문의 차단·대기 → 회신 유효·2대 조건 재확인·갱신 요청·유효시각 도달·100만원 정확히 전결 범위·재보고 뒤 운임 변경 STALE → v2·비권한 결정·재전송 같은 DEC-03·인수 재전송 같은 HAND-03·인수 뒤 2대·운임·도착 변경 재보고), 진짜 엔진 + 공통 BPM 재호출 + 메시지 대기, 결재 담당 = 역할 배정, Center 메시지 `no_receiver` → 폴러 재전송, 세계 따라가기(열기·근거 넘기기·장면 3부터 다시), 대시보드 업무 23, 공통 기록 스키마(`docs/records/s2/sc03/`) |
| `engine/tests/test_s2_sc04.py` | 시나리오 2 장면 4 — **통합가상데이터 v0.4와 대조**(SC04실적 약정별 결과·여유·정산, SC04초기선별 8건 전부, SC04회신재현 8개 분기의 처리 경로·ETA·여유·비용·회피액, SC04요청이력 시각, SC04기준적용 표본·APP-04·CFG-04·사건별 버전, SC04요약), 구현명세 시험 01~09(재수신 한 번·정산 누락 비용 미확인·정정 새 판·타 고객 영향 1/미확인 채택 보류·09:10/09:11 경계·반영 불일치·준비 지연·미통과를 통과로 기록 거절·소급 효력 거절·다른 설정 버전 거절·보류), H06 개선 불필요 끝, 담당만 답함(같은 결재로), 진짜 엔진 + 메시지 「실행증빙」 대기, Center 메시지 `no_receiver` → 폴러 재전송, 세계 따라가기(열기·증빙 넘기기·장면 4부터 다시), 대시보드 업무 24, 공통 기록 스키마(`docs/records/s2/sc04/`) |
| `engine/tests/test_s3_sc01.py` | 시나리오 3 장면 1 — 입력 7개 시트만(설계 시트 제외), 정상 표본 수치를 점검·근거가 다시 냄(E2 2026-07-01·1,150·6,458.799691 = 원장·100 − 20 = 80·16분기·PLAN-A-26 60 = CONF-26-F), 구현명세 인수시험 01~08(재진입 같은 두 원업무·결재 0·준비 0/2 → 1/2 → 2/2·E2 개시일 누락은 감가상각비만·CONF-26-F 누락은 충당금만 → 보완 메시지 → 재점검·전기 계획 연결·회차 중복 합산 안 함·1원 차이·단위 오류·자산자료 교체 → 감가상각비만 재점검·옛 버전 응답 409·인계 뒤 교체 → 인계 무효·재점검 실행·미배정 사용자 → 같은 점검), 진짜 엔진 + C15 수행기, Center 기동·보완 메시지 `no_receiver` → 폴러 재전송, 세계 따라가기(만들기·입력 다시 연결·초기화·거두기), 대시보드 업무 31, 기록 스키마(`docs/records/s3/sc01/`), 확장 0.13.0 ↔ 그림 |
| `engine/tests/test_s3_sc03.py` | 시나리오 3 장면 3 — 구현명세 인수시험 01~09(장면 2 상신 전 열기 409·수신함과 두 행이 같은 보고 v1·열람만으로 결정 0·제출 근거(A사 회수 60 · PLAN-A-26 3회 × 20 · CONF-26-S/F · A사 +15 · 전체 +10 · 설정 30 · 상각비 50 · 기말 8,700)·정상 승인 → 결정 1·승인 2/2·두 경로 후속 업무 4건·전표 0/2·주석 0/2·HAND-S3-03·보완 요청 대상·사유 누락 → 같은 결재·충당금만 보완 필요·참조 보강 재상신 v2(금액 동일·변경 전후·이전 사유)·`A-RECOVERY-50` 재계산 전 재상신 보류 → 장면 1 재점검 → 재계산 RES-S3-v2·WP-S3-v2 → 충당금만 재검토(상각비 승계) → v2 요청 40·미지정 403·구버전 409·첨부 접근 실패 보류(복구 담당)·이중 클릭 같은 결정 ID·승인 뒤 보완 409·주석 경로 실패/응답 유실 → 그 경로만 재시도·기존 등록 재사용), 세계 따라가기(「장면 열기」·장면 3/2부터 다시), 대시보드 업무 33, 기록 스키마·예시(`docs/records/s3/sc03/`), 확장 0.15.0 ↔ 그림·DI 좌표 |
| `engine/tests/test_s3_sc02.py` | 시나리오 3 장면 2 — **결산조정 계산근거 견본 v0.1과 대조**(승인요약·상각비비교·유형자산주석·자산별계산·충당금비교·채권별계산·충당금주석·손실률·개별평가 — 50·30, 집합 75 → 70, 기말 8,700, 원본 재현 302,527,880원), 규칙 문안이 결과 칸을 잇고 지시 문구 없음, 구현명세 인수시험 01~09(장면 1 인계 전 열기 409·미배정 403·옛 입력 409·열람만으로 실행 0·연속 클릭 1건·PC 미응답 → 상태 조회·집합 6·개별 1·대사 0·A사 확인액 불일치/1원 차이 → 영향 항목·보완 담당·상신 보류·전송 실패 → 첨부 대기 → 같은 파일 재전송·.xlsx 시트·수식·실행정보·LibreOffice 재계산 오류 0(없으면 skip)·E2 8월 정정 → 상각비만 재점검·재실행·재검토(충당금 승계)·옛 결과 응답 409·상신 재클릭 같은 보고 ID·승인 대기 2행·승인 0), 이전 실행 응답이 최신을 덮지 않음, 세계 따라가기(「장면 열기」·장면 2부터 다시), 대시보드 업무 32, 기록 스키마(`docs/records/s3/sc02/`), 확장 0.14.0 ↔ 그림 |
| `tests/dashboard.test.ts` | 대시보드 표기 — 억·만·원과 부호(−), 없는 값은 0이 아니라 「미산출」, 가상시각은 KST 그대로, 회사 사이트 업무 화면 주소(사이트·세계가 없으면 링크 없음) |
| `engine/tests/test_events.py` · `test_notify.py` | SSE 허브 구독 해제, 다른 워커로의 전파(Postgres) |
| `engine/tests/test_preparation.py` | 장면 시작 배경 진행 — 오래 걸리면 202 → 준비 상태 → 문서, 빨리 끝나면 201, 겹친 시작은 같은 진행, 앞 장면 진행 표시, 배경 실패의 사유·상태 코드, 모르는 사례 422(아무것도 만들지 않음), 모르는 준비 404 |
| `engine/tests/test_sc07_calc.py` | **통합가상데이터 v0.7과 대조** — 앞 92개 시트 = v0.6(값·수식), `SC07판단` 5행(유효 확인·소요 분·120분·마감·적시 공급·후보), `SC07검증결과` 8행을 규칙으로 다시 계산(데이터 PASS를 옮기지 않는다), `SC07요약`·`SC07적용` 판정 ST707·운영 실행 미확인, AT703 무효·지정만 대행, AT704 누락 사유(MISSING·ACCESS_DENIED·NOT_JOINED, 0분 아님), AT705 120분·121분·120분 1초·재공유, AT706 마감 초과 추가 검토, 시각 역전 DATA_INVALID, AT707 페이로드 정답 차단, AT709 확인 조건(CFO 미확인·역할 중복·구버전), AT710 적용 증적(예약·버전·범위·미래 시각), 적재 검사(중복·참조 누락·버전 공란), KST 시각 |
| `engine/tests/test_sc07_process.py` | 장면 6 대표 보고까지 각본 실행 후 적재(확인 전), Studio 장면 6 409, **각본 끝 = SC07확인이력·SC07적용**(행위자·시각·글·버전·업무 완료 시각), AT708 장면 1~6 문서 불변, 장면 6 기록이 바뀌면 TC707 실패 → 「검증 미통과」 끝, 담당 403·대상 버전 422·순서 409, 보완 요청 → 「보완 필요」 끝, 예약 설정 「일치」 422 → 불일치 → 다시 반영, 초기화, 조회 계약 넷·미실행은 NOT_RUN·403·404·409, **조회가 문서·이력을 바꾸지 않는다**, BPMN ↔ 역할표·담당 이름, HTTP — **SQLite·Postgres 양쪽** |
| `engine/tests/test_sc07_external.py` | 기본 확장 `external` 0.7.0 ↔ BPMN(계약 검사·입력·출력·답한 사람·`데모실행ID`·오류 경계), Studio 흉내로 후속 점검까지(늦게 연 업무·같은 기록), 예약 설정 「일치」 → 기록 거절 → 같은 결재, 콘솔 관리자 답은 담당으로 기록, `origin` ↔ 실행 위치 409, 착수 전 열기 409, 가짜 Center + 실행기 흉내로 각본 끝까지(대리 답·운영담당 이름 결재·거절 0), 사전 검사가 Center보다 먼저, 설정 없음 사유·503, 초기화가 작업을 거둠, 사이트가 먼저 답한 결재를 각본이 다시 대리 답하지 않음 |

* 엔진 테스트는 SQLite와 Postgres 두 백엔드를 모두 돈다(Postgres 포함 869개, 2026-11-03). 자리표시자·행 접근·JSON
  타입이 전부 달라 한쪽만 돌리면 나머지가 배포 시점에 터진다. CI는 `REQUIRE_POSTGRES=1`로 skip을
  실패로 바꾼다.
* TS 토폴로지 사본(`tests/fixtures/sc0N-process.json`)과 그것을 BPMN과 대조하던 엔진 시험은 캔버스와 함께 걷었다(2026-11-03).
* 렌더링 테스트는 두지 않는다 — 레이아웃·가독성은 브라우저에서 본다(4.13·4.14).

### 4.9 실시간 전파 (SSE · Postgres LISTEN/NOTIFY)

> **웹은 SSE를 쓰지 않는다**(2026-11-03 — 장면 화면과 `SessionSync`를 걷었다, BFF도 `…/events`를 중계하지 않는다). 대시보드는
> 10초 폴링이다(4.6). 엔진의 SSE 허브·`pg_notify` 전파는 엔진 시험(`test_events`·`test_notify`·장면 API 시험)이 쓰는 그대로 남겼다.

**폴링이 아니라 push다.** 상태가 바뀌는 계기가 전부 우리 코드를 지나간다(수신·응답·시계·초기화).
Chaeksas가 몰래 진행하는 일은 없다 — 서비스 태스크도 그 호출 안에서 돈다.

```
조작(워커 A) → notifier.publish("sc01:{id}")
   SQLite  → hub.fanout                        (같은 프로세스)
   Postgres→ SELECT pg_notify('nowview_instance', id) → LISTEN 중인 모든 워커 → hub.fanout
엔진 GET /sc01/demo-runs/{id}/events → (예전: BFF 중계 → EventSource → Sc01SessionSync → 스토어)
```

* **`event: ready`가 초기 전송의 끝을 알린다.** 클라이언트는 이것을 받으면 폴백 폴링을 멈춘다.
* **폴링을 지우지 않았다.** SSE는 프록시·네트워크 환경에 따라 막힌다. `EventSource`의 `onerror`는
  "영구 실패"가 아니라 "지금은 서 있지 않다"이고, 그 동안만 15초 폴링이 돈다.
* **알림은 부수 효과다.** 루프가 없거나 구독자가 없으면 조용히 넘기고, 전송 실패도 변경을 실패시키지
  않는다 — 여기서 터지면 조작이 실패하는 셈이다. 놓친 알림은 안전망 재조회(20초)가 덮는다.
* **`NOTIFY`가 아니라 `pg_notify`를 쓴다** — `NOTIFY`는 바인드 파라미터를 받지 못한다.
* **보낸 프로세스도 자기 알림을 되받는다** — 그래서 Postgres 경로에서는 로컬 전달을 따로 하지 않는다.
* 15초마다 `: keepalive`를 보내고, 버퍼링을 막는 헤더(`X-Accel-Buffering: no`, `no-transform`)를 엔진과
  BFF 양쪽에 둔다. BFF는 클라이언트가 끊으면 `request.signal`로 상류도 끊는다.
* **구독 해제는 `async with hub.subscribe(...)`로 확정한다.** async generator로 두면 `break`로 빠져나갈
  때 `finally`가 미뤄져 구독자가 누적됐다(테스트가 잡았다).
* `/health`의 `notify.kind`·`listening`이 전파 방식을 드러낸다 — "여러 워커인데 알림이 로컬"인 상태를
  눈치챌 수 있어야 한다.

**실측**(SC01): 실제 엔진에서 각본 9단계를 HTTP로 돌리는 동안 SSE가 변경 16건을 모두 실어 BPM 대기
지점이 `Approve_DQ → … → Accept_FIN → []`로 바뀌는 것을 받았다. (이전 구현에서 두 프로세스·같은
Postgres로 잰 워커 간 전파는 0.026초였다.)
### 4.10~4.12 섹션 탭 · 해설 모드 · 데모 플레이어 — 걷었다

장면 화면과 함께 걷었다(2026-11-03). 해설·업무 설명은 회사 사이트(`/scenario`·업무 화면)로 갔다. 설명과 실측은 git 이력(`79f6ea9`)의
이 절에 있다. 다른 화면에 다시 쓸 만한 교훈만 남긴다:

* **숨겨진 브라우저 패널에서는 `requestAnimationFrame`·`ResizeObserver`가 발화하지 않고 스크롤·resize 이벤트도 배달되지 않는다**
  (`behavior: "smooth"`도 움직이지 않는다). 그런 패널에서 검증하려면 `dispatchEvent(new Event("scroll"|"resize"))`로 깨우고
  `behavior: "auto"`로 본다. 타이머가 필요하면 `setTimeout`을 쓴다.
* **목차·탭은 선언하지 않고 지금 그려진 DOM에서 파생한다** — 손으로 적은 목록은 조건부 카드와 곧 어긋났다.
* **고정 UI의 높이를 상수로 박지 않는다** — 화면 폭에 따라 달라졌다. 재서 CSS 변수로 넘긴다.
* 방법론 설명(「왜 이렇게 보는가」)과 화면 사용에 필요한 말(「이 수치가 무엇인가」)은 문장 단위로 가른다.

### 4.13 UI 토큰과 서드파티 스타일

**라이트 모드에서 페이지와 카드가 둘 다 `oklch(1 0 0)`이었다.** 박스를 가르는 것이
`ring` 하나뿐이어서 "제목줄·내용·박스가 분간되지 않는다"는 지적이 정확했다.

* **`--card`는 건드리지 않는다** — 차트 팔레트가 그 값(라이트 `#ffffff`, 다크 `#171717`)을
  서피스로 잡고 검증했다. 대신 **페이지를 한 단 낮췄다**(`--background` 0.967).
  다크는 페이지가 이미 거의 검정(`#0a0a0a`)이라 더 내릴 수 없으므로 **경계를 세웠다**
  (`--border` 10% → 16% 흰색).
* 페이지를 내리면 **`--muted`도 같이 내려야 한다.** 0.97에 두면 카드 밖의 칩·배지가
  0.967 배경에 묻힌다.
* 제목과 설명의 단차를 벌렸다 — 제목 500 → **600**, 설명 14px → **13px**.
  실측 대비(카드 대비): 제목 19.8:1 / 설명 5.9:1(라이트), 17.2:1 / 6.9:1(다크).
* 카드 `ring`은 `foreground/10` 대신 **`border` 토큰**을 쓴다. 안 그러면 위의 다크
  경계 강화가 카드에는 먹지 않는다.

**화면 틀은 남색 + 남보라 강조다**(2026-10-27, "단색이라 대시보드·데모 성격에 맞게"). 토큰은 `--brand`(278°) ·
`--brand-soft` · `--ink`(틀 남색)이고 `--primary`·`--ring`이 `--brand`를 따른다.

* **색상(hue)을 차트와 비켜 잡았다** — 계열색 파랑(255°)·주황, 상태색 초록·노랑·주황·빨강과 겹치지 않는 남보라다. 틀의
  강조가 차트에서 계열·상태로 읽히면 4.4의 역할 분리가 깨진다. `--brand`를 차트에 쓰지 않는다. `--card`는 그대로다.
* 공통 줄은 `.chrome-ink`다 — 그 안의 토큰(배경·글자·muted·border)을 어두운 판으로 바꾼다. **`.dark`를
  붙이지 않는다** — 테마 버튼 아이콘이 `dark:` 변형으로 갈려 라이트에서도 해 아이콘이 보인다.
* 강조를 쓰는 곳: 기본 버튼, 카드 hover 테두리, 회사 사이트 링크, 결재 진행 막대.

**서드파티 CSS는 우리 뒤에 주입된다** — 컴포넌트에서 import한 라이브러리 스타일시트는 `globals.css`보다 나중에 와서 같은
특이도로는 진다(클래스를 두 번 적어 특이도를 올린다). 예전 React Flow 확대·축소 버튼이 다크에서 흰 버튼에 흰 아이콘이 됐다(대비
1.0 — 콘솔 경고 없음). 캔버스를 걷으며 그 덮어쓰기도 걷었다.

**`scripts/validate_palette.js`가 없었다 — 넣었다.** `globals.css` 주석과 4.4가 오래
그 명령을 가리키고 있었지만 파일이 커밋된 적이 없었다. 즉 "색을 바꾸면 검증기를 돌린다"가
돌릴 것 없이 적혀만 있었다. Claude Code `dataviz` 스킬의 구현을 **그대로** 가져왔다 —
고치면 스킬이 갱신될 때 병합할 수 없으므로 로직은 손대지 않는다.

들여온 뒤 **문서가 이미 주장하던 두 가지를 그대로 재현하는지로 검증했다**:

| 문서의 주장 | 검증기 출력 |
|---|---|
| nova `--chart-1~5`는 chroma floor를 통과하지 못한다 | 5개 전부 `C = 0` → FAIL (`reads gray`) |
| 라이트에서 warning·serious는 대비 3:1 미만 | `#fab219` **1.83:1** · `#ec835a` **2.64:1** → WARN |

현재 팔레트는 계열색·diverging 모두 **라이트/다크 양쪽에서 전 항목 PASS**다.
4.13의 토큰 변경은 서피스 두 값을 바꾸지 않았으므로 이 결과가 그대로 유효하다.


### 4.14 좁은 화면 (모바일)

장면 화면을 폰으로 보다 드러난 것들(실측 표는 git 이력 `79f6ea9`의 이 절). 대시보드에도 그대로 쓴다:

* **`flex-1`은 `flex-wrap`에서 줄바꿈을 유발하지 못한다** — 기여 폭이 0이라 혼자 눌려 글자가 세로로 쌓였다(폭 22px · 높이 512px).
  버튼과 한 줄을 나눠 쓰는 문단은 `basis-full sm:flex-1 sm:basis-0`. 찾는 법: `main` 안에서 폭 60px 미만·높이 120px 초과·자식 없는
  요소를 훑는다.
* **`shrink-0`·긴 `<select>`가 잘라 먹는다** — 페이지 가로 스크롤이 안 생겨도 자식이 화면 밖으로 나간다. 문서 폭(`scrollWidth`)과
  요소 오른쪽 끝을 함께 잰다. 대시보드의 회차 선택이 375px에서 그랬다(옵션 글이 길다 — 좁을 때 `w-full min-w-0`).
* **표 안의 `sr-only`가 문서 폭을 늘렸다**(`position:absolute`가 스크롤 상자를 벗어난다) — 표 머리의 이름은 `aria-label`로 준다.
* 부차적 컨트롤은 좁을 때 라벨을 버리고 `sr-only` 라벨을 둔다.
* 숨겨진 패널에서 뷰포트를 바꾸면 `resize`가 오지 않는다(4.10~4.12) — 폭·높이를 명시해 바꾸고 재기 전에 깨운다.

### 4.15 이전 구현(가동률 시나리오 · LangGraph)에서 남긴 교훈

2026-10-19까지 이 리포는 기획안 v0.1 기준의 다른 사건(파워트레인 가동률 85% 이탈, 영업이익 428억)을
Mock 데이터와 LangGraph 엔진으로 보여 줬다. SC01로 바꾸며 코드는 지웠다(git 이력에 있다 — 브랜치
`feat/sc01-chaeksas` 이전 커밋). **장면 2~7을 만들 때 다시 꺼낼 원칙**만 남긴다:

* **미완료 Agent의 산출물은 어느 패널에서도 보여 주지 않는다.** 경로가 둘이면 두 번 다 막아야 한다 —
  실제로 두 번 새어 나왔다(실행 기록과 노드 설명 문장).
* **과제 효과의 이중 계상 금지.** 이미 Forecast에 반영된 과제를 또 더하면 Gap이 실제보다 메워져 보이고,
  금액이 그럴듯해서 눈으로 안 잡힌다. 승인 직후 과제는 현재 Forecast를 바꾸지 않고 "다음 Rolling 반영
  예정"으로만 잡는다(기획안 6.8의 "이미 실적에 반영 / 승인되었으나 실현 전 / 검토 중" 구분과 같다).
* **대안은 효과·비용·위험·실행 조건을 함께 낸다.** 비용(일회성)과 효과(연간)는 시간 단위가 달라 빼지
  않고 회수 기간으로 본다. 조건 없이 효과만 적힌 대안은 비교가 아니라 홍보다.
* **트레이드오프를 숨기지 않는다.** 임계치를 조이면 감지가 늘지만 오탐도 는다 — 부작용 없는 개선
  제안은 검토가 아니라 홍보다. 백테스트는 공식이 아니라 표다(없는 정밀도를 주장하지 않는다).
* **Agent가 늘 확신에 찬 결론만 내면 사람이 검증할 지점이 없다.** 신뢰도·불완전한 근거(caveat)·
  못 답한 질문(무엇을 모른 채 결정하는가)을 결론과 함께 보인다. 정보가 부족하면 추측하지 않고 묻는다.
* **Agent가 계약을 못 맞추면 지어내지 않고 실패한다.** `kimi-k3:cloud`는 ollama `format` 스키마를 무시했다
  — 스키마를 프롬프트에 넣고 검증·재시도해야 했다. temperature 0이어도 같은 질문에 14.2와 14.5가 나왔다:
  LLM 경로는 값이 아니라 **계약**을 검증한다.
* **설계표·문서는 구현에서 생성한다.** 손으로 쓰면 구현이 바뀔 때 문서만 낡는다. 근거가 없는 칸은
  지어내지 않고 "미정의 — 경영 판단 기준 작성 필요"로 남긴다.
* **값마다 출처를 밝힌다**(기획안 2.3) — 시나리오 설정값 / 시스템 계산 / 실측. 구분이 없으면 데모의
  주장을 검증할 수 없다. 화살표는 값의 증감을, 색은 좋고 나쁨을 가리킨다(한 기호에 둘을 싣지 않는다).
* **승인 후 진행 지점·결정이 데모 플레이어에 가려졌다.** 플레이어가 상태를 장면마다 절대값으로 덮어쓰면
  "화면 간 연동"의 버그가 데모로는 안 드러난다 — 실제 조작 경로로도 돌려 봐야 한다(SC01 플레이어는
  그래서 엔진 각본을 실제로 실행한다).
* **LLM을 요청 안에서 여러 번 부르면 프록시가 끊는다.** Cloudflare 원본 응답 타임아웃은 약 100초다 —
  Agent 3개를 연달아 돌린 생성이 524로 끊기고 인스턴스는 고아가 됐다. 긴 진행은 배경으로 보내고
  SSE로 알리며, 배경 실패는 상태에 남긴다. 노드 사이 스냅샷이 "끝남"으로 새지 않게 진행 중 표시를 둔다.

> **4.16~4.21과 5.3·5.6~5.11의 화면 이야기**(U21… 화면 · 플레이어 · BPM 캔버스 · GNB 장면 칩 · 375px 실측 · 화면 검수)는 걷은
> NowView 장면 화면의 기록이다(2026-11-03 4단계). 엔진의 업무 규칙·계산·Center 실측은 그대로 유효하고, 업무 화면은 회사 사이트에 있다.

### 4.16 SC02 — 단가 인상 검토와 수익성 영향의 경영검토 연결 (장면 2)

공급사 SUP-01이 공통부품 P-COM01(a·b모델 각 1개)의 단가를 2,000 → 2,200원으로 올려 달라고 한다. 구매담당이
접수·팀장 보고·요청안 분석·1차 협상(2,120원)·재분석·기안을 하고, 팀장 → 임원 → (12개월 증가 ≥ 1천만원이면)
대표가 승인한다. 승인 조건으로 원가 버전 C02-APP01을 등록하고, 장면 1 물량 감소(ISSUE-B07)와 장면 2 원가
상승(ISSUE-COST01)을 상위 검토건 MR-2706-01에 **각각** 걸어 경영관리에 넘긴다. **끝나도 위험은 열려 있고 F02는
검토 중이다**(SCOPE-01) — 「장면 2 인계 완료, 장면 3 손익 검토 대기」.

```
engine/processes/sc02.bpmn ──▶ Chaeksas Engine ── chk:serviceCall external ──▶ app/sc02/process.py
                                                                                      │ domain.py · calc.py
                                                                                      ▼
                         sc02_demo_run(id = 장면 1 데모 실행 id) · sc02_history → notifier("sc02:{id}") → SSE
```

**장면 1과 이어지는 방식**

* **데모 실행 id가 장면 1과 같다**(DATA-22). 테이블만 다르다(`sc02_*` — `Sc01Store`의 `prefix`). 장면 1 문서에
  장면 2를 얹지 않았다 — SC01 문서·업무 동기화·바깥 실행 규칙을 건드리지 않으려는 것이다.
* **장면 2는 장면 1 인계에서 시작한다.** `POST /sc02/demo-runs`는 장면 1이 인계 전이면 **각본의 남은 단계를 실제로
  실행**한다(역할 검사·업무 규칙 그대로). `sc01DemoRunId`가 없으면 장면 1 실행부터 새로 만든다 — X 사례는 그래서
  별도 데모 실행이다(ERR-21).
* **화면은 장면 2를 저절로 만들지 않는다.** 만들면 화면에 들어온 것만으로 장면 1 상태가 바뀐다. 404면 「장면 2
  시작」을 묻는다(`Sc02StartCard`, 플레이어).
* **장면 1 결과는 스냅샷이다**(`doc.sc01`) — 인계 run·F02 승인 상태·ISSUE-B07. 장면 1을 초기화해도 장면 2 근거는
  그 시점 것이다(ERR-24 「완료된 승인과 당시 근거는 보존」). 장면 2 초기화도 스냅샷을 그대로 쓴다.
* **장면 1 F02의 2027 물량이 통합 데이터와 다르면 409다**(`baseline_from_sc01`). 장면 2 기대값은 기본 F02 기준이고,
  상충하는 데이터는 임의 보정하지 않는다(구현명세 1장). 장면 1을 정정(EX03)한 실행은 장면 2를 시작할 수 없다.

**경계·범위에서 정한 것**

* **Studio 시험 실행·Center 서버 실행에서 돈다**(SC01 N1~N6과 같은 틀). 처음(2026-10-27 오전)에는 내장만 만들었다가
  「BPM은 Center에서 도는 것 아니냐」는 지적으로 같은 날 붙였다. 구성:
  * **기본 확장 `external` 0.2.0으로 옮겼다**(2026-11-01) — 작업 13개를 업무 이름으로 더했다(`screen_price_request`·
    `record_price_request_review`·`record_purchase_report`·`analyze_price_request`·`request_price_review_draft`·
    `record_price_negotiation`·`analyze_price_negotiation`·`submit_price_proposal`·`record_price_decision`·
    `judge_price_authority`·`register_cost_version`·`hand_off_cost_review`·`accept_cost_review`). 예전 `nowview-sc02` 0.1.0
    (HTTP 본문 템플릿)은 걷었다. `test_sc02_external.py`·`test_consumer.py`가 정의 ↔ 그림을 잠근다.
  * **회사 시스템을 지난다**(같은 날) — 구매 마스터(부품 구성·현행 단가)는 Company1 기간계 `GET /company/purchase/master`에서
    읽어 엑셀의 같은 칸을 대신하고(`seed.with_company` — 외주비가 엑셀 C01과 다르면 409), 요청 「수신」은 공급사가 회사 구매
    수신함에 보내고(`sim/price-requests`) NowView가 사본을 들인다. 원문 확인 결정과 원가 버전 C02-APP01은 `_commit`에서 회사에
    적는다(503이면 저장 안 함). 초기화는 회사 세계의 장면 2 기록만 지운다(`purchase/reset`). 회사와 오간 것은 `company_log`.
  * **BPMN**(원본 Company1 `bpm/company1/company1.sc02`, 0.2.0): `chk:process.extensions`에 `external`(`>=0.2.0,<1`), 결재
    `show`에 `데모실행ID`(회사 사이트의 회사 자료 카드), 결재마다 `answered_by_as`·`answered_via_as`, 기록 작업
    10개마다 오류 경계(`Bnd_Record_*` → 같은 결재), 기록 출력 `error_message`. 팀장 결재 기록은 `condition`·`due_at`을 빈 글
    리터럴로 싣는다 — 본문 템플릿의 입력은 늘 있어야 한다(4.3).
  * **기록 작업이 사전 검사를 다시 한다**(`process._recheck` → `domain.check_answer`). Studio 대화상자·Center 콘솔 답은 NowView
    사전 검사를 거치지 않는다 — 처음에는 검사 오류가 남은 요청을 「확인완료」하면 부수 효과 단계에서 422로 터졌다(시험이 잡았다).
    거절은 감사 이력 `answer_rejected`에 남고 반쯤 적힌 효과는 버린다.
  * **실행 잇기·키**: SC01 `link_external_run`·`note_external_progress`를 그대로 쓴다 — 첫 호출이 묶고, 키가 실행 위치를 말한다
    (어긋나면 409). Studio는 기록 때 업무를 늦게 열고(`opened_late`), 끝은 작업 호출로만 안다 — 종료로 가는 결정(반려·추가
    협상지시·미합의·검토 종결·보완 요청·인수)이 기록되면 끝으로 본다(`domain.TERMINAL`). **Center는 그렇게 끝내지 않는다** —
    끝냈다고 적으면 폴링이 멈춰 도달한 종료를 읽지 못했다(시험이 잡았다). Center는 `run_finished`로 안다.
  * **Center**: 요청 접수 → `POST /jobs`(패키지 `CHAEKSAS_SC02_PACKAGE`, 기본 `company1.sc02`, 멱등 키에 초기화 회차). 화면 답 =
    대리 답(사전 검사 → 열린 결재 찾기 → 답). 폴러는 장면 1·2를 차례로 읽는다(`CenterPoller(sc01, sc02)`). 결재가 열릴 때 업무를
    연다. 끝나면 실행 기록에서 시작만 있고 끝나지 않은 종료 이벤트를 지나온 노드에 넣는다. 초기화는 앞 작업을 거둔다.
  * **설정이 없거나 Center가 거절하면 그 사유가 그대로 보인다** — 조용히 내장으로 돌지 않는다. 로컬 Center(:8800)에서는
    `nowview.sc02`가 아직 배포되지 않아 요청 등록이 422 `no_deployment`로 거절되는 것을 화면에서 봤다(아래 5.6 「Center에 올릴 것」).
  * 장면 2를 시작할 때 장면 1이 Center 실행이면 각본이 대리 답으로 인계까지 가고 인계 작업을 잠깐 기다린다. Studio 실행이면 409 —
    Studio에서 인계까지 진행한다.
* **사람 업무 12개 · 서비스 태스크 17개 · 종료 6개**(인계 완료 · 보완 대기 · 검토 종결 · 미합의 · 반려 · 재협상 대기).
  보완은 기안으로 되돌아가 새 버전(PROP01-v2)이고 팀장부터 다시 받는다 — 이전 결정은 보존하되 승계하지 않는다.
  대표 대상은 S09 서비스(`judge_authority`)가 금액으로 판정한다 — 위험 등급과 무관하다(AUTH-02).
* **상신이 그 버전의 분석 run을 만든다**(RUN-PROP01). 기안가·적용일이 협상안과 다르면 차이 사유가 필요하고(422),
  기안안 분석이 미산출(월중 적용·누락·중복)이면 상신이 409다. 협상을 다시 기록하면 같은 안의 이전 run은 낡음 표시.
* **결재 폼 칸의 기본값은 그 사례 각본의 답이다**(`view._defaults`, 2026-11-01 — 장면 1·6과 같다). 같은 결재가 두 번 나오는
  사례(X07R 보완 → 재상신)는 지금 각본 지점 뒤의 답을 쓴다. 예전에는 빈 폼이라 화면에서 직접 진행하려면 의견·근거를 손으로 썼다.
* **결재·인수는 화면이 본 버전을 싣는다**(`expect: {proposal}`·`{bundle}`) — 그 사이 버전이 바뀌었으면 409(U25-03).
* **화면에서 직접 답해도 각본 지점이 따라간다**(`process._follow_script`) — 기록 작업의 효과가 각본 **바로 다음** 단계의 결재면
  `step`·`script_index`를 옮긴다. 그래서 장면 2는 화면 답과 플레이어 「다음」을 섞어도 409가 아니고(4.1의 「섞으면 멈춘다」는 장면 1
  얘기다), 플레이어 위치도 `scriptIndex`를 따라간다(처음 받은 실행에도 — 저장된 위치는 실행과 무관하다). 예전에는 손으로 D12까지
  가도 D01·D00에 머물렀다(2026-10-27 Center 수동 진행). 결재 id는 단계별 순번이다(APP-T01·E01·C01 — 근거 id와 같다, 보완 뒤 APP-T02).
* **외부 협상기한은 사람이 넣는다**(요청안 분석 때, 기본 6/21 18:00). 협상 업무의 기한이 그것이고 변경은 이력으로
  남는다(`negotiation-due`). 내부 업무 기한은 SC01과 같은 달력(다음 영업일·두 번째 영업일 18시)이고, 「업무이력」
  시트의 due_at과 같은 값이 나온다(테스트가 잠근다).
* **추가 협상지시(X01)는 기록·배정까지다** — NEEDS_RENEGOTIATION, TASK-RENEG, 원가 등록·인계 차단. 상위 검토건에는
  **잠정 자료**(`provisional: true`)로만 걸린다(H23). 2차 협상·재기안·재승인은 후속 범위다.
* **`npm run build`를 dev 서버가 도는 중에 돌리면 dev의 라우트가 404가 된다** — 같은 `.next`를 쓴다. BFF가 모든 장면 경로에
  404를 냈다(앱 코드까지는 갔다). `npm run stack:restart web`으로 풀린다. 빌드 검증은 dev를 내린 뒤나 다른 체크아웃에서 한다.
* **Agent는 mock·fail뿐이다**(`app/sc02/agent.py`). SC01의 ollama 러너는 SC01 계약에 맞춰져 있어 쓰지 않았다. mock도
  같은 검증(본문 숫자가 규칙 결과에 있는가·근거 id)을 통과해야 화면에 나온다. 순간에 끝나므로 서비스 태스크 안에서 만든다.
* **시연 사례**: BASE · X01 · X02(2,050원 — 대표 비대상) · X04(8/1 적용) · X05(기안가 2,130원) · X06(미합의) ·
  X07R(보완 → 재상신) · X07J(반려) · X09A(2028-06 b 누락) · X09B(Agent 실패) · X10(중복 행). 자료 사례는 이 문서의 물량
  표만 바꾼다(`rows_override`) — 시드는 그대로다. X03·X08은 규칙 단위 시험값이라 실행 사례로 두지 않았다(테스트만).

**계산에서 정한 것**(`app/sc02/calc.py`)

* 기간은 **시작 포함·종료 제외**. 잔여 [적용일, 다음 해 1/1), 12개월 [적용일, +12개월). 12개월 창에 5모델 × 12개월이
  다 있어야 12개월 금액·승인선이 나온다 — 없으면 미산출·판정 보류다(대표 비대상으로 처리하지 않는다).
* **인상률 경계는 나눗셈 없이 비교한다** — `단가차이 ≥ 기존단가 × 임계값`(CALC-25). SC01의 비율 8자리 반올림을 가져오지 않았다.
* 협상 효과(M25)는 **요청안의 12개월**로 같은 기간에서 잰다. 적용일이 다르면 가격 효과와 적용일 연기 효과로 나눈다.
* 손익 연결은 F01+C01 → F02+C01 → F02+선택안. 고정비는 공장 월 1회, 모델 배부 없음. 12개월 물량 효과 −1,400만원도
  월별 재집계 결과다. 2028 Target이 없어 12개월 Target 차이는 미산출이다.
* **통합 영향(U27)은 한 안만 고른다** — 승인안이 있으면 그것, 없으면 최신 안을 **잠정**으로(`selectedProvisional`).

**만들며 드러난 것**

* **엑셀 ROUND는 0.5를 올린다.** 2028 물량(F01 × 97%)을 `Decimal.to_integral_value()`로 다시 내면 4898.5가 4898이 되어
  한 행이 어긋났다 — 짝수 반올림이 기본이다. `ROUND_HALF_UP`을 쓴다.
* **ruff의 줄 길이는 화면 폭으로 잰다** — 한글은 한 글자가 2다. 100자 제한이 한글 문장으로는 약 50자다. 주석이 넘치면 줄을 접는다.
* **종료 이벤트는 「시작」만 기록된다**(완료가 없다). 캔버스의 「끝났으면 종료 = 완료」 규칙은 종료가 하나인 장면 1에서만
  맞았다 — 종료가 여섯인 장면 2에서는 가지 않은 반려·재협상 종료까지 완료로 칠했다. 장면 2는 도달한 종료를 `visited`에
  남기고, `nodeStates`는 종료가 기록된 실행이면 그것만 완료로 본다(장면 1 동작은 그대로).
* **층이 많은 흐름은 넓게 편다.** 5열로 접으면 다섯 줄이 되어 fitView 배율이 0.3 남짓이었다 — 장면 2는 `maxColumns={8}`.
* **숫자 칸의 빈 값은 `null`이다**(`components/shared/form-field.tsx`). 빈 글(`""`)을 숫자 칸에 보내면 Chaeksas가
  형식 오류로 거절하고, 0으로 메우면 미합의가 0원이 된다. 장면 2 폼은 빈 값을 아예 보내지 않는다.
* **GNB에 장면 칩을 더하자 375px에서 화면 메뉴가 0px로 눌렸다**(4.14와 같은 종류). 좁을 때 「장면」 글자를 숨기고
  메뉴에 최소 폭을 줬다. 플레이어도 좁을 때 버튼 라벨을 숨긴다 — 154px → 120px.

### 4.17 SC03 — 수익성 변동의 통합 분석과 수시 경영검토 (장면 3)

장면 1 물량 감소(b 7월 −700대분, ISSUE-B07)와 장면 2 승인 단가(2,000 → 2,120원 7/1, ISSUE-COST01)를 기존 검토건
MR-2706-01에서 같은 기준으로 계산하고, 영업·구매·생산이 확인하고, 경영관리 임원이 수시회의(MT31 6/29 10시)에서 검토
결론과 상세 분석 대상을 정하고, 담당자가 분석과제 AT31~34를 인수하면 끝난다(HANDOFF31 → 장면 4 MT41 7/12).
**끝나도 Risk OPEN · Forecast REVIEW_PENDING · Target UNCHANGED다**(P37) — 「장면 3 완료」 ≠ 위험 해소 ≠ 전망 승인.

```
engine/processes/sc03.bpmn ──▶ Studio·Center(또는 시험용 내장) ── 서비스 태스크 external ──▶ app/sc03/process.run_operation
                                                                                                │ domain.check → domain.apply
                                                                                                ▼   (calc는 sc02 월별 계산 재사용)
                       sc03_demo_run(id = 장면 1·2 데모 실행 id) · sc03_history → notifier("sc03:{id}") → SSE
```

**숫자** — 연간 Target 3,477,290,000 · F01 3,323,351,000 · 물량 −14,000,000 · 승인 단가 −9,364,320 · 통합 3,299,986,680 ·
**기존 부족 153,939,000**(Target − F01) · 전체 부족 177,303,320. Q3 788,967,800 · 잔여 1,604,836,680 · 12개월 3,173,163,560
(Target 미설정 → 부족 NULL) · 12개월 구매 증가 18,817,440(손익과 다른 지표). 화면 기본 단위는 **백만원 소수 둘째 자리**다
(`lib/sc03/format.ts`, 장면 1·2의 억·만 표기와 다르다 — 구현명세 2장).

**경계·범위에서 정한 것**

* **착수(S31)는 BPM 밖의 화면 명령이다** — 경영관리 담당이 「분석 시작」을 누르면 검토건을 열고 내장이면 BPM을 시작,
  Center면 SC03 패키지를 기동(`POST /jobs`, `CHAEKSAS_SC03_PACKAGE` 기본 `company1.sc03`), Studio면 착수만 적는다. 그림의
  첫 작업(`open_review`)은 착수된 검토건인지만 본다. 재착수는 같은 결과다(T31).
* **사전 검사는 그림에서 읽는다**(`Sc03Process.answer_args`) — 결재 뒤 기록 작업의 `input` 대응으로 답을 작업 입력으로 바꿔
  `domain.check`를 부른다. 장면 2처럼 「칸 이름 ↔ 입력」 표(`_ANSWER_OF`)를 따로 적지 않았다 — 규칙이 한 벌이고 그림을
  고치면 따라온다. 기록 작업은 같은 `check`를 다시 한다(Studio·콘솔 답).
* **병렬 갈래의 폼 칸에 부서·과제를 붙였다**(영업회신·구매회신·AT31결정…). Chaeksas 변수는 실행 하나에 전역이라 세 부서가
  같은 칸 이름을 쓰면 서로 덮는다. 과제 인수는 **포함 게이트웨이**로 배정된 과제만 갈래가 열린다(`AT31배정`).
* **인수 결재의 담당은 과제 책임자다**(`assignees: "AT31책임자"`, 배정·재배정 기록이 이름을 돌려준다). 역할표의 역할과 별개로
  그 사람만 답한다(`NODE_ROLES.owner_of`) — 타부서 403, 임원도 대신 못 한다(E35).
* **완료는 대기가 아니어도 조건부터 본다**(`act`의 `Complete_Scene`) — 3/4 인수에서 누르면 「대기가 아니다」(409)가 아니라
  422 `COMPLETION_PREREQUISITE_FAILED`와 `blocking_items`다(T37). API는 `detail`을 객체로 싣고 화면이 목록으로 보인다.
* **결론과 후보 판단은 한 결재·한 명령이다**(Decide_Review 칸 15개) — 제외 사유 하나가 빠지면 결론까지 저장하지 않는다.
  포함 후보는 과제 초안(SC03과제 시트 원문)에 묶인다 — C32·C33 → AT32 한 건, AT34는 후보 없는 원인분석(Q32가 있으면).
* **쟁점 번호는 종류별로 센다** — 미확인은 Q31·Q32(데이터 그대로), 부서 이견은 QD31(E31). 판단 폼은 Q31·Q32 칸만 있다 —
  다른 미확인이 생기면 409로 막는다(그림을 고쳐야 한다).
* **확정본·회의록·인계는 고치지 않는다.** 초안 수정은 새 버전(REP31-v0 → v0.1), 이 버전이 바꾼 부서 확인은 STALE(재확인),
  재검토 뒤 확정은 v2. E34 새 전망은 **별도 실행·별도 보고버전**(REP31-v2-E34, REVISION_PENDING)이고 E34 사례에서만 받는다.
* **회의 기록(QA31~)·AG31 회의 요약·과제 초안 수정은 BPM 밖 명령이다** — 실행 위치와 무관하게 NowView 화면에서 한다.
* **시연 사례**: BASE · E31(구매 이견 → 보완 → 재확인) · E32(AT31 반려 → 재배정 v2 → 재인수) · E33(고정비 계수 2 → 계산 차단 →
  정정) · E34(확정 뒤 새 전망) · E36(Agent 실패 → 수동) · E37(완료 뒤 7/6 18:01 제출 지연 알림). E35는 엔진 시험으로 잠근다.
* **기한은 데이터의 일정이다**(`domain.SCHEDULE` — 회신 6/28 18시, 확정 6/29 9시, 회의 10시, 인수 6/30 12시, 제출 7/6 18시,
  취합 7/8 18시, MT41 7/12 10시). 정해진 시각이 지난 뒤 되돌아온 업무는 다음 영업일 18시다. 경과·영업시간(M40)은 분 단위다
  (145시간 25분 · 37시간 25분 — 투입시간이 아니다).
* **각본 입력은 시드에서 읽는다**(회신 문장·쟁점 처리·질의·후보 사유). 끝난 문서를 SC03 시트와 대조한다(`test_sc03_process`).
  예외: 한 명령으로 한 일(EV31-08 쟁점 판단 17:05)의 두 기록 시각이 시트에서 다르다(Q31 17:00) — 명령 시각을 따른다.
* **expected_version은 문서 행 버전으로 받지 않았다** — 장면 1·2처럼 낙관적 잠금(`row_version`, 409)과 객체 버전(`expect`의
  `report`·`assignment`)으로 막는다(구현명세 10장의 의도는 같다).
* **화면 직접 진행(Center)에서 드러난 것**(2026-10-28 점검 세션 — 버튼·역할 전환만으로 D30 → D41):
  * **사전 검사가 형식을 다 보지 않았다** — 회신기한 칸의 기본값 뒤에 「6/28 18:00」을 이어 치면 대리 답은 통과하고 기록 작업이
    422로 거절해 같은 결재로 조용히 돌아왔다. 회신기한 형식을 `domain.check`로 올렸다(화면에 422, 입력 보존).
  * **기록이 거절되면 Center는 같은 결재를 새 결재 id로 연다** — `sync_tasks`가 「대기 id가 다르면 새 업무」라 앞 업무
    (TASK-REQUEST)가 영영 「진행」으로 남아 끝난 일에 지연 알림이 생겼다. 끝나지 않은 같은 노드의 업무가 있으면 새 결재를
    거기 잇는다(이력 「기록이 거절되어 같은 결재가 다시 열렸다」). 거절 사유는 그 업무(`rejected`)에 남고 다시 열린 폼 위에
    보인다 — 사전 검사를 거치지 않는 콘솔·Studio 답의 거절도 사유 없이 묻히지 않는다.
  * **화면 답도 각본 지점을 옮긴다**(`process._follow_script`) — 손으로 D41까지 가도 플레이어가 「단계 1/26 D30」이었다. 장면 2의
    「바로 다음 결재만」으로는 안 된다: 확인·인수가 병렬이라 순서가 바뀌고, 조회·회의 기록·AG31은 화면에서 건너뛰어도 된다.
    화면이 한 결정을 `script_follow.ahead`에 모아 각본의 다음 결재가 거기 있으면 그것과 앞의 비결재 단계를 함께 지난다. Center
    각본이 대리 답한 결재의 기록은 `pending`으로 각본 몫이다(두 번 세지 않는다). 플레이어는 장면 2처럼 `scriptIndex`를 따라간다.
  * **대리 답 뒤 10~25초 화면이 비었다** — 폼은 사라졌고 다음 업무는 아직이다. 엔진이 「보냈는데 기록이 아직 안 온 결재」
    (`bpm.center.inflight`)를 세고 화면 머리가 「Center 반영 중 — … 다시 누르지 않아도 된다」를 보인다(기록이 오면 저절로 걷힌다).
  * **Center 각본은 결재 단계마다 그 기록이 올 때까지 기다린다**(`demo._await_landed` — `inflight`에서 빠질 때까지, 최대
    `center_wait_s`). 기다리지 않으면 다음 단계가 시계를 먼저 옮겨, 업무 18건 중 17건의 완료 시각이 다음 단계 시각이었다
    (Save_Analysis 15:00 → 16:00, 부서 확인 셋이 모두 6/28 15:00). 손익 숫자는 같아도 기한·지연·영업시간이 어긋난다. 장면 4의
    `_await_own_record`와 같은 이유다. 화면 직접 답은 시계를 옮기지 않아 해당이 없다.
  * 남은 것(점검 3·6·7): 손으로 진행할 때 회의 시각으로 옮길 시계 조작이 없다(「다음 영업일 18:30」뿐이라 개회 기한을 넘긴다),
    업무함 업무에 화면 링크가 없다, 기한 칸 형식 예시·인수율 표기 등 작은 표시.

**만들며 드러난 것**

* **GNB에 장면 칩 3을 더하자 375px에서 화면 메뉴가 역할 선택 위로 겹쳤다** — 칩 묶음(62px) + 메뉴 최소 폭(48px)이 nav 최소
  폭(88px)을 넘었다. 겹침은 넘침 검사로 안 잡힌다(4.14) — 요소 좌표로 쟀다. 칩 여백을 줄이고 nav 6rem·메뉴 2.5rem.
* **KPI 카드 제목이 섹션 탭이 된다**(4.10) — 숫자 타일 카드에 `data-index-skip`을 단다.
* **SC03 BPMN은 크다**(사람 노드 26 · 기록 태스크 22 · 오류 경계 22). 캔버스는 `maxColumns={12}`로 펴도 한 화면에서 작다 —
  확대해서 본다. 기록 태스크·오류 경계는 결재 노드에 접힌다.
* **BPMN·확장 정의는 생성기로 처음 만들었다**(남기지 않았다) — 이후로는 파일을 손으로 고친다. 정의 ↔ 그림은
  `test_sc03_external.py`가 잠근다(본문 `{{input.x}}` ⊆ 그림 입력, 출력 대응, 답한 사람, 오류 경계).
* **장면 2 계산의 월별 함수를 공개 이름으로 바꿨다**(`sc02.calc.monthly_rows`) — 장면 3이 같은 월별 공헌이익·원가 효과를
  쓴다. 다시 계산하지 않는다.

### 4.18 SC04 — 수익성 개선 대응안 검토와 실행 승인 (장면 4)

장면 3이 지정한 분석과제(AT31~AT34)의 결과를 부서 책임자가 내고 담당 임원이 확인하면, 경영관리가 비용·중복을 검증하고, 담당
임원들이 우선 실행안 3개를 공동 제안하고(REP41-v1 확정), 대표 주재 월간회의(MT41 7/12 10시)의 질의로 긴급구매 효과를 9월로 미룬
판단본(DEC41-v2)을 확정하고, 대표가 과제별로 결정(REV41 — 승인 2·조건부 1)한 뒤 승인서·회의록(APR41-v1·MIN41-v1)을 함께 확정하고,
실행과제 ACT41~43·조건 CON41·지원 SUP41·추가 발굴 DIR41을 등록해 전체·개별 책임자가 인수하면 끝난다(HANDOFF41 → 장면 5 상세 계획).
**끝나도 Risk OPEN · Forecast REVIEW_PENDING · Target UNCHANGED이고 CON41은 OPEN이다** — 장면 완료 ≠ 실행 완료 ≠ 위험 해소 ≠ 전망 승인.

```
engine/processes/sc04.bpmn ──▶ Studio·Center(또는 시험용 내장) ── 서비스 태스크 external ──────▶ app/sc04/process.run_operation
                                                                                                │ domain.check → domain.apply
                                                                                                ▼   (calc의 기준은 sc03 period 재사용)
                       sc04_demo_run(id = 장면 1~3 데모 실행 id) · sc04_history → notifier("sc04:{id}") → SSE
```

**숫자** — 대응 전 부족 177,303,320 · 보고 효과 137,200,000(REP41-v1) · 판단 효과 127,800,000(DEC41-v2, ALT42 8월 9,400,000 제외 ·
8월 준비비 2,000,000은 그대로) · 남는 연간 부족 49,503,320 · 조건부 제외 부족 85,103,320 · 정상 연간 357,600,000(참고, 합산 금지) ·
Q4 −34,278,880(목표 초과) · 총괄 예산 18,000,000(8·6·4, 예정 7,000,000·여력 11,000,000). 월 반복효과는 ALT41 3,000 × (15,000 −
8,000 − 1,000) · ALT42 (12 − 4) × 1,200,000 − 200,000 · ALT43 6,000 × (5,000 − 4,500 − 100)이다.

**경계·범위에서 정한 것**

* **기본 확장 `external` 0.4.0으로 옮겼다**(2026-11-02) — 작업 18개를 업무 이름으로 더했다(`open_improvement_review`·
  `submit_analysis_result`·`confirm_analysis_result`·`verify_improvement_effects`·`correct_improvement_effects`·`request_improvement_draft`·
  `recommend_priority_actions`·`freeze_improvement_report`·`open_monthly_meeting`·`draft_decision_report`·`confirm_decision_report`·
  `record_ceo_decision`·`draft_execution_approval`·`finalize_execution_approval`·`register_execution_actions`·`accept_execution_assignment`·
  `revise_execution_assignment`·`hand_off_execution_plan`). 예전 `nowview-sc04` 0.1.0은 걷었다. 그림은 Company1 `company1.sc04` 0.4.0
  사본(`>=0.4.0`, 결재 `show`에 `데모실행ID`).
  * **회사에 적는 것은 없다** — 결과·검증·판단·승인서·실행과제는 경영 기록이고, 실제 실행 품의·예산 거래는 장면 5 범위다(구현명세
    v0.2 — 장면 4 예산 위임은 정책 조회뿐). 시계를 옮기면 회사 세계 시각만 함께 옮긴다. Company1 사이트는 결재에 장면 3과 같은 근거
    카드(받은 고객계획·원가 버전)와 각본 예시 값(`scenarios/sc04.json`)을 붙인다.
  * **바깥 답에도 각본·시계가 따라간다**(장면 3 `_follow_script`·`_clock_to_script`를 들였다). 결재 폼 기본값은 각본 답이고(`view._defaults`),
    대리 답 뒤 「Center 반영 중」(`inflight`)을 보이고, 플레이어는 `scriptIndex`를 따라간다. **시계는 이번 결정의 단계 시각으로 옮긴다** —
    먼저 답해 둔 결재와 함께 지나갈 때 지나가는 마지막 단계 시각을 쓰자 AT31 확인이 AT32 제출 시각(15:00)에 적혔다(회사 사이트 실측,
    장면 3은 아직 마지막 단계 시각이다).
* **효과는 `SC04가정`에서 계산 서비스가 낸다** — 다른 SC04 시트(월효과·월손익·비교·예산과제·조건지시·회의·이벤트·인계)는 기대값과
  각본 입력이다. 기준 손익은 장면 3 계산(`sc03.calc.period`)을 월마다 다시 부른다 — 장면 3 문서의 숫자를 옮겨 적지 않는다.
* **가정의 시작은 「보고 시작」이다** — 「판단 시작」(ALT42 9/1)은 회의 뒤에 생기는 값이라 판단 초안의 변경으로만 들어온다. 판단 초안은
  보고본의 가정을 **복제**해 바꾼 칸만 고치고 같은 규칙으로 재계산한다. 폼은 한 칸씩이고 도메인은 여러 칸을 받는다(T403 시험).
* **중복 제거는 관계로 둔다**(`calc.DUPLICATE_OF` — ALT42 초안 할인 ⊂ ALT43 가격차, EVDC44). 두 안이 함께 적용되는 달의 ALT43 물량만큼
  초안 할인과 중복 제거를 같은 값으로 둔다. E402는 제거를 비운 초안(`duplicate_override`)이고, E401은 감가상각을 회피로 넣은 초안
  (`avoided_fixed`)이다 — 둘 다 **제출 초안만** 바꾼다. 검증이 막으면 그 안의 담당 임원이 보완(`Correct_Effects`, 담당은
  `보완담당자명` 변수)하고 가정 새 버전·결과 새 버전으로 재검증한다.
* **우선순위는 효과액 순이 아니다** — ALT42가 1순위(공동 기준 준비가 먼저)다. 과제·결정의 표시 순서는 대안 번호(ALT41→43)로 둔다.
* **대표 결정의 HOLD·REJECTED는 과제를 만들지 않는다**(E403) — 인수 갈래가 포함 게이트웨이(`ACT43배정`)라 열리지 않는다. 승인 범위
  효과·부족은 결정 때 다시 계산한다(121,600,000 · 55,703,320). 판단본(127,800,000)은 그대로다.
* **승인서 초안은 누락이 있어도 저장된다**(누락 목록과 함께) — 확정에서 422 `APPROVAL_INCOMPLETE`로 막고 승인서·회의록을 **둘 다**
  저장하지 않는다(E404). 대표가 「보완요청」을 고르면 초안으로 돌아간다. **금액 칸은 text다** — 빈 값을 null로 보내지 않고 빈 글로
  남겨 0으로 메우지 않는다.
* **인수 대상은 다섯이다** — ACT41~43(실행과제) · SUP41(지원 지시) · TOTAL(전체 책임 + DIR41). ACT42 인수가 CON41 **책임**을 함께
  넘긴다 — 이행은 OPEN 그대로(`execution_gate` BLOCKED_BY_CON41). TOTAL은 반려가 없다. 반려 보완은 경영관리 임원이 승인 범위 안의
  명확화로만 새 배정버전을 낸다 — 범위·책임·한도·기한 변경은 새 승인 버전(이번 범위 밖)이다.
* **종료 요건 미충족은 422 `COMPLETION_BLOCKED`**(장면 3의 `COMPLETION_PREREQUISITE_FAILED`와 이름이 다르다 — 구현명세 15장 그대로).
* **예산 위임은 조회만 한다**(`/budget-policy`, E407) — 전용·초과 거래·이력을 만들지 않는다.
* **새 사용자** — 생산임원 권태윤(`u-prod-exec`)·영업임원 남유진(`u-sales-exec`). 구매임원은 장면 2의 문지후다. 장면 3의 팀장 계정이
  결과를 쓰고(`USR-PROD/BUY/SALES/FINLEAD`) 임원 계정이 확인·인수한다 — 덮어쓰지 않았다.
* **시연 사례**: BASE · E401 · E402 · E403 · E404 · E405 · E408. E406(조건이 남은 완료)은 기본 결말이고 E407은 승인 화면의 조회다 —
  실행 사례가 아니다. T403·T408·T409·T413은 엔진 시험으로 잠근다.
* 일정(`domain.SCHEDULE`) — 시작 7/1 08:59, 제출 7/6 18시, 검증 7/7, 취합 7/8, MT41 7/12 10시, 승인 7/12 18시, 인수 7/13 12시, 계획
  제출 7/16 18시, CON41·SUP41 8/20 18시, DIR41 8/9 10시. 이벤트가 없는 중간 단계(판단 초안 10:30·승인서 초안 14:30·Agent)는 그 사이다.

**만들며 드러난 것**

* **v0.4 파일의 해시가 구현명세가 적은 값과 다르다**(명세 `ff71…`, 받은 파일 `7baa…`). 명세는 「결과로 입력본을 확인하라」고 해서
  결과로 봤다 — 137,200,000 · 127,800,000 · 49,503,320 · 357,600,000과 SC04검증 15줄이 전부 맞는다. 검토요약 외 시트는 v0.3과 같다.
* **장면 칩 4를 더하자 375px에서 화면 메뉴가 역할 선택에 다시 닿았다**(0.7px). nav 최소 폭을 7rem으로 올리면 테마 버튼이 화면 밖
  (문서 폭 386px)으로 밀렸다 — 좁을 때 칩 여백을 `px-0.5`로 줄였다(메뉴 184px · 역할 196px · 문서 375px).
* **SC03 화면을 sed로 옮기며 조사가 틀렸다**(「장면 4을」) — 숫자만 바꾸면 받침이 달라진다. 옮긴 뒤 「장면 N을/은/이」를 훑는다.
* **빌드 검증은 격리된 사본에서 했다**(dev가 도는 중 `npm run build` 금지, 4.16). 스크래치(tmpfs)로 `cp -al`(하드링크)은 파일시스템이
  달라 빈 디렉터리만 생긴다 — `node_modules`를 `cp -a`로 복사해야 Turbopack이 `next/package.json`을 찾는다.

### 4.19 SC05 — 결정 실행과 계획 갱신 (장면 5)

장면 4가 조건부 승인한 ACT42 긴급구매 축소를 구매 담당이 Agent 초안(AG51)으로 상세 계획(PL51-v1)을 쓰고, 생산 임원이 협조를
확인하고, 구매 임원이 확정하고, 경영관리 임원이 정합성을 확인한다(7/16). 준비 중 부재·정례회의 이후 접수의 애로가 드러나 범위 안
변경(PL51-v2 — 대행·수시 확인, 교육 8/18 → 8/19)을 같은 순서로 확정·확인한다(대표 재승인 없음). 8/20 CON41(구매 임원 충족)·SUP41
(경영관리 임원 확인)·REQ51(일회성 2백만원)·OP51(운영지원 80만원)이 모두 끝나도 9/1 09:00 전에는 착수하지 않는다(START51). 9/2 CP51
정상 대응(재고 80 + 기발주 120), 9/10 CP52 긴급 예외(운송 90만 + 할증 30만, 구매 임원 전결). 10/4 9월 초기 결과(60건 중 긴급 5건,
추가비 6백만, 순개선 8.2백만) 확인, 운영계획 OPL51~53(10월 4·11~12월 3건) 확정·확인, 10/5 RUN51·FC51-D 작성·부서 확인·제출, 10/6
대표 승인·게시(FC51), 15:30 후속 책임(FUP51~53·DIR41·RISK51)을 넘기면 끝난다(HANDOFF51). **끝나도 Risk OPEN · Target UNCHANGED이고
ACT42는 운영 추적 중이다** — 장면 완료 ≠ 과제 완료 ≠ 목표 달성 ≠ 위험 해소.

```
engine/processes/sc05.bpmn ──▶ Studio·Center(또는 시험용 내장) ── 서비스 태스크 external ──────▶ app/sc05/process.run_operation
                                                                                                │ domain.check → domain.apply
                                                                                                ▼   (calc 기초 손익은 sc02 월별 계산)
                       sc05_demo_run(id = 장면 1~4 데모 실행 id) · sc05_history → notifier("sc05:{id}") → SSE
```

**숫자** — 과제 전 연간 3,299,986,680 · 과제 순효과 129,000,000(마감 1~9월 37,200,000 + 잔여 10~12월 91,800,000; ACT41 86.0M ·
ACT42 36.8M · ACT43 6.2M) · 새 공식 전망 3,428,986,680 · Target 3,477,290,000 · 남는 부족 48,303,320 · 종전 FC50 3,427,786,680 대비
+1,200,000(9월 −1.2M · 11~12월 +2.4M) · 일회성 집행 7백만·사용가능 11백만. **129백만원 전체를 실현효과로 보이지 않는다**(마감 37.2M도
회피비용 비교모형이다).

**경계·범위에서 정한 것**

* **기본 확장 `external` 0.5.0으로 옮겼다**(2026-11-02) — 작업 27개를 업무 이름으로 더했다(`open_execution_plan`·`draft_execution_plan`·
  `request_plan_change`·`submit_condition_evidence`·`submit_execution_request`·`approve_execution_request`·`start_action_operation`·
  `receive_production_change`·`approve_urgent_purchase`·`record_purchase_order`·`confirm_initial_results`·`confirm_operating_plan`·
  `draft_rolling_forecast`·`publish_rolling_forecast`·`hand_off_follow_up` …). 예전 `nowview-sc05` 0.1.0은 걷었다. 그림은 Company1
  `company1.sc05` 0.5.0 사본(`>=0.5.0`, 결재 `show`에 `데모실행ID`).
  * **회사 시스템에 적는다** — 실행 품의(상태 이력)·예산 원장(약정·정산)·공식 전망(FC50 → FC51)은 회사 기록이다(Company1 기간계
    `execution-requests`·`budget-ledger`·`forecasts`, `docs/worker-interfaces.md` §4.2). 기록 작업이 아니라 **저장 직전의 대조**
    (`process._sync_company`)라 가상시계가 들인 배경 행(ACT41·43 품의·정산·FC50)도 같은 길이다. 적은 것은 `company_synced`, 회사와
    오간 것은 `companyLog`(조건·품의·착수 화면과 전망 화면의 카드). 회사가 받지 못하면 그 조작은 저장되지 않는다(503). 장면 5 초기화는
    회사의 장면 5 기록만 지운다. 고객 변경 원문·구매 주문·근거는 아직 NowView 시드다.
  * **바깥 답에도 각본·시계가 따라간다**(장면 4의 `_follow_script`·`_clock_to_script`를 들였다) — 시계가 가면 `catch_up`도 한다.
    **사전 검사도 옮긴 시각의 사본으로 본다**(`_as_if_followed`) — 지금 시각으로 보면 8/20 아침 근거(DOC51)가 없어 화면 답만
    404였다. **착수(`Start_Operation`)만은 답이 시계를 옮기지 않는다**(`HOLD_CLOCK`) — 적용일이 업무 조건이라 8/20 착수 답이
    9/1로 넘어가면 T506을 넘는다. 착수 시각은 플레이어 「다음 단계 시각」으로 옮긴다. 결재 폼 기본값은 각본 답이다(`view._defaults`,
    Agent 자리표시는 지금 초안으로 푼다). 회사 사이트 각본 사본은 Company1 `scenarios/sc05.json` — 대표 변경 고리처럼 같은 결재가
    두 번이면 사이트가 회사 세계 시각 이후의 첫 줄을 고른다.
* **시각이 지나야 보인다**(`domain.catch_up`, 구현명세 16장). 배경 원천(PL52·PL53 확정·확인, REQ52·REQ53, 예산 원장의 집행 행, 배경
  변경 CH53~56, 구매 주문 58건, 9/30 18:00 납기·품질 확인, FC50 9/6, DIR41 8/9, ACT41·43 운영 상태, 근거 문서의 작성·확인)은 가상시계가
  그 시각을 지날 때 문서에 들어온다 — 미래 행을 내려보내 화면에서 감추지 않는다. 의존이 없으면 기다린다(승인 전 품의의 정산 · 착수 전
  운영 인계는 들이지 않는다). **시각 이동은 사람의 승인·착수를 만들지 않는다** — D5xx 단계만 사람의 업무다(T528).
* **기초 손익은 과제 전 금액이다**(`basis_includes_action_effects=false`) — 장면 2~4 월별 계산(F02 × 승인 단가 반영 단위 CM)을 그대로
  쓴다. 7~9월은 같은 값을 가상 마감(`close_batch` CLOSE51)으로 쓴다. 과제 효과는 모델에 한 번(ACT41 → A-a, ACT42·43 → A-b), 공장
  고정비는 a~e 합계에서 한 번. 고정비 절감 입력은 막는다(T522).
* **효과 입력의 출처가 셋이다** — 장면 4 판단 가정(DEC41-v2, 스냅샷), 마감월의 **관측·집행 실적**(9월 긴급 건수·추가비는 확인된 초기
  결과, 일회성·운영지원은 예산 원장 정산의 손익비용), 잔여월의 **확인된 운영계획**(OPL51 긴급 건수, OPL52·53 월 적용량). 미확인 가정은
  RUN 오류다(CT510). 11~12월 3건은 담당 임원 판단이지 9월 실적의 외삽이 아니다.
* **FC50은 9/6 승인된 가상 중간 공식본이다** — 수치는 장면 4 판단 가정 손익과 같지만 별도 승인이다(DEC41-v2를 공식본으로 소급 전환하지
  않는다). 9/6 전에는 「해당 시점 공식본 미적재」. 변경 대사는 FC50 대비 변화만 원인별로 더하고(긴급·지원·일회성·적용량·기초) 설명 안 된
  차이가 0이어야 제출된다 — **X506(종전 공식본 + 승인효과 127.8M)은 126.6M가 설명되지 않아 막힌다.**
* **착수·대표 승인 요청·장면 완료는 대기가 아니어도 요건부터 본다**(`process.GATED`) — 품의 미승인에서 착수를 누르면 「대기가 아니다」가
  아니라 422 START_BLOCKED와 남은 요건이다(T505). 요건은 0/1씩이고 개수 합이나 ready 값으로 허용하지 않는다(M502).
* **유효 계획은 포인터다** — 변경안(v2)이 확정·경영관리 확인되기 전에는 v1이 유효하고, 미확정 변경안은 착수를 막는다(unresolved).
  범위(예산·효과 개시·최종 기한)를 벗어난 변경안은 NEEDS_SEPARATE_APPROVAL로 남고 그림은 변경 요청으로 돌아간다(X502 — 다음 요청이
  앞 안을 SUPERSEDED로 만든다).
* **대표 변경 건은 BPM 고리를 두 번 돈다**(접수 → 공유 → 구매 확인 → 대응 → [긴급 승인] → 발주 기록). 고리를 나가는 조건은 아직 받지
  않은 대표 원문(`domain.REPRESENTATIVE` — CP51·CP52)이 없을 때다 — 업무설계 V505 「대표 정상 건과 긴급 예외 건」이 시연 범위라서
  그렇게 정했다. 나머지 네 건은 같은 기준의 배경 기록이다. 그림에서는 변수 `변경ID`가 대상이고, 화면 답의 사전 검사는 진행 중인 대표
  건을 쓴다(사전 검사에는 그림 변수가 없다).
* **구매 확인은 지정 대행도 한다**(USR-BUY2 = 장면 2의 구매담당 윤채원) — CON41 충족 뒤에만, 임원 권한은 없다. 결재 담당자가 둘이다.
* **공유 60분·확인 120분**은 달력 경과분, 같으면 정상·넘으면 지연. 넘긴 첫 분에 담당 임원에게 한 번 알린다(CH54 → 9/17 11:31). 미확인은
  평균에서 빼고 따로 센다(X503). 구매 60건과 변경 6건은 다른 모집단이다.
* **긴급 전결**은 추가비 200만원 이하 구매 임원(SC05설정). 넘으면 422 — 상위 전결 전 실행 차단(T513). 미승인 긴급 주문의 실행 기록은
  422 URGENT_NOT_APPROVED(X504).
* **예산**: 승인과 약정(COMMIT)을 한 저장으로, 정산(SETTLE)은 같은 약정을 줄이며 집행. 일회성(과제 8·6·4, 총괄 18백만)과 운영지원(OP51
  80만원, 별도 원장)을 섞지 않는다. 약정 거래 id는 데이터의 시연 식별자(REQ51 → TX53, OP51 → TX57)를 쓴다.
* **전망 버전**: 작성마다 새 RUN과 검토안(FC51-D, FC51-D2 …). 입력이 바뀌면 그 RUN을 본 확인·제출이 STALE. 반려는 RETURNED이고 FC50이
  공식본으로 남는다(X507). 게시가 공식 포인터·공유 기록을 함께 바꾸고, 게시 뒤 입력이 바뀌면 FC52-D(새 RUN)로 간다 — FC51 불변(T526).
* **Agent(AG51~AG58)는 BPM 밖 명령이다** — 고정 초안 재생이라 REPLAY로 보인다(`mode`). 사람이 초안 id를 인용하면 MODIFIED_BY_HUMAN·
  ACCEPTED_BY_HUMAN, 검토 기록은 REVIEWED. 실패 초안은 인용하지 않는다(각본의 `@AG51` 자리표시가 성공 초안만 고른다, T530). AG57은 작성
  전 미리보기(`domain.compute_forecast`)를 설명한다.
* **구현용 보완**(구현명세 12장이 허락한 것) — 활동의 협조·비용은 데이터에 없어 각본이 채운다(`demo.COOPERATION`·`COSTS` — 내부 교육
  0원, 외부 운영 검증 2백만원은 활동 05). 정상 대응(CH51)의 필요일은 원문에서 앞당겨진 첫 구간 시작(9/8)이고 정상조달일은 비운다(재고·
  기발주로 충당). 활동 목록은 폼에서 한 줄에 하나(`번호 | 활동 | 담당 | 시작 | 종료 | 선행 | 협조 | 비용 | 완료근거 | 근거ID`)다 — 비용
  빈칸은 미입력이지 0이 아니다(T503).
* **시연 사례**: BASE · X502 · X503 · X506 · X507 · X508. X501·X504·X505·X509는 시도·거절 확인이라 엔진 시험으로 잠근다.

**만들며 드러난 것**

* **두 갈래가 모이는 곳에 병렬 게이트웨이를 두면 합류(join)가 된다** — 「변경 없음」과 「변경 확인」이 같은 병렬 분기로 들어가자 두 토큰을
  기다려 흐름이 멈췄다(대기 0건). 배타 합류(`Gw_Ready_Merge`)를 앞에 둔다.
* **v0.5 파일 해시가 구현명세가 적은 값과 다르다**(명세 `faa9…`, 받은 파일 `782b…`). 장면 4와 같이 결과로 확인했다 — 129,000,000 ·
  3,428,986,680 · 48,303,320 · 60건·긴급 5건과 SC05 시트들이 전부 맞는다. 기존 45개 시트는 v0.4와 한 글자도 다르지 않다(시험이 잠근다).
* **ruff 줄 길이(한글 2)** — 생성기로 처음 만든 코드의 주석·독스트링·문자열을 표시 폭으로 접었다. 이웃 문자열을 하나 쪼개며 괄호로 감싸면
  `("a" "b") "c"`가 되어 구문 오류다 — 이미 괄호 안이면 그대로 쪼갠다.
* **장면 칩 5를 더하자 375px 헤더가 오른쪽 여백을 11px 넘었다**(이미 칩 4에서 3px 넘치고 있었다 — 테마 버튼 끝 370px). 좁을 때 칩
  여백 1px·묶음 안쪽 여백 0, nav 최소 폭 5.75rem, 역할 선택 5rem으로 줄였다(테마 버튼 끝 359px · 문서 375px · 메뉴가 nav 안).
* 브라우저 검수에서 localStorage의 데모 실행 id를 바꾼 뒤 `location.reload()`를 하면 앱이 언로드 전에 옛 id를 다시 쓴다 — 다른 경로로
  이동한 뒤 바꾸고 돌아온다.

### 4.20 SC06 — 과제 완료와 성과 실현 검토 (장면 6)

대표 과제 완료 후 차 분기(2027 Q4, 측정 12/31 · 자료 마감 2028-01-07 18:00)에 세 과제의 완료와 성과를 검토한다. Q4 자료를 적재하고
(숫자는 규칙 계산), **확인 절차**(D601 착수 → D602·D603 담당 임원 성과 근거 확인 생산 ∥ 구매 → D604 경영관리 종합 확인 → D605 보고 결론
→ D606 보고본 확정 → D607 대표 월간 보고)를 BPM으로 돌린 뒤, 확인된 보고본 RPT61-v1을 **2028-01-14 11:00에 조회한다**. 조회는 두
화면·세 동작(210초)이다 — ① U601 요약 → ② ACT42 주요 차이 한 건(PO61-1103) 펼침 → ③ U602 보고 요약. 끝나도 RISK61 OPEN · PROP61
PROPOSED · FUP61 IN_PROGRESS이고 FC51 연간 전망·Target은 그대로다 — 보고 확정 ≠ 과제 실행 승인 ≠ 위험 종결.

```
장면 5 문서(FC51 산정본·HANDOFF51) ─┐
seed/SYN-SC06-v0.6.xlsx 원천 ───────┴─▶ domain.load_batch(검증) → calculate → sc06_demo_run(문서 1개, 확인 전 — confirm.pending_state)
                                                                                      │
engine/processes/sc06.bpmn ──▶ Studio·Center(또는 시험용 내장) ── external ──▶ app/sc06/process.run_operation
                                                                                      │ confirm.check → confirm.apply (CF61-* 기록)
                                       summary · variance · evidence · report ◀───────┘ 조회(멱등)
```

**숫자** — Q4 기대 91,800,000(BASE61 = FC51 Q4 과제 효과) · 확인 87,000,000 · 차이 −4,800,000 · ACT41 54.0 = 54.0 · ACT42 30.6 → 25.8
(기준 12건 × 120만원 × 3 − 실제 긴급비 16,800,000 − 운영지원 600,000) · ACT43 7.2 = 7.2 · 주문 180건 중 긴급 14건(INTERNAL 4·SUPPLY 9·
MIXED 1) · 확인 지연 5건(복합 포함) · Q4 관리손익(보조) 902,868,880 = FC51 907,668,880 + 효과 차이 −4,800,000, 목표 대비 +31,878,880.

**경계·범위에서 정한 것**

* **확인 절차는 BPM이다**(2026-10-28, `processes/sc06.bpmn` · `app/sc06/confirm.py`). 처음(10-27)에는 구현명세 11장 「SC06은 이미
  확인된 1/14 보고본을 조회하는 시점으로 시작한다. SC05처럼 단계별 결재를 재연할 필요가 없다」·13장 「이 장면의 조회를 결재 트리거와
  분리」를 근거로 CF61-*를 끝난 기록으로 적재하고 BPM을 두지 않았다. 명세는 「시연에서 결재를 재연하지 않는다」였지 BPM을 두지
  말라는 것이 아니었다 — 사용자 요청으로 확인 절차를 Studio·Center 결재로 돌린다. **조회는 여전히 결재 트리거와 분리돼 있다**(조회 넷은
  상태를 바꾸지 않는다). 시연 세 동작은 절차가 끝난 뒤의 조회다.
  * 결재 여섯(`confirm.NODE_ROLES`) — 생산 임원 권태윤(CF61-P) ∥ 구매 임원 문지후(CF61-B) → 경영관리 임원 강민서 종합(CF61-F, 재확인
    요청이면 두 확인을 다시) → 경영관리 담당 정하윤 결론(TXT61) → 강민서 확정(CF61-R + NOTE61, 보완 요청이면 결론을 다시) → 대표 임하준
    보고(CF61-M). 결재 담당은 사람 이름 하나다(N4) — 그 사람만 답한다(403).
  * **확정이 막힐 수 있다**(CT611) — 세 확인이 같은 보고 버전이고 결론 문장의 「…백만원」이 지금 산정의 기대·확인 합계·ACT42 숫자와 같아야
    한다. 아니면 422 `REPORT_INVALID`와 `blocking_items`(기록 거절 → 오류 경계로 같은 결재). **확정이 지금 산정을 보고본에 묶는다**
    (`report.calculation_version`) — 그 뒤의 재적재는 새 산정 버전이고 보고본 숫자는 그대로다(X61-05).
  * **데이터의 확인 기록(SC06보고)은 일정이자 기대값이다**(`doc["schedule"]`) — 기록 시각은 일정이다(가상시계가 앞이면 일정으로 옮긴다,
    시각 이동은 확인을 만들지 않는다). 각본(`demo.steps_for`)은 그 글을 답으로 넣고, 결재 폼 칸의 기본값도 그 글이다(`view._defaults`).
    끝난 문서가 시트와 한 글자도 다르지 않다(시험). 착수 시각은 데이터에 없어 1/11 09:00으로 정했다(구현용 보완).
  * **재확인·보완은 이력을 지우지 않는다** — 물러난 기록은 `record_history`(물러난 사유·시각)에 남는다. 업무는 새 번호(TASK-…-2)다.
  * **각본은 상태를 따라간다**(`demo.done_index`) — 착수했으면 0, 기록이 남은 단계까지. 화면에서 직접 답한 뒤 플레이어 「다음」이 409가
    아니다(장면 2 `_follow_script`와 같은 뜻). 병렬 확인을 구매가 먼저 해도 생산 단계가 남은 단계다.
  * **기본 확장 `external` 0.6.0으로 옮겼다**(2026-11-02) — 작업 6개를 업무 이름으로 더했다(`open_performance_review` + 기록 5:
    `confirm_performance_evidence`(두 담당 임원이 `record_id` 리터럴로 같은 작업)·`review_performance_summary`·`draft_performance_conclusion`·
    `finalize_performance_report`·`report_performance_to_ceo`). 예전 `nowview-sc06` 0.1.0은 걷었다 — 이제 업무별 옛 확장은 없다. 그림은
    Company1 `company1.sc06` 0.6.0 사본(`>=0.6.0`, 결재 `show`에 `데모실행ID`). `test_sc06_external.py`가 정의 ↔ 그림을 잠근다. Center
    패키지 id는 `CHAEKSAS_SC06_PACKAGE`(기본 `company1.sc06`).
  * **회사 시스템은 기준만 준다** — 4분기 기대 효과의 기준인 공식 전망은 장면 5가 회사에 게시한 기록이다. 적재 때 회사의 지금 공식본을
    읽어 장면 5 스냅샷의 FC51과 연간·월 손익을 대조한다(없거나 다르면 409 — 장면 3이 원가 버전을 대조하는 것과 같다, `_company_official`).
    읽은 것은 `companyLog`(확인 절차 화면의 「회사 시스템과 오간 것」)에 남는다. 확인 기록이 가상시계를 일정으로 옮기면 회사 세계 시각도 함께
    옮긴다(`_company_clock`, 초기화는 착수 전 1/11 09:00으로). **회사에 적는 것은 없다** — 확인 효과·원인·완료 판단·확인 기록·보고본·후속
    조치는 NowView 계산과 경영 기록이다. 4분기 구매 거래 180건·운영비·근거는 장면 5의 구매 주문처럼 아직 NowView 시드다. Company1 사이트는
    장면 6 결재에 같은 기준(공식 전망·실행 품의·예산 원장, `kind: "performance"`)을 붙이고 각본 예시 값(`scenarios/sc06.json`)으로 폼을
    채운다.
  * **업무 완료 시각은 그 결재의 기록 시각이다**(`confirm.complete_task`) — 대표 보고는 기록(10:00) 뒤 시계를 조회 시점(11:00)으로 옮기는데
    지금 시각을 쓰자 대표 보고 업무가 11:00에 끝난 것으로 적혔다(Center 실측).
  * **Center 각본은 자기 결재의 기록을 기다린다**(`demo._await_own_record`, 장면 4·5와 같다) — 회사 사이트가 구매 확인을 먼저 답한 뒤
    플레이어 「다음」으로 생산 확인을 내자, 다음 「다음」이 생산 기록이 오기 전이라 구매 확인을 남은 단계로 보고 이미 닫힌 결재를 다시
    대리 답하려다 409였다(섞어 진행 실측). 기다리는 동안 바깥 답이 그 단계를 지났으면 지금 문서를 돌려준다.
  * **과제 정보는 `task_info`다** — 과제 이름·완료일·근거(SC06과제성과)를 `tasks`에 두었더니 확인 절차의 업무가 같은 칸을 비우고 써서
    (`confirm.pending_state`) U601 표가 이름 없이 「완료 미확인」이었다(2026-10-28부터, 2026-11-02 화면 점검에서 드러남). 그 전에 만든 문서는
    원천에서 다시 읽는다(`domain.task_info`).
  * **2026-10-28 전에 만든 문서**는 확인 기록을 끝난 것으로 적재했다(`schedule`이 없다 — `confirm.is_bpm` 거짓). 조회는 그대로 되고
    착수·결재·각본은 409다. 플레이어 「초기화」가 적재는 그대로 두고 확인 전으로 돌린다(실행 위치는 Center).
* **장면 5 FC51에 잇는다.** 데모 실행 id가 같고, 장면 5가 완료 전이면 각본을 끝까지 실제로 실행한다(Studio 실행이면 409). FC51 산정본의
  Q4 과제·월 효과가 BASE61과 원 단위로 다르면 적재를 409로 막는다(CK61-14 — 기준을 실적에 맞춰 고치지 않는다).
* **원천만 읽고 기대값 시트는 시험이 대조한다.** 원천 = 설정·기준·실행실적·운영비·구매거래·변경근거·완료판단·후속조치·근거·Agent·보고.
  `SC06과제성과`는 과제명·완료일·근거·후속 글만 읽는다(TOTAL은 엔터티가 아니다). 요약·월효과·원인집계·운영지표·분기손익·검증은 계산 결과와
  대조하는 기대값이다 — 검증표의 PASS 글을 옮기지 않는다. `SC06예외`(X61-*)는 시험 fixture로만 쓴다(사례 선택에 없다).
* **적재 검증**(구현명세 8장): 숫자 칸 오류값·필수 열 누락은 적재 전체를 422로 거절한다(일부 적재 상태를 내보내지 않는다). 쉼표 문자열은
  읽는다. 긴급 주문의 연결(변경근거·승인자·승인시각·근거) 누락, 승인 전 발주, 같은 키 중복은 **대사 대기**로 두고 그 달 효과를 산정 보류로
  만든다(중복은 뒤의 행만 빼서 이중 합산을 막는다). 미확인 금액(null)은 0이 아니라 산정 보류다 — 확인된 과제만의 소계는 따로 내고 「전체
  확정 합계」라 부르지 않는다(X61-01). `data_status`는 대사 대기·보류가 하나라도 있으면 INCOMPLETE다.
* **수집 상태와 업무 판단을 나눈다**(J601~605, M602 검토 의견). JDG61은 「일부 보완 중」이지만 대체 근거 3건·영향 판단·판단자가 있어 검토
  가능이고, 미비(서명 PDF)·보완 담당·1/18 기한은 지우지 않는다. 대체 근거가 없으면 판단 보류(X61-02). 판단 기록 없는 자동 완료는 없다.
* **보고본은 산정 버전에 묶인다.** 보고 결론(TXT61)의 「…백만원」 숫자를 묶인 산정과 대조한다(어긋나면 `report.problems`). 확정 뒤 수치가
  바뀌면 `domain.reimport`가 새 산정(CALC61-v2)을 만들고 RPT61-v1·그 숫자는 그대로다 — 바뀐 과제에 걸린 확인(CF61-B)부터 종합·확정·보고를
  다시 해야 한다고 조회 응답(`newer_calculation`)이 알린다(X61-05·AT61-06: 운송비 +100,000 → 25.7 · 86.9). 같은 입력을 다시 적재하면 새
  버전을 만들지 않는다. **변경 저장 API는 열지 않았다**(9장 「기본 시연에는 변경 저장 API나 결재 버튼을 노출하지 않는다」, 11장 재적재는
  개발용 별도 권한).
* **원인별 비용과 기대 미달은 다른 지표다.** 원인별 합계는 긴급 14건 전체(16.8백만원)와 대사하고, 기대 미달(−4.8)을 원인에 배분하지
  않는다 — 섞은 표는 잔차가 미달액만큼 생겨 따로 짚는다(X61-07). 대표 주문 한 건으로 전체 원인을 추정하지 않는다.
* **Agent는 고정 기록 재현이다**(REPLAY). 사람 보정이 없는 초안은 후보(CANDIDATE)이고(X61-04), AG62의 후보 원인(INTERNAL)은 표시만 한다 —
  원인 집계는 거래마다의 최종원인(사람 확인)으로만 한다.
* **조회는 아무것도 적지 않는다**(AT61-09) — 문서·이력·감사가 그대로다. 문서 머리(확인 절차)는 SSE로 받고, 조회 넷은 행위자·데모
  실행·보고본, 그리고 확인 기록 수·보고본 상태가 바뀔 때만 다시 받는다. **초기화는 확인 절차만 되돌린다** — 적재(숫자·근거)는 같은
  원천으로 다시 쓰고, 지난 확인 기록은 이력 테이블에 남는다(구현명세 11장 「확정본·근거·확인 이력은 삭제하지 않는다」).
* **권한은 검토건 참여 조직만**(구현명세 9장) — 경영관리·구매·생산·품질·대표 계정과 시연관리자. 영업 등은 403이고 오류에 근거·금액을
  싣지 않는다. 화면은 403이면 「경영관리 담당으로 보기」를 묻고, 플레이어는 장면 이동 때 경영관리 담당 시점으로 바꾼다(역할 선택은 신뢰
  경계가 아니다, 5.4).
* **새 엔진 계정 대응은 없다** — 장면 5 `ACCOUNTS`를 그대로 쓴다(USR-BUY = 구매팀장, USR-BUY2 = 구매담당 대행).

**만들며 드러난 것**

* **장면 칩 6을 더하자 375px에서 화면 메뉴가 nav를 5px 넘었다**(역할 선택과 겹치지는 않았다). nav 최소 폭 6.25rem, 역할 선택 4.5rem
  (메뉴 146~189px가 nav 안 · 역할 선택 201px부터 · 테마 버튼 끝 359px · 문서 375px).
* **v0.6의 수식 칸**(원인집계·분기손익 등)은 `data_only=True`로 캐시값을 읽는다 — 엔진은 그 시트를 입력으로 쓰지 않고 시험만 대조한다.
* 대표 주문의 「대행 확인」은 거래·변경근거 칸에 없고 근거 본문(E61-1103 작성자 USR-BUY2)과 AG62 보정 글에만 있다 — 화면이 글자로 지어
  붙이지 않고 근거·보정 글을 보인다.

### 4.21 SC07 — 실제 경험을 관리모델 개선으로 연결 (장면 7)

장면 6 성과 검토에서 Agent(AG62)는 주담당 확인란과 주문 비용만 받아 PO61-1103을 「확인 지연 가능성」으로 짚었고, 구매 담당이 대행 확인
로그와 공급 가능일을 직접 찾아 「조달 제약」으로 바로잡았다. 장면 7은 그 보정을 개선건 IMP71로 삼아 Agent가 유효 대행의 실제 확인·발주 마감·
요구납기·정상 공급일을 처음부터 잇도록 개선(AGT71-v2 · 기준 MB71-v2 · 입력 투영 PR71-v2)하고, 검증 세트 TS71-v1으로 검증해 두 임원 확인 뒤
다음 운영 설정(CFG71 active_version)에 반영한다. **끝은 「운영 설정 반영 확인 · 운영 실행 미확인」(ST707)이다** — 설정 반영 ≠ 운영 실행 ≠ 장기
효과. 장면 6 보고본·초안·보정·성과 수치와 Target·FC51은 그대로다(CT705).

```
장면 6 문서(RPT61-v1 REPORTED·AG62·CH61-1103) ─┐
seed/SYN-SC07-v0.7.xlsx 원천 ─────────────────┴─▶ domain.load_batch(키·참조·버전 검사) → sc07_demo_run(문서 1개, 확인 전)
engine/processes/sc07.bpmn ──▶ Studio·Center ── external ──▶ app/sc07/process.run_operation → confirm.check → confirm.apply
                                     improvement · verification · application · evidence ◀── 조회(멱등)
```

**숫자·판정** — IN71 공유 09:20 → 대행 10:00 = **40분**(120분 기준 내) · 발주 마감 10:30 전 · 요구 11/14 09:00 < 적시 공급 11/16 09:00 →
**조달 제약 후보**. IN72 180분·마감 초과·적시면 충족 → 내부 지연, IN73 무효 대행 → 근거 보완(INVALID_DELEGATION), IN74 공급일 누락 → 근거
보완(MISSING), IN75 → 복합. TC701~708 8건 충족(정확도 100%가 아니다).

**경계·범위에서 정한 것**

* **결재는 데이터에 시각·담당이 있는 넷뿐이다**(2026-11-02 사용자 결정) — CF71 구매 임원 문지후 1/24 10:00 → CF72 경영관리 임원 강민서
  15:00(순서는 시각대로) → 설정 반영 운영담당(USR-OPS71) 1/25 09:00 → 설정 확인 정하윤(USR-FIN) 10:00. 개선 요청·변경 기준·Agent 개선
  확정(S01~S04)은 적재된 개선건이고, 검증 수행(S05)은 서비스 태스크(`verify_improvement_version`)다. 확인 착수 시각은 IMP71 발의일(1/17)에
  09:00을 붙였다(구현용 보완 — 데이터는 날짜만 준다).
* **새 역할은 역할명을 이름으로 쓴다**(2026-11-02 사용자 결정) — `u-ops` 「운영담당」·`u-dev` 「구현담당」(데이터에 이름이 없다, 인명을 지어내지
  않는다). Center 결재 담당도 「운영담당」이고 Company1 `org.json`에도 더했다(부서 「미지정」). 구현 담당은 결재가 없다.
* **검증 관측값은 규칙으로 다시 계산한다**(`calc.verify`) — 엑셀 `SC07검증결과`의 가상 결과·PASS는 판정에 쓰지 않고 대조로만 싣는다
  (구현명세 5장). TC706은 실제 투영 페이로드에 금지 칸·기대 원인 코드가 없는지, TC707은 **지금 장면 6 문서의 지문이 적재 때와 같은지**,
  TC708은 적용 대상 버전 = 개선 버전인지 본다. 실행 id는 `VR71-n`(가상시계 시각) — Agent 실행 id가 아니다. 데이터의 검증 이력에는
  실행 일시·id가 없다(null).
* **원인 후보 규칙은 `SC07판단` 식과 같다** — 내부 제약 = 120분 초과 **이고** 발주 마감 초과, 공급 제약 = 적시 주문 공급일 > 요구납기. 판정은
  초 단위(120분 1초는 초과)이고 화면 분은 엑셀처럼 반올림한다. 120분 안인데 마감을 넘기면 「내부 영향 추가 검토」를 함께 낸다(AT706).
  유효 확인이 없거나 공급일이 없으면 NEED_EVIDENCE와 사유(MISSING·ACCESS_DENIED·NOT_JOINED·INVALID_DELEGATION·NOT_CONFIRMED)다.
* **확인은 대상 버전이 맞아야 한다**(422) — 다른 버전의 확인은 적용 근거가 아니다. 보완 요청이면 흐름이 「보완 필요」(ST703)로 끝난다 — 새
  버전은 새 실행이다. 검증 미충족이면 확인 결재 없이 「검증 미통과」로 끝난다.
* **설정 확인의 「일치」는 연결된 레코드로 본다**(구현명세 5장 다섯 조건 — 검증 통과 · 서로 다른 두 필수 역할의 같은 버전 확인 · active_version·
  범위 · SETTINGS_SNAPSHOT · 반영 뒤·기준시각 전 확인). 예약(RESERVED)만이면 「적용 예정」(ST705)이고 「일치」는 422 SETTING_MISMATCH, 「불일치」면
  설정 반영으로 돌아간다(앞 반영은 이력). 단순 건수로 판정하지 않는다(AT709·AT710).
* **회사 시스템에 적는 것은 없다**(2026-11-02 사용자 결정) — Agent 설정은 NowView 기록이고, 대행 위임·확인 로그·공급 조건(EV71~74)은 장면 6
  구매 거래처럼 아직 NowView 시드다(합성 사례 IN73·74를 회사 이력에 넣지 말라는 명세와도 맞다). 확인 기록이 시계를 옮기면 회사 세계 시각만
  옮긴다. Company1 사이트는 장면 7 결재에 「회사 기록 없음」 카드(`kind: improvement`)와 각본 예시 값(`scenarios/sc07.json`)을 붙인다.
* **조회는 아무것도 적지 않는다**(AT712) — 보기 A↔B 전환·근거 펼침·새로고침은 화면 상태다(보기는 localStorage, UI710). 조회 응답은 데이터
  버전이 다르면 409로 섞지 않는다. 화면은 PASS 건수로 적용 상태를 다시 판정하지 않는다 — 엔진의 `state`를 쓴다.
* **권한** — 경영관리(담당·팀장·임원)·구매(담당·팀장·임원)·운영담당·구현담당·대표·시연관리자. 그 밖은 403(본문·사유 없음).
* 설정 매핑은 엔진 DB(`nowview_config`)에 저장된 것이 이긴다 — 이 판을 올린 뒤 이미 설정이 저장된 DB에는 관리자 모드(또는 `PUT /admin/config`)로
  `company1.sc07 → 7`을 더해야 일꾼이 장면 7 일감을 받는다(로컬 실측에서 그렇게 했다).

**만들며 드러난 것**

* **v0.7 SC07 시트는 헤더가 한글이다**(「개선 ID」·「입력 ID」…) — 장면 6까지의 영문 헤더 행이 없다. `SC07적용`은 세로 항목이라 객체 하나로
  바꾸고, 담당 계정·스냅샷 id는 「근거 / 해석」 칸의 첫 토큰에서 읽는다.
* **Company1 기간계는 `org.json`을 뜰 때 한 번 읽는다** — 사용자를 더하면 기간계를 다시 띄워야 사이트 직원 목록에 보인다(`--reload`는 .py만 본다).
* 역할명이 곧 이름인 계정은 화면에서 「운영담당 운영담당」으로 두 번 찍혔다 — 같으면 한 번만 쓴다.
* 빈 「회사 시스템과 오간 것」 카드는 「이 기록을 남기기 전에 만든 데모 실행」으로 읽혔다 — 장면 7은 카드 대신 「회사에 적는 것은 없다」 한 줄이다.

---

## 5. 다음 단계와 선행 조건

CI(5.1), Chaeksas 엔진(5.2), SC01 화면(5.3 — 2026-11-03 걷었다, 4.6), Agent와 예외 경로(5.5), 장면 2(5.6), 장면 3(5.7), 장면 4(5.8), 장면 5(5.9), 장면 6(5.10), 장면 7(5.11)은 끝났다(장면 1~7 모두
로컬 Center에 올려 진짜 서버 실행기로 돌렸다). 운영계(5.4)에는 2026-11-04에 BPM·NowView·Company1 세 서버를 올려 장면 1~7을 끝까지 돌렸다.
**시나리오 2 장면 1**(`docs/s2/sc01.md`)은 로컬 Center에서 끝까지 갔다(2026-11-05 — 공통 BPM `platform.case-intake` 공유 패키지 +
`company1.s2.sc01` 0.9.1, 호출 활동이 같은 실행 안에서 공통 BPM을 돈다). 운영계 반영은 남았다.
**시나리오 2 장면 2**(`docs/s2/sc02.md`)는 엔진 시험(진짜 엔진 + 공통 BPM `platform.case-plan` + 기간계 쌍둥이 생산계획 저장소)과
Company1 BPM·사이트 시험을 거쳐 로컬 Center에서 끝까지 갔다(2026-11-05 — 공유 BPM `platform.case-plan` 0.1.0 · `company1.s2.sc02`
0.10.1 · 확장 `external` 0.10.0, 사이트 자동 모드로 H03 확인 → PROD-V2 반영·대조 일치 → S +60분 관찰 · R −30분 → HAND-02). 첫 배포는
Studio가 엉뚱한 공통 BPM(`case-intake`)을 설치해 `call_target_missing`으로 실패했다. 운영계 반영은 남았다.
**시나리오 2 장면 3**(`docs/s2/sc03.md`)은 엔진 시험(진짜 엔진 + 공통 BPM 재호출 + 메시지 대기 + 기간계 쌍둥이 원업무·근거)과 Company1
BPM·기간계·사이트 시험을 거쳐 로컬 Center에서 끝까지 갔다(2026-11-05 — `company1.s2.sc03` 0.12.0 · 확장 `external` 0.11.0, 사이트 자동
모드로 장면 1~3: 근거 메시지 「사건근거」가 `no_receiver` 세 번 뒤 들어가 09:23 비교 → 팀장 재보고 → H05 결정 → H04 인수 → HAND-03,
일감 9/9 성공, 숫자 = SC03요약). 운영계 반영은 남았다.
**시나리오 2 장면 4**(`docs/s2/sc04.md`)는 엔진 시험(진짜 엔진 + 메시지 대기 + 기간계 쌍둥이 실행 증빙, 숫자 = SC04실적·초기선별·회신재현·
기준적용·요약 — 「위험 식별 앞당김」만 12분, 자료 15분)과 Company1 BPM·기간계·사이트 시험, 사이트 화면(임시 회차 — 데스크톱·375px)까지
했다(2026-11-06 — `company1.s2.sc04` 0.13.0 · 확장 `external` 0.12.1, 0.12.0은 Center에서 철회됐다). 같은 날 로컬 Center에서 사이트 자동 모드로
장면 1~4를 끝까지 돌렸다(증빙 메시지 다섯 → H06 착수 → 재현·H04 송신·영향 → 시험 표본 1·1·7 → H07 판정 → H06 적용 → H07 설정 → `End`, 일감
14/14 성공, 대시보드 업무 24 = SC04요약). 운영계 반영은 남았다.
**시나리오 3 장면 1**(`docs/s3/sc01.md`, 공통 `docs/s3/common.md`)은 엔진 시험(진짜 엔진 + C15 수행기 + 기간계 쌍둥이 입력 버전,
인수시험 01~08)과 Company1 BPM 그림 시험까지 했다(2026-11-06 — `company1.s3.sc01` 0.13.0 · 확장 `external` 0.13.0). 로컬 Center 실측·
운영계 반영은 남았다.
**시나리오 3 장면 2**(`docs/s3/sc02.md`)는 엔진 시험(진짜 엔진 + C15 수행기 + 기간계 쌍둥이 첨부·장애 스위치, 인수시험 01~09, 견본 v0.1
대조, 첨부 Excel을 LibreOffice로 다시 계산해 오류 0·요청액 일치)과 Company1 BPM·기간계·사이트 시험, 사이트 화면(점검용 회차 — 데스크톱·
375px, 첨부 내려받기)까지 했다(2026-11-06 — `company1.s3.sc02` 0.14.0 · 확장 `external` 0.14.0). 실제 연계 PC는 없다(모의). 같은 날 로컬 Center에서
사이트 자동 모드로 장면 1·2를 끝까지 돌렸다(실행 RUN-S3-01 모의 → WP-S3-v1 첨부 → 검토 둘 → REP-S3-01 상신, 일감 10/10 성공,
대시보드 업무 32 = 준비 2/2 · 승인 대기 2 · 상신 1 · 승인 0/2). 운영계 반영은 남았다.
**시나리오 3 장면 3**(`docs/s3/sc03.md`)은 엔진 시험(진짜 엔진 + C15 수행기 + 기간계 쌍둥이 후속 업무 등록·장애 스위치, 인수시험 01~09)과
Company1 BPM·기간계·사이트 시험(자동 모드 — 장면 3 열기 → 결정), 사이트 화면(점검용 회차 — 승인 요약·근거·체크리스트·이력, 데스크톱·375px)까지
했다(2026-11-06 — `company1.s3.sc03` 0.15.0 · 확장 `external` 0.15.0). 같은 날 Studio 배포·관리자 매핑 `company1.s3.sc03 → 33` 뒤 로컬 Center에서
사이트 자동 모드로 장면 1~3을 끝까지 돌렸다(결정 DEC-S3-01 → 두 경로 후속 업무 4건 · HAND-S3-03, 일감 20/20 성공, 대시보드 업무 33 = 승인 2/2 ·
승인 보고 1 · 전표 0/2 · 주석 0/2). 정수 결재 변수를 text 칸에 넣어 422가 난 것을 사이트에서 고쳤다. 2026-11-07 예외 경로도 로컬 Center에서 돌렸다(사이트 직원 결재 API로 한
결재씩 — 첨부 접근 실패 보류 → 보완 요청 → 참조 보강 v2 → 구버전 거절 → 주석 경로 실패·응답 유실 → 재시도, 그리고 `A-RECOVERY-50` → 장면 1
재점검 → 재계산 → 재검토 → 재상신 v2(요청 50·40) → 전표 경로 실패 → 재시도, 둘 다 `End`·후속 업무 중복 0). 결재의 파일명·처리안내가 낡은 값으로
남던 것을 고쳤다(확장 `external` 0.15.1 · 그림 0.15.1 — Studio 배포 뒤 Center·사이트 화면에서 확인). 운영계 반영은 남았다.

### 5.1 CI — 완료

원격은 **https://github.com/wrapper755/NowView** (private)이고
`.github/workflows/ci.yml`이 `main` 푸시와 모든 PR에서 돈다. **잡이 둘이고 병렬로 돈다** —
서로 의존이 없고, 순차로 두면 어느 쪽이 깨졌는지 알기까지 더 오래 걸린다.

```
verify (TS)     npm ci           → lint → test(vitest) → build
engine (Python) uv sync --locked → ruff → pytest        (Postgres 서비스 컨테이너)
docker          docker compose build                    (푸시하지 않는다)
```

* 빠르게 실패하는 순서로 뒀다 — lint(수초) → test(1초대) → build(가장 느림).
* build가 TypeScript 검사를 겸하므로 별도 typecheck 단계를 두지 않는다.
* `npm ci`는 락파일이 `package.json`과 어긋나면 바로 실패한다. 로컬에서는 보이지 않는
  종류의 문제라 이 단계가 잡는 몫이 있다.
* `node-version`은 22로 고정했다. `@types/node`도 `^22`다 — 어긋나면 타입 정의와 실제
  런타임이 다른 상태로 검증하게 된다. **이것은 액션 자체의 실행 런타임과는 다른 값이다**(아래).
* `.next/cache`만 캐시한다. 빌드가 가장 느린 단계이기 때문이다.
* 빌드에 시크릿이 필요 없다 — 화면 데이터는 클라이언트가 엔진에서 받고 엔진 시드는 리포의 엑셀이다.

**engine 잡에서 알아둘 것:**

* **Python 버전의 원천은 `engine/.python-version`이다.** 워크플로에 또 적으면 로컬
  venv와 CI가 갈라진다 — `node-version` / `@types/node`에서 겪은 것과 같은 문제다.
  `uv`가 없는 인터프리터를 직접 내려받으므로 `setup-python`이 필요 없다.
* `uv sync --locked`가 `npm ci`의 몫을 한다 — `uv.lock`이 `pyproject.toml`과 어긋나면
  바로 실패한다. 실제로 의존성을 하나 더해 확인했다.
* 엔진이 Chaeksas를 git으로 받는다 — 러너에 git이 있어 추가 설정이 없다(Docker 이미지는 4.5).
* 캐시 키를 `engine/uv.lock`으로 좁혔다 — 앱 쪽 변경으로 엔진 캐시가 날아가지 않게 한다.
* **Postgres 서비스 컨테이너를 붙여 두 백엔드를 모두 돌린다.** `TEST_DATABASE_URL`이
  없으면 Postgres 테스트가 전부 skip되는데, 초록색 체크만 보고는 "검증했다"와
  "건너뛰었다"를 구분할 수 없다. `REQUIRE_POSTGRES=1`이 **skip을 실패로 바꾼다** —
  조용한 미검증이 가장 나쁘다.
* **docker 잡은 이미지를 빌드만 하고 푸시하지 않는다.** Dockerfile은 로컬에서 잘 돌다가
  조용히 깨지는 종류다(standalone 산출물 경로, 락파일 불일치, 베이스 태그). 러너에
  docker·compose v2가 이미 있어 추가 액션을 쓰지 않았다 — 액션을 늘리면 버전 관리할
  대상만 늘어난다. 레이어 캐시가 없으므로 느려지면 buildx + `type=gha`를 붙인다.

**워크플로를 손댈 때는 액션 최신 버전을 조회하고 쓴다.** 관례적으로 `@v4`를 썼다가 첫
실행에서 "Node 20 deprecated, Node 24로 강제 실행" 경고를 받았다. 액션의 실행 런타임은
`node-version`과 무관하므로 액션 버전을 올려야 해소된다:

```bash
gh api repos/actions/checkout/releases/latest --jq .tag_name
```

현재 checkout v7 · setup-node v7 · cache v6이며, 올린 뒤 경고가 사라진 것을 확인했다.

**부동 메이저 태그가 있다고 가정하지 말 것.** `actions/*`는 `v7` 같은 이동 태그를 두지만
`astral-sh/setup-uv`는 **v8부터 두지 않는다** — 최신 릴리스가 `v10.2.0`인 것을 조회하고도
`@v10`으로 줄여 쓰는 바람에 `Unable to resolve action … unable to find version v10`으로
engine 잡이 실패했다. 새 액션을 쓸 때는 태그 목록을 직접 본다:

```bash
gh api repos/astral-sh/setup-uv/tags --jq '.[].name' | head
```

저장소를 **private으로 둔 이유**: INNONOW 방법론, 벤치마킹 대상 실제 회사명(SJG세종·인팩),
실명이 들어 있다. 공개로 바꾸는 것은 언제든 가능하지만 되돌리는 것은 사실상 불가능하다
(캐시·포크·검색 색인).

### 5.2 BPM 엔진 — Chaeksas로 교체 완료

`engine/`은 FastAPI + Chaeksas BPM이다. LangGraph(StateGraph·체크포인터·`seek`·Agent 러너)는 2026-10-19에
걷어냈다(4.15). 설계와 함정은 4.5, 엔진 README.

* `chaeksas-core`는 **git 커밋 고정 의존성**이다. Chaeksas 리포(`wrapper755/Chaeksas`, public)가 바뀌어도
  `rev`를 올리기 전에는 NowView가 따라가지 않는다. 올린 뒤에는 엔진 테스트를 양쪽 백엔드로 돌린다.
  2026-10-25에 `6088b75` → `c127c6f`로 올렸다 — 결재 담당자(`assignees`)를 엔진이 풀게 됐다(N4).
  2026-10-26에 `c127c6f` → `8f0b08d`로 올렸다 — 결재에 답한 사람이 변수로 온다(R1, ADR-0096).
  같은 날 `8f0b08d` → `d2e2e46`으로 올렸다 — 입력의 값 출처(가상 직원, ADR-0099)·`input_not_from_caller`·
  `assignees_missing`(N5).
  **고정된 판이 낡으면 계약 검사도 낡는다**: 옛 판에서는 확장 정의가 통과했지만 최신 Center는 E3로 거절했다.
* Chaeksas 패키지는 `requires-python <3.13`이다 — 엔진도 그 범위로 묶었다(`>=3.12,<3.13`).

### 5.3 화면 → SC01 전환 — 완료

UI01~UI06과 BPM 흐름 화면이 엔진 `/sc01/*`을 쓴다(4.6). 기본 시연 11장면을 데모 플레이어 자동 재생으로
끝까지 돌려 인계 완료까지 가는 것을 브라우저에서 확인했다. 수동 경로(역할 전환 → 수신 → 확인)와
거절(검증 오류가 있는 원천의 확인 완료 → 409, 입력 보존), 되감기(지난 시점 읽기 전용), 375px 폭을
확인했다.

**확인하며 잡은 것**

* **표 안의 `sr-only`가 좁은 화면의 문서 폭을 늘렸다**(375px → 555px). `position:absolute`라 스크롤
  상자(`overflow-x-auto`)를 벗어난다 — 표 머리·caption의 이름은 `aria-label`로 준다.
* **역할 선택이 GNB를 0px로 눌렀다**(375px). 좁을 때 폭을 묶고 아이콘을 뺐다.
* **표의 행 머리(`th scope="row"`)는 기본이 가운데 정렬이다** — `text-left`를 준다.
* **BPMN 15층을 한 줄로 펴면 캔버스에서 글자가 안 읽힌다** — 5열마다 줄을 접는다.
* **dev의 StrictMode가 데모 실행을 둘 만들었다** — 생성 요청을 공유한다(4.2).

### 5.4 운영계 배포 — 세 서버 운영 중 (2026-11-04)

> **2026-11-04 세 서버 역할 분담 5단계로 운영에 올렸다** — 한 서버(`hetzner-server`)에 셋이다. 순서는 BPM → NowView → Company1이다
> (`docs/chaeksas-integration.md` §7이 절차다).
>
> | 무엇 | 자리 | 바깥 주소 |
> |---|---|---|
> | BPM Center·콘솔·서버 실행기 (docker compose — BPM 리포 `server/deploy/`, 옛 이름 Chaeksas) | 127.0.0.1:8800 · 8501 | `https://bpm.nowview.work` · `https://console.nowview.work` |
> | NowView 웹·엔진 (systemd, main `053cfb9`) | 127.0.0.1:3100 · 8077 | `https://www.nowview.work` |
> | Company1 기간계·사이트 API·웹 (systemd, Company1 `scripts/deploy.sh`) | 127.0.0.1:8191 · 8190 · 3200 | `https://company1.nowview.work` (사이트 비밀번호 하나) |
>
> * **키는 셋 다 설치가 지었다** — `app.worker_file`이 서버에서 일꾼·연동용·대리 답용 키를 짓고 해시를 Center 일꾼 폴더
>   (`/root/Workspace/BPM/server/deploy/consumers`)에 썼다. 원문은 서버 `engine/.consumer/keys.json`뿐이다. 사이트도 제 대리 답 키를 따로 쓴다
>   (`company1-site-relay.key.json`, 원문은 `/etc/company1.env`). `/etc/nowview.env`의 옛 키 줄(`CHAEKSAS_INTEGRATION_KEY`·`RELAY_KEY`·
>   `INTAKE_WORKER`·`NOWVIEW_SYSTEM_KEY*`)은 주석으로 걷었다 — 환경 변수가 보관 파일을 이겨서 남기면 옛 키로 불렀다.
> * **저장된 설정이 env를 이긴다** — 엔진이 회사 주소 없이 처음 뜨며 기본 설정을 `nowview_config`에 적었고, 그 `system_url: null`이 나중에 넣은
>   `COMPANY_COMPANY1_URL`을 덮어 세계 따라가기가 뜨지 않았다(`/health.follower.running: false`). 관리 API로 고치고 엔진을 다시 띄웠다(따라가기는
>   뜰 때만 시작한다).
> * **운영 DB를 비웠다**(사용자 결정) — 10-28 판의 데모 실행 49건 중 하나가 「진행 중」으로 남아 새 Center에 없는 실행을 2초마다 읽었다. 비우기 전
>   덤프는 서버 `/root/backup/nowview-db-20261104*.sql.gz`(0600)다. 엔진이 테이블을 다시 만든다.
> * **운영에서 장면 1→7을 자동 모드로 끝까지 돌렸다**(회차 `demo-f478fd07`, 22:03 → 22:41 약 38분 — site-api로 회차를 만들고 직원 전부 켜기 ·
>   장면 1~7 자동). 일꾼 일감 135건 실패 0, 엔진·사이트 API 오류 로그 0. 대시보드(`www.nowview.work/c/company1`) 지표가 4.6의 기대값과 같다:
>   F02 33.09억 · 목표 대비 −1.68억 · 사건 −1,400만 / 원가 증가 18,817,440 · 협상 감소 12,544,960 / 통합 3,299,986,680 · 부족 177,303,320 /
>   개선 효과 127,800,000 · 남는 부족 49,503,320 / 전망 3,428,986,680 · 남는 부족 48,303,320 / Q4 91.8 → 87.0백만원 / 「운영 설정 반영 확인」.
>   사이트 로그인 화면을 브라우저로 지나 본 것은 아니다(쿠키 값으로 200·없으면 `/login` 307만 확인했다).
> * 사이트 비밀번호는 데모용 고정값이다(사용자 결정 — 서버 `/etc/company1.env`의 `SITE_PASSWORD`). 계정이 없어 신원 확인이 아니라 남용을 막는 문이다.
> * **rsync가 `.claude/worktrees`를 올리지 않는다** — 다른 세션의 worktree 사본이 서버에 겹으로 쌓인다. 같은 이유로 로컬
>   `eslint .`도 그 사본까지 훑어 오류 수천 개를 낸다(`--ignore-pattern '.claude/**'`로 돌린다).


**https://www.nowview.work** — `hetzner-server`(46.62.215.120)에 systemd 서비스 2개로
상주하고, cloudflared 터널이 외부에 내보낸다. **Chaeksa가 같은 서버에서 3000·8000을 쓰고
있어 포트를 비켜 잡았다** — 웹 3100, 엔진 8077, **둘 다 127.0.0.1에만** 바인딩한다.

```bash
scripts/deploy.sh --bootstrap   # 최초 1회 (Postgres 역할·DB·/etc/nowview.env까지)
scripts/deploy.sh               # 이후 배포 (rsync → uv sync → npm ci·build → 재시작)
scripts/deploy.sh --status
scripts/deploy.sh --logs engine 80
```

* **NowView는 docker를 쓰지 않는다.** `docker compose`는 로컬 검증용으로 남고, 운영은 systemd로
  돈다(Company1도 같다). 서버의 docker는 BPM Center 묶음(compose)만 쓴다.
* **`--delete`로 rsync한다.** 없으면 삭제한 화면·데이터 파일이 서버에 남아 라우트로
  계속 잡힌다. `.git`은 올리지 않는다 — 배포본은 체크아웃이 아니라 산출물이다.
* **빌드는 서버에서 한다.** 로컬 `.next`를 올리면 절대경로·플랫폼 의존 바이너리가 섞여
  "로컬에서는 되는데 서버에서 죽는" 종류가 된다. `npm ci`·`uv sync --locked`가 CI와 같은
  몫을 한다(락파일 불일치를 여기서 잡는다).
* **비밀은 `/etc/nowview.env`(0600, root)에만 있다.** `deploy/bootstrap.sh`가 서버에서
  DB 비밀번호를 생성하므로 리포에도, 이 문서에도 값이 없다. 두 유닛이 **같은 파일**을
  읽는다 — 따로 두면 `WEB_PORT`와 `ENGINE_URL`의 포트가 갈라진다.
* **bootstrap은 멱등이다.** 파일이 이미 있으면 덮어쓰지 않는다 — 덮어쓰면 비밀번호가
  바뀌어 엔진이 붙지 못한다. 포트가 이미 쓰이고 있으면 거기서 멈춘다(겹치면 서비스가
  조용히 재시작 루프에 빠진다).
* **웹·엔진 모두 127.0.0.1에만 바인딩한다.** 엔진은 원래부터 그랬다 — 브라우저는 Next의
  `/api/engine/*`을 거치고 엔진을 직접 부르지 않는다(4.3). 웹도 터널이 붙으면서 내렸다:
  **서버에 방화벽이 없어 0.0.0.0에 열면 IP:포트로도 그대로 들어오고 그 경로는 HTTPS가
  아니다.** 터널이 같은 호스트에서 돌므로 localhost로 충분하다. 바꾼 뒤 IP:3100이 연결
  거부로 바뀌고 도메인은 그대로 200인 것을 확인했다.
* **외부 주소는 Cloudflare 대시보드가 정한다.** 터널이 토큰 방식이라 라우트가 서버 파일에
  없다 — `deploy.sh`가 URL을 알아낼 방법이 없으므로 완료 메시지에 상수로 적어 두었다
  (`NOWVIEW_PUBLIC_URL`로 덮을 수 있다). 도메인을 바꾸면 그 값과 이 절을 함께 본다.
* 엔진 유닛은 `Requires=postgresql.service`다. `DATABASE_URL`이 있는데 못 붙으면 SQLite로
  되돌리지 않고 실패하는 것이 설계이므로(4.5), 기동 순서를 systemd에 맡긴다.
* `uv`는 `/root/.local/bin`에 있고 systemd는 로그인 셸을 거치지 않아 PATH가 비어 있다 —
  두 유닛 모두 `Environment=PATH=…`가 필요하다.
* **엔진에 `--timeout-graceful-shutdown`이 없으면 SSE가 종료를 붙잡는다.** uvicorn은 열린
  연결이 닫히기를 기다리는데 SSE 스트림은 끝나지 않는다. 화면 하나가 구독 중일 때
  종료가 **91초**를 끌다 systemd에 SIGKILL로 죽었다(구독자가 없으면 즉시 멈춘다) —
  배포마다 엔진이 그만큼 내려가는 셈이고 시연 중이면 더 나쁘다. `10`으로 두고
  `TimeoutStopSec=20`을 백스톱으로 뒀더니 재시작이 **15초**(종료 10 + 기동 2)가 됐고
  SIGKILL이 사라졌다 — 종료 핸들러(`notifier.stop()`)가 실제로 돌게 됐다는 뜻이다.
  **유령 LISTEN 세션은 원래도 남지 않았다** — 프로세스가 죽으면 OS가 소켓을 닫아
  Postgres가 정리한다. 4.9의 그 걱정은 graceful 경로에서 정리를 빠뜨렸을 때의 것이다.
* **`next start`와 `output: standalone`은 조합이 어긋나 있다.** Next 16이 기동 때
  경고한다(`Use "node .next/standalone/server.js" instead`). `output: standalone`은
  Dockerfile을 위한 것인데(`CMD ["node", "server.js"]`) systemd는 `npm run start`를
  쓴다 — **동작은 한다**(다섯 화면 200, `/_next/static/*` 전부 200으로 실측했다).
  즉 standalone 산출물을 만들고 쓰지 않는 상태다. 유닛을 standalone 진입점으로
  바꾸려면 `.next/static`과 `public`을 그 옆에 복사하는 단계가 붙는다 — 조용히 낡을
  수 있는 복사가 늘어나므로, 경고가 실제 고장이 되기 전까지는 그대로 두었다.

**운영계에서 실제로 확인한 것** — 이전 구현 기준 (Postgres 18.6 · `notify.kind=postgres listening=true`):

| 확인 | 결과 |
|---|---|
| 다섯 화면 외부 접근 | 전부 200 (1.3~1.6초) |
| 시나리오 1 (에스컬레이션 경로) | 승인 → 확인 → 종료까지 완주, `op-control` skipped |
| 시나리오 2 (현업 통제 경로) | `simulate` skipped · `op-control` done으로 완주 |
| 사유 10자 미만 | 400이 아니라 같은 지점 + `pendingApproval.error` |
| **엔진 재시작** | 대기 중이던 두 인스턴스가 **같은 지점에서** 이어졌다 (Postgres를 쓰는 이유) |
| SSE (`/api/engine/events`) | `event: snapshot` → `event: ready` 정상 전달 |
| 되감기 (`seek`) | 과거 뷰는 `historical: true`, **라이브 인스턴스는 온전** |
| LLM 모드 | Agent 3회 128초, `provenance: llm:kimi-k3:cloud` — 서버 ollama 그대로 |
| Chaeksa | 3000·8000 영향 없음 |

**터널을 붙인 뒤 다시 확인한 것** (직접 IP는 연결 거부, 도메인은 200):

| 확인 | 결과 |
|---|---|
| 다섯 화면 (HTTPS) | 전부 200 |
| SSE | 통과한다 — 25초에 이벤트 3개 + `: keepalive` 1개. **버퍼링되지 않았다** |
| Server Actions 전제 | 이 앱에는 `"use server"`가 없다 — `serverActions.allowedOrigins` 설정이 필요 없다 |
| LLM 승인 재개 | 1.5초 (다음 사람 대기까지) |
| LLM 마지막 확인 (`evolution` Agent 1회) | 20.6초 |
| **LLM 인스턴스 생성** | 처음엔 **524 (126초)** — 배경 진행으로 고쳤다(4.15) |

**남은 것:**

* **인증이 없다 — 당장 붙이지 않기로 했다.** 지금 목적이 사용자에게 데모를 보여주는
  것이어서, 볼 사람을 미리 등록해야 하는 방식은 그 목적과 맞지 않는다. 아래 사실만
  알고 두는 것이다.

  **이 판(2026-11-03 4단계)부터 NowView 웹으로 열린 것은 회사 목록·대시보드 읽기뿐이다** — BFF가 장면 경로(404)·쓰기(405)·
  행위자 헤더를 막는다. 업무 조작(결재·시연 조작)은 회사 사이트로 갔으니 남용 걱정도 그쪽(`company1.nowview.work`, 5단계의 사이트
  비밀번호)으로 옮겨 갔다 — 운영계도 이 판이다(2026-11-04). 사이트는 비밀번호 하나로 닫혀 있지만 그 비밀번호를 아는 사람은 누구나
  아무 직원으로 결재하고 회차를 만들고 지울 수 있다. Agent를 `llm` 모드로 켜면 비용 위험이 생긴다(운영 기본은 `mock`).

  **시스템 작업(서비스 태스크의 업무 기록)은 웹에 경로가 없다**(2026-10-31, 4.3) — 엔진의 C15 일꾼이 Center에서
  가져간다.

  **막을 자리를 짚을 때 층을 틀리기 쉽다.** 엔진(8077)은 **이미 127.0.0.1 전용이고**
  외부에서 연결 거부다 — 그래서 *엔진에* API key를 걸어도 BFF↔엔진 사이만 인증되고
  공격 경로는 그대로다. 공격자는 엔진을 직접 부르지 않는다. **방화벽도 안 된다**:
  요청이 전부 터널에서 오므로 남의 브라우저와 볼 사람의 브라우저가 출처로 구별되지
  않는다. 막을 자리는 **BFF 앞**(Cloudflare Access · WAF 레이트 리밋)이거나 **BFF 안**
  (라우트 핸들러 검사)이다.

  비용·남용만 겨냥하려면 링크 공유를 잃지 않는 쪽이 싸다 — WAF 레이트 리밋(무료 플랜 규칙 1개). NowView
  쪽에는 걸 쓰기 경로가 없다.
  검색 색인은 별개다: `robots.txt`에 `Disallow`가 없다(Cloudflare가 넣는 것은
  content-signal 주석뿐이다).

  **화면 데이터가 새는 것은 근거가 아니다.** 5.1이 리포를 private으로 둔 이유로 든
  실제 회사명(SJG세종·인팩)과 실명은 **이 문서에만 있고 앱 코드에는 없다.** 화면의
  회사·인물(이도윤·박서진·김태오·최유나·정하윤·한준호·윤채원·서도현·문지후·임하준·강민서·오세린·배정훈·신예준·권태윤·남유진)은 가상이다. 공개되는
  것은 방법론 이름(`INNONOW Management Reference Model`, `app/layout.tsx`의 설명)이다.
* **서버에 방화벽이 아예 없다**(`ufw inactive`, iptables 정책 ACCEPT). 지금은 웹·엔진이
  둘 다 127.0.0.1이라 닫혀 있지만, 앞으로 무엇이든 0.0.0.0에 바인딩하면 **그 순간
  공개된다** — 실제로 웹이 그 상태였다. 인증과 무관하게 인바운드를 22번만 열어 두는
  편이 안전하다.
* 로그 회전은 journald 기본값에 맡겼다. Agent 호출이 늘면 따로 본다.

`www`와 apex(`nowview.work`) 모두 200이다.

### 5.5 Agent와 예외 경로 — 완료

구현명세 3단계. 설계와 드러난 것은 4.5·4.6. 브라우저에서 기본 시연 · 초안 채택 · EX08 · EX03(인계 뒤
정정 → 재검토 업무·재확인) · EX07(시계 이동 → 알림)을 확인했다.

**남은 것**

* **운영에서 LLM을 켤지.** 지금 기본은 `mock`이다. 켜면 초안에 100초 안팎이 걸리고(배경이라 업무는 안
  막힌다) 비용이 생긴다(5.4).
* **reload·종료가 실행 중인 LLM 작업을 기다린다.** 스레드 풀은 데몬이 아니라 진행 중인 초안이 끝나야
  프로세스가 내려간다 — `mock`에서는 순간이라 문제가 없다.
* EX01·04·05는 엔진 테스트로 잠갔고 화면에서는 고객계획 화면의 시연 원천으로 돌릴 수 있다. 화면 검수는
  기본·EX03·EX07·EX08만 했다.
* **장면 5 이후**는 Business 설계(설계표·데이터)가 나와야 시작한다 — 지어내지 않는다(4.7).
* 운영 배포 전 확인: 인증이 없는 상태에서 `X-Demo-Actor`로 아무 역할이나 될 수 있다(5.4).

### 5.6 장면 2(SC02) — 완료 (Studio·Center 실행)

2026-10-27. 설계·데이터는 4.16. 엔진 테스트(SQLite·Postgres)와 브라우저에서 기본 시연 D00 → D12(인계 완료)와 X01
(추가 협상지시 — 재협상 대기·원가 등록 차단)을 확인했다. 숫자는 통합가상데이터 v0.2의 파생 시트와 같다(2027 물량
−14,000,000 · 단가 −9,364,320 · 통합 3,299,986,680 · Target 대비 부족 177,303,320 · 12개월 3,173,163,560).

**남은 것**

* **Center에 올릴 것**(사람이 한다 — 서명·관리자 권한): ① CON-07에 `chaeksas/nowview-sc02.extension.json` 0.1.0 서명·등록,
  외부 앱 키(`NOWVIEW_SYSTEM_KEY`)·시험용 키(`NOWVIEW_SYSTEM_KEY_TEST`) — SC01과 같은 값, 로컬 Center는 「서버 주소」를
  `http://host.docker.internal:3000`(실행기가 컨테이너일 때)으로 덮어쓰기. ② Studio에서 `engine/processes/sc02.bpmn`을 열어
  내보낸 패키지 `nowview.sc02` 승인·배포. 엔진 설정은 더 필요 없다(패키지 id 기본값). — **사용자가 올렸고, 로컬 Center + 진짜
  서버 실행기로 장면 1 기동(접수 가상 직원 경유) → 인계 → 장면 2 D00 → D12 인계까지 각본으로 갔다**(2026-10-27, 숫자 12개월
  인상 18,817,440 · 감소 12,544,960). Studio 시험 실행은 아직 돌려 보지 않았다. 실측으로 고친 셋:
  * **장면 2 시작이 접수 일괄에서 멈췄다** — 각본이 장면 1을 인계까지 끝낼 때 감독자 승인을 넘지 못했다. 그때는 각본이 일괄을
    감독자로 대리 승인하게 했다 — 2026-11-01 접수 가상 직원을 걷으며 그 길도 없어졌다(4.5).
  * **대리 답 대기 10초가 모자랐다** — 작업 배정 약 8초, 답을 실행기가 집어 다음 결재를 올리기까지 약 10초다. `CENTER_WAIT_S`를
    30초로 올렸다(찾으면 바로 돌아온다). 실행 기록(`/runs/{id}/events`)도 첫 호출 직후엔 404라 각본은 그것을 넘긴다(폴러가 따라잡는다).
  * **앞 결재 뒤의 계산을 실행기가 아직 안 불렀는데 다음 답의 사전 검사가 돌았다**(재분석 확인 직후 상신 → 「재분석이 최신이
    아니다」 409). 사전 검사가 409면 그 결재가 열릴 때까지 기다렸다가 **다시 검사한다** — 여전히 Center에 답하기 전이다.
* **운영 Center에서 인계까지 갔다**(2026-10-28, `demo-eb479405` — 장면 1을 운영 Center로 인계한 실행에서 시작, 13단계 약 4분).
  처음 돌렸을 때 업무 12건 중 9건이 늦게 열렸고 완료 시각이 전부 다음 단계 시각이었다(협상 업무에 거짓 지연 알림). 고친 둘:
  대리 답이 폴러보다 먼저면 업무를 그때 연다(`_relay`, 장면 1·3~6과 같다), Center 각본은 그 결재의 업무가 끝나거나 기록이
  거절될 때까지 기다린다(`demo._await_own_record` — 확인 결재는 `answer_via`를 남기지 않아 업무 완료로 본다). 다시 돌려 늦게 연
  업무·거절·지연 알림 0, 완료 시각 12건이 각본과 같다.
* **external·Company1로 옮긴 뒤 로컬 Center에서 인계까지 갔다**(2026-11-01, `demo-698a849b` — `company1.sc02` 0.2.0 배포, 장면 1을
  Center로 인계까지 준비 150초 → D01~D12 13단계 약 4분, 결재 한 단계 약 20초). 일꾼이 장면 2 일감 18건을 모두 `complete`(origin
  `run`), 업무 12건 늦게 연 것·`answer_rejected`·지연 알림 0, 완료 시각이 각본과 같다. 숫자 12개월 인상 18,817,440 · 협상 감소
  12,544,960 · 통합 3,299,986,680 · 부족 177,303,320. 회사 기간계에 요청 PRQ-0001 VERIFIED(윤채원 6/17 09:20)·C02-APP01
  REGISTERED_FUTURE(a 75,120 · b 95,120원)가 적혔다. 화면 플레이어 초기화 → 자동 재생으로도 같은 결과였다.
* **Agent LLM 러너** — 지금은 mock·fail뿐이다. SC02 계약(summary·findings·questions·draft_text)에 맞춘 프롬프트와 실호출 시험이 필요하다.
* **2차 이후 협상·재기안·재승인**(S14 뒤) — 설계상 후속 범위다.
* **장면 1 F02가 정정된 뒤의 장면 2**(ERR-24) — 지금은 시작을 409로 막는다. 정정 물량으로 새 분석·재검토를 요청하는 길은 없다.
* **요청 정정 버전**(U21-03) — 같은 문서 키·다른 내용은 BPM 시작 전에만 받는다.
* 화면 검수는 BASE·X01만 했다. 나머지 X 사례는 엔진 테스트로 잠갔고 플레이어의 사례 선택으로 돌릴 수 있다.

### 5.7 장면 3(SC03) — 완료 (Studio·Center 실행)

2026-10-27. 설계·데이터는 4.17. 엔진 시험(SQLite·Postgres)으로 기본 시연 D30 → D41과 E31~E37을 잠갔고, 숫자는 통합가상데이터
v0.3의 파생 시트, 끝난 문서는 SC03 시트와 같다. 바깥 실행은 Studio 흉내(진짜 엔진 + `origin: test` 일감)·가짜 Center + 실행기 흉내로
완료까지 갔다. 브라우저에서는 **내장 실행(시험용, API로 만든 데모 실행)**으로 U31~U37·BPM 화면, 플레이어 진행, 3/4 완료 거절(422
남은 항목), 화면 폼 인수(4/4) → 완료, 375px를 확인했다.

**남은 것**

* **Center에 올릴 것**(2026-11-02 이전 — 지금은 기본 확장 `external` 0.3.0을 일꾼이 올리고 `company1.sc03` 0.3.0만 Studio로 배포한다): ① CON-07에 `chaeksas/nowview-sc03.extension.json` 0.1.0 서명·등록, 외부 앱 키·시험용 키
  (장면 1·2와 같은 값), 로컬 Center 「서버 주소」 덮어쓰기. ② Studio에서 `engine/processes/sc03.bpmn`을 내보내 `nowview.sc03`
  승인·배포. — **사용자가 올렸고, 로컬 Center + 진짜 서버 실행기로 장면 1·2 인계 → 장면 3 D30 → D41(HANDOFF31, 인수 4/4,
  조건부 수용)까지 각본으로 갔다**(2026-10-27, 숫자 통합 3,299,986,680 · 기존 부족 153,939,000 · 전체 부족 177,303,320 · 경과
  8,725분 · 영업시간 2,245분). Studio 시험 실행은 아직 돌려 보지 않았다. 실측으로 고친 셋:
  * **대리 답 대기가 10초였다** — 첫 결재(Save_Analysis)부터 찾지 못했다. 장면 1·2의 `CENTER_WAIT_S`(30초)를 쓴다. 사전 검사가
    409면 그 결재가 열릴 때까지 기다렸다가 다시 검사한다(장면 2와 같다).
  * **대리 답 뒤의 기록 작업은 실행기가 따로 부른다** — 각본이 바로 다음 단계를 넣으면 BPM 밖 명령(회의 기록)이 「진행 중인
    회의가 없다」, 인수가 「본 배정버전(0)이 최신(1)이 아니다」, 완료가 「미인수」(422)였다. Center 실행의 각본은 409·완료 조건
    미충족을 `center_wait_s`까지 다시 해 보고(`demo._after_record`), 화면이 보는 버전은 시도마다 다시 읽는다. 화면에서 사람이 누를
    때는 그대로 거절 사유를 보인다.
  * **장면 3 시작(`POST /sc03/demo-runs`)이 BFF에서 300초에 503이었다** — 장면 1·2를 Center로 인계까지 돌리는 데 약 7분이 걸리고,
    Node `fetch`(undici)의 응답 헤더 대기 기본값이 300초다. 엔진은 끝까지 진행해 장면 3 문서가 생겼다. **장면 2~6 시작을 배경
    진행 + 준비 상태 조회로 바꿨다**(4.3 「장면 2~6 시작은 오래 걸리면 202다」). SSE가 아니라 폴링(3초)인 것은 문서가 아직 없어
    장면 채널을 구독할 대상이 없어서다. 같은 날 장면 4·5의 대리 답 대기·사전 검사 재시도·각본 대기(`app/script_wait.py`)와
    장면 6의 완료 기록 대기도 같은 값으로 맞췄다 — 장면 4·5는 Center에 배포 전이라 실측하지 않았다.
* **운영 Center에서 HANDOFF31까지 갔다**(2026-10-28, `demo-eb479405` — 장면 1·2를 운영 Center로 인계한 실행에서 시작, 시작 201,
  25단계 약 5분 20초, 결재 한 단계 10~26초). 고친 것 없이 한 번에 갔다: 인수 4/4 · 조건부 수용 · BPM `done`(`End`) · 통합
  3,299,986,680 · 기존 부족 153,939,000 · 전체 부족 177,303,320. 업무 18건 모두 늦게 연 것 0, 완료 시각이 각본 시각과 같고
  (`_await_landed`), 감사 이력 `answer_rejected` 0, 지연 알림 0. 각본이 끝난 순간에는 BPM이 아직 `running`(Complete_Scene 기록
  직후)이었고 곧 `done`이 됐다.
* **external·Company1로 옮긴 뒤 로컬 Center에서 HANDOFF31까지 갔다**(2026-11-02, `demo-e718bf82` — `company1.sc03` 0.3.0 배포, 장면
  1·2를 Center로 인계까지 준비 약 6분 30초 → D31~D41 25단계, 결재 한 단계 약 20초). 일꾼이 장면 3 일감 20건을 모두 `complete`(origin
  `run`), 업무 18건 늦게 연 것·`answer_rejected`·지연 알림 0, 완료 시각이 각본과 같다. 숫자 통합 3,299,986,680 · 기존 부족 153,939,000 ·
  전체 부족 177,303,320 · 경과 8,725분 · 영업시간 2,245분 · 인수 4/4. 장면 3만 초기화한 뒤 **섞어서** 다시 갔다 — 화면 「분석 시작」 →
  회사 사이트 답(정하윤 Save_Analysis) → 플레이어 「다음」 ×2 → 회사 사이트 답(생산 배정훈을 영업보다 먼저 · 영업 박서진) → 자동 재생.
  같은 결과이고, 각본보다 먼저 답한 생산 확인만 답한 시각(6/24 16:00)으로 적혔다(각본 다음 단계가 아니면 시계를 옮기지 않는다 —
  장면 1·2와 같은 규칙). 같이 고친 것:
  * **회사 시스템을 지난다** — 시작 때 장면 2가 회사에 등록한 원가 버전 C02-APP01을 읽어 장면 2 기록과 대조한다(없거나 다르면 409,
    구현명세 「승인단가·적용일은 원천 승인 기록에서 읽는다」). 회사와 오간 것(`companyLog`)은 통합분석 화면에 보이고, 시계를 옮기면
    회사 세계 시각도 옮긴다(C02-APP01 적용 예정 → 7/1부터 적용 중). 손익·부족·회의·과제는 회사에 적지 않는다(경영 기록).
  * **바깥 답에도 시계가 각본을 따라간다**(`process._clock_to_script`, 화면 착수 포함 — 장면 1·2와 같다). 결재 폼 칸의 기본값은 그
    사례 각본의 답이다(`view._defaults`). 회사 사이트 각본 사본은 Company1 `scenarios/sc03.json`.
  * **회사 사이트로만 진행하면 회의 기록이 비어 있다**(2026-11-02 사용자 수동 실행 — 결재 17건을 사이트에서 답해 HANDOFF31까지,
    숫자·시각·업무는 각본과 같다). 회의 질의·답변(QA31~)·AG31 회의 요약은 결재가 아니라 NowView 화면 명령이라 사이트에 길이 없다.
    그런데도 인계의 제외 후보 근거는 시드 그대로 QA33·QA34를 가리킨다 — 결론 때 인용한 회의 기록이 있는지 보지 않는다. 그대로
    두기로 했다(사용자 결정) — 회의 기록까지 보이려면 화면에서 진행한다.
* **E34 재확인 흐름** — 새 전망 버전은 기록·비교까지다. 임원 재확인 뒤 새 버전으로 회의 자료를 바꾸는 길은 없다(확정본으로 간다).
* **Agent LLM 러너** — mock·fail뿐이다(장면 2와 같다).
* 화면 검수는 내장 BASE만 했다. E 사례는 엔진 시험으로 잠갔고 플레이어의 사례 선택으로 돌릴 수 있다.
* 장면 4는 5.8 — HANDOFF31에서 시작한다.

### 5.8 장면 4(SC04) — 완료 (Studio·Center 실행)

2026-10-27. 설계·데이터는 4.18. 엔진 시험(SQLite·Postgres)으로 기본 시연 D401 → D413과 E401~E405·E408, T401~T416을 잠갔고, 숫자는
통합가상데이터 v0.4의 파생 시트(월효과 36행·월손익·비교·검증), 끝난 문서는 SC04 시트(예산과제·조건지시·회의·이벤트 23건·인계)와 같다.
바깥 실행은 Studio 흉내(진짜 엔진 + `origin: test` 일감)·가짜 Center + 실행기 흉내로 완료까지 갔다. 브라우저에서는 **내장 실행(시험용, API로 만든
데모 실행)**으로 U401~U408·BPM 화면을 각본으로 진행하고, 전체 책임 인수와 장면 완료는 화면 폼으로 했다. 예산 위임 조회, 375px를 확인했다.

**남은 것**

* **Center 등록 끝 · 로컬 Center 실측**(2026-10-28): `nowview-sc04` 0.1.0 정의·키·주소, `nowview.sc04` 패키지를 사람이 올렸다.
  장면 3까지 Center로 끝난 데모 실행에서 각본 D401 → D413을 대리 답으로 돌려 HANDOFF41 · 실행 `done`(`End`)까지 갔다(진짜 서버
  실행기). 막힌 곳 둘을 고쳤다: ① 등록 기록 전의 인수가 404(「없는 인수 대상」)라 각본 대기가 다시 해 보지 않았다 — 아는 대상이면
  409(`check_acceptance`). ② 인수 다섯 건의 기록 작업을 실행기가 차례로 불러 완료 조건이 30초 안에 서지 않았다(약 50초) — 각본
  대기를 대리 답 대기의 세 배로(`demo._after_record`). Studio 시험 실행은 아직 돌려 보지 않았다.
  화면 검수(같은 날)에서 셋을 더 고쳤다: ③ 각본이 대표 결정의 기록 작업보다 먼저 AG43을 요청해 **실패 초안**이 남았다 — 입력
  자료가 없으면 요청 명령이 409이고 초안을 남기지 않는다(`process.agent`, 서비스 태스크의 AG41 자동 요청과 E408 생성 실패는
  그대로 실패 초안). ④ 각본이 대리 답만 하고 다음 단계로 가서 기록이 뒤 시각으로 적혔다(인수 시각 전부 10:00, 되감으면 인수
  0/3) — Center 실행이면 그 결재의 기록(`answer_via`·`answer_rejected`)을 기다린다(`demo._await_own_record`). 고친 뒤 초기화 →
  재실행에서 33단계가 손대지 않고 끝났고 인수 시각이 09:00~09:30으로 각본과 같다. ⑤ **초기화 뒤 되감기가 초기화 전 진행을
  보였다** — 이력을 지우지 않아 같은 지점 번호가 앞에 있다. `historySeqFor`(장면 1~5 플레이어 공용)가 마지막 `reset` 이후만 본다.
* **운영 Center에서 HANDOFF41까지 갔다**(2026-10-28, `demo-eb479405` — 장면 1~3을 운영 Center로 끝낸 실행에서 시작, 시작 201,
  33단계 약 8분 30초, 결재 한 단계 10~28초, 재시도 0). 고친 것 없이 한 번에 갔다: BPM `done`(`End`) · 인수 3/3 + 전체 책임 · 종료 요건
  전부 충족 · 보고 효과 137,200,000(REP41-v1) · 판단 효과 127,800,000(DEC41-v2) · 남는 연간 부족 49,503,320 · 조건부 제외 부족
  85,103,320(BASE는 세 안 모두 승인이라 승인 범위도 127.8M — 121.6M은 E403). 업무 24건 늦게 연 것 0, 완료 시각이 각본 시각과 같고
  (인수 7/13 09:00~09:30), 감사 이력 `answer_rejected` 0, 지연 알림 0, Agent 초안 AG41~43 모두 성공(실패 초안 없음).
* **external·Company1로 옮긴 뒤 로컬 Center에서 HANDOFF41까지 갔다**(2026-11-02, `demo-e718bf82` — `company1.sc04` 0.4.0 배포, 장면 3을
  Center로 끝낸 실행에서 시작 201, 각본 D401~D413 33단계, 결재 한 단계 10~22초). 일꾼이 장면 4 일감 26건을 모두 `complete`(origin
  `run`), 업무 24건 늦게 연 것·`answer_rejected`·지연 알림·실패 초안 0, 완료 시각이 각본과 같다. 숫자 보고 효과 137,200,000 · 판단
  효과 127,800,000 · 남는 부족 49,503,320 · 조건부 제외 85,103,320 · 인수 3/3 + 전체 책임. 장면 4만 초기화한 뒤 **섞어서** 다시 갔다 —
  화면 착수 → 회사 사이트 답(구매팀장 AT32를 생산팀장 AT31보다 먼저) → 화면 폼(생산임원 AT31 확인) → 플레이어 자동 재생. 같은 결과이고,
  각본보다 먼저 낸 AT32 제출만 답한 시각(7/1 09:00)에 적혔다. 이때 AT31 확인이 AT32 제출 단계 시각에 적혀 시계를 「이번 결정의
  단계」로 옮기게 고쳤다(4.18).
* **승인 이후 수정**(구현명세 11장 — 새 판단·승인 버전, 대표 재확인, 영향받은 인수 STALE) — 반려 보완(승인 범위 안의 명확화)만 있다.
* **Agent LLM 러너** — mock·fail뿐이다(장면 2·3과 같다).
* 화면 검수는 내장 BASE만 했다. E 사례는 엔진 시험으로 잠갔고 플레이어의 사례 선택으로 돌릴 수 있다.
* **장면 5(상세 실행계획)** — 설계표·데이터가 나오면 시작한다. HANDOFF41이 출발점이다(상세 계획은 비어 있는 정상 상태 `PLAN_PENDING`).

### 5.9 장면 5(SC05) — 완료 (Studio·Center 실행)

2026-10-27. 설계·데이터는 4.19. 엔진 시험(SQLite·Postgres)으로 기본 시연 D501 → D518과 X501~X509, T501~T532를 잠갔고, 숫자는 통합가상데이터
v0.5의 파생 시트(모델손익 60행·월효과 18행·월손익·초기지표·예산·변경대사), 끝난 문서는 SC05 시트(계획·활동·조건품의·예산원장·변경공유·
구매표본 60건·운영계획·전망버전·인계·이벤트 시각과 사람·Agent 상태)와 같다. 바깥 실행은 Studio 흉내(진짜 엔진 + `origin: test` 일감)·가짜 Center +
실행기 흉내로 완료까지 갔다. 브라우저에서는 **내장 실행(시험용, API로 만든 데모 실행)**으로 U501~U508·BPM 화면을 각본으로 진행하고, Agent
초안을 폼으로 가져와 협조·비용이 빈 초안을 저장해 확정 차단 사유 12건이 보이는 것을 확인했다. 375px(문서 폭·좁은 칸)를 확인했다.

**남은 것**

* **Center에 올릴 것**(사람이 한다): ① CON-07에 `chaeksas/nowview-sc05.extension.json` 0.1.0 서명·등록, 외부 앱 키·시험용 키(장면 1~4와
  같은 값), 로컬 Center 「서버 주소」 덮어쓰기. ② Studio에서 `engine/processes/sc05.bpmn`을 내보내 `nowview.sc05` 승인·배포. 그 전에는
  Center 실행의 착수가 Center 거절(배포 없음)로 막힌다. — **사용자가 올렸고, 장면 4까지 Center로 끝난 데모 실행에서 로컬 Center + 진짜
  서버 실행기로 D501 → D518(HANDOFF51, 실행 done)까지 각본으로 갔다**(2026-10-28, FC51 3,428,986,680 게시 10/6 10:05, 결재 한 단계 약
  20초). 끝난 문서의 사건 기록(EV51-*) 42건의 시각·행위자가 내장 실행과 같다. Studio 시험 실행은 아직 돌려 보지 않았다. 실측으로 고친 둘:
  * **상신 기록 전의 현업 승인이 404(「없는 품의: REQ51」)라 각본 대기가 다시 해 보지 않았다** — 아는 품의면 409로 낸다
    (`check_approve_request`, 장면 4 `check_acceptance`와 같다).
  * **Center 각본이 그 결재의 기록을 기다리지 않아** 계획·조건·상신 기록 13건이 다음 단계의 시각으로 적혔다(PL51-v1 경영관리 확인이
    7/16 16:00 → 8/10 10:00). 장면 4의 `_await_own_record`를 그대로 들였다(`answer_via`·`answer_rejected`가 들어올 때까지).
* **운영 Center에서 HANDOFF51까지 갔다**(2026-10-28, `demo-eb479405` — 장면 1~4를 운영 Center로 끝낸 실행에서 시작, 시작 201,
  61단계 약 13분, 결재 한 단계 9~30초, 재시도 0). 고친 것 없이 한 번에 갔다: BPM `done`(`End`) · 종료 요건 전부 충족 · FC51
  3,428,986,680 게시 10/6 10:05(대표 승인 10:00, 부모 FC50) · 과제 순효과 129,000,000(마감 37.2M + 잔여) · 남는 부족 48,303,320 · FC50
  대비 +1,200,000(9월 −1.2M · 11~12월 +2.4M, 대사 ok). 업무 46건 늦게 연 것 0, 감사 이력 `answer_rejected` 0, 사건 기록(EV51-*) 42건의
  시각·행위자가 각본과 같다(로컬 실측과 같다). 알림은 CH54 확인 지연 9/17 11:31 한 건(데이터의 EV51-35 그대로), Agent 초안 AG51~58
  모두 성공.
* **화면 직접 진행(Center)에서 드러난 넷을 고쳤다**(2026-10-28, 버튼·역할 전환만으로 착수 → 변경 접수):
  * **화면 답이 각본 지점을 옮기지 않았다** — 손으로 착수·계획 확정을 해도 D500에 머물렀고 플레이어 「다음」이 「단계를 건너뛸 수
    없다 — 다음은 0번이다」였다(그런데 표시는 단계 4/62로 넘어갔다). 장면 3의 `_follow_script`(`ahead`·`pending`)를 들였다 — 사이의
    Agent·조회는 건너뛰고 병렬 조건 결재는 순서가 바뀌어도 된다. 플레이어는 `scriptIndex`를 따라가고, 실패하면 엔진이 간 지점으로 되돌린다.
  * **대리 답 뒤 약 10초 화면이 비었다** — 장면 3처럼 `bpm.center.inflight`로 「Center 반영 중」을 보인다.
  * **시계 조작이 「다음 영업일 18:30」뿐이었다** — 7/13 → 8/19에 27번 눌렀고, 8/20 아침에 들어오는 근거(DOC51·52)를 쓰려면 기한(18:00)
    뒤인 18:30까지 가야 해 지연 알림 네 건이 생겼다. 플레이어에 **「다음 단계 시각」**(다음 각본 단계의 `at`으로 시계만 옮긴다)을 더했다.
  * **아직 오지 않은 원문이 접수됐다** — 9/2에 9/10 원문 CP52가 CH52가 됐다. 대표 원문도 접수 시각에 도착하는 배경 원천(`original`)이고
    `check_receive`가 도착 전이면 409다.
* **external·Company1로 옮긴 뒤 로컬 Center에서 HANDOFF51까지 갔다**(2026-11-02, `demo-e718bf82` — `company1.sc05` 0.5.0 배포, 장면 4를
  Center로 끝낸 실행에서 시작 201, 각본 D501~D518 61단계, 결재 한 단계 10~30초). 일꾼이 장면 5 일감 47건을 `complete`, 업무 46건 늦게
  연 것·`answer_rejected` 0, 알림은 CH54 9/17 11:31 한 건, EV51-* 42건의 시각·행위자가 시트와 같다. FC51 3,428,986,680 게시 10/6 10:05
  (부모 FC50) · 남는 부족 48,303,320 · FC50 대비 +1,200,000(대사 차이 0). 회사 기간계에 품의 넷(REQ51·OP51·배경 REQ52·53, 각 상신 →
  현업 → 예산 승인)·원장 여덟 줄(일회성 집행 7백만)·공식 전망 FC50 → FC51이 문서와 같게 적혔다. 장면 5만 초기화한 뒤 **섞어서** 다시
  갔다 — 화면 착수 → 회사 사이트 답(8/20 CON41 근거를 시계를 옮기지 않고 답해도 받는다) → 9/1 전 사이트 착수(거절 → 같은 결재가
  사유와 함께 다시 열림) → 「다음 단계 시각」 → 사이트 착수 → 플레이어 「다음」. 숫자·회사 기록은 같고, 병렬 결재를 각본과 다른 순서로
  답한 것은 답한 시각에 적혔다(장면 3·4와 같은 규칙). 드러난 둘을 고쳤다: ① 기록 거절로 Center가 같은 결재를 새 id로 다시 열면 새
  업무(TASK-START-2·3)가 생겨 앞 업무가 「배정」으로 남고 지연 알림이 났다 — 장면 3처럼 같은 업무에 잇는다(`domain.sync_tasks`).
  ② 사이트에서 답한 직후 플레이어 「다음」이 이미 닫힌 결재를 찾다 409였다 — 기다리는 동안 바깥 답이 그 단계를 지났으면 지금 문서를
  돌려준다(`demo.run_step`).
* **승인 후 입력 변경의 재승인 흐름** — 게시 뒤 새 RUN·검토본(FC52-D)은 도메인에서 만들 수 있지만(T526) 그림에는 장면 완료 뒤 다시 도는
  길이 없다.
* **예산 전용·총괄 초과의 실제 처리**(경영관리 임원 전용 승인·대표 별도 승인) — 범위 이탈은 시행 보류로 표시까지만 한다(X502).
* **Agent LLM 러너** — 고정 초안 재생(REPLAY)·실패뿐이다(장면 2~4와 같다).
* 화면 검수는 내장 BASE만 했다. X 사례는 엔진 시험으로 잠갔고 플레이어의 사례 선택으로 돌릴 수 있다.
* 장면 6은 5.10 — HANDOFF51·FC51에서 이어진다.

### 5.10 장면 6(SC06) — 완료 (확인 절차 Studio·Center 실행 + 확인본 조회)

2026-10-27. 설계·데이터는 4.20. 엔진 시험(SQLite·Postgres)으로 v0.6 파생 시트(과제성과·월효과 9행·원인집계·운영지표·분기손익·검증 17항목)
대조, 기존 71개 시트 = v0.5, FC51 ↔ BASE61 대사, X61-01~08·AT61-06·적재 검증(오류값·연결 누락·승인 전 발주·고정비 절감), 조회 계약·403·
409·404·조회 멱등을 잠갔다. 브라우저에서 기존 데모 실행(장면 5 미완료)으로 「장면 6 열기」 → 장면 5 각본 완료 → 적재, U601 요약 → 상세 →
U602 → U601 복귀(펼침 보존), 403 → 경영관리 담당 전환, 375px를 확인했다.

2026-10-28 확인 절차를 BPM으로 돌렸다(4.20). 엔진 시험으로 내장 각본 끝 = SC06보고 시트, 확정 차단·보완·재확인 고리, Studio 흉내·가짜
Center + 실행기 흉내로 대표 보고까지 잠갔다. 브라우저에서는 **내장 실행(시험용, API로 만든 데모 실행 — 이 worktree 엔진에 Center 설정이
없었다)**으로 화면 착수 → 생산 임원 폼 제출 → 플레이어가 화면 답을 따라가 대표 보고까지 → 조회 세 동작, BPM 흐름 캔버스, 초기화 →
결론 단계까지 진행한 DRAFT 보고 요약(「확인 중 3/5」·결론 「초안」), 375px를 확인했다.

**남은 것**

* **Center 등록 끝 · 로컬 Center 실측**(2026-10-28): `nowview-sc06` 0.1.0 정의·키·주소, `nowview.sc06` 패키지를 사람이 올렸다. 장면 5까지
  Center로 끝난 데모 실행에서 장면 6을 열고 각본 D601 → D607을 대리 답으로 돌려 REPORTED · 실행 `done`(`End`)까지 갔다(진짜 서버 실행기,
  확인 기록 일곱 건·시각이 각본과 같다). 막힌 곳 하나를 고쳤다: **대리 답이 폴러(2초)보다 먼저 결재를 찾으면 폴러는 대리 답한 결재를
  건너뛰어 업무가 기록 때 「늦게 열림」으로 생겼다**(6건 중 4건) — 대리 답 때 업무가 없으면 그 결재로 연다(`_relay`). 초기화 → 재실행에서
  6건 모두 제때 열렸다. **장면 3~5의 `_relay`도 같은 모양이라 함께 고쳤다** — 같은 데모 실행의 Center 각본에서 늦게 연 업무가 장면 3
  8/18 · 장면 4 11/24 · 장면 5 12/46건이었다(시험 `test_center_relay_ahead_of_the_poller_opens_the_task_on_time`이 장면 3~6에서 잠근다 —
  장면 3~5는 진짜 실행기로 다시 돌려 보지 않았다). Studio 시험 실행은 아직 돌려 보지 않았다.
* **운영 Center에서 대표 보고까지 갔다**(2026-10-28, `demo-eb479405` — 장면 1~5를 운영 Center로 끝낸 실행에서 시작, 적재 201, 착수 +
  6단계 약 2분, 결재 한 단계 14~30초(병렬 구매 확인은 0초 — 이미 열려 있었다), 재시도 0). 고친 것 없이 한 번에 갔다: RPT61-v1
  REPORTED(CALC61-v1, 확정 1/13 17:00) · BPM `done`(`End`) · 시계 1/14 11:00 · 확인 기록 일곱 건(CF61-P·B·F·R·M · TXT61 · NOTE61)의
  단계·행위자·시각·상태·글·버전이 SC06보고 시트와 같다. 업무 6건 늦게 연 것 0·기한 초과 0, 감사 이력 `answer_rejected` 0, 물러난 기록 0.
  조회 넷(경영관리 담당) — Q4 기대 91,800,000 · 확인 87,000,000 · 차이 −4,800,000 · ACT42 30.6 → 25.8백만원 · 원인 14건 16,800,000
  (INTERNAL 4·SUPPLY 9·MIXED 1, 잔차 0) · `data_status` COMPLETE, 근거 E61-1103(대행 USR-BUY2 작성), 영업담당은 403 ACCESS_DENIED.
* **external·Company1로 옮긴 뒤 로컬 Center에서 대표 보고까지 갔다**(2026-11-02, `demo-e718bf82` — `company1.sc06` 0.6.0 배포, 장면 5를
  Center로 끝낸 실행에서 적재 201, 각본 D601~D607, 결재 한 단계 10~30초). RPT61-v1 REPORTED(CALC61-v1) · BPM `done`(`End`) · 시계 1/14
  11:00(회사 세계 시각도 같다), 확인 기록 일곱 건의 단계·행위자·시각·상태·글·근거가 SC06보고 시트와 같다. 업무 6건 늦게 연 것·
  `answer_rejected` 0, 「회사 시스템과 오간 것」에 FC51 읽기 한 줄. 조회 넷 — Q4 기대 91,800,000 · 확인 87,000,000 · ACT42 30.6 → 25.8 ·
  원인 14건 16,800,000(INTERNAL 4·SUPPLY 9·MIXED 1) · `data_status` COMPLETE, 영업담당 403. 초기화 뒤 **섞어서** 다시 갔다 — 화면 착수 →
  회사 사이트 답(구매 임원 확인을 생산보다 먼저, 회사 자료 카드 `performance`·FC51) → 플레이어 → 사이트 답(보고 결론) → 플레이어. 같은
  결과다. 드러난 둘을 고쳤다(4.20): 대표 보고 업무 완료 시각이 11:00으로 적혔다 → 기록 시각, Center 각본이 자기 기록을 기다리지 않아
  사이트가 먼저 답한 구매 확인 단계에서 409였다 → `_await_own_record`. 사이트 기록이 플레이어 기록보다 늦게 오면 그 단계는 결재 찾기를
  기다린 뒤(30초) 지금 문서를 돌려준다 — 409는 아니다. 브라우저(:3006 worktree 웹)에서 U601 요약·ACT42 차이 상세·U602·확인 절차(회사
  카드)·BPM 흐름(노드 14개 완료)을 확인했다.
* **새 보고 버전(RPT61-v2) 흐름** — 재적재가 새 산정과 재확인 대상을 알리는 데까지다. 새 보고본 작성·확인은 없다.
* **Agent LLM 러너** — AG61~63은 고정 기록 재현뿐이다(장면 2~5와 같다).
* 운영계(5.4)에서 장면 1→7을 자동 모드로 끝까지 돌렸다(2026-11-04).

### 5.11 장면 7(SC07) — 완료 (확인·적용 절차 Studio·Center 실행 + U701 조회)

2026-11-03. 설계·데이터는 4.21. 엔진 시험(SQLite·Postgres)으로 v0.7 대조(앞 92개 시트 = v0.6, `SC07판단`·`SC07검증결과`·`SC07적용`),
AT701~AT712 변형, 확인·적용 절차의 고리(검증 미통과·보완 요청·설정 불일치)와 조회 계약을 잠갔다. Studio 흉내·가짜 Center + 실행기 흉내로 후속 점검까지.

* **로컬 Center에서 끝까지 갔다**(`demo-e718bf82` — 장면 1~6을 Center로 끝낸 실행에서 적재 201, `company1.sc07` 0.7.0 사용자 배포, 확장
  `external` 0.7.0은 일꾼이 올렸다). 각본 D701~D705 대리 답, 결재 한 단계 약 20초, 합계 약 85초. 검증 VR71-1 8건 충족, CF71·CF72·설정 반영·
  확인의 행위자·시각·글·버전이 시트와 같고, 업무 4건 제때 열림(늦게 연 것 0)·`answer_rejected` 0, BPM `done`(`End`), ST707·운영 실행 미확인·
  후속 점검 2/11 10:00.
* **섞어서 한 번 더 갔다** — 초기화 → 화면 착수 → 회사 사이트 답(구매 임원 CF71, 폼은 `sc07.json` 예시·카드 `kind: improvement`) → 플레이어
  (각본 위치가 따라가 그 단계는 다시 대리 답하지 않음, CF72) → 회사 사이트 답(운영담당 설정 반영) → 플레이어(설정 확인). 기록·시각·업무가
  같고 거절 0, 대리 답 2건(나머지 둘은 사이트).
* 브라우저(:3007 worktree 웹): U701 A(개선 사유·기존/개선 비교·근거 칩·기준·절차 한 줄) → B(TC701 상세·7건 요약·적용 확인·확인 이력·다음
  점검), 보기 새로고침 유지, 확인·적용 절차·BPM 흐름(모든 노드 완료), 375px(문서 폭 375·좁은 칸 없음).
* **남은 것**: 실시간 Agent 실행(구현명세 UI702 — 선택 구현, 지금은 규칙 재계산), 운영 실행 확인(UI708 — 실행 id·사용 버전 증적), 적용 실패 시
  이전 버전 복귀 절차(V708 — 참조만 보인다), 새 보고·개선 버전의 재검증 흐름, Studio 시험 실행 실측, 운영계(5.4) 반영. 첫 렌더에 「관리모델 개선이
  아직 열리지 않았다」가 잠깐 보인다(데모 실행 id 복원 전 — 장면 6 화면과 같은 모양).

