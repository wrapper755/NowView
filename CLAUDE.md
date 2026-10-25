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
uv run pytest                                      # 177개 (SQLite만, LLM 제외)
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
  `TEST_DATABASE_URL=postgresql://nowview:nowview@localhost:55432/nowview uv run pytest` (217개)

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
* **지금 구현된 것**: 대표 시나리오 1의 **장면 1(SC01)** — 고객 생산계획 변경을 감지해 현업 통제와 Management Review로 인계하기까지. 업무 흐름은 **Chaeksas BPM**이 BPMN을 해석해 돌린다(4.5).
* **Core Philosophy**:
  * **Target vs. Forecast vs. Plan**: 목표(Target)는 임의로 변경하지 않으며, 실행 결과와 최신 가정을 반영한 전망(Forecast)과 실행계획(Plan)을 Rolling 방식으로 갱신하고 잔여 Gap을 명시적으로 관리한다.
  * **Human-in-the-Loop**: AI Agent는 데이터 수집, 이상 징후 감지, 원인 분석, 대안 초안을 지원하고, 최종 판단과 승인은 사람이 책임진다.
  * **Deterministic BPM + Rule Calculation + Probabilistic AI**: 업무 흐름은 결정론적 BPM(Chaeksas)이, 지표·위험 판정은 규칙 계산이, 해석·설명은 Agent가 맡는다. **숫자는 규칙 계산만 만든다**(구현명세 AG-01).

---

## 2. Business Context & Virtual Company Spec

기준 문서(리포 밖, 사용자 Downloads/INNONOW): 기획안 v0.5 · SC01 설계서 v0.5 · SC01 구현명세 v0.2 ·
통합 가상 데이터 설계 v0.2(→ `engine/seed/`) · 설계 Template v0.5. 기획안 v0.1은 v0.5의 1~4장과 같다.
**문서의 요구사항 ID(UI01-xx, CALC-xx, WF-xx, AT-xx, EX-xx, D-xx)를 코드 주석·테스트 이름에 그대로 쓴다.**

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

**SC01은 1·2단계와 3단계 "연결"까지다.** 장면 2~7(단가 인상 · 통합 손익 · 대안 결정 · 실행·Rolling ·
효과 검증 · Evolution)은 기획안 6장에 이야기만 있고 설계표·데이터가 없다 — 화면은 수치를 지어내지
않고 "다음 장면"으로만 보인다. 기획안의 100억 → 85억 → 97억은 **설명용 예시**이고 데이터의 손익
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
├── chaeksas/                     # 바깥 Chaeksas에 올릴 외부 확장 정의 (nowview-sc01 한 벌 — 로컬은 Center가 주소를 덮어쓴다, 4.3)
├── docs/                         # chaeksas-integration.md(바깥 Chaeksas 연계 설계 — 제안) · handoff/(Chaeksas 요청서)
├── app/
│   ├── layout.tsx                # GNB · 역할 전환 · 테마 · 세션 동기화 · 데모 플레이어
│   ├── globals.css               # 테마 토큰 + --viz-* 시각화 팔레트
│   ├── page.tsx                  # UI01 A제품 경영 현황
│   ├── plans/page.tsx            # UI02·UI03 고객 생산계획 수신 · 원천 확인
│   ├── risk/page.tsx             # UI04 공급전망 변동 · 위험 검토
│   ├── tasks/page.tsx            # UI05 검토·승인 업무
│   ├── handoff/page.tsx          # UI06 경영이슈 · 인계 현황
│   ├── process/page.tsx          # BPM 흐름 (BPMN 캔버스)
│   └── api/engine/sc01/[...path]/route.ts   # 엔진 프록시(BFF) — 유일한 라우트
├── components/
│   ├── ui/                       # Shadcn 원시 컴포넌트
│   ├── shared/                   # section-nav(섹션 탭), commentary(해설), disclosure(접기)
│   ├── sc01/                     # SC01 화면들 + 공용 조각(bits, action-form, actor-switcher,
│   │                             #   session-sync, demo-player, use-dashboard, profit-trend-chart)
│   ├── flow/sc01-canvas.tsx      # React Flow 전용
│   ├── theme-provider.tsx
│   └── theme-toggle.tsx
├── lib/
│   ├── utils.ts                  # cn()
│   ├── sc01/                     # types · client · format · scenes(데모 장면) · process-layout
│   └── store/                    # sc01(데모 실행 사본·행위자·플레이어), ui-prefs(해설)
├── tests/                        # Vitest — sc01.test.ts, fixtures/sc01-process.json
└── engine/                       # Python BPM 엔진 (별도 프로세스)
    ├── pyproject.toml            # uv · chaeksas-core(git 커밋 고정)
    ├── processes/sc01.bpmn       # SC01 업무 흐름 — 유일한 원천
    ├── seed/SYN-SC01-v0.2.xlsx   # 통합 가상 데이터 설계 — 원천 시트=시드, 파생 시트=기대값
    ├── app/
    │   ├── main.py               # FastAPI — health + /sc01 라우터
    │   ├── store.py              # 백엔드 선택 (SQLite 파일 / Postgres 풀)
    │   ├── events.py · notify.py # SSE 허브 · 프로세스 경계 전파
    │   └── sc01/                 # seed · calc · domain · process · store · demo · view · api · auth
    │                             #   · center(Center 클라이언트) · poller(진행 폴링) — N3
    └── tests/                    # pytest — test_sc01_calc · _process · _api · _agent · _exceptions · _center,
                                  #   test_events · _notify
```

**디렉토리 규칙**
* `components/sc01/` — SC01 화면 전용. 장면 2 이후를 만들면 같은 원칙으로 디렉토리를 나눈다.
* `components/flow/` — React Flow 노드·엣지·캔버스 **전용**.
* `components/shared/` — 두 화면 이상이 쓰는 조각 중 SC01에 묶이지 않은 것만 둔다.
* `engine/app/sc01/` — 업무 규칙. 화면(TS)은 규칙을 다시 구현하지 않는다(4.3).

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
브라우저 ──/api/engine/sc01/*──▶ Next Route Handler(BFF, 그대로 중계) ──/sc01/*──▶ 엔진(127.0.0.1:8077)

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
```

* **시스템 작업은 Chaeksas 외부 확장(HTTP 어댑터)으로 부른다** — 정의는 `chaeksas/nowview-sc01.extension.json`.
  내장 BPM의 `_InProcessCalls`와 HTTP가 **같은 함수**(`process.run_operation`)를 써서 출력 모양이 같다 —
  BPMN의 `output` 대응이 두 길 모두에서 맞는다. 내장 BPM을 걷어내기 전까지 두 길이 함께 있다.
  * **확장 id에는 점을 쓸 수 없다**(C13 `^[a-z][a-z0-9-]{1,49}$`). 그래서 서비스 앱 id가 `nowview.sc01` →
    `nowview-sc01`이 됐다(BPMN `app_id`·`service_keys`, `process.APP_ID`). BPM 프로세스 id는 그대로다.
  * **어댑터는 `base_url`의 경로를 버린다**(호스트·포트만 쓴다) — 그래서 작업 `path`에 BFF 경로
    `/api/engine/…`를 통째로 적었다.
  * **정의는 한 벌이고, 로컬 Center가 주소만 덮어쓴다**(R4, ADR-0097). 기본 주소는 운영계
    (`https://www.nowview.work`)이고 `allowed_hosts`가 `[www.nowview.work, localhost]`,
    `allow_private_network: true`다. 로컬 Center에서만 CON-07 → `nowview-sc01` → 「서버 주소」를
    `http://localhost:3000`으로 바꾼다(`PUT /api/v1/resources/extensions/nowview-sc01/address`, 관리자).
    Center는 정의의 허용 호스트 **안에서만** 받는다 — 정의가 상한이다. 해시가 하나라 로컬에서 시험한
    그 판이 운영에 간다. 예전에는 Center에서 바꿀 길이 없어 `.local` 정의를 따로 두고 작업 정의를 두 파일에
    맞춰 적었다 — 지웠다. 사설망 허용을 운영 정의에 켠 득실은 `docs/chaeksas-integration.md` §7의 5.
    `test_extension_definition_matches_the_bpmn_service_calls`가 정의 ↔ BPMN 입력을 잠근다.
  * **어댑터는 `localhost`를 `::1`로 푼다**(실측). `next dev`는 양쪽에 듣지만 웹을
    `-H 127.0.0.1`로 띄우면 연결 거부다. `127.0.0.1`로 덮어쓰면 허용 호스트 밖이라 어댑터가 거절한다.
  * 정의를 고치면 `version`을 올리고 다시 서명한다(같은 버전·다른 내용은 409). 지금 0.6.0 — 기록 작업
    응답에 `error_message`(성공이면 null, 4.5의 기록 거절)가 있고, 기록 작업과 계산은 `answered_by`를 받는다.
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
  `GET /runs/{id}/events` 진행, `DELETE /jobs/{id}` 대체된 작업 거두기) · `CHAEKSAS_RELAY_KEY`(대리 답용 — 결재
  읽기·답, `X-CHK-On-Behalf-Of` = 행위자 이름) · `CHAEKSAS_SC01_PACKAGE`(기본 `nowview.sc01`). 키가 둘인 것은
  Chaeksas 권한표 그대로다 — 대리 답용 키는 결재만, 연동용 키는 결재를 못 읽는다. `/health.center`가 설정·폴링
  여부를 드러낸다(값은 싣지 않는다). 시스템 작업 키(N6)와는 방향이 반대인 다른 키다.
  * **메시지는 `schema: 1`이 있어야 한다**(`MessageRequest`) — 없으면 422 `input_invalid`(실측). 작업(`/jobs`)은
    `schema`가 없는 계약이다.
  * **선택 입력을 본문 템플릿에 넣지 않는다.** 어댑터는 `{{input.x}}`의 `x`가 없으면 호출을 실패시킨다 —
    그래서 배정 기록이 생산·자재(`record_dispatch`)와 경영관리(`record_review_request`)로 갈렸다.
    `answered_via`는 대리 답이 아니면 `null`이지만 **변수는 늘 있다**(결재가 `answered_via_as`를 채운다) —
    없는 것과 `null`은 다르다. 값 하나뿐인 템플릿은 JSON 값 그대로 실린다.
  * **모든 작업 본문에 `{{run_id}}`·`{{node_id}}`를 싣는다**(0.3.0, N2). 이름이 `chaeksas_run_id`인 것은
    작업 입력의 `run_id`가 이미 **계산** id라서다. 실행 id가 없는 호출(0.2.0 정의)은 422다 — 묶을 수 없다.

* **BFF는 경로를 하나씩 옮겨 적지 않고 그대로 중계한다.** 업무 규칙(권한 403 · 없음 404 · 상태 충돌 409 ·
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
    판정이 그만큼 느슨하다(Studio). Center 실행은 폴링이 결재를 읽을 때 연다(N3, 아래).
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
  * 화면 답(`act`)·각본 → **사전 검사가 Center보다 먼저**(403·409·422, 입력 보존) → 열린 결재 찾기(최대 10초 —
    실행기가 결재를 올리는 동안) → 대리 답(`if_review_digest`). 업무 효과는 여전히 기록 작업이 낸다.
  * 폴러(`poller.py`, 2초)는 `bpm.state == running`인 center 데모 실행만 읽는다(`store.running_external`).
    C3 → 지나온 노드·토큰 위치·열린 결재·끝. 새 결재는 대리 답용 키로 읽어 검토 자료·폼을 싣고 **업무를 그때
    연다**(늦게 열지 않는다). 대리 답한 결재는 `human_answered`가 오기 전까지 다시 보이지 않는다(`relayed`).
  * **설정이 없으면 조용히 내장으로 돌지 않는다** — 수신은 되고 「기동하지 않았다」 사유가 배너에 남는다
    (첫 폴링에서 걷힌다). 화면 답·각본은 503. 화면은 엔진이 정한 `answerHere`로 폼·각본을 켠다.
  * 시험은 가짜 Center(`test_sc01_center.py`)와 **따로 띄운 빈 Center**(실측)로 했다. 진짜 서버 실행기·배포된
    패키지로는 아직 돌려 보지 않았다(기동·메시지 전달이 남았다).
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
| `/plans` | UI02·03 고객계획 | 수신 목록, CP01 → 수신본 변경 비교, 자동 검증, 원천 확인·비교 계산 |
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
| `engine/tests/test_sc01_center.py` | N3 — 가짜 Center(C3·C5·C6·C12 계약 그대로) + 진짜 Chaeksas 엔진의 실행기 흉내로 각본 끝까지(대리 답), 사전 검사가 Center보다 먼저, Center 거절 사유, 설정 없음 503, 정정 메시지·대체 — **SQLite·Postgres 양쪽** |
| `engine/tests/test_events.py` · `test_notify.py` | SSE 허브 구독 해제, 다른 워커로의 전파(Postgres) |
| `tests/sc01.test.ts` | 화면이 엔진 응답을 **잘못 읽는** 종류 — BPMN 배치(되돌아가는 흐름·줄 접기), 노드 상태 파생, 장면 → 이력 seq, 표기(누락·판정 보류·억/만) |

* 엔진 테스트는 SQLite와 Postgres 두 백엔드를 모두 돈다(177개 / 217개). 자리표시자·행 접근·JSON
  타입이 전부 달라 한쪽만 돌리면 나머지가 배포 시점에 터진다. CI는 `REQUIRE_POSTGRES=1`로 skip을
  실패로 바꾼다.
* `tests/fixtures/sc01-process.json`은 BPMN 토폴로지의 사본이다. BPMN을 고치면 엔진 테스트가
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

---

## 5. 다음 단계와 선행 조건

CI(5.1), Chaeksas 엔진(5.2), SC01 화면(5.3), Agent와 예외 경로(5.5)는 끝났다. 운영계(5.4)는 아직
이전 구현이 떠 있다.

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
  회사·인물(이도윤·박서진·김태오·최유나·정하윤·한준호)은 가상이다. 공개되는
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
* **장면 2 이후**는 Business 설계(설계표·데이터)가 나와야 시작한다 — 지어내지 않는다(4.7).
* 운영 배포 전 확인: 인증이 없는 상태에서 `X-Demo-Actor`로 아무 역할이나 될 수 있다(5.4).
