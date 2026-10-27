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
npx vitest run tests/sc01.test.ts                   # 파일 하나
npx vitest run tests/sc01.test.ts -t "판정 보류"     # 이름으로 하나만
```

**BPM 엔진 (Python · `engine/`)**

```bash
cd engine
uv sync
uv run uvicorn app.main:app --port 8077 --reload   # http://localhost:8077/docs  (키: --env-file .env.local)
uv run pytest                                      # 539개 (SQLite만, LLM 제외)
uv run pytest -m llm                               # ollama 실호출 (OLLAMA_URL 필요, 약 100초)
uv run ruff check .
```

**로컬 프로세스 제어 (웹 · 엔진 · DB)**

```bash
npm run stack:start            # 엔진 → 웹 순서로 띄운다 (db는 별도: stack:start db)
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
  `TEST_DATABASE_URL=postgresql://nowview:nowview@localhost:55432/nowview uv run pytest` (739개)

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
* **React Flow는 스타일시트를 직접 import해야 한다.** `import '@xyflow/react/dist/style.css'` 없이는 노드·엣지가 레이아웃 없이 렌더되어 "아무것도 안 보이는" 상태가 된다. 첫 React Flow 화면을 만들 때 함께 넣는다.
* **React Flow는 부모에 명시적 높이가 필요하다.** `h-[440px]` 같은 고정 높이가 없으면 캔버스가 접힌다.
* **`markerEnd`의 색에 CSS 변수를 쓰면 화살촉이 사라진다.** React Flow가 색 문자열을 marker DOM id에
  그대로 끼워 넣고 `url(#...)`로 참조하는데, `var(--x)`의 괄호가 그 참조를 깨뜨린다. 콘솔 경고가 없어
  원인을 찾기 어렵다. **라이트/다크 값이 같은** 팔레트 스텝만 리터럴로 쓴다 — `#0ca30c`(status-good),
  `#898781`(muted). 선(path)은 `style`로 칠하므로 CSS 변수를 그대로 써도 된다.
* **숨겨진 브라우저 패널에서는 React Flow를 검증할 수 없다.** 패널이 표시되지 않으면 `document.hidden`이
  true가 되어 `requestAnimationFrame`과 `ResizeObserver` 콜백이 전혀 발화하지 않는다. React Flow는 이
  둘로 노드를 측정하므로 초기화가 끝나지 않고 **엣지 0개 + fitView 미적용** 상태가 된다 —
  기본 노드 2개짜리 최소 예제도 동일하게 실패하므로 앱 버그로 오진하지 말 것. 반면 Recharts는 마운트 시
  컨테이너 폭을 동기로 읽어 정상 렌더되므로, "차트는 되는데 플로우만 안 된다"는 정상 증상이다.
  **같은 상태에서 스크롤·resize 이벤트도 배달되지 않고 `behavior: "smooth"` 스크롤도 움직이지
  않는다** — 검증 방법은 4.10에, ResizeObserver에 기대면 안 되는 이유는 4.12에 적어 두었다.
* **React Flow / Recharts는 클라이언트 컴포넌트다.** 둘 다 브라우저 전용 API에 의존하므로 사용하는 파일 최상단에 `'use client'`가 필요하다. App Router 기본값은 서버 컴포넌트다.
* **Recharts 커스텀 `shape` + entrance 애니메이션은 같이 쓰면 안 된다.** `<Bar shape={<Custom/>}>`에
  애니메이션이 켜져 있으면 막대가 `height: 0`에 멈춘 채 렌더된다 — 에러도 콘솔 경고도 없고 SVG 골격만
  그려지므로 원인 파악이 오래 걸린다. 커스텀 shape를 쓸 때는 `isAnimationActive={false}`를 함께 준다.
  (이전 Cockpit의 브릿지 차트에서 실제로 겪었다.)
* **`<Cell radius>`는 배열을 받지 못한다** (타입이 `string | number`). 모서리별 반경이 필요하면
  `<Bar shape>`로 `<Rectangle radius={[…]}/>`를 직접 그린다.
* **커스텀 `tick` 엘리먼트를 주면 Recharts 기본 클래스가 붙지 않는다.** `.recharts-cartesian-axis-tick-value`
  선택자로 축 라벨을 찾는 테스트는 실패한다. 또한 v3의 zIndex 레이어 구조 때문에 축 눈금이
  `.recharts-xAxis`의 자손이 아닐 수 있으므로, 좌표 기준으로 찾는 편이 안전하다.
* **테마 의존 UI를 `useState`+`useEffect`(mounted 플래그)로 그리면 lint가 막는다** —
  `react-hooks/set-state-in-effect`. 적용 테마를 렌더 결과에 반영하는 대신 `dark:` 변형(CSS)으로
  전환하면 마크업이 양쪽 테마에서 동일해져 hydration 불일치도 같이 사라진다.
  `components/theme-toggle.tsx`가 그 패턴이다(`resolvedTheme`은 클릭 시점에만 읽는다).

---

## 1. Project Overview
* **Project Name**: NowView (INNONOW Management Reference Model Pilot Web Platform)
* **Description**: 매출 약 1조원 규모 가상 자동차 부품사를 대상으로, 체계화된 Management Framework 및 BPM 프로세스 위에서 사람과 AI Agent가 협업하는 경영 운영 플랫폼 프로토타입.
* **지금 구현된 것**: 대표 시나리오 1의 **장면 1(SC01)** — 고객 생산계획 변경을 감지해 현업 통제와 Management Review로 인계하기까지. 업무 흐름은 **Chaeksas BPM**이 BPMN을 해석해 돌린다(4.5). Center 실행에서는 고객계획 접수를 **가상 직원**(접수 Bot)이 맡고 감독자가 승인한 건만 SC01이 된다(4.5 N5).
  **장면 2(SC02)** — 외주 공통부품 단가 인상 요청을 접수·분석·1차 협상·기안·순차 승인(팀장 → 임원 → 금액 기준 대표)하고 원가 버전을 등록해, 장면 1 물량 감소와 함께 경영관리에 인계하기까지(4.16). 장면 1과 **같은 데모 실행**을 잇는다. **Studio 시험 실행·Center 서버 실행**에서 돈다(외부 확장 `nowview-sc02`).
  **장면 3(SC03)** — 장면 1 물량 감소와 장면 2 승인 단가를 한 수익성 검토건(MR-2706-01)에 잇고, 통합 분석 → 영업·구매·생산
  확인 → 쟁점 판단 → 자료 확정 → 경영관리 임원 주재 수시회의(결론·후보 포함/제외) → 분석과제 AT31~34 배정·인수 → 장면 4 인계
  (HANDOFF31)까지(4.17). 같은 데모 실행을 잇고 **Studio·Center 실행**에서 돈다(외부 확장 `nowview-sc03`).
  **장면 4(SC04)** — 장면 3 분석과제 AT31~34의 결과를 받아 비용·중복을 검증하고, 담당 임원들이 우선 실행안 3개를 공동 제안하고,
  대표 주재 월간회의(MT41)의 질의로 판단본(DEC41-v2)을 확정한 뒤 대표가 책임·예산 한도·두 기한·조건을 포괄 승인(APR41-v1)하고,
  전체·개별 책임자가 실행과제 ACT41~43·조건·지시를 인수하면 장면 5로 인계(HANDOFF41)까지(4.18). 같은 데모 실행을 잇고 **Studio·
  Center 실행**에서 돈다(외부 확장 `nowview-sc04`).
  **장면 5(SC05)** — 장면 4가 조건부 승인한 ACT42(긴급구매 축소)를 상세 실행계획(PL51-v1 → 범위 내 변경 v2)으로 확정·확인하고,
  CON41·SUP41 이행 확인과 품의(REQ51·OP51) 뒤 9/1 운영 적용, 생산 변경 공유·구매 대응(정상 CH51 · 긴급 CH52), 9월 초기 결과,
  월간 Rolling 운영계획(OPL51~53)과 공식 Forecast(FC50 → FC51) 작성·부서 확인·대표 승인·게시를 거쳐 후속 책임을 넘기기까지
  (HANDOFF51, 4.19). ACT41·43은 요약만 한다. 같은 데모 실행을 잇고 **Studio·Center 실행**에서 돈다(외부 확장 `nowview-sc05`).
  **장면 6(SC06)** — 과제 완료 후 차 분기(2027 Q4)의 완료·성과 검토. Q4 자료를 적재하고(숫자는 규칙 계산), **확인 절차**(담당 임원
  성과 근거 확인 생산 ∥ 구매 → 경영관리 종합 확인 → 보고 결론 → 보고본 확정 → 대표 보고)를 BPM으로 돌린 뒤, 확인된 보고본 RPT61-v1을
  2028-01-14 11:00에 **조회**한다(U601 요약 → ACT42 차이 상세 → U602 보고 요약, 두 화면·세 동작). Q4 기대 91.8 → 확인 87.0백만원
  (−4.8), ACT42 30.6 → 25.8, 운영 보완 FUP61·추가 검토 발의 PROP61까지(4.20). 같은 데모 실행을 잇고 **Studio·Center 실행**에서 돈다
  (외부 확장 `nowview-sc06`, 2026-10-28 사용자 요청으로 확인 절차를 BPM으로 돌렸다).
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
Management Evolution 상세는 범위 밖이다. 장면 7은 설계표·데이터가 없다 — 화면은 수치를 지어내지 않는다. 기획안의 100억 → 85억 → 97억은 **설명용 예시**이고 데이터의 손익
(공장관리손익 목표 34.77억)과 다르다(D18).

---

## 3. Tech Stack

* **Frontend**: Next.js 16.3.6 (App Router, Turbopack), React 19.2, TypeScript 5, Tailwind CSS v4, Shadcn/UI (`radix-nova` 프리셋 / Radix 기반 / Lucide 아이콘)
* **Process Visualization**: `@xyflow/react` 12.12 (React Flow) — BPMN 토폴로지를 엔진에서 받아 그린다
* **Data Visualization**: **Recharts** 3.10 (단일 차트 라이브러리)
* **State Management**: Zustand 5.0 (데모 실행 사본 · 행위자 · 플레이어)
* **Backend / API**: Next Route Handler 하나가 엔진을 프록시한다(BFF, 4.3)
* **BPM**: **Chaeksas BPM** (`chaeksas-core`, BPMN 2.0 해석기 — git 커밋 고정 의존성으로 임베드)
* **Engine**: Python 3.12 · FastAPI · uv
* **Database**: PostgreSQL(운영·compose·CI) / SQLite(로컬 기본). 시드는 엑셀(`engine/seed/`)

### 3.1 확정된 기술 선택 (Decided — 재검토 불필요)

| 영역 | 선택 | 배제한 대안 | 사유 |
|---|---|---|---|
| BPM | **Chaeksas BPM** (`chaeksas-core` 라이브러리 임베드) | LangGraph StateGraph(이전 선택), Camunda 8, Chaeksas Center 연동 | 2026-10-19 사용자 결정. BPMN 2.0을 그대로 해석하므로 업무 흐름이 **BPMN 파일 하나**에 있고 Chaeksas Studio로 열 수 있다. Camunda는 Zeebe 브로커 운영이 과중했다. Center·서버 실행기 경유는 정의마다 서명·배포가 필요하고 결재 응답이 관리자 토큰 전용이며 작업 결과 값을 돌려주지 않아 배제했다(4.5). |
| 차트 | Recharts | Apache ECharts | Shadcn/UI·Tailwind와의 컴포지션이 자연스럽다. 차트 라이브러리는 하나만 쓴다 — 두 개를 섞으면 테마·툴팁·반응형 동작이 갈라진다. |
| Shadcn 프리미티브 | Radix (`-b radix`) | Base UI, React Aria | 기존 shadcn/ui 문서·스니펫이 Radix 기반이라 이식 비용이 가장 낮다. |
| 테마 전환 | next-themes (`attribute="class"`) | 직접 구현 | 초기 렌더에 잘못된 테마가 번쩍이는(FOUC) 문제를 직접 처리하지 않아도 된다. `.dark` 클래스 방식이 Tailwind v4 `@custom-variant dark`와 `globals.css`의 `.dark .viz-root`를 동시에 만족시켜, UI 토큰과 차트 색이 항상 함께 전환된다. |

**토폴로지의 원천은 BPMN 파일**(`engine/processes/*.bpmn`)이다. 화면은 `GET /sc01/process`로 받아
React Flow로 그린다(배치는 화면이 계산한다 — BPMN에 DI가 없다).

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
│   ├── deploy.sh                 # 운영계 배포 (rsync → 빌드 → systemd 재시작) — 5.4
│   └── validate_palette.js       # 차트 팔레트 검증기 (dataviz 스킬에서 들여옴)
├── deploy/                       # 운영계 자산 (5.4) — bootstrap.sh · systemd 유닛 2개
├── chaeksas/                     # 바깥 Chaeksas에 올릴 외부 확장 정의 — 장면마다 한 벌(nowview-sc01~sc06, 로컬은 Center가 주소를 덮어쓴다, 4.3)
├── docs/                         # chaeksas-integration.md(바깥 Chaeksas 연계 설계 — 제안) · handoff/(Chaeksas 요청서)
├── app/
│   ├── layout.tsx                # 세 단(왼쪽 업무 · 가운데 머리·본문 · 오른쪽 데모 플레이어) · 역할 전환 · 테마 · 세션 동기화
│   ├── globals.css               # 테마 토큰 + --viz-* 시각화 팔레트
│   ├── page.tsx                  # UI01 A제품 경영 현황
│   ├── plans/page.tsx            # UI02·UI03 고객 생산계획 수신 · 원천 확인
│   ├── risk/page.tsx             # UI04 공급전망 변동 · 위험 검토
│   ├── tasks/page.tsx            # UI05 검토·승인 업무
│   ├── handoff/page.tsx          # UI06 경영이슈 · 인계 현황
│   ├── process/page.tsx          # BPM 흐름 (BPMN 캔버스)
│   ├── sc02/                     # 장면 2 — page(현황·D00) · request(U21) · analysis(U22) · negotiation(U23)
│   │                             #   · proposal(U24) · approval(U25) · cost(U26) · handoff(U27) · process(BPM)
│   ├── sc03/                     # 장면 3 — page(업무함 U31) · analysis(U32) · confirm(U33) · meeting(U34·U35)
│   │                             #   · tasks(U36) · handoff(U37) · process(BPM)
│   ├── sc04/                     # 장면 4 — page(결과 업무함 U401) · verify(U402) · recommend(U403) · report(U404)
│   │                             #   · meeting(U405) · approval(U406) · actions(U407) · handoff(U408) · process(BPM)
│   ├── sc05/                     # 장면 5 — page(과제 현황 U501) · plan(U502) · ready(U503 조건·품의·착수) · changes(U504)
│   │                             #   · results(U505) · operating(U506) · forecast(U507) · handoff(U508) · process(BPM)
│   ├── sc06/                     # 장면 6 — page(완료·성과 검토 U601, ACT42 차이 상세 포함) · confirm(확인 절차 결재)
│   │                             #   · report(U602 보고 요약) · process(BPM)
│   └── api/engine/[scene]/[...path]/route.ts  # 엔진 프록시(BFF) — 유일한 라우트(sc01~sc06만 중계)
├── components/
│   ├── ui/                       # Shadcn 원시 컴포넌트
│   ├── shared/                   # section-nav(섹션 탭), commentary(해설), disclosure(접기), form-field(결재 칸),
│   │                             #   scenario-nav(업무 사이드바 · 머리의 업무 · 화면 메뉴), demo-player-switch(장면별 플레이어),
│   │                             #   preparation-note(장면 시작 준비 중 — 앞 업무 진행 표시)
│   ├── sc01/                     # SC01 화면들 + 공용 조각(bits, action-form, actor-switcher,
│   │                             #   session-sync, demo-player, use-dashboard, profit-trend-chart,
│   │                             #   intake-card — 접수 가상 직원, N5)
│   ├── sc02/                     # SC02 화면들 + bits · action-form · analysis-parts · session-sync · demo-player
│   ├── sc03/                     # SC03 화면들 + bits · action-form · bridge-chart(손익 브리지) · agent-card · session-sync · demo-player
│   ├── sc04/                     # SC04 화면들 + bits · action-form · agent-card(AG41~43) · session-sync · demo-player
│   ├── sc05/                     # SC05 화면들 + bits(Tile·Requirements) · action-form · agent-card(AG51~58) · session-sync · demo-player
│   ├── sc06/                     # SC06 화면 — review(U601)·report(U602)·confirm(확인 절차 결재 폼)·process(BPM) + bits(LoadGate·EvidenceChip)
│   │                             #   · session-sync(머리는 SSE, 조회는 멱등) · demo-player(확인 절차 7단계 각본 + 조회 세 동작)
│   ├── flow/sc01-canvas.tsx      # React Flow 전용 (장면 2·3도 같은 캔버스 — `maxColumns`만 다르다)
│   ├── theme-provider.tsx
│   └── theme-toggle.tsx
├── lib/
│   ├── utils.ts                  # cn()
│   ├── preparation.ts            # 장면 시작 202(준비 중) → 준비 상태를 읽다가 문서를 받는다(4.3)
│   ├── sc01/                     # types · client · format · scenes(데모 장면) · process-layout
│   ├── sc02/                     # types · client · format · scenes(엔진 각본 → 장면)
│   ├── sc03/                     # types · client(완료 실패의 blockingItems) · format(백만원) · scenes
│   ├── sc04/                     # types · client(예산 위임 조회) · format(목표 초과 표기) · scenes
│   ├── sc05/                     # types · client(Agent 검토 기록) · format(미확인·비해당·활동 목록 글) · scenes
│   ├── sc06/                     # types · client(조회 4개 · 착수·결재·각본·초기화) · format(미확인·산정 보류·미산정·부호)
│   │                             #   · scenes(확인 절차 7단계 + 세 동작)
│   └── store/                    # sc01(데모 실행 사본·행위자·플레이어), sc02~sc05(장면 사본·플레이어), sc06(조회·펼침), ui-prefs(해설)
├── tests/                        # Vitest — sc01~sc06.test.ts, fixtures/sc0{1,2,3,4,5,6}-process.json
└── engine/                       # Python BPM 엔진 (별도 프로세스)
    ├── pyproject.toml            # uv · chaeksas-core(git 커밋 고정)
    ├── processes/sc01.bpmn       # SC01 업무 흐름 — 유일한 원천
    ├── processes/sc01-intake.bpmn # 고객계획 접수 Bot(가상 직원, N5) — Center 서버 Bot으로만 돈다
    ├── processes/sc02.bpmn       # SC02 업무 흐름 — Studio·Center 실행(4.16)
    ├── processes/sc03.bpmn       # SC03 업무 흐름 — Studio·Center 실행(4.17)
    ├── processes/sc04.bpmn       # SC04 업무 흐름 — Studio·Center 실행(4.18)
    ├── processes/sc05.bpmn       # SC05 업무 흐름 — Studio·Center 실행(4.19)
    ├── processes/sc06.bpmn       # SC06 확인 절차 — Studio·Center 실행(4.20)
    ├── seed/SYN-SC01-v0.2.xlsx   # 통합 가상 데이터 설계 — 원천 시트=시드, 파생 시트=기대값
    ├── seed/SYN-SC02-v0.2.xlsx   # SC01_SC02 통합가상데이터 v0.2 — 같은 원칙(2027 행은 SC01 시드와 같다)
    ├── seed/SYN-SC03-v0.3.xlsx   # SC01_SC02_SC03 v0.3 — 숫자 시트는 v0.2와 같다, SC03 시트는 종료 시점 완성 레코드(기대값)
    ├── seed/SYN-SC04-v0.4.xlsx   # SC01~SC04 v0.4 수정본 — 숫자·SC03 시트는 v0.3과 같다, SC04가정이 원천, 나머지 SC04 시트는 기대값
    ├── seed/SYN-SC06-v0.6.xlsx   # SC01~SC06 v0.6 — 기존 71개 시트는 v0.5와 같다, SC06 원천(기준·실적·거래 180·변경·판단·후속·근거·Agent·보고)을 한 번에 적재
    ├── seed/SYN-SC05-v0.5.xlsx   # SC01~SC05 v0.5 — 기존 45개 시트는 v0.4와 같다, SC05 원천(설정·활동·고객계획·변경·구매·원장·근거)은 시각대로 들인다
    ├── app/
    │   ├── main.py               # FastAPI — health + /sc01 ~ /sc05 라우터
    │   ├── store.py              # 백엔드 선택 (SQLite 파일 / Postgres 풀)
    │   ├── events.py · notify.py # SSE 허브 · 프로세스 경계 전파
    │   ├── preparation.py        # 장면 2~6 시작의 배경 진행 · 준비 상태(4.3)
    │   ├── script_wait.py        # Center 실행의 각본이 앞 결재의 기록 작업을 기다린다(장면 3~5, 4.17)
    │   └── sc01/                 # seed · calc · domain · process · store · demo · view · api · auth
    │                             #   · center(Center 클라이언트) · poller(진행 폴링) — N3
    │   └── sc02/                 # seed · calc · domain · agent · process(내장·Studio·Center) · demo · view · api (저장은 sc01/store의 `sc02_*`)
    │   └── sc03/                 # seed · calc(장면 2 월별 계산 재사용) · domain · agent · process · demo · view · api (`sc03_*`)
    │   └── sc04/                 # seed · calc(효과·중복·검증·잔여 부족, 기준은 장면 3 계산) · domain · agent · process · demo · view · api (`sc04_*`)
    │   └── sc05/                 # seed · calc(관측·예산·과제 효과·월 손익·FC50 대비 대사) · domain(배경 원천 catch_up) · agent · process · demo · view · api (`sc05_*`)
    │   └── sc06/                 # seed · calc(Q4 기대 대비 확인 효과·원인·운영지표·보조 손익) · domain(적재 검증·판단·조회·재적재)
    │                             #   · confirm(확인 절차 — 결재 검사·기록·업무) · process(내장·Studio·Center) · demo(D601~D607) · view · api (`sc06_*`)
    └── tests/                    # pytest — test_sc01_calc · _process · _api · _agent · _exceptions · _center · _intake,
                                  #   test_sc02_calc · _process · _external, test_sc03_calc · _process · _external,
                                  #   test_sc04_calc · _process · _external, test_sc05_calc · _process · _external,
                                  #   test_sc06_calc · _process · _external,
                                  #   test_events · _notify · test_preparation
```

**디렉토리 규칙**
* `components/sc01/`~`sc05/` — 장면별 화면 전용. 장면 6 이후도 같은 원칙으로 나눈다.
* `components/flow/` — React Flow 노드·엣지·캔버스 **전용**.
* `components/shared/` — 두 화면 이상이 쓰는 조각 중 SC01에 묶이지 않은 것만 둔다.
* `engine/app/sc01/`~`sc05/` — 업무 규칙. 화면(TS)은 규칙을 다시 구현하지 않는다(4.3).

### 4.1 데모 플레이어

`components/sc01/demo-player.tsx`가 하단 고정 바로 상주한다. 장면은 `lib/sc01/scenes.ts`(SC01 설계서
2.10 기본 시연 순서, 11장면), 각본(누가·언제·무엇을)은 엔진 `app/sc01/demo.py`(EV01~EV07)다.

* **앞으로는 실행, 뒤로는 읽기.** 장면이 엔진의 각본 지점보다 앞이면 그 단계까지 `POST …/script/{i}`로
  **실제로 실행**한다 — 역할 검사·업무 규칙을 그대로 탄다(지름길 없음). 이미 지나간 장면이면 그 시점의
  이력을 읽어 보여 주기만 한다(`past`). "초기화"만 데모 실행을 S0로 되돌린다.
* **장면 → 이력 seq는 그 지점에 처음 도달한 기록이다**(`historySeqFor`). 마지막 기록을 쓰면 다음 단계
  직전의 가상시계 이동이 섞여 "이 장면의 상태 + 다음 장면의 시각"이 보인다.
* 장면 이동은 한 핸들러에서 상태 적용과 라우팅을 함께 한다 — 상태를 감시하는 effect로 라우팅하면
  GNB로 직접 이동할 때 플레이어가 되돌려 버린다.
* **자동 재생은 자기 예약 루프다.** 장면이 반영된 뒤 7초 머문다. 자동 재생 effect는 `jump`에 의존하지
  않고 ref로 쓴다 — 의존하면 화면이 바뀔 때마다 타이머가 다시 걸린다. 요청에 일련번호를 붙여 최신
  응답만 반영한다.
* **각본과 수동 조작을 섞으면 각본이 멈춘다.** 화면에서 직접 수신·확인한 뒤 "다음 장면"을 누르면 엔진이
  "지금 기다리는 업무가 아니다"(409)로 거절하고 플레이어가 사유를 보인다. 초기화 후 다시 한다.

### 4.2 상태 영속화

`lib/store/sc01.ts`는 `persist`로 localStorage(`nowview-sc01`)에 **데모 실행 id · 행위자 · 장면 · 펼침**만
저장한다. 문서는 저장하지 않는다 — 새로고침하면 엔진에서 다시 받는다(낡은 값이 먼저 보이지 않게).

* **`skipHydration: true`가 핵심이다.** 화면이 정적 프리렌더라 서버 HTML은 항상 기본 상태인데, 모듈 로드
  시점에 복원하면 첫 클라이언트 렌더가 달라져 하이드레이션이 깨진다. `Sc01SessionSync`가 mount 이후 복원한다.
* 저장 형태를 바꾸면 `version`을 올린다.
* **저장된 데모 실행이 엔진에 없으면(DB 초기화 등) 새로 만든다.** 개발 모드의 StrictMode가 effect를 두 번
  돌려 실행이 둘 생겼다 — 진행 중인 생성 요청을 공유한다(`pendingCreate`).

### 4.3 API 계층

```
브라우저 ──/api/engine/{sc01|sc02}/*──▶ Next Route Handler(BFF, 그대로 중계) ──/{sc01|sc02}/*──▶ 엔진(127.0.0.1:8077)

GET  /sc01/process · /users · /rules · /script · /customer-plans/{id}
POST /sc01/demo-runs  {caseId, executor}   → 새 데모 실행(S0). executor = embedded|studio|center (N2)
GET  /sc01/demo-runs/{id}                  → 문서 뷰 (BPM 대기·업무·이슈·인계 조건)
GET  /sc01/demo-runs/{id}/dashboard?period=&month=&seq=   → UI01 집계 (seq = 지난 시점)
GET  /sc01/demo-runs/{id}/history · /history/{seq}         → 지난 시점(읽기 전용)
POST /sc01/demo-runs/{id}/sources/receive  {fixtureId}     → 시연 원천 수신
POST /sc01/demo-runs/{id}/actions/{nodeId} {answer}        → BPM 사람 대기에 응답
POST /sc01/demo-runs/{id}/clock {at} · /script/{i} · /reset {caseId, executor}
GET  /sc01/demo-runs/{id}/events           → SSE
     시스템 작업 — 바깥 Chaeksas가 서비스 태스크에서 부른다 (행위자 헤더 없음)
     본문에 늘 {chaeksas_run_id: {{run_id}}, chaeksas_node_id: {{node_id}}} — 데모 실행을 바깥 실행에 묶는다
POST /sc01/demo-runs/{id}/sources/{sourceId}/validation    → {passed, error_count}
POST /sc01/demo-runs/{id}/sources/{sourceId}/comparison    → {run_id, risk, issue_id}
POST /sc01/demo-runs/{id}/calc-runs/{runId}/agent-draft    → {output_id}
POST /sc01/demo-runs/{id}/calc-runs/{runId}/handoff        → {handed_off}
POST /sc01/demo-runs/{id}/answers/{nodeId}  {결재 칸…}      → 결정 기록 (N1, 아래 4.5)
     접수 Bot(N5)이 부른다 — 데모 실행을 바깥 실행에 묶지 않는다
POST /sc01/demo-runs/{id}/intake/sources/{sourceId}/screening → {summary}  (검증 결과·변경 요약)
POST /sc01/demo-runs/{id}/intake/sources/{sourceId}/decision  → {recorded} (반려면 보완 요청)
GET  /sc01/intake                          → 「접수 가상 직원」 카드 (Center 가상 직원 그대로)
POST /sc01/intake/approvals/{requestId}/answer {answer}  → 일괄 결재 대리 답 (감독자는 Center가 대조)

     장면 2(4.16) — 데모 실행 id는 장면 1과 같다
GET  /sc02/process · /cases · /rules · /parts · /script?case_id=
POST /sc02/demo-runs  {sc01DemoRunId?, caseId, executor=center|studio}  → 장면 2 시작(D00). 장면 1이 인계 전이면 각본으로 인계까지 실행
GET  /sc02/demo-runs/{id} · /history · /history/{seq} · /events(SSE, 채널 sc02:{id})
POST /sc02/demo-runs/{id}/requests/receive {fixtureId}        → 요청 접수 = BPM 시작
POST /sc02/demo-runs/{id}/actions/{nodeId} {answer, expect}   → 사람 대기에 응답. expect = {proposal}·{bundle}
POST /sc02/demo-runs/{id}/negotiation-due {due, reason}        → 외부 협상기한 변경(이력 보존)
POST /sc02/demo-runs/{id}/agent-outputs/{oid}/adopt · /clock {at} · /script/{i} · /reset {executor?}
POST /sc02/demo-runs/{id}/operations/{name} {chaeksas_run_id, chaeksas_node_id, …}  → 시스템 작업 13개(외부 확장 nowview-sc02, 키 검사)

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
POST /sc03/demo-runs/{id}/operations/{name} {chaeksas_run_id, chaeksas_node_id, …}  → 시스템 작업 18개(외부 확장 nowview-sc03, 키 검사)

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
POST /sc04/demo-runs/{id}/operations/{name} {chaeksas_run_id, chaeksas_node_id, …}  → 시스템 작업 18개(외부 확장 nowview-sc04, 키 검사)

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
POST /sc05/demo-runs/{id}/operations/{name} {chaeksas_run_id, chaeksas_node_id, …}  → 시스템 작업 27개(외부 확장 nowview-sc05, 키 검사)

     장면 6(4.20) — 데모 실행 id는 장면 1~5와 같다. 조회 넷은 멱등이고, 쓰기는 적재와 확인 절차(BPM)다
GET  /sc06/process · /script
POST /sc06/demo-runs  {sc01DemoRunId?, executor=center|studio}  → RV61 적재(확인 전). 장면 5가 완료 전이면 각본으로 HANDOFF51까지. 이미 있으면 그대로
GET  /sc06/demo-runs/{id} · /history · /history/{seq} · /events(SSE, 채널 sc06:{id})  → 머리(보고본·산정·FC51·적재 묶음·확인 절차). 없으면 404
POST /sc06/demo-runs/{id}/start                         → 확인 착수(경영관리 담당) = BPM 시작(내장)·SC06 기동(Center)·착수만(Studio)
POST /sc06/demo-runs/{id}/actions/{nodeId} {answer}     → 결재 답(담당만). 확정의 요건 미충족 → 422 REPORT_INVALID (blocking_items)
POST /sc06/demo-runs/{id}/script/{i} · /reset {executor?}   → 각본 D601~D607 · 확인 절차만 확인 전으로(적재는 그대로)
POST /sc06/demo-runs/{id}/operations/{name} {chaeksas_run_id, chaeksas_node_id, …}  → 시스템 작업 6개(외부 확장 nowview-sc06, 키 검사)
GET  /sc06/demo-runs/{id}/reviews/RV61/summary?report_version=          → U601 요약(3과제·합계·완료 판단·Agent)
GET  /sc06/demo-runs/{id}/reviews/RV61/tasks/ACT42/variance?report_version=  → 원인별 건수·실제 긴급비, PO61-1103, AG62
GET  /sc06/demo-runs/{id}/evidence/{evidenceId}?report_version=           → 근거 본문·작성/확인 이력(가상 증빙)
GET  /sc06/demo-runs/{id}/reports/RPT61-v1                → U602 결론·FUP61·PROP61·FUP62·RISK61·확인 다섯 단계·다음 보고
     모든 조회 응답: review_id · report_version · calculation_version · as_of · data_status. X-Demo-Actor가 검토건 참여자가 아니면
     403 ACCESS_DENIED · 다른 보고 버전 409 VERSION_MISMATCH · 없음 404 NOT_FOUND(`detail.error_code`)
```

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
  * 화면: 각 클라이언트의 `create`(장면 6은 `open`)가 202면 `lib/preparation.ts`로 3초마다 읽다가 문서를 받는다 — 시작 카드·
    플레이어는 그대로 결과를 기다리고, 준비 중에는 「앞 업무를 끝까지 진행하는 중 — 고객 생산계획 변경 대응 EV07 · 외주 단가 인상
    검토 D08 (2분 10초)」처럼 보인다(`preparation-note.tsx`, 업무 이름).
* **시스템 작업은 Chaeksas 외부 확장(HTTP 어댑터)으로 부른다** — 정의는 `chaeksas/nowview-sc01.extension.json`.
  내장 BPM의 `_InProcessCalls`와 HTTP가 **같은 함수**(`process.run_operation`)를 써서 출력 모양이 같다 —
  BPMN의 `output` 대응이 두 길 모두에서 맞는다. 내장 BPM을 걷어내기 전까지 두 길이 함께 있다.
  * **확장 id에는 점을 쓸 수 없다**(C13 `^[a-z][a-z0-9-]{1,49}$`). 그래서 서비스 앱 id가 `nowview.sc01` →
    `nowview-sc01`이 됐다(BPMN `app_id`·`service_keys`, `process.APP_ID`). BPM 프로세스 id는 그대로다.
  * **어댑터는 `base_url`의 경로를 버린다**(호스트·포트만 쓴다) — 그래서 작업 `path`에 BFF 경로
    `/api/engine/…`를 통째로 적었다.
  * **정의는 한 벌이고, 로컬 Center가 주소만 덮어쓴다**(R4, ADR-0097). 기본 주소는 운영계
    (`https://www.nowview.work`)이고 `allowed_hosts`가 `[www.nowview.work, localhost, host.docker.internal]`,
    `allow_private_network: true`다. 로컬 Center에서만 CON-07 → `nowview-sc01` → 「서버 주소」를 바꾼다
    (`PUT /api/v1/resources/extensions/nowview-sc01/address`, 관리자) — 실행기가 호스트 프로세스면
    `http://localhost:3000`, **Chaeksas compose의 컨테이너면 `http://host.docker.internal:3000`**이다. 컨테이너
    안의 `localhost`는 컨테이너 자신이라 연결 거부다(실측 — 그래서 0.7.1에서 허용 호스트를 더했다).
    Center는 정의의 허용 호스트 **안에서만** 받는다 — 정의가 상한이다. 해시가 하나라 로컬에서 시험한
    그 판이 운영에 간다. 예전에는 Center에서 바꿀 길이 없어 `.local` 정의를 따로 두고 작업 정의를 두 파일에
    맞춰 적었다 — 지웠다. 사설망 허용을 운영 정의에 켠 득실은 `docs/chaeksas-integration.md` §7의 5.
    `test_extension_definition_matches_the_bpmn_service_calls`가 정의 ↔ BPMN 입력을 잠근다.
  * **어댑터는 `localhost`를 `::1`로 푼다**(실측). `next dev`는 양쪽에 듣지만 웹을
    `-H 127.0.0.1`로 띄우면 연결 거부다. `127.0.0.1`로 덮어쓰면 허용 호스트 밖이라 어댑터가 거절한다.
  * 정의를 고치면 `version`을 올리고 다시 서명한다(같은 버전·다른 내용은 409). 지금 0.7.1 — 기록 작업
    응답에 `error_message`(성공이면 null, 4.5의 기록 거절)가 있고, 기록 작업과 계산은 `answered_by`를 받는다.
    0.7.0에서 접수 Bot 작업 둘(`screen_source`·`record_intake_review`)과 `validate_source.processed_by`가 생겼다.
    0.7.1은 허용 호스트에 `host.docker.internal`만 더했다.
  * **두 BPMN은 `chk:process.extensions`에 `nowview-sc01`(`>=0.7.1,<1`)을 선언한다.** Studio는 이 칸에 적힌 확장만
    패키지 `requires.extensions`로 옮기고, 서버 실행기는 거기 있는 확장만 Center에서 정의(주소)를 받아 온다.
    빠지면 실행기가 `nowview-sc01`을 서비스 앱으로 보고 「서비스 앱 주소를 모른다」로 첫 호출에서 실패한다
    (2026-10-27 로컬 Center 실측). 정의 해시(`definition_hash`)는 고정하지 않는다 — 고정하면 정의를 올릴 때마다
    그림·패키지를 다시 만들어야 한다(Studio가 경고만 한다, ADR-0060). 범위 밖으로 정의를 올리면(1.0) 그림의
    범위도 올린다 — `test_extension_definition_matches_the_bpmn_service_calls`가 잡는다.
    시험이 정의 ↔ **두 BPMN**(SC01·접수 Bot)의 입력을 잠근다.
  * **시스템 작업은 키를 받는다**(0.4.0, N6) — `auth: {type: bearer}` + `requires_keys: [{purpose: run}]`.
    ADR-0091 이후 둘 중 `requires_keys`만 있으면 E3다. BPMN의 키 참조는 `service_keys`의 `nowview`다.
    **키는 NowView가 짓는다**(R6 답) — 운영 키(`NOWVIEW_SYSTEM_KEY`)는 Center의 「외부 앱 키」, 시험용 키
    (`NOWVIEW_SYSTEM_KEY_TEST`)는 「시험용 키」에 넣는다(CON-07 → `nowview-sc01`). Center에는 검증 API가 없다.
    * **어느 키로 왔는지가 실행 위치다** — 시험용 키는 Studio에만 간다. 데모 실행의 선언(`executor`)과 어긋나면
      409(`domain.link_external_run`). 키가 없거나 틀리면 401, 엔진에 키가 하나도 없으면 **503**이다 — 환경
      파일이 빠진 채 올라간 운영계가 조용히 열리면 안 된다. 끄려면 `NOWVIEW_SYSTEM_AUTH=off`를 명시한다.
      두 키가 같아도 503이다(실행 위치를 가를 수 없다). `/health`의 `systemAuth.mode`가 `keys`·`off`·
      `unconfigured`를 드러낸다(값은 싣지 않는다).
    * 로컬은 `engine/.env.local`(gitignore)에 두면 `stack:start engine`이 `--env-file`로 읽는다. 운영은
      `/etc/nowview.env` — `deploy/bootstrap.sh`가 **파일이 이미 있어도 빠진 키만** 지어 더한다.
* **반대 방향 — 엔진이 Center를 부른다**(N3, `engine/app/sc01/center.py`). 키는 **엔진만** 쥔다(BFF·브라우저에
  없다). `CHAEKSAS_CENTER_URL` · `CHAEKSAS_INTEGRATION_KEY`(연동용 — `POST /jobs` 기동, `POST /messages` 정정본,
  `GET /runs/{id}/events` 진행, `DELETE /jobs/{id}` 대체된 작업 거두기, `GET /jobs/{id}` 앞 작업 상태,
  `GET /virtual-workers/{id}` 가상 직원) · `CHAEKSAS_RELAY_KEY`(대리 답용 — 결재 읽기·답, `X-CHK-On-Behalf-Of` =
  행위자 이름) · `CHAEKSAS_SC01_PACKAGE`(기본 `nowview.sc01`) · `CHAEKSAS_INTAKE_WORKER`(접수 가상 직원 id — 있으면
  수신이 `/jobs` 대신 메시지 시작으로 접수 Bot을 깨운다, N5). 키가 둘인 것은
  Chaeksas 권한표 그대로다 — 대리 답용 키는 결재만, 연동용 키는 결재를 못 읽는다. `/health.center`가 설정·폴링
  여부를 드러낸다(값은 싣지 않는다). 시스템 작업 키(N6)와는 방향이 반대인 다른 키다.
  * **메시지는 `schema: 1`이 있어야 한다**(`MessageRequest`) — 없으면 422 `input_invalid`(실측). 작업(`/jobs`)은
    `schema`가 없는 계약이다.
  * **Center 멱등 키에는 초기화 회차가 들어간다**(`_center_key`). 초기화하면 원천 번호가 다시 SRC02라
    `데모실행:원천`만으로는 초기화 전의 작업이 그대로 돌아왔다(N5 실측 — 거절된 작업이 돌아와 새 접수가 안 됐다).
  * **앞 작업이 NowView를 부르기 전에 끝났으면 기다리지 않는다.** 수신 때 `GET /jobs/{id}`로 읽어 거절·만료·취소·
    실행 끝이면 `center_job_ended`를 남기고 새로 보낸다. 읽지 못하면 막는다(모르면 막는 쪽). 실행기가 `not_ready`로
    거절한 접수 작업 때문에 다음 수신이 영영 409였다(N5 실측).
  * **선택 입력을 본문 템플릿에 넣지 않는다.** 어댑터는 `{{input.x}}`의 `x`가 없으면 호출을 실패시킨다 —
    그래서 배정 기록이 생산·자재(`record_dispatch`)와 경영관리(`record_review_request`)로 갈렸다.
    `answered_via`는 대리 답이 아니면 `null`이지만 **변수는 늘 있다**(결재가 `answered_via_as`를 채운다) —
    없는 것과 `null`은 다르다. 값 하나뿐인 템플릿은 JSON 값 그대로 실린다.
  * **모든 작업 본문에 `{{run_id}}`·`{{node_id}}`를 싣는다**(0.3.0, N2). 이름이 `chaeksas_run_id`인 것은
    작업 입력의 `run_id`가 이미 **계산** id라서다. 실행 id가 없는 호출(0.2.0 정의)은 422다 — 묶을 수 없다.

* **BFF는 장면(`sc01`~`sc06`)만 고르고 나머지 경로는 옮겨 적지 않고 그대로 중계한다.** 목록 밖의 장면은 404 —
  엔진의 다른 경로(`/health` 등)를 열지 않는다. 바깥 Chaeksas가 부르는 `/api/engine/sc01/…` 주소는 그대로다. 업무 규칙(권한 403 · 없음 404 · 상태 충돌 409 ·
  입력 422 — API-03)은 전부 엔진에 있다. 같은 검사를 BFF에 또 두면 두 곳이 갈라진다. 넘기는 헤더는
  `X-Demo-Actor`·`Idempotency-Key`·`Authorization`(시스템 작업 키, N6)이다. 키 검사도 엔진이 한다.
* **화면은 규칙을 다시 구현하지 않는다.** 금액·비율은 엔진이 문자열 DECIMAL로 주고 화면은 단위만 바꾼다
  (`lib/sc01/format.ts`). 판정 임계값도 `/rules`로 받아 표시한다.
* **페이지는 정적 프리렌더(`○`)다.** 데이터는 클라이언트에서 받는다 — 서버에서 엔진을 부르면 전부 `ƒ`가
  되고, 엔진이 꺼져 있으면 페이지가 깨진다.
* **엔진이 꺼져 있는 것은 고장이 아니라 상태다.** 클라이언트는 throw하지 않고 `{ ok: false }`를 돌려
  화면이 배너로 말한다.

### 4.4 데이터 시각화 규칙

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
  SC01의 손익 추이는 모두 원 단위라 한 축이고, 물량(대분)은 표로 둔다.
* 모든 차트에는 표 뷰를 둔다(값이 툴팁에만 갇히면 접근성 위반). `ProfitTrendChart`의 "표로 보기"가 그 예다.

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
* **화면은 내장을 고르지 않는다**(2026-10-27). 플레이어의 실행 위치는 Center·Studio뿐이고 API 기본(`POST /demo-runs`의
  `executor`)이 `center`다. 지금 실행이 내장(이전에 만든 것)이면 플레이어는 Center를 고른 것으로 보이고 초기화가 Center로
  바꾼다. 엔진의 내장 경로·`Sc01Process.create()`의 기본값(내장)은 시험이 업무 규칙을 같은 프로세스에서 잠그는 데 쓴다.
* **사람 결정의 업무 효과는 결재 뒤의 「… 기록」 서비스 태스크가 낸다**(`Record_*` → `record_*` 작업,
  `docs/chaeksas-integration.md` N1). 결재를 내장·Studio·Center 어디서 닫았든 같은 길이다 — 예전에는
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
    먼저 결재를 찾으면 대리 답 때 연다(장면 3~6 `_relay`, 5.10).
  * 캔버스는 기록 태스크를 결재 노드에 접어 그린다(`canvasTopology`, 토폴로지의 `recordOf`) — 그대로
    두면 노드가 20 → 27개가 되어 글자가 읽히지 않았다.
  * **기록이 거절되면 같은 결재로 되돌아간다** — 기록 태스크마다 오류 경계(`Bnd_Record_*`, `TASK_FAILED`).
    Center 콘솔 답은 사전 검사를 거치지 않아 예전에는 실행이 실패로 끝났다. 결재 `show`의 `error_message`에는
    **사유가 없다** — HTTP 어댑터가 4xx 본문을 버리고 「…이 409를 돌려줬다」만 남긴다. 사유는 감사 이력
    `answer_rejected`에 있다. 검사가 부수 효과보다 먼저라 거절된 답은 기록·업무를 남기지 않고, 성공한 기록은
    `error_message: null`을 돌려줘 낡은 사유를 비운다. 캔버스는 경계도 결재에 접는다.
* **실행 위치는 데모 실행마다 하나다**(`bpm.executor` = `embedded`|`studio`|`center`, N2). 만들 때·초기화할
  때 고른다(플레이어의 실행 위치 선택, `POST /demo-runs {executor}`). 바깥이면 **내장 엔진은 그 문서에서
  step하지 않는다** — 수신은 원천만 등록하고, 화면 답·각본은 409, 진행은 작업 호출이 알려 준 노드뿐이다.
  예전에는 수신이 내장 BPM을 늘 시작해서 바깥 실행과 한 문서에서 함께 돌았다(내장 쪽이 Approve_DQ에 멈춘
  채 남았다, 2026-10-25 실측).
  * **첫 작업 호출의 `{{run_id}}`가 묶는다**(`bpm.external_run_id`). 같은 데모 실행에 다른 실행이 오면 409,
    내장 데모 실행에 바깥 호출이 와도 409다. 예외는 정정(EX03): 묶인 실행이 있는데 보완 대기가 아닌 때
    정정본이 오면 그 실행을 `bpm_history`(`superseded`)로 옮긴다 — 그 실행의 남은 호출은 409이고 다음
    새 실행이 묶인다. 바깥 실행은 취소할 수 없으니 이것이 내장의 cancel에 해당한다.
  * **Studio인지 Center인지는 선언하고, 키로 검사한다.** 템플릿으로 알 길이 없고(요청 R5 거절), 인증된
    구분은 시험용 키 ↔ 운영 키다(N6, 4.3). 선언을 남긴 것은 화면이 첫 호출 전부터 읽기 전용이어야 해서다
    (`docs/chaeksas-integration.md` §5 N2).
  * 바깥 실행의 업무는 대기 id를 (실행, 결재, 원천·계산)으로 지어 `sync_tasks`에 넘긴다 — 정정 뒤의 새
    실행이 같은 결재에 오면 인수한 업무에 재확인, 끝난 업무에 재검토 업무가 생긴다(내장과 같은 규칙).
  * 캔버스는 바깥 실행이 끝나도 알려 주지 않은 노드를 미실행으로 칠하지 않는다 — 시작·게이트웨이처럼
    작업 호출이 없는 노드는 지나왔어도 모른다. 토큰 위치도 비워 둔다(호출이 끝나면 토큰은 이미 갔다).
  * **보완 대기인지는 바로 앞 원천으로 본다**(`receive_external`). `corrects`는 같은 고객계획의 첫 원천을
    가리켜, 보완 → 정정 → 확인 뒤의 또 다른 정정본을 보완 대기로 오인했다(N3 시험에서 드러남).
* **Center 실행(`center`)은 NowView가 기동하고, 화면 답이 대리 답이며, 진행을 폴링한다**(N3,
  `docs/chaeksas-integration.md` N3 「구현에서 정한 것」).
  * 수신 → `POST /jobs`. 묶인 실행이 보완 대기면 정정본은 `POST /messages`(상관 키 = 데모실행ID — 그래서
    `Wait_Correction`에 `correlation`이 있다. Center는 상관 키 없는 메시지로 기다리는 실행을 찾지 않는다).
    대체·초기화 때는 앞 작업을 거둔다.
  * 화면 답(`act`)·각본 → **사전 검사가 Center보다 먼저**(403·409·422, 입력 보존) → 열린 결재 찾기(최대 30초 —
    실행기가 결재를 올리는 동안) → 대리 답(`if_review_digest`). 업무 효과는 여전히 기록 작업이 낸다.
  * 폴러(`poller.py`, 2초)는 `bpm.state == running`인 center 데모 실행만 읽는다(`store.running_external`).
    C3 → 지나온 노드·토큰 위치·열린 결재·끝. 새 결재는 대리 답용 키로 읽어 검토 자료·폼을 싣고 **업무를 그때
    연다**(늦게 열지 않는다). 대리 답한 결재는 `human_answered`가 오기 전까지 다시 보이지 않는다(`relayed`).
  * **설정이 없으면 조용히 내장으로 돌지 않는다** — 수신은 되고 「기동하지 않았다」 사유가 배너에 남는다
    (첫 폴링에서 걷힌다). 화면 답·각본은 503. 화면은 엔진이 정한 `answerHere`로 폼·각본을 켠다.
  * 시험은 가짜 Center(`test_sc01_center.py`)와 **따로 띄운 빈 Center**(실측)로 했다. 진짜 서버 실행기·배포된
    패키지로는 아직 돌려 보지 않았다(기동·메시지 전달이 남았다).
* **고객계획 접수 가상 직원(N5)** — `engine/processes/sc01-intake.bpmn`, `docs/chaeksas-integration.md` N5.
  * 메시지 시작 `고객계획접수`(본문 `원천목록`만) → 원천마다 `screen_source` → 감독자 **일괄** 결재 → 원천마다
    `record_intake_review` → 승인이면 SC01 위임 반복(함께 돈다), 반려면 끝. **감독자 이름을 그림에 적지 않는다** — 입력
    `감독자`의 값 출처가 `virtual_worker.supervisors`이고 결재가 `assignees: "감독자"`로 받는다(ADR-0099). 출처가 있는 입력은
    부르는 쪽이 보낼 수 없다(422 `input_not_from_caller`) — NowView도, 접수 Bot의 `chk:call.input`도.
  * **일괄로 승인·반려한다** — 폼에 다중 선택이 없고, 결재 뒤에 목록을 다시 만들면 B16이라 Center가 가상 직원에 묶지
    않는다(`intake_not_gated`). 수신 한 번 = 메시지 하나라 일괄 하나가 대개 원천 하나다.
  * **접수 Bot의 작업은 데모 실행을 묶지 않는다**(`_intake_operate`) — 묶으면 위임된 SC01의 첫 호출이 409다.
  * **반려 = SC01을 시작하지 않는다.** 원천 `NEEDS_INFO` + TASK-DQ 보완 요청(`NEEDS_INFO`). 정정본이 승인되면 위임된 SC01의
    원천 확인이 같은 업무를 「보완 후 재배정」으로 잇는다.
  * SC01 입력 `처리자`(`virtual_worker.name`, 필수 아님)를 `validate_source.processed_by`로 받아 실행에 남긴다
    (`processed_by`, 감사 이력 `processed_by_virtual_worker`). 혼자 기동·내장은 `None`이다.
  * **`chaeksas-core` `b421880` 이후**는 담당자 변수가 `None`이면 결재를 만들 때 실행이 `assignees_missing`으로 실패한다
    (예외가 아니라 `run_finished.error_code`). 가상 직원 없이 돌린 접수 Bot은 `감독자`가 필수라 시작조차 하지 않는다.
  * 실측은 임시 Center(:8810) + **진짜 서버 실행기**로 했다(승인 → 인계, 반려 → 보완 요청). 환경변수 키로 붙은 실행기에는
    Center가 앱 키를 봉해 줄 수 없다 — `CHK_SERVER_RUNNER__SVC__NOWVIEW`로 준다(아니면 작업이 `not_ready`로 거절된다).
  * **로컬 Center(docker compose, 실행기 컨테이너) + Studio로 내보낸 패키지로 승인 → 인계까지 갔다**(2026-10-27). 순서: CON-07 정의
    등록·외부 앱 키·시험용 키·주소(`http://host.docker.internal:3000` — 실행기가 컨테이너다) → Studio 내보내기 두 패키지 승인·배포 →
    CON-13 가상 직원 → `engine/.env.local`(`CHAEKSAS_*` 키·`NOWVIEW_SYSTEM_KEY*`·`CHAEKSAS_INTAKE_WORKER`) → `uv sync` +
    `stack:restart engine`. 상세는 `docs/chaeksas-integration.md` N5 「로컬 Center 실측」.
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

**노드 상태는 저장하지 않고 파생한다**(`lib/sc01/process-layout.ts`). 엔진이 주는 것은 지나온 노드
(`visited` — 조작마다 RunLog가 새로 열리므로 문서에 누적한다), 사람 대기(`waiting`), 토큰 위치다.
**실행 중에는 안 간 분기를 미실행으로 칠하지 않는다** — 게이트웨이가 돌기 전에는 갈 수도 있다.
실행이 끝났을 때만 안 간 노드가 미실행이다. 종료 이벤트는 완료 기록을 남기지 않으므로 끝났으면 완료로 본다.

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

### 4.6 SC01 화면

| 경로 | 화면 | 핵심 |
|---|---|---|
| `/` | UI01 경영 현황 | T01·F01·(계산 후) F02 손익, 목표 차이 vs 사건 영향, 모델별 표, 이슈·업무 요약 |
| `/plans` | UI02·03 고객계획 | 수신 목록, CP01 → 수신본 변경 비교, 자동 검증, 원천 확인·비교 계산, (Center) **접수 가상 직원** 카드 — 오늘 접수·승인 대기·기동된 SC01, 일괄 결재 대리 답 |
| `/risk` | UI04 위험 검토 | 계산 선택(정정 시 이전 결과·정정 이력), 상태 칩, 지표 타일(임계값은 `/rules`), 경보 행 비교(15행은 접기), 이슈 이력, **AI 초안 ↔ 담당자 검토 의견**, 배정·Review 요청 |
| `/tasks` | UI05 업무 | 알림, 업무 목록(기한 초과·재확인 요청), 상세·계산별 확인·이력, 인수·재확인 |
| `/handoff` | UI06 인계 | 이슈 근거, 장면 완료 조건, 후속 업무, 정정 이력, 감사 이력, 다음 장면(이야기만) |
| `/process` | BPM 흐름 | BPMN 캔버스, 지금 기다리는 사람 업무, 노드 상세(분기 조건) |

* **변경을 받는 곳은 `Sc01SessionSync` 하나다**(레이아웃 상주). 화면·패널마다 받으면 같은 화면의 두
  패널이 서로 다른 순간을 보고 요청이 패널 수만큼 는다(이전 구현에서 겪었다). SSE가 기본, 서 있지
  않은 동안만 폴링(15초)이다. 조작 응답은 스토어에 **즉시** 반영한다 — SSE를 기다리면 누른 뒤 잠깐
  옛 상태가 보인다.
* **폼 칸은 BPMN의 `chk:approval.fields`에서 온다**(`ActionForm`). 화면이 폼을 따로 정의하면 BPMN과
  갈라진다. `…담당자` 칸은 사용자 마스터에서 고른다 — 이름을 손으로 치면 배정이 거절된다.
* **거절은 상태로 보인다.** 엔진이 403/409/422로 거절하면 사유를 그대로 띄우고 입력은 지우지 않는다.
  버튼 비활성(역할 불일치·필수 칸)은 편의일 뿐 강제가 아니다.
* **지난 시점에서는 조작할 수 없다.** 배너와 "현재로" 버튼을 둔다 — 표시하지 않으면 지금 처리할 수
  있다고 착각한다. 대시보드도 그 시점의 문서로 계산한다(`?seq=`) — 그래야 S0 장면에 F02가 안 보인다.
* **상태를 칩 하나로 뭉치지 않는다**(설계서 1.9) — 자료 확인 · 계산 · 위험 · 업무 · 전망 승인 · 장면.
  "장면 1 인계 완료" · "전망 승인" · "위험 해소"는 서로 다른 말이다(UI06-02).
* **고객 원천 비교(UI02)와 전망 비교(UI04)를 섞지 않는다.** 전자는 CP01 → CP02, 후자는 승인 전망
  F01 → 검토 전망 F02다(UI02-02).
* 화면 머리는 **제목 한 줄 + 상태 한 줄**(가상시각 · 장면 상태 · "시연 데이터")이다. 화면 id·질문·범위는
  해설 모드에서만 보인다(설계서 2.3의 항목은 그대로 있고 표시 시점만 갈랐다). 사용자 id는 화면에 내지 않고 "역할 이름"으로 바꿔 보인다(`useUserName`).
* **AI 초안과 담당자 의견은 다른 카드다**(AG-03). "의견에 가져오기"는 폼을 초안으로 다시 열 뿐이고
  제출은 사람이 한다 — 가져왔다는 사실과 검토 시점의 초안 id가 기록된다.
* **더 오래된 문서로 덮지 않는다**(`setLive`). 배경 초안 완료 SSE가 그 초안을 시작한 조작의 HTTP 응답보다
  먼저 오자 응답이 "생성 중"으로 되돌렸다 — 감사 이력 길이(늘기만 한다)로 순서를 가린다.
* 플레이어에 **시연 사례 선택**(기본 · EX08)과 **가상시계 "다음 영업일 18:30"**(EX07)이 있다.

**단순화 원칙** — "글자가 꽉 차 답답하다"는 지적으로 정리했다. 1280px에서 `main` 글자 수가
경영 현황 1,063 → 489 · 고객계획 909 → 417 · 위험 검토 2,130 → 852 · 인계 **6,019 → 513**자다.

* **화면마다 판단에 쓸 숫자를 먼저 보인다.** 경영 현황은 공장관리손익 한 숫자, 위험 검토는 고른 모델의
  지표 네 개다. "왜 이렇게 보는가"는 해설 모드(4.11)로 옮겼다.
* **지우지 않고 접는다**(`components/shared/disclosure.tsx`, 네이티브 `<details>`). 15행 비교 표·감사
  이력·근거·AI 초안의 사실·질문은 확인할 때만 펼친다. 표는 **바뀐 행·경보 행만 먼저** 보이고 전체는 접는다
  — 정상 14행에 경보 한 행이 묻혔다. 인계 화면의 6천 자는 거의 전부 펼쳐진 감사 이력이었다(최근 5건만 보인다).
* **접지 않는 것**: 검증 오류(고칠 것이다), 미산출 사유, 오독을 막는 문구("감소액은 영업이익 변화가
  아니다", "공장관리손익은 전사 영업이익이 아니다"). 해설이 아니라 숫자를 바르게 읽게 하는 문장이다.
* 섹션 탭(4.10)은 카드 제목에서 만들어지므로 **제목에 버튼·값을 넣지 않는다** — 월 선택 버튼을 제목 밖으로 뺐다.
* 닫힌 `<details>` 안의 글자는 `innerText`에 잡히지 않는다 — 위 수치는 그 기준으로 쟀다.

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
| `engine/tests/test_sc01_api.py` | HTTP 오류 코드(API-03), 대시보드 노출(F02는 계산 후), 지난 시점, 동시 읽기·쓰기 회귀, **TS 토폴로지 사본 = BPMN** |
| `engine/tests/test_sc01_intake.py` | N5 — 접수 Bot 그림(계약 검사·B16 없음·감독자 출처), 출처 입력(`input_required`·`input_not_from_caller`·`assignees_missing`), 가짜 Center 메시지 시작 + 진짜 엔진으로 승인 → 위임 → 인계·반려 → 보완 요청, 거절된 앞 작업·초기화 뒤 멱등 키 — **SQLite·Postgres 양쪽** |
| `engine/tests/test_sc01_center.py` | N3 — 가짜 Center(C3·C5·C6·C12 계약 그대로) + 진짜 Chaeksas 엔진의 실행기 흉내로 각본 끝까지(대리 답), 사전 검사가 Center보다 먼저, Center 거절 사유, 설정 없음 503, 정정 메시지·대체 — **SQLite·Postgres 양쪽** |
| `engine/tests/test_sc02_calc.py` | **통합가상데이터 v0.2 파생 시트와 대조** — 단가안비교 5안 전부, 통합손익 17행 전부, Q3 모델별, 정합성검증 V05·V06·V09·V16·V17, 2027 행 = SC01 시드, 2028 = F01×97%(엑셀 ROUND), X02~X10 경계·기간·누락·중복 |
| `engine/tests/test_sc02_process.py` | Chaeksas 위의 기본 시연 D00~D12(T21~T30), 권한·순서·버전 403/409, 멱등, X01·X02·X04~X07·X09·X10, 기한·알림·시계·초기화, BPMN ↔ 역할표, HTTP, **TS 토폴로지 사본 = BPMN** — **SQLite·Postgres 양쪽** |
| `engine/tests/test_sc02_external.py` | 확장 정의 `nowview-sc02` ↔ BPMN(본문 입력·답한 사람·오류 경계·확장 선언), Studio 흉내(진짜 엔진 + 시험용 키)로 인계까지, 기록 거절 → 같은 결재, 키 ↔ 실행 위치 409, 가짜 Center + 실행기 흉내로 각본 끝까지(대리 답·폴링·도달한 종료), 사전 검사가 Center보다 먼저, 설정 없음 사유·503, 초기화가 작업을 거둠 |
| `engine/tests/test_sc03_calc.py` | **통합가상데이터 v0.3 파생 시트와 대조** — 통합손익(연간·Q3·잔여·12개월), 통합모델손익 a~e, SC03검증 V31·V32·V39·V40, 숫자 원천 = v0.2, 구매 증가 156,812개·18,817,440원, E33 정합 실패, E34 −1,988,000원, 엑셀 시각 KST·초 반올림 |
| `engine/tests/test_sc03_process.py` | Chaeksas 위의 기본 시연 D30~D41 — **끝난 문서 = SC03 시트**(사실확인·쟁점·후보·과제·인계·이벤트 시각), T31 재착수, T33 무응답 차단, T34 담당·기한 필수, 차단 → 재분석, T35 제외 사유 누락 시 전체 미저장, T36 C32·C33 → AT32, T37 3/4 완료 422·타부서 403, E35-M 책임자 NULL 전건 보류, T38 구버전 인수 409, 멱등, E31·E33·E34·E36·E37, 화면 답이 각본 지점을 옮김(병렬 순서 바뀜·조회 건너뜀), BPMN ↔ 역할표, HTTP, **TS 토폴로지 사본 = BPMN** — **SQLite·Postgres 양쪽** |
| `engine/tests/test_sc04_calc.py` | **통합가상데이터 v0.4 파생 시트와 대조** — SC04월효과 36행 전부(보고·판단), SC04월손익 월·연간·Q3·Q4·잔여, SC04비교 대안별 효과·정상 연간, SC04검증, 숫자 시트 = v0.3, T403(2,900 → 124.8M)·E401 감가상각 회피 차단·E402 중복 180만원·E403 승인 범위 121.6M, 입력 한도(전망·원가·긴급 역전·일회성비), E407 위임 조회 |
| `engine/tests/test_sc04_process.py` | Chaeksas 위의 기본 시연 D401~D413 — **끝난 문서 = SC04 시트**(예산과제·조건지시·인계·이벤트 23건 시각·행위자·회의 기록), T401 재착수·재등록, T402 보고본/판단본 분리, 작성자 ≠ 확인자·AT33 제외·Q31·Q32 이력, 다른 부서 403, 보완 요청 새 버전, E401·E402 검증 차단 → 담당 임원 보완, 추천 2~3개·우선순위, 회의 기록 역할, 판단 변경 사유·임원 확인, T403, 대표만 결정·판단본 409, T407 승인서 누락 422 무저장, T406 보류 과제 미생성, T408 2/3 종료 422·타인 403, T409 반려·보완·구버전 409, T411·T412·T413, 시계·초기화·각본, BPMN ↔ 역할표, HTTP, **TS 토폴로지 사본 = BPMN** — **SQLite·Postgres 양쪽** |
| `engine/tests/test_sc04_external.py` | 확장 정의 `nowview-sc04` ↔ BPMN, Studio 흉내로 완료까지(늦게 연 업무·같은 숫자), 기록 거절 → 같은 결재, 키 ↔ 실행 위치 409, 가짜 Center + 실행기 흉내로 각본 끝까지(대리 답·책임자 이름 결재), 사전 검사가 Center보다 먼저, 설정 없음 사유·503, 초기화가 작업을 거둠 |
| `engine/tests/test_sc05_calc.py` | **통합가상데이터 v0.5 파생 시트와 대조** — v0.4 45개 시트 그대로, 기초 손익 = SC05모델손익 60행, FC50 = 장면 4 판단 가정 손익, SC05월효과 18행, SC05월손익 월·연간·마감·전망·Q3, 모델별 효과, 변경 대사(9월 −1.2M · 11~12월 +2.4M · 차이 0), X506 재가산 대사 실패, X508 3,427,786,680, SC05초기지표, 임계값 같으면 정상·NULL 미확인, X509 중복·비용 NULL, 납기·품질 미수집, SC05예산(정산 이중 차감 없음), 고객계획 a~e 월합계 0 |
| `engine/tests/test_sc05_process.py` | Chaeksas 위의 기본 시연 D501~D518 — **끝난 문서 = SC05 시트**(계획·활동·조건품의·예산원장·변경공유·구매표본 60건·운영계획·전망버전·인계·이벤트 시각·사람·Agent 상태), SC05착수조건 GT51~55, T501~T532(X501 착수 422·T506 9/1 전 READY·T502 권한·T503 누락 저장·확정 422·T504 v1 유지·T507/X502 범위 이탈·T509 예산 초과·T512/X504·T513 전결 경계·대행 확인·T516/X509·T518·T521/X506·T522·T523/X505·T524/X507·T525/X508·T526 새 RUN·T527 게시 멱등·T528 시계만으로 승인 없음·T530 Agent 실패·T531), BPMN ↔ 역할표, HTTP, **TS 토폴로지 사본 = BPMN** — **SQLite·Postgres 양쪽** |
| `engine/tests/test_sc05_external.py` | 확장 정의 `nowview-sc05` ↔ BPMN, Studio 흉내로 완료까지(늦게 연 업무·같은 숫자), 기록 거절 → 같은 결재, 키 ↔ 실행 위치 409, 가짜 Center + 실행기 흉내로 각본 끝까지(대리 답·구매 확인 대행 담당자), 사전 검사가 Center보다 먼저, 설정 없음 사유·503, 초기화가 작업을 거둠 |
| `engine/tests/test_sc06_calc.py` | **통합가상데이터 v0.6 파생 시트와 대조** — 기존 71개 시트 = v0.5, BASE61 = 장면 5 FC51 산정본(어긋나면 409), 과제성과·월효과 9행·원인집계·운영지표·분기손익·SC06요약·검증 17항목(계산값), 보고 결론 숫자 ↔ 산정, X61-01 비용 null 산정 보류·확인 소계, X61-02 판단 보류, X61-03 중복 대사 대기, X61-04 Agent 후보, AT61-06/X61-05 재적재 새 산정·확인 재수행 대상·같은 입력 되돌림, X61-06 미산정 ≠ 0, X61-07 원인 비용 + 미달 대사 오류, X61-08 검토 가능, 오류값 422·쉼표 문자열, 연결 누락·승인 전 발주, 고정비 절감 거절, AT61-12·14 |
| `engine/tests/test_sc06_process.py` | 장면 5 완료까지 각본 실행 후 적재(확인 전 DRAFT · 새 실행·도중 실행), 다시 열어도 재적재 없음, **확인 절차 각본 끝의 기록 일곱 건 = SC06보고 시트**(행위자·시각·상태·글·근거)·보고본이 CALC61-v1에 묶임, 담당만 답함 403, 결론 숫자가 다르면 확정 422 REPORT_INVALID → 보완 요청 → 다시 결론·확정, 재확인 요청 → 두 확인 이력·다시 열림, 초기화는 확인만 되돌림, BPMN ↔ 역할표·담당 이름, HTTP 착수·결재·각본·폼 기본값, 조회 계약 4개(문맥 칸·3과제·원인·PO61-1103·AG62·근거·확인 다섯 단계·후속·연간 FC51 그대로), 403 ACCESS_DENIED(오류에 금액·근거 없음)·409 VERSION_MISMATCH·404, **조회가 문서·이력·감사를 바꾸지 않는다**, Studio 장면 5 409, **TS 토폴로지 사본 = BPMN** — **SQLite·Postgres 양쪽** |
| `engine/tests/test_sc06_external.py` | 확장 정의 `nowview-sc06` ↔ BPMN(계약 검사·본문 입력·답한 사람·오류 경계), Studio 흉내로 대표 보고까지(늦게 연 업무·같은 기록), 결론 숫자 틀린 확정 → 기록 거절 → 같은 결재(남은 항목은 감사 이력), 키 ↔ 실행 위치 409, 착수 전 열기 409, 가짜 Center + 실행기 흉내로 각본 끝까지(대리 답·담당 이름 결재), 사전 검사가 Center보다 먼저, 설정 없음 사유·503, 초기화가 작업을 거둠 |
| `engine/tests/test_sc03_external.py` | 확장 정의 `nowview-sc03` ↔ BPMN, Studio 흉내로 완료까지(늦게 연 업무·같은 숫자), 기록 거절 → 같은 결재, 키 ↔ 실행 위치 409, 가짜 Center + 실행기 흉내로 각본 끝까지(대리 답·과제 책임자 이름 결재), 사전 검사가 Center보다 먼저, 설정 없음 사유·503, 초기화가 작업을 거둠, **콘솔 답 거절 → 같은 업무에 잇고 사유가 폼에·반영 중(`inflight`)·화면 답이 각본 지점을 옮김**, 회신기한 형식 사전 검사 |
| `engine/tests/test_events.py` · `test_notify.py` | SSE 허브 구독 해제, 다른 워커로의 전파(Postgres) |
| `engine/tests/test_preparation.py` | 장면 시작 배경 진행 — 오래 걸리면 202 → 준비 상태 → 문서, 빨리 끝나면 201, 겹친 시작은 같은 진행, 앞 장면 진행 표시, 배경 실패의 사유·상태 코드, 모르는 사례 422(아무것도 만들지 않음), 모르는 준비 404 |
| `tests/sc02.test.ts` | 장면 2 배치(기록 태스크 접기·보완 고리), 도달한 종료만 완료, 엔진 각본 → 장면, 기간 표기 |
| `tests/sc05.test.ts` | 장면 5 배치(기록 태스크·오류 경계 접기, 보완·범위 이탈·반려·대표 변경 고리·대사 실패 고리), 실행 중 안 간 갈래 보존, 엔진 각본 → 장면(노드·단계 코드별 화면), 사람 노드 41개 전부 화면, 미확인·비해당 표기, Agent 활동 → 폼 글(빈칸을 0으로 메우지 않는다) |
| `tests/sc06.test.ts` | 장면 6 표기(null ≠ 0 — 미확인·산정 보류·미산정·비해당, 차이 부호), 세 동작 210초, 화면·펼침 → 장면, 확인 절차 7단계 = 엔진 각본 D601~D607, 확인 절차 화면·BPM 흐름은 엔진 각본 위치 |
| `tests/sc04.test.ts` | 장면 4 배치(기록 태스크·오류 경계 접기, 보완 요청·검증 보완·승인 보완·반려 보완 고리), 실행 중 안 간 갈래 보존, 엔진 각본 → 장면(노드·종류·조회 코드별 화면), 모든 사람 노드의 화면, 목표 초과 표기 |
| `tests/sc03.test.ts` | 장면 3 배치(기록 태스크·오류 경계 접기, 재분석·재확인·재배정 고리), 실행 중 안 간 갈래 보존, 엔진 각본 → 장면(종류별 화면), 모든 사람 노드의 화면, 백만원 표기·NULL |
| `tests/sc01.test.ts` | 화면이 엔진 응답을 **잘못 읽는** 종류 — BPMN 배치(되돌아가는 흐름·줄 접기), 노드 상태 파생, 장면 → 이력 seq, 표기(누락·판정 보류·억/만) |

* 엔진 테스트는 SQLite와 Postgres 두 백엔드를 모두 돈다(Postgres 포함 739개). 자리표시자·행 접근·JSON
  타입이 전부 달라 한쪽만 돌리면 나머지가 배포 시점에 터진다. CI는 `REQUIRE_POSTGRES=1`로 skip을
  실패로 바꾼다.
* `tests/fixtures/sc0{1,2,3,4,5,6}-process.json`은 BPMN 토폴로지의 사본이다. BPMN을 고치면 엔진 테스트가
  실패하며 다시 만드는 명령을 알려 준다.
* 렌더링 테스트는 두지 않는다 — 레이아웃·가독성은 브라우저에서 본다(4.10~4.14의 실측들).

### 4.9 실시간 전파 (SSE · Postgres LISTEN/NOTIFY)

**폴링이 아니라 push다.** 상태가 바뀌는 계기가 전부 우리 코드를 지나간다(수신·응답·시계·초기화).
Chaeksas가 몰래 진행하는 일은 없다 — 서비스 태스크도 그 호출 안에서 돈다.

```
조작(워커 A) → notifier.publish("sc01:{id}")
   SQLite  → hub.fanout                        (같은 프로세스)
   Postgres→ SELECT pg_notify('nowview_instance', id) → LISTEN 중인 모든 워커 → hub.fanout
엔진 GET /sc01/demo-runs/{id}/events → BFF 중계 → EventSource → Sc01SessionSync → 스토어
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
### 4.10 섹션 탭 (앵커 네비게이션)

> 4.10~4.14의 실측값은 이전 화면(Cockpit 등 다섯 화면) 기준이다. 규칙은 SC01 화면에도 그대로 쓰인다.

다섯 화면 모두 스크롤이 길어(Cockpit 기준 약 4,000px) 원하는 섹션을 찾기 어렵다.
`components/shared/section-nav.tsx`가 **GNB 바로 아래 한 줄**로 섹션 탭을 놓는다.

**먼저 왼쪽 레일로 만들었다가 걷어냈다.** 쓸모보다 방해가 컸다:

* 화면 위(GNB)와 왼쪽(목차)으로 **시선 축이 둘로 갈렸다.** 찾기 쉬우라고 넣은 것이
  오히려 어디를 봐야 할지 흩뜨렸다.
* 겹쳐 띄우면 카드를 가리므로 **펼칠 때 본문을 밀어내야 했다** — 목차를 여닫을 때마다
  레이아웃이 통째로 움직였다. 1600px 화면에서도 `max-w-7xl` 좌우 여백이 152px뿐이라
  208px짜리 레일이 들어갈 자리가 애초에 없었다.
* 그래서 "언제 자동으로 펼칠 것인가"(폭 경계)라는 문제가 따라붙었는데, 헤더 안에 넣으니
  그 문제 자체가 사라졌다.

남은 규칙:

* **항목은 선언하지 않고 지금 그려진 DOM에서 파생한다.** 화면별 섹션 목록을 손으로 적어
  두면 조건부 섹션(미답 질문, 엔진 패널, 승인 후 나타나는 것들)과 데이터가 들어간 제목
  ("실행 과제 3건")이 곧 어긋난다 — 설계표를 손으로 쓰지 않는 것과 같은 이유다(4.15).
  수집 대상은 `main` 안의 `h1` · `h2` · `[data-slot="card-title"]`이고, 스크롤 목표는
  그 제목을 감싼 카드·섹션이다. 빼려면 `data-index-skip`을 단다.
* **탭 라벨은 제목의 앞머리만 쓴다**(`—` 뒤 부연과 건수를 뗀다). 부연은 카드에 가면 바로
  보이고, 건수를 남기면 값이 바뀔 때마다 탭 폭이 흔들린다.
* **앵커 id는 제목에서 만들되 숫자를 뺀다.** "실행 과제 3건"이 승인으로 4건이 되면 id가
  달라져 링크가 일회용 좌표가 된다.
* **첫 항목은 "맨 위"다.** 화면 이름은 GNB가 이미 말하고 있어 그대로 쓰면 같은 말이 두 번
  나온다.
* **`requestAnimationFrame`을 쓰면 안 된다.** 숨겨진 브라우저 패널에서 콜백이 발화하지
  않아 목차가 영영 비어 있다 — React Flow 함정과 같은 원인이고 실제로 그렇게 만들었다가
  검증에서 드러났다. 수집·스크롤 감지 모두 `setTimeout`이다.
* **덧붙여 드러난 것**: 그 상태에서는 **스크롤·resize 이벤트가 아예 배달되지 않고**
  (실측 0건) `behavior: "smooth"`도 움직이지 않는다. 숨겨진 패널에서 검증하려면
  `dispatchEvent(new Event("scroll"))`로 직접 깨우고 `behavior: "auto"`로 확인해야 한다.
* 앵커 여백은 두 곳에 걸린다 — JS 스크롤은 헤더 높이를 **실측**하고, hash 이동(새로고침·
  링크 붙여넣기)은 `globals.css`의 리터럴(96px)을 쓴다. 헤더 구성을 바꾸면 함께 본다.

**실측**: 다섯 화면 모두 탭이 생성되고(4~6항목), 어느 화면에서도 탭 줄이 넘치지 않는다
(1497px에서 `scrollWidth == clientWidth`). 앵커 이동 후 섹션 상단이 헤더 아래 12px에
놓인다. 정적 프리렌더(`○`)는 다섯 화면 모두 그대로다.

### 4.11 해설 모드

이 화면들은 **방법론을 설명하는 자료**와 **경영자가 쓰는 화면**을 겸한다. 카드 설명
20개 중 8개가 "왜 이렇게 보는가"를 말하는 문장이었고, 그것이 상시로 박혀 있으니 정작
봐야 할 수치가 문장에 묻혔다. 지우지 않고 **모드로 갈랐다** — 시연 때 켜고 평소엔 끈다.

* 스위치는 GNB에 있다(`components/shared/commentary-toggle.tsx`). 상태는
  `lib/store/ui-prefs.ts`이며 **기본은 꺼짐**, localStorage에 남는다.
* **데모·엔진 스토어와 분리했다.** 저 둘은 시나리오별로 갈라진 "어느 안건이 어디까지
  갔는가"이고, 해설을 켰는지는 안건과 무관하다. 섞으면 시나리오를 바꿀 때 표시 설정까지
  흔들릴 여지를 만든다.
* **무엇을 감추고 무엇을 남길지의 기준**: "이 수치가 무엇인가 · 몇 건인가 · 무엇을 누르면
  되는가"는 화면을 쓰는 데 필요하므로 남긴다. "왜 이렇게 보는가 · 이 구분이 왜 중요한가"는
  방법론 설명이므로 `<Commentary>`로 감싼다. 한 문장 안에서 갈리는 경우가 많아
  **문장 단위로 쪼갰다**(예: "1~3Q는 마감 확정, 4Q는 전망이다"는 남기고 "분기 합은 전사
  Target·Forecast와 일치한다"는 감춘다).
* 화면 하단의 Mock 데이터 주석 5개도 해설이다.
* `skipHydration`은 다른 스토어와 같은 이유다(4.2). 서버 HTML은 항상 꺼짐 상태이고
  `StoreHydrator`가 mount 이후 복원한다.

**실측**: Cockpit 기준 문서 높이가 켬 4,139px → 끔 4,017px이다. 줄어드는 양보다
**한 화면에 문장 덩어리가 4개에서 0개로 주는 것**이 목적이다.

### 4.12 데모 플레이어는 자리를 차지한다

떠 있는 카드였을 때 **스크롤 도중 본문 위를 덮었다.** 하단 여백(`pb-48`)은 문서 끝에만
자리를 비우므로 중간을 보고 있을 때는 소용이 없다. 화면 폭 전체를 쓰는 **하단 고정 바**로
바꿨고, 본문은 그 높이만큼 아래를 비운다.

* **높이를 상수로 박지 않는다.** 예전 주석에 "플레이어 최대 높이 170px"이라고 적어 두었고
  그 값은 이미 실제와 달랐다. 접으면 얇아지고, 화면이 좁으면 컨트롤이 한 줄 더 내려간다
  (1497px에서 78.5px, 820px에서 117px — 실측). 플레이어가 **자기를 재서**
  `--demo-player-h`에 넣고 `globals.css`가 그것을 읽는다.
* **ResizeObserver만으로는 부족하다.** 숨겨진 탭에서 발화하지 않아 폭이 바뀌어도 값이 낡은
  채로 남는 것을 실제로 봤다 — `resize`도 함께 듣고, CSS에는 폴백(7rem)을 둔다.
* 내레이션은 두 줄로 제한한다. 바 높이가 들쭉날쭉하면 본문에 비워 둔 자리와 어긋난다.

**넓은 화면에서는 오른쪽 단이다**(xl, 2026-10-27). 맨 위는 화면 폭 전체의 **공통 줄**(로고·역할·해설·테마, 높이 3rem 고정
— `body pt-12`)이고, 업무와 무관한 것만 둔다. 사이드바·오른쪽 플레이어·가운데 머리가 `top-12`에 맞물린다. 공통 줄은 `<header>`가
아니다 — 섹션 탭이 첫 `header`의 **아래 끝**으로 스크롤 여백을 잰다. 그 아래 화면은 세 단이다 — 왼쪽 업무 사이드바(lg, `w-56`, 장면을 「장면 N」이
아니라 수행하는 업무 이름으로 보인다 — `scenario-nav.tsx`의 `WORKS`), 가운데 머리·본문, 오른쪽 플레이어(`w-80`, 높이 전체,
장면 목록을 제목으로 세로로 보인다). 가운데 머리 맨 윗줄은 지금 업무 이름이고, 업무마다 다른
화면 메뉴는 그 아래 줄, 섹션 탭은 또 그 아래다(공통 줄 + 머리 약 166px — `scroll-margin-top` 184px).

* 본문 여백은 `body:has([data-demo-player="expanded"])`가 xl에서 오른쪽 20rem·아래 1rem으로 바꾼다. 접으면 오른쪽 아래 알약이다.
* 플레이어 여섯 벌이 같은 클래스를 쓴다 — 하나를 고치면 여섯을 같이 고친다. 오른쪽 단에서 컨트롤 묶음은 `sm:shrink-0`
  때문에 한 줄 폭(777px)으로 잘렸다 — `xl:w-full xl:shrink`로 접힌다.
* **화면 글에 「장면 N」을 쓰지 않는다**(2026-10-27) — 업무 이름(`WORKS`의 label)으로 쓴다. 플레이어 안의 시연 순서는
  「단계」다. 「장면」·SC0N은 설계 문서·코드·주석의 용어로만 남는다. 바꾸기 전에 저장된 데모 실행의 문서 글(인계 메모 등)은
  그대로라 새 데모 실행부터 바뀐 글이 보인다.
* lg~xl(사이드바만 있을 때) 하단 바는 `lg:left-56`로 사이드바를 덮지 않는다. lg 미만에서는 사이드바 대신 머리의 업무 선택이다.

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
`--brand-soft` · `--ink`(틀 남색) · `--demo-surface`(플레이어 면)이고 `--primary`·`--ring`이 `--brand`를 따른다.

* **색상(hue)을 차트와 비켜 잡았다** — 계열색 파랑(255°)·주황, 상태색 초록·노랑·주황·빨강과 겹치지 않는 남보라다. 틀의
  강조가 차트에서 계열·상태로 읽히면 4.4의 역할 분리가 깨진다. `--brand`를 차트에 쓰지 않는다. `--card`는 그대로다.
* 공통 줄·업무 사이드바는 `.chrome-ink`다 — 그 안의 토큰(배경·글자·muted·border)을 어두운 판으로 바꾼다. **`.dark`를
  붙이지 않는다** — 테마 버튼 아이콘이 `dark:` 변형으로 갈려 라이트에서도 해 아이콘이 보인다. `color-scheme: dark`라
  역할 선택의 펼침 목록도 어둡다.
* 강조를 쓰는 곳: 활성 업무(채움), 화면 메뉴·섹션 탭의 밑줄, 기본 버튼(자동 재생·장면 시작), 플레이어의 지금 장면·단계 칩·윗선.

**서드파티 CSS는 우리 뒤에 주입된다.** `@xyflow/react/dist/style.css`는 컴포넌트에서
import되므로 `globals.css`보다 나중에 온다 — 같은 특이도로 덮어쓰려 하면 **진다.**
클래스를 두 번 적어(`.react-flow__controls-button.react-flow__controls-button`)
특이도를 올린다.

* **다크에서 React Flow 확대·축소 아이콘이 보이지 않았다.** 버튼 배경은 라이브러리가
  `#fefefe`로 박아 두는데 아이콘은 `currentColor`를 타고 우리 foreground(`#fafafa`)를
  따라간다 — **흰 버튼에 흰 아이콘**이다. 색이 빠진 게 아니라 대비가 사라진 것이라
  콘솔 경고가 없고, 요소는 DOM에 멀쩡히 있어서 찾기 어렵다. 실측 대비 1.0 → **17.2:1**.
* `Controls`를 쓰는 화면을 추가하면 같은 문제가 이미 해결되어 있다 — 토큰으로 칠하므로
  테마 전환도 따라온다.

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

데모를 폰으로 보다 세 가지가 드러났다. 셋 다 **좁을 때만** 나고 데스크톱에서는 보이지 않는다.

**`flex-1`은 `flex-wrap`에서 줄바꿈을 유발하지 못한다.** `flex: 1 1 0%`라 기여 폭이 0이고,
형제가 자리를 다 가져가도 "안 들어간다"가 성립하지 않아 혼자 눌린다. 엔진 패널의 설명
문단이 375px에서 **폭 22px · 높이 512px**로 한 글자씩 세로로 쌓였다 — 카드가 1,175px로
부풀어 그 아래 내용이 사실상 닿지 않았다.

* 버튼과 한 줄을 나눠 쓰는 문단은 **`basis-full sm:flex-1 sm:basis-0`**로 좁을 때 한 줄을
  통째로 쓰게 한다. 아이콘+문단+버튼처럼 아이콘을 떼면 어색한 줄은 대신 **`min-w-[12rem]`**을
  줘서 버튼이 아래로 내려가게 한다.
* **`min-w-0`과 같이 쓸 수 없다** — 최소 폭을 주려면 그것을 빼야 한다.
* 이 형태를 찾는 법: `main` 안에서 **폭 60px 미만인데 높이 120px 넘고 자식이 없는** 요소를
  훑으면 나온다. 눈으로 찾지 말 것.

**고정 UI가 화면의 3분의 1을 먹었다.** 360×640에서 sticky 헤더 84px + 데모 바 137px =
**35%**다. 본문에 남는 434px보다 React Flow 캔버스(360px)가 커서 "캔버스 하나 = 한 화면"이
됐다. 줄인 것:

| | 전 | 후 |
|---|---|---|
| 데모 바 | 137px | 123px (스크러버 감춤 · 내레이션 1줄) |
| 캔버스 | 360px | 240px (`sm:h-[360px]`) |
| 첫 카드 (트래커) | 1,175px | 641px |

* **스크러버는 좁을 때 감춘다.** 장면 8개를 가로로 나눈 칸이라 손가락으로 짚기 어렵고
  세로를 28px 먹는다. 이동은 이전/다음으로 한다.
* **`shrink-0`이 잘라 먹는다.** 플레이어 컨트롤 묶음이 360px 화면에서 **478px**로 삐져나가
  시나리오 탭과 버튼 일부가 보이지 않았다. 페이지 가로 스크롤은 안 생기므로(`scrollWidth`가
  같다) **넘침 검사로는 안 잡힌다** — 자식 폭을 직접 재야 한다.
* **`line-clamp`는 반응형으로 건다**(`line-clamp-1 sm:line-clamp-2`). 바 높이는 본문이
  비워 둔 자리(`--demo-player-h`)와 맞물리므로 값 자체는 여전히 재서 넣는다(4.12).

**부차적 컨트롤은 좁을 때 라벨을 버린다.** 해설 토글이 GNB에서 고정 폭을 차지해 정작
화면 이동에 쓰는 메뉴를 좁은 스크롤 영역으로 밀어냈다. 아이콘만 남기고(59px → 30px)
헤더 간격도 좁혔더니(`gap-6` → `gap-3 sm:gap-6`) GNB가 134px → **170px**가 됐다.
**`sr-only` 라벨을 함께 둔다** — `title`만으로는 접근성 이름이 약하다.

**검증은 숨겨진 패널에서 하기 어렵다.** 뷰포트를 바꿔도 `resize`가 배달되지 않아
`--demo-player-h` 같은 실측값이 낡은 채 남는다(4.10·4.12와 같은 원인) — 실제로 78.5px로
남아 있어 버그로 오진할 뻔했다. `dispatchEvent(new Event("resize"))`로 깨운 뒤 재야 하고,
"native size"로 되돌리면 0×0이 되므로 **폭·높이를 명시**한다.

**데스크톱은 건드리지 않았다.** 전부 `sm:` 분기이고, 1280×800에서 해설 라벨·스크러버·
플레이어 79px·캔버스 360px·문단 752px가 이전과 같은 것을 확인했다.

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

### 4.16 SC02 — 단가 인상 검토와 수익성 영향의 경영검토 연결 (장면 2)

공급사 SUP-01이 공통부품 P-COM01(a·b모델 각 1개)의 단가를 2,000 → 2,200원으로 올려 달라고 한다. 구매담당이
접수·팀장 보고·요청안 분석·1차 협상(2,120원)·재분석·기안을 하고, 팀장 → 임원 → (12개월 증가 ≥ 1천만원이면)
대표가 승인한다. 승인 조건으로 원가 버전 C02-APP01을 등록하고, 장면 1 물량 감소(ISSUE-B07)와 장면 2 원가
상승(ISSUE-COST01)을 상위 검토건 MR-2706-01에 **각각** 걸어 경영관리에 넘긴다. **끝나도 위험은 열려 있고 F02는
검토 중이다**(SCOPE-01) — 「장면 2 인계 완료, 장면 3 손익 검토 대기」.

```
engine/processes/sc02.bpmn ──▶ Chaeksas Engine ── chk:serviceCall nowview-sc02 ──▶ app/sc02/process.py
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
  * **외부 확장 `nowview-sc02` 0.1.0**(`chaeksas/nowview-sc02.extension.json`) — 작업 13개, 모두
    `POST /api/engine/sc02/demo-runs/{id}/operations/{이름}`. 본문은 그림의 서비스 입력 전부 + `{{run_id}}`·`{{node_id}}`.
    키·주소 규칙은 `nowview-sc01`과 같다(같은 운영·시험용 키, 기본 운영계, 로컬 Center만 주소 덮어쓰기).
    `test_sc02_external.py`가 정의 ↔ BPMN을 잠근다(본문의 `{{input.x}}`가 그림 입력에 없으면 어댑터가 실행 중에 멈춘다).
  * **BPMN**: `chk:process.extensions`에 `nowview-sc02`(`>=0.1.0,<1`), 결재마다 `answered_by_as`·`answered_via_as`, 기록 작업
    10개마다 오류 경계(`Bnd_Record_*` → 같은 결재), 기록 출력 `error_message`. 팀장 결재 기록은 `condition`·`due_at`을 빈 글
    리터럴로 싣는다 — 본문 템플릿의 입력은 늘 있어야 한다(4.3).
  * **기록 작업이 사전 검사를 다시 한다**(`process._recheck` → `domain.check_answer`). Studio 대화상자·Center 콘솔 답은 NowView
    사전 검사를 거치지 않는다 — 처음에는 검사 오류가 남은 요청을 「확인완료」하면 부수 효과 단계에서 422로 터졌다(시험이 잡았다).
    거절은 감사 이력 `answer_rejected`에 남고 반쯤 적힌 효과는 버린다.
  * **실행 잇기·키**: SC01 `link_external_run`·`note_external_progress`를 그대로 쓴다 — 첫 호출이 묶고, 키가 실행 위치를 말한다
    (어긋나면 409). Studio는 기록 때 업무를 늦게 열고(`opened_late`), 끝은 작업 호출로만 안다 — 종료로 가는 결정(반려·추가
    협상지시·미합의·검토 종결·보완 요청·인수)이 기록되면 끝으로 본다(`domain.TERMINAL`). **Center는 그렇게 끝내지 않는다** —
    끝냈다고 적으면 폴링이 멈춰 도달한 종료를 읽지 못했다(시험이 잡았다). Center는 `run_finished`로 안다.
  * **Center**: 요청 접수 → `POST /jobs`(패키지 `CHAEKSAS_SC02_PACKAGE`, 기본 `nowview.sc02`, 멱등 키에 초기화 회차). 화면 답 =
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
engine/processes/sc03.bpmn ──▶ Studio·Center(또는 시험용 내장) ── 서비스 태스크 nowview-sc03 ──▶ app/sc03/process.run_operation
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
  Center면 SC03 패키지를 기동(`POST /jobs`, `CHAEKSAS_SC03_PACKAGE` 기본 `nowview.sc03`), Studio면 착수만 적는다. 그림의
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
engine/processes/sc04.bpmn ──▶ Studio·Center(또는 시험용 내장) ── 서비스 태스크 nowview-sc04 ──▶ app/sc04/process.run_operation
                                                                                                │ domain.check → domain.apply
                                                                                                ▼   (calc의 기준은 sc03 period 재사용)
                       sc04_demo_run(id = 장면 1~3 데모 실행 id) · sc04_history → notifier("sc04:{id}") → SSE
```

**숫자** — 대응 전 부족 177,303,320 · 보고 효과 137,200,000(REP41-v1) · 판단 효과 127,800,000(DEC41-v2, ALT42 8월 9,400,000 제외 ·
8월 준비비 2,000,000은 그대로) · 남는 연간 부족 49,503,320 · 조건부 제외 부족 85,103,320 · 정상 연간 357,600,000(참고, 합산 금지) ·
Q4 −34,278,880(목표 초과) · 총괄 예산 18,000,000(8·6·4, 예정 7,000,000·여력 11,000,000). 월 반복효과는 ALT41 3,000 × (15,000 −
8,000 − 1,000) · ALT42 (12 − 4) × 1,200,000 − 200,000 · ALT43 6,000 × (5,000 − 4,500 − 100)이다.

**경계·범위에서 정한 것**

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
engine/processes/sc05.bpmn ──▶ Studio·Center(또는 시험용 내장) ── 서비스 태스크 nowview-sc05 ──▶ app/sc05/process.run_operation
                                                                                                │ domain.check → domain.apply
                                                                                                ▼   (calc 기초 손익은 sc02 월별 계산)
                       sc05_demo_run(id = 장면 1~4 데모 실행 id) · sc05_history → notifier("sc05:{id}") → SSE
```

**숫자** — 과제 전 연간 3,299,986,680 · 과제 순효과 129,000,000(마감 1~9월 37,200,000 + 잔여 10~12월 91,800,000; ACT41 86.0M ·
ACT42 36.8M · ACT43 6.2M) · 새 공식 전망 3,428,986,680 · Target 3,477,290,000 · 남는 부족 48,303,320 · 종전 FC50 3,427,786,680 대비
+1,200,000(9월 −1.2M · 11~12월 +2.4M) · 일회성 집행 7백만·사용가능 11백만. **129백만원 전체를 실현효과로 보이지 않는다**(마감 37.2M도
회피비용 비교모형이다).

**경계·범위에서 정한 것**

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
engine/processes/sc06.bpmn ──▶ Studio·Center(또는 시험용 내장) ── nowview-sc06 ──▶ app/sc06/process.run_operation
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
  * 외부 확장 `nowview-sc06` 0.1.0 — 작업 6개(`open_review` + 기록 5: `confirm_owner`(두 담당 임원이 `record_id` 리터럴로 같은 작업)·
    `review_finance`·`draft_conclusion`·`finalize_report`·`report_ceo`). 키·주소 규칙은 장면 1~5와 같다. 정의는 그림에서 생성했고(생성기는
    남기지 않았다) `test_sc06_external.py`가 정의 ↔ 그림을 잠근다. Center 패키지 id는 `CHAEKSAS_SC06_PACKAGE`(기본 `nowview.sc06`).
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

---

## 5. 다음 단계와 선행 조건

CI(5.1), Chaeksas 엔진(5.2), SC01 화면(5.3), Agent와 예외 경로(5.5), 장면 2(5.6), 장면 3(5.7), 장면 4(5.8), 장면 5(5.9), 장면 6(5.10)은 끝났다(장면 1~6 모두
로컬 Center에 올려 진짜 서버 실행기로 돌렸다). 운영계(5.4)는 아직 이전 구현이 떠 있다.

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

### 5.4 운영계 배포 — 완료 (이전 구현 기준)

> **운영계(`www.nowview.work`)는 아직 이전 구현(가동률 시나리오 · LangGraph)이다.** SC01 브랜치를 main에
> 합친 뒤 `scripts/deploy.sh`로 올린다. 서버에 git이 있어 `uv sync --locked`가 Chaeksas를 받는다.
> 엔진 테이블은 기동 시 만들어진다. 이전 LangGraph 테이블(`checkpoint*`, `instance_spec`)은 남지만
> 쓰이지 않는다 — 지울지는 배포 때 정한다.


**https://www.nowview.work** — `hetzner-server`(46.62.215.120)에 systemd 서비스 2개로
상주하고, cloudflared 터널이 외부에 내보낸다. **Chaeksa가 같은 서버에서 3000·8000을 쓰고
있어 포트를 비켜 잡았다** — 웹 3100, 엔진 8077, **둘 다 127.0.0.1에만** 바인딩한다.

```bash
scripts/deploy.sh --bootstrap   # 최초 1회 (Postgres 역할·DB·/etc/nowview.env까지)
scripts/deploy.sh               # 이후 배포 (rsync → uv sync → npm ci·build → 재시작)
scripts/deploy.sh --status
scripts/deploy.sh --logs engine 80
```

* **서버에 docker가 없다.** `docker compose`는 로컬 검증용으로 남고, 운영은 systemd로
  돈다 — Chaeksa가 이미 그 방식이라 서버에 새 런타임을 들이지 않았다.
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

  실제로 열려 있는 것은 읽기만이 아니다(SC01 기준). **`X-Demo-Actor` 헤더로 아무 역할이나 될 수
  있고**, 데모 실행을 횟수 제한 없이 만들 수 있으며(행이 쌓인다), id를 알면 남의 실행을 초기화할 수
  있다(id는 무작위 8자리 hex). Agent를 `llm` 모드로 켜면 비용 위험이 다시 생긴다 — 계산마다 모델을 한 번
  (실패 시 두 번) 부르고, 영업담당·팀장 역할이면 "다시 생성"으로 횟수 제한 없이 부를 수 있다. 운영 기본은 `mock`이다.

  **시스템 작업(바깥 Chaeksas가 부르는 길)은 이제 키를 받는다**(N6, 4.3). 아래 경고와 다른 경우다 — 키는
  BFF↔엔진 사이의 것이 아니라 **바깥 호출자가 싣고 BFF가 그대로 넘기는 것**이라 공격 경로 끝에서 검사된다.
  화면이 쓰는 업무 조작(행위자 헤더)은 여전히 열려 있다.

  **막을 자리를 짚을 때 층을 틀리기 쉽다.** 엔진(8077)은 **이미 127.0.0.1 전용이고**
  외부에서 연결 거부다 — 그래서 *엔진에* API key를 걸어도 BFF↔엔진 사이만 인증되고
  공격 경로는 그대로다. 공격자는 엔진을 직접 부르지 않는다. **방화벽도 안 된다**:
  요청이 전부 터널에서 오므로 남의 브라우저와 볼 사람의 브라우저가 출처로 구별되지
  않는다. 막을 자리는 **BFF 앞**(Cloudflare Access · WAF 레이트 리밋)이거나 **BFF 안**
  (라우트 핸들러 검사)이다.

  비용·남용만 겨냥하려면 링크 공유를 잃지 않는 쪽이 싸다 — `POST /api/engine/sc01/demo-runs`에
  WAF 레이트 리밋(무료 플랜 규칙 1개).
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
  * **장면 2 시작이 접수 일괄에서 멈췄다** — 각본이 장면 1을 인계까지 끝낼 때 감독자 승인을 넘지 못했다. 이제 각본이 일괄을
    **감독자(가상 직원 등록의 이름)로 대리 승인**한다(`Sc01Process.approve_intake_for_script`, 장면 2 시작에서만). 장면 1
    플레이어는 그대로 「접수 가상 직원」 카드에서 사람이 승인한다.
  * **대리 답 대기 10초가 모자랐다** — 작업 배정 약 8초, 답을 실행기가 집어 다음 결재를 올리기까지 약 10초다. `CENTER_WAIT_S`를
    30초로 올렸다(찾으면 바로 돌아온다). 실행 기록(`/runs/{id}/events`)도 첫 호출 직후엔 404라 각본은 그것을 넘긴다(폴러가 따라잡는다).
  * **앞 결재 뒤의 계산을 실행기가 아직 안 불렀는데 다음 답의 사전 검사가 돌았다**(재분석 확인 직후 상신 → 「재분석이 최신이
    아니다」 409). 사전 검사가 409면 그 결재가 열릴 때까지 기다렸다가 **다시 검사한다** — 여전히 Center에 답하기 전이다.
* **Agent LLM 러너** — 지금은 mock·fail뿐이다. SC02 계약(summary·findings·questions·draft_text)에 맞춘 프롬프트와 실호출 시험이 필요하다.
* **2차 이후 협상·재기안·재승인**(S14 뒤) — 설계상 후속 범위다.
* **장면 1 F02가 정정된 뒤의 장면 2**(ERR-24) — 지금은 시작을 409로 막는다. 정정 물량으로 새 분석·재검토를 요청하는 길은 없다.
* **요청 정정 버전**(U21-03) — 같은 문서 키·다른 내용은 BPM 시작 전에만 받는다.
* 화면 검수는 BASE·X01만 했다. 나머지 X 사례는 엔진 테스트로 잠갔고 플레이어의 사례 선택으로 돌릴 수 있다.

### 5.7 장면 3(SC03) — 완료 (Studio·Center 실행)

2026-10-27. 설계·데이터는 4.17. 엔진 시험(SQLite·Postgres)으로 기본 시연 D30 → D41과 E31~E37을 잠갔고, 숫자는 통합가상데이터
v0.3의 파생 시트, 끝난 문서는 SC03 시트와 같다. 바깥 실행은 Studio 흉내(진짜 엔진 + 시험용 키)·가짜 Center + 실행기 흉내로
완료까지 갔다. 브라우저에서는 **내장 실행(시험용, API로 만든 데모 실행)**으로 U31~U37·BPM 화면, 플레이어 진행, 3/4 완료 거절(422
남은 항목), 화면 폼 인수(4/4) → 완료, 375px를 확인했다.

**남은 것**

* **Center에 올릴 것**(사람이 한다): ① CON-07에 `chaeksas/nowview-sc03.extension.json` 0.1.0 서명·등록, 외부 앱 키·시험용 키
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
* **E34 재확인 흐름** — 새 전망 버전은 기록·비교까지다. 임원 재확인 뒤 새 버전으로 회의 자료를 바꾸는 길은 없다(확정본으로 간다).
* **Agent LLM 러너** — mock·fail뿐이다(장면 2와 같다).
* 화면 검수는 내장 BASE만 했다. E 사례는 엔진 시험으로 잠갔고 플레이어의 사례 선택으로 돌릴 수 있다.
* 장면 4는 5.8 — HANDOFF31에서 시작한다.

### 5.8 장면 4(SC04) — 완료 (Studio·Center 실행)

2026-10-27. 설계·데이터는 4.18. 엔진 시험(SQLite·Postgres)으로 기본 시연 D401 → D413과 E401~E405·E408, T401~T416을 잠갔고, 숫자는
통합가상데이터 v0.4의 파생 시트(월효과 36행·월손익·비교·검증), 끝난 문서는 SC04 시트(예산과제·조건지시·회의·이벤트 23건·인계)와 같다.
바깥 실행은 Studio 흉내(진짜 엔진 + 시험용 키)·가짜 Center + 실행기 흉내로 완료까지 갔다. 브라우저에서는 **내장 실행(시험용, API로 만든
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
* **승인 이후 수정**(구현명세 11장 — 새 판단·승인 버전, 대표 재확인, 영향받은 인수 STALE) — 반려 보완(승인 범위 안의 명확화)만 있다.
* **Agent LLM 러너** — mock·fail뿐이다(장면 2·3과 같다).
* 화면 검수는 내장 BASE만 했다. E 사례는 엔진 시험으로 잠갔고 플레이어의 사례 선택으로 돌릴 수 있다.
* **장면 5(상세 실행계획)** — 설계표·데이터가 나오면 시작한다. HANDOFF41이 출발점이다(상세 계획은 비어 있는 정상 상태 `PLAN_PENDING`).

### 5.9 장면 5(SC05) — 완료 (Studio·Center 실행)

2026-10-27. 설계·데이터는 4.19. 엔진 시험(SQLite·Postgres)으로 기본 시연 D501 → D518과 X501~X509, T501~T532를 잠갔고, 숫자는 통합가상데이터
v0.5의 파생 시트(모델손익 60행·월효과 18행·월손익·초기지표·예산·변경대사), 끝난 문서는 SC05 시트(계획·활동·조건품의·예산원장·변경공유·
구매표본 60건·운영계획·전망버전·인계·이벤트 시각과 사람·Agent 상태)와 같다. 바깥 실행은 Studio 흉내(진짜 엔진 + 시험용 키)·가짜 Center +
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
* **화면 직접 진행(Center)에서 드러난 넷을 고쳤다**(2026-10-28, 버튼·역할 전환만으로 착수 → 변경 접수):
  * **화면 답이 각본 지점을 옮기지 않았다** — 손으로 착수·계획 확정을 해도 D500에 머물렀고 플레이어 「다음」이 「단계를 건너뛸 수
    없다 — 다음은 0번이다」였다(그런데 표시는 단계 4/62로 넘어갔다). 장면 3의 `_follow_script`(`ahead`·`pending`)를 들였다 — 사이의
    Agent·조회는 건너뛰고 병렬 조건 결재는 순서가 바뀌어도 된다. 플레이어는 `scriptIndex`를 따라가고, 실패하면 엔진이 간 지점으로 되돌린다.
  * **대리 답 뒤 약 10초 화면이 비었다** — 장면 3처럼 `bpm.center.inflight`로 「Center 반영 중」을 보인다.
  * **시계 조작이 「다음 영업일 18:30」뿐이었다** — 7/13 → 8/19에 27번 눌렀고, 8/20 아침에 들어오는 근거(DOC51·52)를 쓰려면 기한(18:00)
    뒤인 18:30까지 가야 해 지연 알림 네 건이 생겼다. 플레이어에 **「다음 단계 시각」**(다음 각본 단계의 `at`으로 시계만 옮긴다)을 더했다.
  * **아직 오지 않은 원문이 접수됐다** — 9/2에 9/10 원문 CP52가 CH52가 됐다. 대표 원문도 접수 시각에 도착하는 배경 원천(`original`)이고
    `check_receive`가 도착 전이면 409다.
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
* **새 보고 버전(RPT61-v2) 흐름** — 재적재가 새 산정과 재확인 대상을 알리는 데까지다. 새 보고본 작성·확인은 없다.
* **Agent LLM 러너** — AG61~63은 고정 기록 재현뿐이다(장면 2~5와 같다).
* 운영계 배포는 5.4와 같이 남았다.

