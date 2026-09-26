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
npx vitest run tests/framework.test.ts                        # 파일 하나
npx vitest run tests/framework.test.ts -t "예방 통제가 없는"   # 이름으로 하나만
```

**BPM 엔진 (Python · `engine/`)**

```bash
cd engine
uv sync
uv run uvicorn app.main:app --port 8077 --reload   # http://localhost:8077/docs
uv run pytest                                      # 56개 (SQLite만, LLM 제외)
uv run pytest -m llm                               # ollama 실호출 (약 40초)
uv run ruff check .
```

**전체 스택 (앱 · 엔진 · Postgres)**

```bash
docker compose up --build   # 앱 :3000 · 엔진 :8077 · Postgres :55432
```

* `docker compose`는 **Postgres 백엔드**로 돈다. 로컬 `uv run`은 기본이 SQLite다.
* **포트가 이미 쓰이고 있으면 컨테이너가 포트 매핑 없이 만들어질 수 있다.** 그 상태로
  `up`을 다시 해도 compose가 기존 컨테이너를 재사용해 계속 접속이 안 된다 —
  `docker compose down` 후 다시 올려야 한다. 실제로 dev 서버가 3000을 잡고 있어 겪었다.
* 두 백엔드를 모두 검증하려면:
  `TEST_DATABASE_URL=postgresql://nowview:nowview@localhost:55432/nowview uv run pytest` (90개)

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
* **React Flow / Recharts는 클라이언트 컴포넌트다.** 둘 다 브라우저 전용 API에 의존하므로 사용하는 파일 최상단에 `'use client'`가 필요하다. App Router 기본값은 서버 컴포넌트다.
* **Recharts 커스텀 `shape` + entrance 애니메이션은 같이 쓰면 안 된다.** `<Bar shape={<Custom/>}>`에
  애니메이션이 켜져 있으면 막대가 `height: 0`에 멈춘 채 렌더된다 — 에러도 콘솔 경고도 없고 SVG 골격만
  그려지므로 원인 파악이 오래 걸린다. 커스텀 shape를 쓸 때는 `isAnimationActive={false}`를 함께 준다.
  (실제로 `components/cockpit/op-bridge-chart.tsx`에서 겪었다.)
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
* **Description**: 매출 1조원 규모 가상 자동차 부품사를 대상으로, 체계화된 Management Framework 및 BPM 프로세스 위에서 사람과 멀티 AI Agent가 유기적으로 협업하는 차세대 경영 운영 플랫폼 프로토타입/SaaS.
* **Core Philosophy**:
  * **Target vs. Forecast vs. Plan**: 목표(Target)는 임의로 변경하지 않으며, 실행 결과와 최신 가정을 반영한 전망(Forecast)과 실행계획(Plan)을 Rolling 방식으로 갱신하고 잔여 Gap을 명시적으로 관리한다.
  * **Human-in-the-Loop**: AI Agent는 데이터 수집, 이상 징후 감지, 다차원 원인 분석, 대안 시뮬레이션을 수행하고, 최종 판단과 승인은 사람이 책임진다.
  * **Deterministic BPM + Probabilistic AI**: 워크플로우 통제는 결정론적 BPM(LangGraph StateGraph)으로 통제하고, 데이터 해석 및 분석은 LLM 에이전트가 담당한다.

---

## 2. Business Context & Virtual Company Spec

### 2.1 가상 고객사: (주)넥스트오토모티브 (Next Automotive Corp.)
* **기업 규모**: 연간 매출 1조 200억 원 / 목표 영업이익 428억 원 (영업이익률 4.2%)
* **주요 고객**: 현대자동차, 기아 (1차 협력사, SJG세종 및 인팩 모델 벤치마킹)
* **사업부 구조**:
  1. **파워트레인/샤시 사업부 (기존 사업, 매출 비중 75%)**:
     * 주요 품목: 배기 시스템, 컨트롤 암 등 내연/하이브리드 부품
     * 핵심 고민: 전동화 전환에 따른 가동률 하락, 고정비 흡수율 방어, 완성차 단가 인하 압박
  2. **친환경/전장 사업부 (신사업, 매출 비중 25%)**:
     * 주요 품목: 배터리 관리 시스템(BMS), 전동식 조향 제어기(ECU)
     * 핵심 고민: 신차 양산 시점 불확실성, 초기 수율 안정화, 차량용 반도체/핵심 소자 공급망 리스크

### 2.2 경영 작동모델 6단계 루프 (Management Loop)
1. **Risk Sensing & Monitoring**: 현재 실적 편차(수율/가동률) 및 선행 리스크(구매가 인상/물량 축소) 감지.
2. **Operation Control**: 현업 단위의 사전 예방·통제 수행, 부서 간 조정이 필요한 건은 Management Review로 에스컬레이션.
3. **Management Review (Human-in-the-Loop)**: AI 보고서 검토, 3가지 대응 대안 시뮬레이션, 경영진 의사결정.
4. **Management Action**: 결정 사항을 담당자/기한/목표 회수액이 명시된 실행 과제로 변환 및 배포.
5. **Rolling Plan Update**: 과제 실행 효과를 반영하여 향후 손익 Forecast 즉각 갱신, 잔여 Gap 명시.
6. **Management Evolution**: 프레임워크 지표 정의 보완, KRI 감지 임계치 강화, 에이전트 룰 개선.

---

## 3. Tech Stack

* **Frontend**: Next.js 16.3.6 (App Router, Turbopack), React 19.2, TypeScript 5, Tailwind CSS v4, Shadcn/UI (`radix-nova` 프리셋 / Radix 기반 / Lucide 아이콘)
* **Process Visualization**: `@xyflow/react` 12.12 (React Flow)
* **Data Visualization**: **Recharts** 3.10 (단일 차트 라이브러리), Lucide React
* **State Management**: Zustand 5.0 (시나리오 데모 플레이어 상태 관리용)
* **Backend / API**: Next.js Server Actions & Route Handlers (FastAPI/Python LangGraph 연동 지원)
* **Workflow / Agent Engine**: **LangGraph StateGraph** (BPM 상태 머신 + Multi-Agent 오케스트레이션 공용)
* **Database & Mock**: PostgreSQL, DuckDB, JSON Mock Datasets

### 3.1 확정된 기술 선택 (Decided — 재검토 불필요)

| 영역 | 선택 | 배제한 대안 | 사유 |
|---|---|---|---|
| BPM 상태 머신 | LangGraph StateGraph | Camunda 8 (BPMN 2.0) | Camunda는 Zeebe 브로커 운영이 필요해 프로토타입에 과중하다. LangGraph는 BPM 상태 전이와 에이전트 오케스트레이션을 하나의 그래프 런타임으로 처리한다. |
| 차트 | Recharts | Apache ECharts | Shadcn/UI·Tailwind와의 컴포지션이 자연스럽다. 차트 라이브러리는 하나만 쓴다 — 두 개를 섞으면 테마·툴팁·반응형 동작이 갈라진다. |
| Shadcn 프리미티브 | Radix (`-b radix`) | Base UI, React Aria | 기존 shadcn/ui 문서·스니펫이 Radix 기반이라 이식 비용이 가장 낮다. |
| 테마 전환 | next-themes (`attribute="class"`) | 직접 구현 | 초기 렌더에 잘못된 테마가 번쩍이는(FOUC) 문제를 직접 처리하지 않아도 된다. `.dark` 클래스 방식이 Tailwind v4 `@custom-variant dark`와 `globals.css`의 `.dark .viz-root`를 동시에 만족시켜, UI 토큰과 차트 색이 항상 함께 전환된다. |

BPMN 2.0 다이어그램 표현이 필요한 경우에도 엔진을 Camunda로 바꾸지 않는다. 시각화는 `@xyflow/react` 커스텀 노드로 처리하고, 상태의 원천은 LangGraph 그래프로 유지한다.

---

## 4. Project Directory Structure

아래는 **실제 구조**다(목표 설계가 아니라 파일 시스템 기준). 구조를 바꾸면 이 트리를 갱신한다.

```text
NowView/
├── CLAUDE.md
├── AGENTS.md                     # next dev 자동 생성 (Next.js 에이전트 규칙)
├── components.json               # Shadcn 설정
├── .claude/launch.json           # preview 서버 설정 (nowview-dev)
├── app/
│   ├── layout.tsx                # 전사 레이아웃, GNB, 테마 공급자
│   ├── globals.css               # 테마 토큰 + --viz-* 시각화 팔레트
│   ├── page.tsx                  # ① Executive Cockpit
│   ├── bpm-tracker/page.tsx      # ② Live BPM & Agent Process Tracker
│   ├── workspace/page.tsx        # ③ Human-Agent Collaboration Station
│   ├── rolling-plan/page.tsx     # ④ Rolling Plan & Action Tracker
│   ├── evolution/page.tsx        # ⑤ Management Evolution Lab
│   └── api/
│       ├── mock/route.ts         # 데이터셋 목록
│       ├── mock/datasets.ts      # 데이터셋 레지스트리 (라우트 아님)
│       ├── mock/[dataset]/       # 데이터셋 조회
│       ├── bpm/                  # state · transition · decision (무상태 계산기)
│       └── engine/               # Python 엔진 프록시(BFF) — instances 생명주기
├── components/
│   ├── ui/                       # Shadcn 원시 컴포넌트 8종
│   ├── shared/                   # 두 화면 이상이 쓰는 조각: stat-tile, severity
│   ├── cockpit/                  # ① division-card, op-bridge-chart, risk-signal-list
│   ├── flow/                     # React Flow 전용: bpmn-node, process-canvas
│   ├── bpm/                      # ② tracker-shell, step-controls, node-detail-panel,
│   │                             #   agent-activity-panel
│   ├── workspace/                # ③ workspace-shell, agent-report-viewer,
│   │                             #   alternative-comparison, simulator-panel, decision-panel
│   ├── rolling/                  # ④ rolling-shell, gap-panel, forecast-trend-chart,
│   │                             #   action-tracker, revision-history
│   ├── evolution/                # ⑤ evolution-shell, kri-tuning-panel, backtest-chart,
│   │                             #   proposal-list
│   ├── demo/                    # demo-player, store-hydrator (전 화면 공통)
│   ├── theme-provider.tsx
│   └── theme-toggle.tsx
├── lib/
│   ├── format.ts                 # 억원·퍼센트 표기
│   ├── utils.ts                  # cn()
│   ├── demo-scenario.ts          # 데모 각본 (연출 설정이라 mock-data가 아니다)
│   ├── api/response.ts           # Route Handler 공통 응답·본문 파싱
│   ├── store/demo-controller.ts  # Zustand: 진행 지점 + 승인 결정
│   ├── types/                    # cockpit, bpm, workspace, rolling, evolution
│   └── mock-data/                # next-automotive, bpm-process, review-case,
│                                 #   rolling-plan, evolution-lab
├── services/
│   ├── bpm-engine.ts             # 워크플로우 상태 파생, 승인 지점 계산
│   ├── agent-orchestrator.ts     # Agent 활동 + 대안 시뮬레이션
│   ├── rolling-plan.ts           # Gap 집계, 결정→과제 변환
│   ├── evolution-lab.ts          # 임계치 백테스트 조회
│   ├── engine-spec.ts            # 시나리오 → 엔진 명세 (토폴로지 유일 원천)
│   └── engine-client.ts          # Python 엔진 HTTP 클라이언트 (서버 전용)
└── engine/                       # Python BPM 엔진 (별도 프로세스)
    ├── pyproject.toml            # uv
    ├── README.md
    ├── app/
    │   ├── main.py               # FastAPI — instances 생명주기
    │   ├── spec.py               # 받는 명세 (Pydantic, camelCase 별칭)
    │   ├── state.py              # 인스턴스 상태
    │   ├── graph.py              # 명세 → LangGraph StateGraph 조립
    │   ├── agents.py             # MockRunner · OllamaRunner + 계약 검증
    │   └── instances.py          # 생명주기 · checkpointer · 스냅샷 파생
    └── tests/                    # pytest 33개
```

**디렉토리 규칙**
* `components/<화면>/` — 그 화면 전용 패널. 화면을 추가하면 디렉토리도 함께 만든다.
* `components/flow/` — React Flow 노드·엣지·캔버스 **전용**. 트래커의 나머지 패널은 `components/bpm/`이다.
* `components/shared/` — 두 화면 이상이 쓰게 된 조각만 올린다. 한 화면만 쓰면 그 화면 디렉토리에 둔다.
* `services/` — 화면이 실제로 호출하는 파생·계산 로직. 인터페이스만 있는 스텁은 두지 않는다.

**아직 없는 것** — `lib/store` 영속화(전체 새로고침 시 진행 상태 초기화).

### 4.1 데모 플레이어

`components/demo/demo-player.tsx`가 레이아웃에 상주하며 다섯 화면을 6단계 루프 순서로 잇는다.
각본은 `lib/demo-scenario.ts`다.

* **각 장면은 목표 상태를 전부 선언한다** — 화면 경로, BPM 지점, 승인 여부. 이전 장면 대비
  증분이 아니라 절대 상태이므로 스크러버로 아무 장면이나 찍어도 앞뒤가 맞는다.
  역방향으로 점프하면 승인이 지워지고, 다시 앞으로 가면 같은 상태가 재현된다.
* **엔진 모드에서도 동작한다**(4.18). 장면이 선언한 지점으로 인스턴스를 옮긴다.
* **장면 이동은 한 핸들러에서 상태 적용과 라우팅을 함께 한다.** 상태를 감시하는 effect로
  라우팅하면 사용자가 GNB로 직접 이동했을 때 플레이어가 되돌려 버리는 싸움이 난다.
* `DEMO_DECISION.decidedAt`은 **고정 문자열**이다. 스토어가 모듈 로드 시점에 만들어지므로
  `new Date()`를 쓰면 서버와 클라이언트 값이 달라져 하이드레이션이 깨진다.
  금액은 `simulateAlternative`로 계산해 화면·API와 같은 값이 되게 한다(하드코딩 금지).
* 자동 재생의 `setState`는 타이머 콜백 안에서만 일어난다 — effect 본문에서 상태를 바꾸면
  `react-hooks/set-state-in-effect`에 걸린다.
* **자동 재생은 고정 간격이 아니다**(4.18). 장면이 반영된 뒤에 머무름을 시작한다.
* 플레이어가 화면 하단을 가리므로 `app/layout.tsx`의 본문 래퍼에 `pb-48`(192px)을 둔다.
  플레이어 최대 높이 170px + 하단 오프셋 16px = 186px이 필요하다(측정값).
* **시나리오가 조작해야 하는 값은 화면 로컬 상태로 두지 않는다.** ⑤의 KRI 임계치가
  `useState`에 있어서 "87%로 올리면"을 말로만 하고 슬라이더는 85%에 머물렀다.
  스토어로 올려 장면이 값을 지정하게 했다(`DemoScene.kri`).

### 4.2 상태 영속화

스토어는 `persist` 미들웨어로 localStorage(`nowview-demo`)에 저장된다. 시연 중 새로고침해도
진행 상태가 남는다.

* **`skipHydration: true`가 핵심이다.** 화면들이 정적 프리렌더라 서버 HTML은 항상 기본
  상태인데, persist가 모듈 로드 시점에 자동 복원하면 첫 클라이언트 렌더가 서버와 달라져
  하이드레이션이 깨진다. 자동 복원을 끄고 `components/demo/store-hydrator.tsx`가 mount
  이후 명시적으로 복원한다. 첫 페인트가 아주 짧게 기본 상태로 나갔다가 바뀐다.
* **`isPlaying`은 저장하지 않는다.** 새로고침하자마자 화면이 저절로 넘어가면 곤란하다.
* 저장 형태를 바꾸면 `version`을 올린다. 올리지 않으면 예전 구조가 그대로 복원돼 터진다.
* 초기 상태로 되돌리려면 플레이어의 "처음으로"를 누르거나 localStorage의 `nowview-demo`를
  지운다.

### 4.3 API 계층

```
GET  /api/mock                  사용 가능한 데이터셋 목록
GET  /api/mock/[dataset]        company · rolling-plan · framework · evolution-lab · scenarios
                                process-<시나리오id> · review-<시나리오id> (레지스트리에서 생성)
GET  /api/bpm/state?step=N      해당 지점의 노드 상태·Agent 활동·현재 단계
POST /api/bpm/transition        {step, action: next|prev|reset|goto, target?} → 다음 지점
POST /api/bpm/decision          {alternativeId, leverValue, rationale} → 결정·과제·Gap 변화

GET  /api/engine                엔진 도달 여부·모델·엔드포인트 목록
POST /api/engine/instances      {scenarioId, agentMode: mock|llm} → 인스턴스 생성 후 첫 대기까지
GET  /api/engine/instances      인스턴스 목록
GET  /api/engine/instances/{id} 스냅샷 (노드 상태·Agent 산출물·대기 지점)
POST /api/engine/instances/{id}/resume   승인 입력 → 재개
DELETE /api/engine/instances/{id}
```

**`/api/bpm/*`와 `/api/engine/*`는 성격이 다르다.** 앞의 것은 진행 지점을 받아 계산해
돌려주는 무상태 계산기이고, 뒤의 것은 서버에 사는 인스턴스를 다룬다(4.16). 둘을 함께
두는 이유는 데모가 계속 계산기 쪽으로 동작해야 하기 때문이다.

**상태를 서버에 저장하지 않는다.** 진행 지점은 요청이 들고 오고 서버는 파생 상태를 계산해
돌려줄 뿐이다 — 서버리스에서 인메모리 상태는 인스턴스마다 갈라지고, 이 프로젝트는 이미
클라이언트(Zustand)가 진행 지점을 소유한다. 실제 백엔드(FastAPI/LangGraph)가 붙으면
여기가 그 접합면이다.

* **API는 로직을 다시 구현하지 않고 `services/`를 그대로 호출한다.** 화면과 API가 같은
  함수를 쓰므로 결과가 어긋날 수 없다. 덕분에 "미완료 Agent의 산출물은 감춘다"나
  "이중 계상 금지" 같은 규칙이 API에서도 저절로 지켜진다.
* **사유 10자 검사는 UI와 API 양쪽에 있다.** 버튼 비활성은 편의일 뿐 강제가 아니며 API를
  직접 부르면 우회된다. 두 곳이 갈라지지 않도록 `DECISION_RATIONALE_MIN_LENGTH` 상수를 공유한다.
* 범위를 벗어난 전이는 400이 아니라 잘라내고 `clamped: true`로 알린다 — 마지막 단계에서
  next를 누르는 것은 오류가 아니라 정상적인 UI 동작이다.
* **화면들은 `/api/bpm/*`를 쓰지 않는다.** Mock 경로는 `lib/mock-data/*`를 직접 import하고,
  엔진 경로는 `/api/engine/*`를 **클라이언트에서** 부른다(4.17). 그래서 다섯 화면 모두
  정적 프리렌더(`○`)를 유지한다. `/api/bpm/*`는 외부 소비자(별도 클라이언트, Python
  서비스)를 위한 경계로 남아 있다.

### 4.4 데이터 시각화 규칙

차트 색은 `app/globals.css`의 **`--viz-*` 변수만** 사용한다. 이유와 제약:

* **shadcn nova 프리셋의 `--chart-1~5`는 무채색 그레이스케일**(`oklch(… 0 0)`)이다. 계열 식별에 쓰면
  chroma floor를 통과하지 못하므로 차트에 쓰지 않는다.
* 역할을 섞지 않는다: `favorable`/`unfavorable`은 극성(개선/악화), `series-1|2`는 엔티티 식별,
  `status-*`는 상태 전용이다. 계열색을 상태색으로, 상태색을 계열색으로 재사용하지 않는다.
* 계열색은 **엔티티에 고정 배정**한다. 목록 순서나 순위에 따라 다시 칠하면 안 된다.
* 상태는 색 단독으로 전달하지 않는다 — `SeverityTag`(아이콘+한글 라벨)를 항상 동반한다.
  라이트 서피스에서 warning/serious는 대비 3:1 미만이라 이 조합이 유일한 완화 수단이다.
* 색을 바꾸면 **눈으로 판단하지 말고 검증기를 돌린다.** 서피스는 카드 배경 기준(라이트 `#ffffff`,
  다크 `#171717`)이며 명령은 `globals.css`의 `.viz-root` 주석에 적어 두었다.
* **단위가 다른 두 계열을 한 차트에 겹치지 않는다.** 축이 둘이면 없는 상관관계를 만들어낸다.
  Evolution Lab의 감지/오탐은 같은 단위(건)라 한 축에 두고, 조기 감지일(일)은 지표 타일로 뺐다.
* 모든 차트에는 표 뷰를 둔다(값이 툴팁에만 갇히면 접근성 위반). `OpBridgeChart`의 "표로 보기"가 그 예다.

### 4.5 BPM 상태 모델

**노드 상태는 저장하지 않고 파생한다.** 실행 순서(`BpmProcessInstance.sequence`)와 현재 진행 지점이
유일한 진실이고, 노드별 상태·Agent 실행 상태는 전부 `services/`에서 계산한다
(`deriveNodeStatuses`, `agentActivities`). 노드마다 status 필드를 두면 순서와 상태가 곧 어긋난다.

* `sequence`에 없는 노드는 선택되지 않은 분기이므로 자동으로 `skipped`가 된다.
* 현재 지점의 노드가 `user-task`면 `active`가 아니라 **`waiting`**(승인 대기)이다 —
  경영진이 "지금 내 결재가 걸려 있는지"를 구분해야 한다.
* **게이트웨이는 산출물 은닉 대상이 아니다.** 분기 판정은 오래 걸리는 산출 작업이 아니라
  즉시 평가이고, 캔버스가 이미 어느 경로를 탔는지 점선으로 보여 준다. 상세 패널만
  "산출물 확정 전"이라고 하면 같은 화면이 서로 다른 말을 한다.
* **아직 완료되지 않은 Agent의 산출물은 어느 패널에서도 보여주지 않는다.** 미래 결과를 미리 노출하면
  분석이 이미 끝난 것처럼 읽힌다. **경로가 둘이라 두 번 다 막아야 한다** — 실제로 두 번 새어 나왔다:
  1. `AgentRun.output` — `run`을 넘기기 전 상태가 `done`인지 확인한다.
  2. `BpmNodeSpec.outcome` — 완료된 결과를 서술한 문장이므로(`…산출 완료` 같은) `done`과
     `waiting`에서만 보여 준다. `active`에는 "수행 중 — 산출물 확정 전"을 대신 띄운다.
     `waiting`은 사람의 판단을 기다리는 상태라 outcome이 결과가 아니라 대기 사유다.
* **단계별 문구를 하드코딩하지 말 것.** 사람 대기 배너는 `user-task`면 모두 뜨는데, Review 전용 문구를
  넣어 두었다가 Management Action 단계에서 "대안 선택과 승인"을 말하는 버그가 있었다.

### 4.6 화면 간 수치·상태 연동

다섯 화면은 **같은 사건 하나**(파워트레인 가동률 임계치 이탈)를 각각 다른 관점으로 본다 —
감지(①) → 프로세스(②) → 판단(③) → 반영(④) → 시스템 개선(⑤).
숫자가 어긋나면 데모 전체의 신뢰가 무너지므로 아래 항등식을 깨지 말 것:

* `review-case.ts`의 각 대안 `lever.base × profitPerUnit` = `bpm-process.ts`의 Simulation Agent
  산출물 문구에 적힌 금액 (1안 2×9=18억, 2안 20×0.6=12억, 3안 3×3=9억).
* `review-case.profitGap`(-69억) = `next-automotive.ts`의 전사 영업이익 Gap.
* `rolling-plan.ts`의 `target`(428) / `forecast`(359) = `next-automotive.ts`의 전사 영업이익.
  분기 합도 각각 같아야 하며 `assertQuartersBalance`가 이를 검증한다.
* `reflectedInForecast: true`인 과제의 목표 회수액 합(20억)
  = `next-automotive.committedActionRecovery` = Cockpit 브릿지의 "확정 Action 회수 효과 +20억".
* `riskId`·`processId`로 네 화면이 같은 건을 가리킨다.

**과제 효과의 이중 계상 금지.** Rolling Plan에서 가장 틀리기 쉬운 지점이다. 이미 Forecast에
반영된 과제를 또 더하면 Gap이 실제보다 메워진 것처럼 보인다. `ActionItem.reflectedInForecast`로
갈라서 합산하고(`summarizeGap`), 승인 직후 과제는 **현재 Forecast를 바꾸지 않고** "다음 Rolling
반영 예정"으로만 잡는다 — 전망치(`projectedForecast`)는 따로 표시한다.

**상태 연동:** 협업 스테이션에서 승인하면 Zustand 스토어의 `decision`이 기록되고
① BPM 진행 지점이 Management Action 단계로 이동하며
② Rolling Plan의 과제 목록에 미반영 과제로 추가된다(`decisionToAction`).
스토어는 메모리에만 있으므로 **전체 새로고침하면 초기화된다** — 연동을 확인하려면 GNB나
화면 내 링크로 클라이언트 라우팅 이동해야 한다.

⑤ Evolution Lab은 예외로 **전역 상태를 바꾸지 않는다.** 채택·보류는 화면 로컬 상태다 —
프레임워크 변경은 배포 절차를 타야 하고, 이 단계의 결정은 다음 루프부터 효력이 생긴다.

### 4.7 Mock 데이터를 지어낼 때의 규칙

화면이 주장하는 바를 데이터가 배반하지 않아야 한다. 지금까지 지킨 것들:

* **트레이드오프를 숨기지 않는다.** KRI 임계치를 조이면 감지가 늘지만 오탐도 반드시 는다.
  기대 효과만 있고 부작용이 없는 제안은 검토가 아니라 홍보다(`EvolutionProposal.tradeoff`는 필수).
* **백테스트는 공식이 아니라 표다.** 임계치별 결과를 값으로 들고 있고 보간하지 않는다.
  Mock 단계에서 그럴듯한 수식을 만들면 없는 정밀도를 주장하게 된다. 시뮬레이터의 선형 응답
  모델도 같은 이유로 의도적으로 단순하다.
* **개선 제안은 앞 화면에서 실제로 드러난 공백에서만 뽑는다.** 임의로 지어낸 항목을 섞으면
  "루프가 학습한다"는 주장 자체가 무너진다.


### 4.8 Management Framework 모델 (KPI–KRI–Control)

기획안 1.1의 "무엇을 보고 어떻게 판단할지에 대한 공통 기준"을 구조로 옮긴 것이다.

```
Value Driver (성과 동인)
  └ KPI  결과 지표 — 이미 일어난 일을 잰다 (후행). 임계치를 두지 않는다.
      └ KRI  위험 지표 — 아직 결과에 다 나타나지 않은 위험 (선행). 임계치가 여기 붙는다.
          └ Control  예방 · 탐지 · 시정
```

* **KPI와 KRI를 같은 것으로 취급하지 않는다.** 가동률 82.1%는 결과(KPI)이면서 임계치를 건
  감지 신호(KRI)로도 쓰이지만, 전자는 "얼마나 나빠졌나"를, 후자는 "언제 손을 대야 하나"를
  답한다. 그래서 `Kpi`에는 `target`만, `Kri`에는 `threshold`가 있다.
* **통제는 예방·탐지·시정 셋으로 나눈다.** 나누지 않으면 "탐지만 있고 막을 방법이 없는"
  상태가 보이지 않는다. 현재 6개 KRI 중 3개에 예방 통제가 없고, 화면이 이를 표시한다.
* KRI와 `RiskSignal`은 **같은 사건을 다른 관점으로 본 것**이며 `riskId`로 묶인다.
  한쪽 수치를 고치면 다른 쪽도 고쳐야 한다.
* `services/framework.ts`의 `buildChains`는 끊어진 참조(없는 KPI·통제)와 통제가 0개인 KRI를
  **조용히 넘기지 않고 throw한다** — Framework의 구멍이지 표시상의 문제가 아니다.

### 4.9 경영 수행 성과

기획안 2.3은 성과를 **두 관점**으로 나눈다 — 사업 성과(손익·품질·재고)와 경영 수행 성과
(속도·정확성·실행력). 둘을 섞으면 "손익은 나빠졌지만 대응은 빨라졌다"를 말할 수 없다.

* **일곱 지표 중 넷은 실제 데이터에서 계산한다**(`services/execution-performance.ts`).
  Agent 실행 기록·실행 과제·백테스트가 이미 시스템 안에 있으므로 값을 다시 적지 않는다 —
  적으면 원본이 바뀔 때 조용히 어긋난다. `lib/mock-data/execution-performance.ts`의
  `current`는 `provenance: "system"`인 지표에서는 **쓰이지 않는 자리표시자**다.
* **값마다 출처를 표시한다**(`Provenance`). 기획안 2.3의 "시나리오에서 설정한 결과와
  시스템 실행으로 확인한 결과를 구분한다"를 UI로 옮긴 것이다. 구분이 없으면 데모의
  주장을 검증할 수 없다.
* `previous`(직전 주기)는 전부 시나리오 설정값이다 — 시스템에 이전 주기 기록이 없다.
  경영 수행 성과는 절대 수준보다 개선 여부가 핵심이라 비교 대상 자체는 있어야 한다.
* 개선 표기는 **화살표가 값의 증감을, 색이 좋고 나쁨을** 가리킨다. 처음에는 화살표에
  "개선 여부"를 실었는데 소요시간 단축이 `↑ -2일`로 나와 화살표와 부호가 반대로 읽혔다.
  값의 방향과 평가를 한 기호에 겹쳐 실으면 둘 다 흐려진다.
* `parseDurationMinutes`는 형식을 못 읽으면 0이 아니라 throw한다 — 조용히 0이 되면
  소요시간이 실제보다 짧게 보인다.

### 4.10 실행계획 (Plan)

기획안 3.4는 **Target · Forecast · Plan** 셋을 정의한다. 셋의 운영 원칙이 서로 다르다:

| 구분 | 원칙 | 구현 |
|---|---|---|
| Target | 자동 변경하지 않는다 | `ForecastRevision`에 target 필드 자체를 두지 않는다 |
| Forecast | 새 정보·실행 결과를 반영해 **갱신**한다 | Rolling 회차마다 값이 움직인다 |
| Plan | 승인된 대응안과 운영 여건 변화를 반영해 **조정**한다 | `PlanItem`, `planView()` |

* Plan은 **활동·물량·일정·자원** 네 축으로 나눈다(기획안 3.4의 정의 그대로). 승인 하나가
  네 축에 각각 다르게 파급되는데, 뭉뚱그리면 "무엇을 언제 누가 얼마로"가 사라진다.
* 값이 숫자가 아니라 문자열이다 — 일정과 활동은 수치화되지 않는다. 계산은 Forecast의
  몫이고 Plan은 서술한다.
* **승인 전에는 조정 후 값을 유효한 계획으로 보여주지 않는다**(`drivenByDecision`).
  결정되지 않은 계획을 확정된 것처럼 표시하는 것은, 실행 중인 Agent의 산출물을 미리
  노출하는 것과 같은 종류의 거짓말이다. 대신 "승인 시 조정 예정"으로 남긴다.
* 전환 투자비 22억과 `review-case.ts`의 연간 회수 18억은 회수 기간 약 1.2년으로 맞물린다.
  한쪽을 바꾸면 다른 쪽도 함께 본다.

### 4.11 대안 비교의 3요소 · 신호의 출처 · 개선 대상 3축

기획안의 세 요구를 각각 구조로 옮긴 것이다.

**대응 대안은 효과·비용·위험·실행 조건을 함께 제시한다** (기획안 2.1)
* 비용은 `lever.costPerUnit`으로 **레버에 비례**한다. 비용이 고정이면 레버를 끝까지 올리는
  것이 항상 정답이 되어 트레이드오프가 사라진다.
* 비용(일회성)과 효과(연간)는 **시간 단위가 다르므로 차감하지 않는다.** 단순히 빼면
  첫해 기준 손해처럼 보이는 잘못된 그림이 된다. 대신 회수 기간(`paybackYears`)으로 본다.
  비용·효과가 모두 선형이라 회수 기간은 레버와 무관하게 일정한데, 이는 의도한 단순 모델의
  귀결이다(4.7 "백테스트는 공식이 아니라 표다"와 같은 태도).
* `prerequisites`(실행 조건)가 없는 대안은 만들지 않는다 — 조건 없이 효과만 적힌 대안은
  비교가 아니라 홍보다.
* 1안 전환 투자비 22억은 `rolling-plan.ts`의 Plan 항목과 같은 값이다. 한쪽을 바꾸면 함께 본다.

**관측된 사실과 예측·가정을 구분한다** (기획안 3.2)
* `RiskSignal.origin` — `observed`(현재 실적의 편차) / `leading`(선행 위험).
* `leading`에는 `assumption`을 반드시 적고 화면에 함께 띄운다. 그 가정이 틀리면 위험 자체가
  성립하지 않는다. `observed`에는 가정을 두지 않는다 — 사실에 가정을 붙이면 사실이 흐려진다.

**개선 대상은 Framework · Process · Agent 셋이다** (기획안 3.5)
* `ProposalKind`를 `targetOf()`로 이 세 축에 매핑하고 화면에 축별 건수를 표시한다.
  한 축이 0건이면 눈에 띈다 — 실제로 Process가 0건이어서 이 갭을 발견했다.

### 4.12 데이터 불완전성과 판단 불확실성

기획안 2.1("데이터의 불완전성")과 3.6("정보 부족이나 판단 불확실성이 있을 때의 처리
방식")을 구조로 옮긴 것이다. **Agent가 늘 확신에 찬 결론만 내면 사람이 검증할 지점이
없어진다.**

* `DataSource`는 이름만이 아니라 **품질**을 들고 있다 — `complete` / `partial`(결손) /
  `stale`(최신성) / `estimated`(추정). `complete`가 아니면 `caveat`에 무엇이 어떻게
  불완전한지 반드시 적는다. 라벨만으로는 결론을 얼마나 믿어야 할지 알 수 없다.
* caveat는 **툴팁에만 넣지 않는다.** 데이터가 어떻게 불완전한지는 결론을 읽을 때 같이
  보여야 하는 정보이지 마우스를 올려야 알 수 있는 부가 정보가 아니다.
* `AgentRun.confidence`로 산출물 신뢰도를 밝히고, `high`가 아니면 이유를 적는다.
* **정보가 부족하면 Agent는 추측하지 않고 묻는다**(`AgentEscalation`). 질문·못 답하는
  이유·답할 사람과 함께, 답을 받지 못한 채 진행할 때 어떤 가정 위에 서는지
  (`ifUnanswered`)를 남긴다 — 나중에 결론이 틀렸을 때 어디서 갈렸는지 되짚기 위해서다.
* 미답 질문은 협업 스테이션에서 **보고서보다 먼저** 보여 준다. 결정의 전제이므로
  "무엇을 모른 채 결정하는지"를 알고 승인해야 한다.
* 이 필드들도 "미완료 Agent의 산출물은 감춘다" 규칙(4.5)을 그대로 따른다 — 실행 중인
  Agent의 신뢰도·질문은 노출되지 않는다.

### 4.13 시나리오 구조 (기획안 4.2)

시나리오는 `lib/mock-data/scenarios.ts` 레지스트리에 등록한다. **세 번째를 붙일 때도 이
파일에 한 항목을 더하는 것으로 끝나야 한다** — 화면이나 스토어를 고쳐야 한다면 구조가
시나리오에 묶여 있다는 뜻이다.

**시나리오 소유 vs 전사 공유**

| 시나리오 소유 | BPM 프로세스 인스턴스, Review 안건, 데모 장면, 진행 지점, 결정 |
| 전사 공유 | Framework(KPI·KRI·Control), Rolling Plan, Evolution Lab, 리스크 신호 |

전사 자산을 시나리오마다 복제하면 재사용이 아니라 복사다. Rolling Plan은 **모든 시나리오의
승인 과제를 함께** 받고(`decisionByScenario`를 순회), Framework는 두 안건의 KRI를 같은
표에 놓는다. 전사 Gap은 하나이고 여러 안건이 그것을 나눠 메우므로 합산이 한곳에서 맞아야 한다.

* 스토어는 진행 지점·결정·장면을 **시나리오별 맵**으로 들고 있다. 하나만 들고 있으면 시나리오를
  오갈 때 앞 시나리오의 상태가 딸려 가거나 초기화된다. 읽을 때는 `selectStepIndex` 등
  선택자를 쓴다(원시값만 돌려주므로 리렌더가 새지 않는다).
* 승인 후 이동 지점은 노드 id를 고정하지 않고 **user-task의 다음 지점**으로 계산한다
  (`approvalStepIndex`) — 시나리오마다 승인 단계 이름이 다르다.
* 두 시나리오는 기획안 3.3의 **두 경로를 나눠 맡는다**: 시나리오 1은 부서 간 조정이 필요해
  Management Review로 에스컬레이션되고, 시나리오 2는 구매·생산 권한 안이라 현업 통제로
  처리된다. 결정 주체도 경영진 vs 구매본부로 다르지만 화면과 규칙은 그대로 재사용한다.

**시나리오를 붙이며 드러난 것** — 매번 하나씩 나왔고, 그때마다 구조를 고쳤다:
* **시나리오 2**: 대안의 부수 효과가 `utilizationPerUnit`(가동률)으로 타입에 박혀 있었다.
  납기 안건에는 맞지 않아 `secondaryLabel`/`secondaryUnit`/`secondaryPerUnit`으로 일반화했다.
* **시나리오 3**: `app/api/mock/datasets.ts`가 시나리오별 데이터셋을 하드코딩하고 있어
  시나리오마다 두 항목씩 손으로 더해야 했다. 레지스트리에서 생성하도록 바꿨고,
  같은 데이터를 가리키던 옛 이름(`bpm-process`·`review-case`)은 중복이라 제거했다.

**시나리오 3에서 화면·스토어·서비스는 한 줄도 고치지 않았다.** 새 데이터 파일 2개,
장면 배열 1개, 레지스트리 1항목, 그리고 전사 자산(리스크 신호·Framework)에 축 하나를
더한 것이 전부다. 장면별 설계표도 손대지 않았는데 시나리오 3을 자동으로 잡는다.

**결정의 성격이 셋 다 다르다** — 이것이 기획안 4.2의 "추가로 보여줄 경영 가치"다:
1번은 조치(에스컬레이션·경영진), 2번은 조치(현업 권한 내), 3번은 **배분**이다.
배분은 어느 대안을 골라도 반대편이 줄어 비용이 0인 안이 없고, 회수가 빠른 안이 곧
좋은 안도 아니다(2안은 0.5년이지만 신사업 시점 경쟁력을 포기한다).

### 4.14 장면별 설계표 (기획안 4.2)

`docs/scene-design.md`는 **손으로 쓰지 않고 구현에서 생성한다**(`services/scene-design.ts`).

```bash
curl -s http://localhost:3000/api/docs/scene-design > docs/scene-design.md
```

* 설계표는 기획안 4.2가 "Business 설계를 BPM과 Agent 구현으로 연결하는 공통 명세"로
  규정한 문서다. 손으로 쓰면 구현이 바뀔 때 문서만 낡아 명세로서 쓸모가 없어진다.
  **데이터를 고친 뒤 다시 생성할 것.**
* 코드에 근거가 없는 항목은 지어내지 않고 `미정의 — 경영 판단 기준 작성 필요`로 남긴다.
  현재 140행 중 9칸이며, Mock에 `outcome`이 없는 후반 노드들이다. 기획안은 경영 내용을
  임근석 박사가 주도한다고 했으므로 이 칸은 사람이 채울 자리다.
* **사람·시스템 노드의 입력은 선행 Agent 산출물이다.** 경영진은 원천 데이터가 아니라
  Agent 보고서를 보고 판단한다. 처음엔 해당 노드의 실행 기록만 봐서 Management Review의
  입력이 "미정의"로 나왔다 — 생성기를 쓸 때 이 경로를 빠뜨리기 쉽다.

### 4.15 테스트

`tests/`에 Vitest로 **순수 로직만** 검증한다(139개). 엔진 테스트는 `engine/tests/`에
pytest로 따로 있다(56개) — 4.16 참조. 렌더링 테스트는 두지 않았다 —
jsdom과 React 플러그인 없이 node 환경에서 1초대에 끝나고, 레이아웃·가독성처럼 계산으로
못 잡는 것은 어차피 브라우저에서 눈으로 봐야 한다.

| 파일 | 무엇을 잠그는가 |
|---|---|
| `invariants.test.ts` | 화면 간 수치 연동 항등식 (4.6) — 합산, 브릿지, 분기 합, 시나리오 간 연결 |
| `bpm-engine.test.ts` | 상태 파생 규칙 (4.5) — skipped/waiting 판정, **미완료 Agent 산출물 은닉**, 승인 지점 |
| `engine-spec.test.ts` | 엔진 명세 생성 (4.16) — 게이트웨이 분기 규칙, **Mock 플래그가 선언된 경로와 일치하는지**, 시나리오 전환 시 대안 선택 |
| `engine-view.test.ts` | 엔진 스냅샷 → 뷰모델 (4.17) — **미완료 산출물 은닉**, 모르는 상태 값 처리, 결정·단계·소요시간·Evolution 산출물 파생 |

엔진 쪽은 `engine/tests/`에 pytest로 있다 — **SQLite와 Postgres 두 백엔드를 모두 돌린다**
(41개 / 61개). 자리표시자·행 접근·날짜 타입이 전부 달라 한쪽만 돌리면 나머지가 배포
시점에 터진다.
| `rolling-plan.test.ts` | **이중 계상 금지** (4.6·4.17), 승인→과제 변환, Plan 조정, Mock↔엔진 승인 병합 |
| `framework.test.ts` | KPI–KRI–Control 연결 무결성 (4.8), 이탈 판정 방향 |
| `simulation.test.ts` | 선형 관계·회수 기간·등급 단조성, 시나리오 레지스트리 무결성 |
| `metrics.test.ts` | 표기 유틸, 경영 수행 성과가 **실제 데이터에서 계산되는지** (4.9), 엔진 실측값 반영 (4.17) |

* 검증 대상은 **이미 한 번 이상 실제로 틀렸던 것들**을 우선했다. 미완료 산출물 은닉은
  두 경로로 새어 나갔고, 이중 계상과 자리표시자 노출은 숫자가 그럴듯해 눈으로 안 잡힌다.
* 테스트를 넣으면서 실제 불일치를 하나 잡았다 — BMS 라인 수율의 감지 임계치가 리스크
  신호에만 `95.0%`(목표값)로 적혀 있었다. Framework·Evolution Lab·백테스트는 모두 `90`이다.
* 엔진을 붙이면서 또 하나 잡았다 — 승인 후 진행 지점이 0으로 돌아가는 버그(4.16).
  **두 번 다 "화면 간 연동"을 주장하는 지점에서 나왔다.** 데모 플레이어가 상태를 절대값으로
  덮어쓰기 때문에 데모로는 드러나지 않는 종류다.
* `vitest.config.mts`가 `.mts`인 이유와 `resolve.tsconfigPaths`는 그 파일 주석에 적어 두었다.
* `@types/node`는 `^20`에서 `^22`로 올렸다. 런타임이 Node 22인데 스캐폴딩 값이 20이라
  Vitest peer dependency와 충돌했다 — 우회가 아니라 실제와 맞춘 것이다.

### 4.16 BPM 엔진 (Python · LangGraph)

`engine/`이 실제 상태 머신이다. 자세한 것은 `engine/README.md`이고, 여기에는 TS 쪽에서
알아야 할 것만 적는다.

**지금까지 "상태 머신"은 배열 인덱스였다.** `sequence`가 미리 선언된 한 경로이고 노드
상태를 거기서 파생했을 뿐, 분기도 사람 승인도 실제로는 일어나지 않았다(4.5). 엔진에서는
그래프가 진짜로 멈추고(`interrupt`) 재개된다(`Command(resume=...)`), 그리고 **경로가
실행의 결과로 나온다.**

* **엔진은 토폴로지를 모른다.** 노드·엣지·Agent 정의는 `lib/mock-data/`가 유일한
  원천이고 `services/engine-spec.ts`가 명세로 만들어 보낸다. 엔진이 같은 것을 따로
  들고 있으면 시나리오를 추가할 때 양쪽을 손대야 한다 — **세 시나리오가 엔진 코드
  수정 없이 돈다.**
* **경영 규칙도 실어 보낸다** — 사유 최소 길이(`DECISION_RATIONALE_MIN_LENGTH`), 승인
  노드, 선택지. 엔진이 숫자를 다시 적으면 UI·API·엔진 세 곳이 갈라진다.
* **규칙 소유권**: Python은 "무슨 일이 일어났는가", TS는 "그것이 숫자에 어떻게
  반영되는가". 결정→과제 변환(`decisionToAction`)은 TS에 남긴다 — 이중 계상 금지
  규칙이 거기 있고 이미 테스트가 잠그고 있다.
* **분기는 결정론적, 판정은 확률적.** 게이트웨이는 상태의 플래그 하나를 읽고, 그
  플래그는 선행 Agent가 만든다. 기획안의 "Deterministic BPM + Probabilistic AI"가
  여기서 갈린다. 플래그가 없으면 `whenFalse`다 — 판정되지 않은 것을 "조정 필요"로
  보면 에스컬레이션이 기본값이 되어 현업 통제 경로가 죽는다.
* **`sourceHandle`로 분기를 판정하면 안 된다.** `main`/`branch`는 캔버스 레이아웃
  관심사이고 의미가 고정되지 않았다 — 실제로 납기 시나리오는 `main`이 "아니오"다.
  라벨 문자열("예"/"아니오")을 읽는 것도 표기를 바꾸면 깨진다. 규칙은
  `BpmNodeSpec.decision`에 명시한다.
* **미실행 판정이 TS보다 정확하다.** TS는 `sequence`에 없는 노드를 처음부터 `skipped`로
  봤지만, 실제로는 게이트웨이가 돌기 전까지 그 분기는 `pending`이다.
* **미완료 Agent 산출물 은닉이 규칙에서 구조로 바뀐다.** 노드가 돌기 전에는 기록 자체가
  없다 — TS에서 두 경로로 새어 나갔던 종류의 실수가 성립하지 않는다.
* **Agent가 계약을 못 맞추면 지어내지 않고 502로 실패한다.** `kimi-k3:cloud`는 ollama의
  `format` 스키마를 무시하므로(마크다운 산문이 온다) 스키마를 프롬프트에 넣고 검증·
  재시도한다. 조용히 그럴듯한 값으로 메우면 Agent가 고장난 것을 아무도 모른다.
* 산출물마다 `provenance`(`mock` · `mock-missing` · `llm:<model>`)가 붙는다. 인스턴스는
  **생성 시 모드로 재개된다** — 섞이면 어느 것이 실제 호출인지 알 수 없다.
* **엔진이 꺼져 있는 것은 고장이 아니다.** 앱은 Mock만으로 전부 동작하므로
  `engine-client.ts`는 연결 실패를 throw하지 않고 `{ ok: false }`로 돌려준다.
* **저장 백엔드는 `DATABASE_URL` 유무로 갈린다** — 있으면 Postgres, 없으면 파일 SQLite.
  로컬에서 DB를 띄우라고 요구하면 위의 "엔진 없이도 동작한다"가 깨지므로 기본값을
  마찰 없는 쪽에 둔다. 다만 **SQLite로는 운영할 수 없고**(워커마다 파일이 갈라진다),
  연결 실패를 SQLite로 조용히 되돌리지 않는다 — 운영에서 DB가 안 붙었다면 즉시
  드러나야 한다. `/health`의 `storage`가 어느 쪽인지 알려 준다.
* **`PostgresSaver`는 `autocommit=True`와 `row_factory=dict_row`를 요구한다.** 문서에만
  있고 타입으로는 드러나지 않아 빠뜨리기 쉽다.

**엔진을 붙이며 드러난 것** — 둘 다 TS만 볼 때는 보이지 않았다:

1. **`op-control`에 나가는 엣지가 없다**(시나리오 1·3). `sequence`에 없어 `skipped`로
   조용히 넘어가므로 아무도 눈치채지 못했다. 엔진은 END로 잇고 `specWarnings`로 알린다.
   현업 통제로 끝났을 때 루프가 어디로 가는지는 경영 판단이라 **지어내지 않았다** —
   4.14의 "미정의" 칸과 같은 성격으로 사람이 채울 자리다.
2. **승인 후 진행 지점이 0으로 돌아갔다.** `approvalStepIndex`가 `nodes` 배열 순서로
   첫 `user-task`를 찾아 선택되지 않은 분기의 `op-control`을 집었고, 그 노드가
   `sequence`에 없어 `indexOf`가 -1이 됐다. 시나리오 1·3에서 깨져 있었고(2는 우연히
   맞았다) 데모 플레이어가 장면마다 `step`을 절대값으로 덮어써서 가려져 있었다.
   `services/bpm-engine.ts`의 `approvalNodeId`로 올리고 테스트로 잠갔다.

### 4.17 화면 ↔ 엔진 (모드 공존)

②·③은 엔진 모드로 옮겨 타고, ④는 엔진 승인을 과제로 받고, **①⑤는 엔진이 소유하는
조각만** 받는다.

**화면 전체를 옮기지 않는다.** ①의 전사 스냅샷(매출·영업이익·브릿지·사업부)과 Framework,
⑤의 백테스트·개선 제안은 엔진이 소유하지 않으므로 옮기면 정적 렌더만 잃는다
(4.16 규칙 소유권). 옮기는 것은 "무슨 일이 일어났는가"에 해당하는 조각뿐이다:

| 화면 | 엔진이 소유하는 조각 |
|---|---|
| ① | Agent 분석 소요시간(실측), 안건이 **실제로** 도달한 단계 |
| ⑤ | Evolution Agent가 실행한 산출물 |

* **`Provenance`에 `measured`를 더했다.** `system`(Mock에서 계산)과 근거가 다르다 —
  소요시간은 ollama가 돌려준 실제 경과 시간이다. 둘을 같은 배지로 묶으면 "시스템
  산출값"이 실측인지 Mock 계산인지 알 수 없어 기획안 2.3의 구분이 이름만 남는다.
  세 배지가 한 화면에 공존하는 것을 확인했다.
* **빈 실행 기록은 무시한다.** 엔진을 켰지만 아직 Agent가 안 돌았을 때 0시간으로 덮으면
  "분석이 즉시 끝났다"가 된다.
* **`RiskSignal.stage`는 엔진 인스턴스가 있으면 실제 진행 지점으로 바꾼다.** 감지 화면이
  "지금 어디까지 왔나"를 틀리게 말하면 그 화면을 보는 이유가 없어진다. `riskId`로 묶는다.
* **⑤의 Agent 산출물을 정식 개선 제안(`EvolutionProposal`)으로 바꾸지 않는다.** 그 타입은
  before/after·기대효과·**트레이드오프**·담당자를 요구하는데 산출물에는 없다. 지어내면
  "부작용 없는 제안은 검토가 아니라 홍보다"(4.7)를 스스로 어긴다. 산출물은 산출물로
  보여 주고 승격은 사람의 몫으로 남긴다.
* ⑤가 전역 상태를 바꾸지 않는다는 규칙(4.6)은 그대로다 — 여기서는 읽기만 한다.

**LLM 모드에서 실제로 확인한 것** — 시나리오 1을 끝까지 돌렸다(전체 185초, Agent 4회 호출):
Evolution Agent가 "단일 임계치 85% → 3단계 구간 + 2개월 연속 이탈 조건 + 데이터 품질
게이팅"을 제안하고, **제시한 수치가 과거 분포 데이터 없이는 잠정안임을 스스로 밝혔다.**
미답 질문 4건도 함께 남겼다. 계약 검증(신뢰도가 high가 아니면 이유를 요구)이 강제한 결과다.

**드러난 공백** — `evolution` 노드에는 Mock 산출물도 참조 데이터 정의도 없다(세 시나리오
모두). 그래서 Mock 모드에서는 `mock-missing`으로, LLM 모드에서는 근거가 빈 채로 나온다.
**지어내지 않고 화면이 그 사실을 말하게 했다** — 빈 자리를 그냥 두면 "근거 없이 결론을
냈다"로 읽힌다. 4.14의 "미정의 — 경영 판단 기준 작성 필요"와 같은 자리다.

* **정적 프리렌더를 잃지 않았다.** 다섯 화면 모두 여전히 `○`다. 서버에서 엔진을 부르면
  전부 `ƒ`가 되는데, **페이지 껍데기는 정적으로 두고 엔진 데이터만 클라이언트에서**
  채우면 둘 다 얻는다. 엔진을 쓰지 않는 사람은 이전과 같은 속도로 화면을 받는다.
* **화면은 출처를 모른다.** `services/engine-view.ts`가 스냅샷을 Mock 경로와 같은 모양의
  뷰모델로 바꾸고, 컴포넌트 트리는 그대로다. 화면마다 `if (engineMode)`가 흩어지면 두
  경로가 조금씩 달라져 "엔진 모드에서만 나는 버그"가 생긴다.
* **②와 ③이 같은 인스턴스를 본다**(`use-engine-process.ts`). 따로 만들면 ②에서 실행한
  프로세스를 ③에서 승인할 수 없어, "한 사건을 여러 관점으로 본다"는 전제가 엔진
  모드에서만 깨진다.
* **스냅샷을 가져오는 곳은 `SnapshotPoller` 하나뿐이다**(레이아웃 상주). 화면·훅이 각자
  가져오면 두 가지가 깨진다: (1) **같은 화면의 두 패널이 서로 다른 순간을 본다** — ①은
  경영 수행 성과와 리스크 신호가 각각 같은 훅을 불러 실제로 두 번 가져오고 있었다.
  (2) 폴링을 붙이면 요청이 패널 수만큼 배로 늘어난다. 화면들은 스토어를 읽고
  (`lib/store/engine-snapshots.ts`), 변경(생성·재개)은 응답을 스토어에 **즉시 반영**한 뒤
  다시 읽게 한다 — 폴링 주기를 기다리면 승인했는데 한동안 옛 상태가 보인다.
* **폴링 주기는 상태에 따라 다르다**(`use-visible-poll.ts`). 실행 중이면 3초(값이 실제로
  움직인다), 멈춰 있으면 15초 — 0으로 두지 않는 이유는 변화가 **다른 탭이나 다른
  사람**에게서 올 수 있기 때문이다. 협업 스테이션에서 승인하면 Rolling Plan의 과제가
  달라지는데, 다시 읽지 않으면 새로고침해야 반영된다.
* **탭이 숨겨지면 폴링을 멈추고, 다시 보이면 즉시 한 번 읽는다.** 보이지도 않는 화면
  때문에 초당 요청이 늘면 LLM 모드의 엔진이 그만큼 느려진다. 돌아왔을 때 다음 주기까지
  낡은 값을 보여 주지 않으려면 즉시 따라잡아야 한다.
* **엔진 모드에서는 단계 이동 컨트롤을 감춘다.** 진행은 실행의 결과이므로 임의로 앞당길
  수 없다. 지난 시점을 되짚어 보는 것은 데모 플레이어가 장면 단위로 한다(4.18).
* **승인 반려는 오류가 아니라 상태다.** 사유가 짧으면 400이 아니라 같은 지점에 다시 멈춘
  스냅샷이 오므로, 입력한 내용을 지우지 않고 반려 사유만 덧붙인다.
* **금액은 화면이 계산한다.** 엔진은 "무엇을 골랐는가"(대안·레버)만 돌려주고
  `simulateAlternative`가 손익을 낸다. 엔진이 금액도 계산하면 화면·API와 갈라진다.
  반대로 **결정 시각은 엔진이 찍는다** — "무슨 일이 일어났는가"의 일부이고, 화면이
  찍으면 새로고침할 때마다 값이 달라진다.
* **엔진이 꺼져 있는 것은 고장이 아니다.** 연결 실패는 배너로 알리고 화면은 Mock으로
  계속 동작한다.

**④ Rolling Plan은 성격이 다르다.** ②·③은 지금 보는 한 시나리오의 인스턴스를 다루지만,
④는 전사 자산이라 **모든 시나리오의 승인 과제를 함께** 받는다(4.13). 인스턴스가 여럿이면
여럿을 다 읽어야 합산이 맞는다.

* **이중 계상을 `mergeDecisions`가 막는다.** 한 시나리오에 엔진 인스턴스가 붙어 있으면
  그 시나리오의 권위는 엔진에 있다 — Mock 결정과 함께 더하면 같은 승인이 두 번 잡히고
  **금액이 그럴듯해서 눈으로는 잡히지 않는다.** 실측으로 확인했다: 같은 시나리오에 Mock
  9억과 엔진 4.8억을 함께 두었을 때 합계가 37억이 아니라 28억으로 남았다.
* **엔진이 소유했지만 아직 승인 전이면 Mock 결정을 되살리지 않는다.** 실행 중인 그래프가
  승인 지점에 닿지도 않았는데 과제가 잡히면, 결정되지 않은 계획을 확정된 것처럼
  표시하는 셈이다(4.10과 같은 이유).
* **엔진 조회가 실패해도 Mock으로 조용히 되돌아가지 않는다.** 되돌아가면 승인이 두 번
  잡힌다. 대신 오류 배너와 함께 **몇 건이 목록에서 빠졌는지** 밝힌다 — 조용히 넘기면
  Gap이 실제보다 덜 메워진 것으로 보이는데 그것도 눈으로 안 잡힌다.
* **결정 변환은 ③과 ④가 같은 함수를 쓴다**(`engineDecisionToReview`). 각자 변환하면
  협업 스테이션이 보여주는 금액과 과제 목표액이 갈라질 수 있다.

**여기서 드러난 것** — 둘 다 데모가 가려 놓고 있었다:

1. **루트 `app/loading.tsx`가 화면을 두 벌로 만들었다.** 앱 전체에 Suspense 경계가
   생기면서 스트리밍 교체가 끝나지 않아 서버 HTML(기본 시나리오)과 클라이언트 렌더가
   **둘 다 DOM에 남았다**(`<main>`이 2개). 손대지 않은 화면에서도 재현됐다. 다섯 화면이
   정적이라 덮을 서버 대기 자체가 없어 이득도 없으므로 제거했다 — 로딩 표시는 엔진
   패널 안의 것으로 충분하다. `app/error.tsx`는 Suspense가 아니라서 무관하며 유지한다.
2. **시나리오를 바꾸면 다른 시나리오의 대안이 승인됐다.** `selectedId`·`leverValue`가
   `useState`로 첫 렌더 값만 잡는데, 화면이 정적 프리렌더라 첫 렌더는 항상 기본
   시나리오다. 스토어 복원으로 시나리오가 바뀌어도 id가 남아 새 목록에 없으니
   `alternatives[0]`으로 떨어진다 — 시나리오 3에서 권고안(3안)이 아니라 1안이,
   레버도 시나리오 1의 값(2)이 기록됐다. 렌더 중 조정 패턴으로 고쳤다
   (effect로 고치면 `react-hooks/set-state-in-effect`에 걸린다).

### 4.18 데모 플레이어 × 엔진 (되감기)

**"실행 중인 그래프는 시간을 되감을 수 없다"고 여러 번 적어 두었는데 틀렸다.** LangGraph는
노드마다 체크포인트를 남기므로 지난 시점을 되짚어 볼 수 있다. 그래서 데모 플레이어가 엔진
모드에서도 동작한다 — 장면이 선언한 지점(`DemoScene.step` → `sequence[step]` 노드)으로
인스턴스를 옮긴다(`engine/app/seek.py`, `use-engine-playback.ts`).

**두 방향의 성격이 완전히 다르다.**

| | 동작 | 인스턴스 |
|---|---|---|
| 뒤로 | 그 시점 체크포인트를 **읽기만** 한다 | 그대로 |
| 앞으로 | 사람 대기마다 장면이 선언한 입력을 넣어 **실행**한다 | 진행한다 |

* **뒤로 가기를 실행으로 구현하면 안 된다.** 과거 체크포인트의 config로 `invoke`하면 위치만
  옮기는 게 아니라 **거기서부터 다시 실행된다** — Agent 노드는 멈추지 않으므로 다음 사람
  대기까지 가 버리고, 그 과정에서 (1) **LLM을 다시 호출하고** (2) 이미 내려진 승인이
  사라진다. 실제로 그렇게 만들었다가 테스트에서 드러났다. 스크러버를 15회 움직인 뒤에도
  인스턴스가 온전한 것을 확인했다(종료 상태·결정·산출물 4건 보존, LLM 재호출 0회).
* **읽기 전용이라도 화면이 보는 것은 같다.** 승인 이전 시점의 스냅샷에는 `decision`이 없으니
  "역방향으로 점프하면 승인이 지워진다"(4.1)가 표시 수준에서 그대로 성립한다. 차이는
  인스턴스의 실제 진행이 파괴되지 않는다는 것뿐이고, 그 편이 맞다.
* **멈출 수 있는 곳은 사람 대기 지점뿐이다.** 목표가 Agent·시스템 노드면 지나쳐 다음
  대기까지 간다 — 그 상태를 그대로 주면 장면이 가리킨 지점이 아니라 그보다 앞선 화면이
  보이므로, 지나쳤으면 그 지점을 되짚어 돌려준다.
* **엔진이 임의로 승인하지 않는다.** 목표가 승인 노드보다 뒤면 호출자가 결정을 함께 줘야
  하고, 장면이 "아직 승인 전"이라고 선언했으면 결정을 보내지 않는다. 승인 이전 장면을
  통과시켜 버리면 각본과 화면이 어긋나고, 무엇보다 Human-in-the-Loop이 무너진다.
* **과거 시점에서는 승인할 수 없다**(`historical`). 표시하지 않으면 지금 결재할 수 있다고
  착각한다. 패널에 "현재로" 버튼을 둬 라이브로 돌아온다.
* **표시용 스냅샷은 스토어에 둔다**(`viewByScenario`). 되감기가 읽기 전용이라 다시 조회하면
  "지금"이 와 버린다. 서버가 돌려준 과거 스냅샷을 들고 있는 것이므로 지어낸 값이 아니고,
  저장하지 않는다(새로고침하면 라이브로 돌아간다).
* **`revision` 카운터로 화면들을 함께 갱신한다.** 플레이어가 seek하면 ②③④⑤가 모두 같은
  변화를 봐야 하는데, 훅마다 상태를 따로 들고 있으면 한 화면만 바뀐다.
* 장면 이동은 **스토어 상태를 먼저 적용하고** 엔진 왕복을 비동기로 던진다 — LLM 모드에서
  수십 초를 기다리는 동안 화면이 멈춰 있으면 플레이어가 고장난 것처럼 보인다.

**자동 재생은 `setInterval`이 아니라 자기 예약 루프다.** 7초마다 넘기면 Mock 모드에서는
맞지만 LLM 모드에서 깨진다 — 앞 장면의 왕복이 수십 초인데 타이머는 그것을 모르고 다음
장면을 발사하므로 요청이 겹치고, 화면은 아직 반영되지 않은 장면의 내레이션을 읽는다.
**장면이 반영된 뒤에 머무름을 시작한다**: 한 장면의 체류 = 엔진 왕복 + `DEMO_SCENE_INTERVAL_MS`.

* **`jump`을 effect 의존성에서 빼는 것이 핵심이다.** `jump`은 `pathname`에 의존하는데,
  장면이 화면을 바꾸면 effect가 재실행되고 머무름 타이머가 처음부터 다시 걸린다 — 왕복이
  40초여도 7초 뒤에 다음 장면이 발사되어 **고치려던 문제가 그대로 남는다.** ref에 최신
  `jump`을 담아 쓰고, ref는 렌더 중이 아니라 effect에서 갱신한다(`react-hooks/refs`).
* **요청에 일련번호를 붙인다.** 왕복이 긴 동안 사람이 다른 장면을 누르면 두 요청이 겹치고,
  먼저 보낸 것이 나중에 도착하면 화면이 뒤로 튄다. 최신 요청의 응답만 반영한다.
* **엔진이 실패하면 자동 재생을 멈춘다.** 계속 넘어가면 화면과 인스턴스가 어긋난 채로
  데모가 진행된다. `skipped`(엔진 없음)는 실패가 아니므로 구분한다.
* **실측으로 확인했다.** `seek` 응답을 12초 늦춘 상태에서 장면 간격이 **21초**(= 12 + 7 +
  오버헤드)로 나왔고, 옛 동작이면 7초 고정이었다. 장면 8개를 완주하며 `seek` 호출이 정확히
  **7회**(전환 수와 동일)로, 겹침도 누락도 없었다. 엔진 없는 Mock 모드는 기존과 같은 8초다.

---

## 5. 다음 단계와 선행 조건

셋 다 끝났다 — CI(5.1), LangGraph 엔진과 Postgres·Docker(5.2), ②·③의 엔진 전환(5.3).
각 절에 **남은 것**을 따로 적어 두었다.

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
* 데이터가 전부 Mock 코드고 **Agent 노드도 기본이 Mock이라 LLM 자격증명 없이 전부
  검증된다.** 시크릿도 서비스 컨테이너도 아직 필요 없다.

**engine 잡에서 알아둘 것:**

* **Python 버전의 원천은 `engine/.python-version`이다.** 워크플로에 또 적으면 로컬
  venv와 CI가 갈라진다 — `node-version` / `@types/node`에서 겪은 것과 같은 문제다.
  `uv`가 없는 인터프리터를 직접 내려받으므로 `setup-python`이 필요 없다.
* `uv sync --locked`가 `npm ci`의 몫을 한다 — `uv.lock`이 `pyproject.toml`과 어긋나면
  바로 실패한다. 실제로 의존성을 하나 더해 확인했다.
* **ollama 실호출 테스트(`-m llm`)는 CI에 넣지 않는다.** 비결정적이고 모델 자격증명이
  필요하다. `pyproject.toml`의 `addopts`가 기본으로 제외하므로 워크플로에 플래그가 없다.
  계약 검증(`_validate`)은 네트워크 없이 돌아 CI가 잡는다.
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

### 5.2 LangGraph 엔진 — 골격 완료

`engine/`에 FastAPI + LangGraph StateGraph가 있고, Next의 `/api/engine/*`가 프록시한다.
설계와 함정은 4.16과 `engine/README.md`에 있다. **런타임은 Python으로 정했다** — JS
포트로도 되지만(Postgres checkpointer까지 있다) 분석 에이전트 생태계·룰을 손댈 사람·
레퍼런스 구현이라는 이유다.

확인한 것:

* 세 시나리오 모두 인스턴스 생성 → Agent 실행 → 승인 대기 → 재개 → 종료까지 돈다.
  **엔진이 실제로 간 경로가 TS `sequence`와 일치한다.**
* 승인 사유 10자 미만은 엔진이 반려하고 같은 지점에 다시 멈춘다(400이 아니라 상태다).
* `kimi-k3:cloud` 실호출이 산출물 계약을 지킨다(`pytest -m llm`, 약 40초).
* 재시작해도 인스턴스가 복구된다(명세를 checkpointer와 함께 저장한다).
* **Postgres 백엔드와 `docker compose` 스택이 돈다.** 엔진 컨테이너를 재시작해도 승인
  대기 중이던 인스턴스가 같은 지점에서 이어진다 — Postgres를 쓰는 이유가 그것이다.

**남은 것:**

* **LLM 비용·레이트·타임아웃 관리** — 지금은 Agent 노드마다 10초 이상이고 재시도가
  붙는다. 노드가 많은 프로세스에서는 전체 지연이 누적된다.
* **화면이 엔진을 쓰게 하는 일** — 5.3.

**테스트 전략이 예고대로 갈렸다.** 실측으로 확인했다 — temperature 0인데도 같은 질문에
`14.2`와 `14.5`가 나왔다.

| 지금 | 실 엔진에서 |
|---|---|
| 전사 합산·브릿지 균형·분기 합 | **그대로 유효** — 데이터 출처와 무관한 불변식이다 |
| "Simulation Agent 산출물 문구에 `+18억`이 있다" | **성립하지 않음** — Mock 모드에서만 유효하다 |
| 파생 규칙(skipped/waiting, 산출물 은닉) | **더 중요해졌다** — 실행 중 상태가 진짜로 생긴다 |

그래서 LLM 경로는 값이 아니라 **계약**을 검증한다(스키마, 열거값 범위, 근거 소스가
비어 있지 않은가, 신뢰도가 high가 아니면 이유가 있는가). `engine/tests/test_agents.py`가
그 예다.

**데모 플레이어는 두 모드 모두에서 동작한다**(4.18). "실행 중인 그래프는 시간을 되감을
수 없다"고 적어 두었던 것은 **틀렸다** — LangGraph는 노드마다 체크포인트를 남기므로 지난
시점을 되짚어 볼 수 있다.

### 5.3 화면 → 엔진 전환 — 완료 (다섯 화면)

②·③이 엔진 모드로 옮겨 타고, ④가 엔진 승인을 과제로 받고, ①⑤가 엔진이 소유하는 조각을
받는다. 설계와 함정은 4.17에 있다. **다섯 화면 모두 정적
프리렌더(`○`)를 유지했다** — 클라이언트에서만 엔진을 부르기 때문이다.

**화면 전체를 옮긴 것은 하나도 없다.** 각 화면에서 엔진이 실제로 소유하는 조각만 클라이언트
컴포넌트로 감쌌다 — 전사 수치·Framework·백테스트는 그대로 Mock이다(4.16 규칙 소유권).

**남은 것:**

* **실시간성이 아직 폴링이다**(실행 중 3초 / 대기 15초, 탭이 보일 때만). 다섯 화면이 같은
  폴러를 쓰므로 요청 수는 인스턴스 수에 비례한다. 인스턴스가 많아지면 SSE로 바꿔야 하고,
  그때 React Flow 캔버스가 갱신마다 다시 그려지지 않도록 주의가 필요하다.
  **실측**: 멈춘 상태에서 15.7초 주기, ①(패널 2개)에서도 주기당 조회 1회.
  외부에서 승인한 것이 새로고침 없이 1.5초 만에 ④에 반영됐다(5억 → 23억).
* **여러 사람이 같은 인스턴스를 볼 때의 충돌** — 지금은 마지막 요청이 이긴다.
  다만 폴링이 15초 안에 서버 상태를 따라잡으므로 오래 어긋나 있지는 않다.
* **데모 플레이어와 엔진 모드는 여전히 분리되어 있다.** 의도한 것이다(4.17).
