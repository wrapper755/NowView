# NowView

**INNONOW Management Reference Model Pilot** — 매출 1조원 규모 가상 자동차 부품사를 대상으로,
체계화된 Management Framework와 BPM 프로세스 위에서 사람과 멀티 AI Agent가 협업하는
경영 운영모델을 구현한 프로토타입이다.

보여주려는 것은 화면이 아니라 **하나의 경영 루프가 끝까지 도는 모습**이다 —
이상 징후를 감지하고, Agent가 분석하고, 사람이 판단하고, 실행 과제로 배포되고,
전망이 갱신되고, 그 경험이 다시 감지 체계를 고친다.

---

## 시작하기

```bash
npm install
npm run dev     # http://localhost:3000
```

| 명령 | 용도 |
|---|---|
| `npm run dev` | 개발 서버 (Turbopack) |
| `npm run build` | 프로덕션 빌드 — TypeScript 검사 포함 |
| `npm run lint` | ESLint |
| `npm run test` | Vitest 1회 실행 (86개) |
| `npm run test:watch` | Vitest 감시 모드 |

단일 테스트는 `npx vitest run tests/framework.test.ts -t "예방 통제가 없는"`.

---

## 다섯 화면

경영 작동모델 6단계 루프에 대응한다.

| 화면 | 경로 | 무엇을 보여주는가 |
|---|---|---|
| ① Executive Cockpit | `/` | 영업이익 Gap, Target→Forecast 브릿지, 사업부 듀얼 매트릭스, **KPI–KRI–Control 연결**, **경영 수행 성과**, 감지된 리스크 신호 |
| ② Live BPM & Agent Tracker | `/bpm-tracker` | BPMN 프로세스 진행 상태, Agent 실행 현황과 근거 데이터 |
| ③ Human-Agent Collaboration Station | `/workspace` | Agent 보고서, 대안 비교, 시뮬레이터, **사람의 승인** |
| ④ Rolling Plan & Action Tracker | `/rolling-plan` | Target·Forecast·Plan, 실행 과제, 잔여 Gap |
| ⑤ Management Evolution Lab | `/evolution` | KRI 임계치 백테스트, Framework·Process·Agent 개선 제안 |

화면 아래 **플로팅 데모 플레이어**가 다섯 화면을 루프 순서로 이어 준다. 자동 재생,
장면 건너뛰기, 시나리오 전환을 지원한다.

---

## 세 시나리오

모두 같은 가상 회사·같은 전사 Gap(−69억)을 공유하며, **결정의 성격이 각각 다르다.**

| | 안건 | 경로 | 결정 주체 | 결정의 성격 |
|---|---|---|---|---|
| 1 | 수익성 하락 | 부서 간 조정 필요 → **에스컬레이션** | 경영진 (CFO) | 조치 |
| 2 | 납기 준수 | 권한 내 처리 → **현업 통제** | 구매본부 | 조치 |
| 3 | 재원 배분 | 사업부 넘는 이동 → **전사 검토** | 경영진 (CEO) | **배분** |

1·2번이 기획안 3.3의 두 경로를 나눠 맡고, 3번은 성격 자체가 다르다 —
배분은 어느 대안을 골라도 반대편이 줄어 **비용이 0인 안이 없다.**

시나리오를 추가하려면 `lib/mock-data/scenarios.ts`에 한 항목을 더한다.
화면·스토어·서비스를 고쳐야 한다면 구조가 시나리오에 묶여 있다는 뜻이다.

---

## 구조

```
app/            화면 5개 + api/ (Route Handler)
components/
  <화면>/       그 화면 전용 패널 (cockpit·bpm·workspace·rolling·evolution)
  flow/         React Flow 노드·엣지·캔버스 전용
  shared/       두 화면 이상이 쓰는 조각
  demo/         플로팅 시나리오 플레이어
  ui/           shadcn 원시 컴포넌트
lib/
  types/        도메인 타입 — 규칙이 주석이 아니라 타입으로 들어 있다
  mock-data/    가상 회사 데이터 + 시나리오 레지스트리
  store/        Zustand 데모 컨트롤러
services/       파생·계산 로직 (화면과 API가 공유)
tests/          Vitest — 순수 로직만
docs/           장면별 설계표 (구현에서 생성)
```

**`services/`가 핵심이다.** 화면과 API가 같은 함수를 호출하므로 둘의 결과가 어긋날 수
없다. "미완료 Agent 산출물은 감춘다" 같은 규칙을 여기 두면 새 화면·새 필드에도
자동으로 적용된다.

---

## 알아둘 설계 판단

처음 보면 의아할 만한 것들이다. 자세한 근거는 [CLAUDE.md](CLAUDE.md)에 있다.

- **상태를 저장하지 않고 파생한다.** BPM 노드 상태는 실행 순서(`sequence`)와 진행 지점에서
  계산한다. 노드마다 status를 두면 순서와 상태가 곧 어긋난다.
- **Target은 바뀌지 않는다.** `ForecastRevision`에 target 필드 자체가 없다 —
  회차마다 들고 있으면 언젠가 누군가 고친다.
- **이중 계상을 구조로 막는다.** 승인 과제는 현재 Forecast를 바꾸지 않고 "다음 Rolling
  반영 예정"으로만 잡힌다. 전망치는 따로 표시한다.
- **미완료 Agent의 산출물은 보여주지 않는다.** 실제로 두 경로로 새어 나간 적이 있다.
- **Agent는 정보가 부족하면 추측하지 않고 묻는다.** 답을 받지 못한 채 진행할 때 어떤
  가정 위에 서는지를 함께 남긴다.
- **차트 색은 `--viz-*` 변수만 쓴다.** shadcn 프리셋의 `--chart-1~5`는 무채색이라 계열
  식별에 못 쓴다. 색을 바꾸면 눈으로 판단하지 말고 검증기를 돌린다.

---

## 현재 상태

**구현 완료** — 화면 5개, 시나리오 3개, API 계층, 데모 플레이어, 상태 영속화,
장면별 설계표 생성기, 테스트 86개.

**Mock이다** — 모든 데이터가 `lib/mock-data/`의 코드이고, BPM 엔진(LangGraph)과 실제
Agent 호출은 연결되지 않았다. 화면은 API가 아니라 Mock을 직접 import한다(정적 프리렌더 유지).
API는 외부 소비자를 위한 접합면으로 먼저 만들어 두었다.

**다음 단계와 그 선행 조건**은 [CLAUDE.md](CLAUDE.md)의 "다음 단계" 절에 정리해 두었다.

---

## 문서

| 문서 | 용도 |
|---|---|
| [CLAUDE.md](CLAUDE.md) | 작업 매뉴얼 — 설계 판단의 근거, 함정, 수치 연동 규칙 |
| [docs/scene-design.md](docs/scene-design.md) | 장면별 설계표 (기획안 4.2) — Business 설계를 BPM·Agent 구현으로 잇는 명세 |

설계표는 손으로 쓰지 않고 구현에서 생성한다:

```bash
curl -s http://localhost:3000/api/docs/scene-design > docs/scene-design.md
```

---

본 저장소의 회사명·제품군·조직·수치는 전부 가상이다. 특정 회사의 실제 경영 상태를
재현한 것이 아니다.
