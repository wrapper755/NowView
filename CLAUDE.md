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
* **Process Visualization**: `@xyflow/react` (React Flow)
* **Data Visualization**: **Recharts** (단일 차트 라이브러리), Lucide React
* **State Management**: Zustand (시나리오 데모 플레이어 상태 관리용)
* **Backend / API**: Next.js Server Actions & Route Handlers (FastAPI/Python LangGraph 연동 지원)
* **Workflow / Agent Engine**: **LangGraph StateGraph** (BPM 상태 머신 + Multi-Agent 오케스트레이션 공용)
* **Database & Mock**: PostgreSQL, DuckDB, JSON Mock Datasets

### 3.1 확정된 기술 선택 (Decided — 재검토 불필요)

| 영역 | 선택 | 배제한 대안 | 사유 |
|---|---|---|---|
| BPM 상태 머신 | LangGraph StateGraph | Camunda 8 (BPMN 2.0) | Camunda는 Zeebe 브로커 운영이 필요해 프로토타입에 과중하다. LangGraph는 BPM 상태 전이와 에이전트 오케스트레이션을 하나의 그래프 런타임으로 처리한다. |
| 차트 | Recharts | Apache ECharts | Shadcn/UI·Tailwind와의 컴포지션이 자연스럽다. 차트 라이브러리는 하나만 쓴다 — 두 개를 섞으면 테마·툴팁·반응형 동작이 갈라진다. |
| Shadcn 프리미티브 | Radix (`-b radix`) | Base UI, React Aria | 기존 shadcn/ui 문서·스니펫이 Radix 기반이라 이식 비용이 가장 낮다. |

BPMN 2.0 다이어그램 표현이 필요한 경우에도 엔진을 Camunda로 바꾸지 않는다. 시각화는 `@xyflow/react` 커스텀 노드로 처리하고, 상태의 원천은 LangGraph 그래프로 유지한다.

---

## 4. Project Directory Structure

아래는 **목표 구조**다. 현재 실제로 존재하는 것은 `create-next-app` + `shadcn init` 산출물뿐이다:
`app/{layout.tsx,page.tsx,globals.css,favicon.ico}`, `lib/utils.ts`, `public/`, `components.json`, `AGENTS.md`, 설정 파일들.
`app/bpm-tracker/` 이하 5개 화면, `app/api/`, `components/*`, `lib/store|types|mock-data`, `services/`는 **아직 없다.** 실제 구조가 이 트리와 갈라지면 실제 구조를 기준으로 삼고 이 절을 갱신한다.

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