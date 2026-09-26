# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
npm run dev     # 개발 서버 (Turbopack)
npm run build   # 프로덕션 빌드 — TypeScript 타입 검사를 포함한다
npm run lint    # eslint (flat config: eslint.config.mjs)
npm run start   # 빌드 산출물 실행
```

* **타입 검사 단독 실행**: `npx tsc --noEmit`. `npm run build`가 타입 검사를 겸하므로 별도 `typecheck` 스크립트는 두지 않았다.
* **테스트 러너 미설치.** 테스트를 도입하면 여기에 러너와 **단일 테스트 실행 방법**을 함께 기록한다.
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
│       └── bpm/                  # state · transition · decision
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
└── services/
    ├── bpm-engine.ts             # 워크플로우 상태 파생
    ├── agent-orchestrator.ts     # Agent 활동 + 대안 시뮬레이션
    ├── rolling-plan.ts           # Gap 집계, 결정→과제 변환
    └── evolution-lab.ts          # 임계치 백테스트 조회
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
* **장면 이동은 한 핸들러에서 상태 적용과 라우팅을 함께 한다.** 상태를 감시하는 effect로
  라우팅하면 사용자가 GNB로 직접 이동했을 때 플레이어가 되돌려 버리는 싸움이 난다.
* `DEMO_DECISION.decidedAt`은 **고정 문자열**이다. 스토어가 모듈 로드 시점에 만들어지므로
  `new Date()`를 쓰면 서버와 클라이언트 값이 달라져 하이드레이션이 깨진다.
  금액은 `simulateAlternative`로 계산해 화면·API와 같은 값이 되게 한다(하드코딩 금지).
* 자동 재생의 `setState`는 타이머 콜백 안에서만 일어난다 — effect 본문에서 상태를 바꾸면
  `react-hooks/set-state-in-effect`에 걸린다.
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
```

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
* **화면들은 아직 이 API를 쓰지 않는다.** 다섯 화면 모두 `lib/mock-data/*`를 직접 import해
  정적 프리렌더를 유지한다. API는 외부 소비자(별도 클라이언트, Python 서비스)를 위한 경계다.
  화면을 API로 옮기면 정적 렌더를 잃으므로, 실제 백엔드가 붙을 때 함께 판단할 것.

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
