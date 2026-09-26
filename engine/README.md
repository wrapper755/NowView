# NowView BPM Engine

LangGraph StateGraph 기반 BPM 런타임. Next 앱의 `/api/engine/*`가 이것을 프록시한다.

```bash
uv sync
uv run uvicorn app.main:app --port 8077 --reload   # http://localhost:8077/docs
uv run pytest                                      # 56개 (SQLite만, LLM 제외)
uv run pytest -m llm                               # ollama 실호출 (약 40초)
uv run ruff check .

# 두 백엔드 모두 검증 (Postgres가 떠 있을 때)
TEST_DATABASE_URL=postgresql://nowview:nowview@localhost:55432/nowview uv run pytest   # 90개
```

전체 스택은 저장소 루트에서:

```bash
docker compose up --build
```

`--reload` 없이 띄우면 코드를 고쳐도 반영되지 않는다 — 실제로 그 때문에 별칭 변경이
적용되지 않아 422가 났다.

## 왜 별도 서비스인가

Next 안에서 `@langchain/langgraph`(JS)로도 돌 수 있고 Postgres checkpointer도 있다.
Python을 고른 이유는 기능 부족이 아니다:

* 기획안이 요구하는 **다차원 원인 분석**은 pandas·DuckDB 영역이고, 스택 명세에 이미
  DuckDB가 있다. JS에는 대응물이 없다.
* ⑤ Evolution Lab의 취지가 **에이전트 룰 개선**인데, 그걸 하는 사람은 경영·분석 쪽이다.
* Python이 레퍼런스 구현이다 — `langgraph-checkpoint-postgres`가 3.x인데 JS는 1.0.x다.
  `langgraph-cli`로 그래프를 Studio에서 재생·디버깅하는 것도 Python이 1급이다.

## 이 엔진은 토폴로지를 모른다

노드·엣지·Agent 정의는 **TS(`lib/mock-data/`)가 유일한 원천**이고, 인스턴스 생성 요청에
명세로 실려 온다(`services/engine-spec.ts` → `app/spec.py`). 엔진이 같은 것을 따로 들고
있으면 두 벌이 되고, 시나리오를 추가할 때 양쪽을 손대야 한다.

그래서 **세 시나리오가 엔진 코드 수정 없이 돈다.** 경영 규칙(사유 최소 길이, 승인 노드,
선택지)도 같은 방식으로 받는다 — 숫자를 다시 적으면 UI·API·엔진이 갈라진다.

## 규칙 소유권

> Python은 "무슨 일이 일어났는가", TypeScript는 "그것이 숫자에 어떻게 반영되는가".

| Python (여기) | TypeScript (`services/`) |
|---|---|
| 프로세스 인스턴스 상태, 노드 상태 파생 | 전사 Gap 집계(`summarizeGap`), 이중 계상 금지 |
| Agent 실행·산출물·신뢰도·에스컬레이션 | Plan 조정(`planView`), Framework 연결 |
| 승인 `interrupt` / `resume`, 사유 검증 | 결정 → 실행 과제 변환(`decisionToAction`) |

결정→과제 변환을 TS에 남긴 이유: 이중 계상 금지 규칙이 거기 있고 이미 테스트가 잠그고
있다. 엔진은 "승인됨 + 어느 대안 + 레버값"만 돌려준다.

## 저장 백엔드 — SQLite / Postgres

`DATABASE_URL`이 있으면 Postgres, 없으면 파일 SQLite다. **로컬 개발에서 DB를 띄우라고
요구하면 "엔진이 없어도 앱은 전부 동작한다"는 성질이 깨진다** — 켜는 쪽이 선택이고
기본값은 마찰이 없는 쪽이다.

**SQLite로는 운영할 수 없다.** 여러 워커·인스턴스로 띄우면 각자 다른 파일을 보거나
쓰기가 잠긴다. `docker compose`와 CI는 Postgres를 쓴다. `/health`의 `storage`가 어느
쪽인지 알려 준다 — 드러내지 않으면 "SQLite로 운영에 올렸다"를 눈치챌 방법이 없다.

**연결 실패를 SQLite로 되돌리지 않는다.** 운영에서 DB가 안 붙었다면 즉시 드러나야
한다. 조용히 파일로 떨어지면 인스턴스가 워커마다 갈라진 채 돈다.

두 가지 함정:

* **`PostgresSaver`는 `autocommit=True`와 `row_factory=dict_row`를 요구한다.** 빠뜨리면
  `setup()`이나 첫 쓰기에서 터지는데, 문서에만 있고 타입으로는 드러나지 않는다.
* **테스트가 두 백엔드를 모두 돈다.** SQL 자리표시자(`?` vs `%s`), 행 접근(튜플 vs
  dict), `created_at` 타입(문자열 vs datetime)이 전부 다르다. 한쪽만 돌리면 나머지가
  배포 시점에 터진다. `TEST_DATABASE_URL`을 주면 양쪽을 돌고, 없으면 Postgres 쪽을
  건너뛴다 — CI에서는 `REQUIRE_POSTGRES=1`로 **건너뛰기를 실패로 바꾼다**(초록색
  체크만 보고는 "검증했다"와 "건너뛰었다"를 구분할 수 없다).

## 되감기 — 데모 플레이어가 엔진 위에서 도는 이유

노드마다 체크포인트가 남으므로 지난 시점을 되짚어 볼 수 있다(`seek.py`). **뒤로는 읽기
전용이고 앞으로는 실행이다.** 과거 체크포인트에서 `invoke`하면 거기서부터 다시 실행되어
LLM이 재호출되고 승인이 사라지므로, 되감기는 조회로만 구현한다.

멈출 수 있는 곳은 사람 대기 지점뿐이라, 목표가 Agent·시스템 노드면 지나친 뒤 그 지점을
되짚어 돌려준다. 승인 노드를 통과해야 하면 호출자가 결정을 줘야 한다 — 엔진이 임의로
승인하면 Human-in-the-Loop이 무너진다.

## 상태 소유권이 넘어왔다

TS 쪽 `/api/bpm/*`는 진행 지점을 받아 계산해 돌려주는 **무상태 계산기**다. 여기서는
checkpointer가 인스턴스를 소유하므로 식별자가 진행 지점이 아니라 `instanceId`이고,
생성·조회·재개·종료라는 생명주기가 처음으로 생긴다.

명세도 함께 저장한다(`instance_spec` 테이블) — 체크포인트만 남기면 재시작 후 그래프를
다시 조립할 수 없어 진행 중인 인스턴스가 되살아나지 않는다.

## 분기: Deterministic BPM + Probabilistic AI

게이트웨이는 상태의 **플래그 하나**를 읽어 경로를 고른다(결정론적). 그 플래그를 만드는
것은 선행 Agent다(확률적). 기획안의 두 성질이 여기서 갈린다.

```
rca(Agent) ──판정: crossFunctionalCoordination──▶ gw-escalate ──▶ simulate | op-control
```

`sourceHandle`(main/branch)로 분기를 판정하면 안 된다 — 캔버스 레이아웃 관심사일 뿐이고
실제로 납기 시나리오는 `main`이 "아니오"다. 규칙은 `BpmNodeSpec.decision`에 명시한다.

플래그가 없으면 `whenFalse`로 간다. 판정되지 않은 것을 "조정 필요"로 보면 에스컬레이션이
기본값이 되어 현업 통제 경로가 죽는다.

## Agent 모드

| 모드 | 동작 |
|---|---|
| `mock` (기본) | 명세에 실려 온 산출물을 그대로 돌려준다. 결정론적이라 데모·테스트가 쓴다. |
| `llm` | ollama로 실제 호출. 기본 모델 `kimi-k3:cloud`. |

인스턴스는 **생성 시 모드로 재개된다.** Mock으로 시작한 것을 LLM으로 재개하면 앞뒤
산출물의 출처가 섞여 어느 것이 실제 호출인지 알 수 없다. `provenance`(`mock` ·
`mock-missing` · `llm:<model>`)가 산출물마다 붙는다.

### 검증된 제약 — `format` 스키마가 강제되지 않는다

`kimi-k3:cloud`에 ollama의 `format`으로 JSON 스키마를 줘도 **무시된다.** 실측:

| 시도 | 결과 |
|---|---|
| `format` 스키마만 | JSON조차 아님 — 마크다운 산문 |
| 스키마를 프롬프트에 넣음 | 준수 (약 10~12초) |

그래서 스키마를 프롬프트에 박고, 받은 것을 검증하고, 무엇이 틀렸는지 알려주며
재시도한다(`max_attempts=3`). `format`도 계속 보내지만 로컬 모델용이고 기대하지 않는다.

**계약을 못 맞추면 지어내지 않고 502로 실패한다.** 조용히 그럴듯한 값으로 메우면
Agent가 고장난 것을 아무도 모른 채 화면에 숫자가 나간다.

`sources`는 모델이 만들지 않고 명세의 것을 쓴다 — 근거 데이터의 출처와 품질을 모델이
지어내면 검증 자체가 무의미해진다.

## 테스트가 값 비교에서 계약 검증으로 바뀐다

temperature 0에서도 같은 질문에 `14.2`와 `14.5`가 나왔다. 그래서 LLM 경로는 값을
확인하지 않고 **스키마·범위·근거가 비어 있지 않은가**를 본다. 반대로 파생 규칙
(분기, 대기 판정, 승인 게이트)은 실행 중 상태가 진짜로 생기므로 더 중요해졌다.

## 환경 변수

| 변수 | 기본값 |
|---|---|
| `DATABASE_URL` | (없음) — 있으면 Postgres, 없으면 SQLite |
| `NOWVIEW_ENGINE_DB` | `engine-state.sqlite` (SQLite일 때만) |
| `OLLAMA_URL` | `http://localhost:11434` |
| `OLLAMA_MODEL` | `kimi-k3:cloud` |
| `LOG_LEVEL` | `INFO` |

Next 쪽은 `ENGINE_URL`(기본 `http://localhost:8077`)로 이 서비스를 가리킨다.

## 아직 안 된 것

* **화면이 이 엔진을 쓰지 않는다** — 다섯 화면은 여전히 Mock을 직접 import한다
  (정적 프리렌더 유지). 엔진은 `/api/engine/*`로만 노출된다.
* **실시간성이 폴링이다** — 실행 중 3초, 대기 15초, 탭이 보일 때만. 인스턴스가 많아지면
  SSE로 바꿔야 한다.
* **같은 인스턴스를 여러 사람이 볼 때의 충돌** — 지금은 마지막 요청이 이긴다.
