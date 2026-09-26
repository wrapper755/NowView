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

아래는 **목표 구조**다. 실제 구조가 이 트리와 갈라지면 실제 구조를 기준으로 삼고 이 절을 갱신한다.

**현재 구현된 것** — ① Executive Cockpit, ② Live BPM & Agent Process Tracker:
* `app/{layout.tsx,page.tsx,globals.css}`, `app/bpm-tracker/page.tsx`
* `components/cockpit/*`, `components/flow/*`(BPMN 노드·캔버스), `components/bpm/*`(트래커 패널),
  `components/ui/*`(card·badge·separator·progress·button), `components/theme-provider.tsx`·`theme-toggle.tsx`
* `lib/types/{cockpit,bpm}.ts`, `lib/mock-data/{next-automotive,bpm-process}.ts`, `lib/store/demo-controller.ts`,
  `lib/format.ts`, `lib/utils.ts`, `services/{bpm-engine,agent-orchestrator}.ts`, `.claude/launch.json`

4장 트리와 다른 점: 트래커 화면의 비-플로우 패널은 `components/bpm/`에 둔다 —
`components/flow/`는 React Flow 노드·엣지·캔버스 전용으로 좁혀 쓴다.

**아직 없는 것** — `app/workspace/`·`rolling-plan/`·`evolution/` 3개 화면, `app/api/`,
`components/workspace|demo`(플로팅 데모 플레이어 포함). GNB는 이 3개를 "준비중"으로 비활성 표시하며,
라우트를 만들 때 `app/layout.tsx`의 `NAV_ITEMS`에 `href`를 채운다.

### 4.2 BPM 상태 모델

**노드 상태는 저장하지 않고 파생한다.** 실행 순서(`BpmProcessInstance.sequence`)와 현재 진행 지점이
유일한 진실이고, 노드별 상태·Agent 실행 상태는 전부 `services/`에서 계산한다
(`deriveNodeStatuses`, `agentActivities`). 노드마다 status 필드를 두면 순서와 상태가 곧 어긋난다.

* `sequence`에 없는 노드는 선택되지 않은 분기이므로 자동으로 `skipped`가 된다.
* 현재 지점의 노드가 `user-task`면 `active`가 아니라 **`waiting`**(승인 대기)이다 —
  경영진이 "지금 내 결재가 걸려 있는지"를 구분해야 한다.
* **아직 완료되지 않은 Agent의 산출물은 어느 패널에서도 보여주지 않는다.** 미래 결과를 미리 노출하면
  분석이 이미 끝난 것처럼 읽힌다. 노드 상세 패널에서 이 검사를 빠뜨려 한 번 새어 나온 적이 있으므로,
  `run`을 넘기기 전 상태가 `done`인지 확인한다.

### 4.1 데이터 시각화 규칙

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
* 모든 차트에는 표 뷰를 둔다(값이 툴팁에만 갇히면 접근성 위반). `OpBridgeChart`의 "표로 보기"가 그 예다.

```text
NowView/
├── CLAUDE.md
├── AGENTS.md                     # next dev 자동 생성 (Next.js 에이전트 규칙)
├── components.json               # Shadcn 설정
├── package.json
├── tsconfig.json
├── app/
│   ├── layout.tsx                # 전사 레이아웃, GNB, 데모 컨트롤러
│   ├── page.tsx                  # ① Executive Cockpit (대시보드)
│   ├── bpm-tracker/              # ② Live BPM & Agent Process Tracker
│   │   └── page.tsx
│   ├── workspace/                # ③ Human-Agent Collaboration Station
│   │   └── page.tsx
│   ├── rolling-plan/             # ④ Rolling Plan & Action Tracker
│   │   └── page.tsx
│   ├── evolution/                # ⑤ Management Evolution Lab
│   │   └── page.tsx
│   └── api/
│       ├── mock/                 # 부품사 Mock Data API
│       └── bpm/                  # BPM & Agent 상태 전이 API
├── components/
│   ├── ui/                       # Shadcn 공통 UI 컴포넌트
│   ├── cockpit/                  # Waterfall 차트, 듀얼 매트릭스 카드
│   ├── flow/                     # React Flow 기반 BPMN 노드/엣지 커스텀
│   ├── workspace/                # Agent Report Viewer, 시뮬레이터 슬라이더
│   └── demo/                     # Demo Scenario Controller (플로팅 플레이어)
├── lib/
│   ├── store/                    # Zustand Demo Controller 상태
│   ├── types/                    # BPM, Agent, Financial Data 타입 정의
│   └── mock-data/                # 1조원 부품사 재무/운영 JSON 데이터
└── services/
    ├── bpm-engine.ts             # 워크플로우 상태 제어 인터페이스
    └── agent-orchestrator.ts     # Multi-Agent 분석 및 시뮬레이션 호출기