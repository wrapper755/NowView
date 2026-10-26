# NowView BPM Engine

**Chaeksas BPM**(`chaeksas-core`, BPMN 2.0 해석기) 위의 시나리오 1 — 장면 1(SC01)·장면 2(SC02). Next 앱의
`/api/engine/{sc01|sc02}/*`가 이것을 프록시한다. 설계와 함정은 루트 `CLAUDE.md` 4.5(장면 1)·4.16(장면 2).

```bash
uv sync
uv run uvicorn app.main:app --port 8077 --reload   # http://localhost:8077/docs
uv run pytest                                      # 266개 (SQLite만, LLM 제외)
OLLAMA_URL=http://localhost:11434 uv run pytest -m llm   # Agent 실호출 계약 (약 100초)
uv run ruff check .

# 두 백엔드 모두 검증 (Postgres가 떠 있을 때 — 루트에서 npm run stack:start db)
TEST_DATABASE_URL=postgresql://nowview:nowview@localhost:55432/nowview uv run pytest   # 347개
```

`--reload` 없이 띄우면 코드를 고쳐도 반영되지 않는다.

## 구성

```
processes/sc01.bpmn     업무 흐름 — 유일한 원천. Chaeksas Studio(bpmn-js)로 열린다
processes/sc02.bpmn     장면 2 업무 흐름 — 내장 실행만
seed/SYN-SC01-v0.2.xlsx 통합 가상 데이터 설계. 원천 시트 = 시드, 파생 시트 = 테스트 기대값
seed/SYN-SC02-v0.2.xlsx SC01_SC02 통합가상데이터 v0.2 — 같은 원칙
app/sc02/               장면 2 — seed · calc(구매 증가·위험·승인선·손익 연결) · domain · agent · process · demo · view · api
app/sc01/
  seed.py      원천 시트 적재 (행 번호가 아니라 영문 헤더로 읽는다)
  calc.py      지표·위험 판정·손익 집계 — 규칙 계산. Agent·BPM은 숫자를 만들지 않는다
  agent.py     Agent 검토 초안 — 입력 구성, 계약 검증(숫자·근거 대조), mock·ollama·fail 러너
  domain.py    원천 검증·이슈·업무·기한·인계 (문서 하나 = 데모 실행 하나)
  process.py   Chaeksas 엔진 래퍼 + 서비스 태스크 어댑터(nowview.sc01)
  store.py     문서·이력 저장 (row_version 낙관적 잠금)
  demo.py      기본 시연 각본 EV01~EV07
  view.py      응답 모양 · UI01 대시보드 · 토폴로지
  api.py       /sc01/* 라우터
app/events.py  SSE 허브 · app/notify.py  프로세스 경계 전파(Postgres LISTEN/NOTIFY)
```

## Chaeksas를 라이브러리로 쓴다

`chaeksas-core`를 **git 커밋에 고정한** 의존성으로 가져온다(`pyproject.toml`). Center·서버
실행기는 쓰지 않는다 — 정의 변경마다 패키지 서명·배포가 필요하고, 결재 응답은 관리자
토큰으로만 되고, 작업 결과 값을 돌려주지 않는다. Chaeksas를 올리려면 `rev`를 바꾸고
`uv lock`한다.

라이브러리로 쓰면서 **우리가 붙인 것**: SSE(Chaeksas에 없다), 지난 시점(Chaeksas 스냅샷은
현재 하나뿐이라 `sc01_history`에 매번 문서 전체를 남긴다), 폼이 못 거는 업무 규칙
(`Sc01Process._before_answer`), 역할 배정(`domain.NODE_ROLES` — `chk:approval`에 역할 칸이 없다).

## 저장 백엔드 — SQLite / Postgres

`DATABASE_URL`이 있으면 Postgres, 없으면 파일 SQLite(`engine-state.sqlite`). **연결 실패를
SQLite로 조용히 되돌리지 않는다.** `/health`의 `storage`가 어느 쪽인지 알려 준다.

* 한 데모 실행 = 문서 한 행. 계산 결과·이슈 갱신·BPM 스냅샷이 한 번의 쓰기라 원자적이다.
* 워커 사이는 `row_version`이 막는다(409). 워커 안은 데모 실행별 잠금이다.
* SQLite 저장소는 **자기 연결을 잠금으로 줄 세운다.** 연결을 잠금 없이 나눠 쓰자 SSE 읽기가
  쓰는 도중의 빈 행을 받아 스트림이 죽었다.

## 변경 알림 (SSE)

`GET /sc01/demo-runs/{id}/events`가 문서를 밀어 준다. 상태가 바뀌는 계기가 전부 우리 코드를
지나가므로(수신·응답·시계·초기화) 그 지점에서 `notifier.publish("sc01:{id}")`한다.

* 연결 직후 현재 문서를 보내고 `event: ready`로 끝을 알린다.
* 알림은 **부수 효과**다. 루프가 없거나 구독자가 없으면 조용히 넘긴다 — 여기서 터지면
  조작이 실패하는 셈이 된다. 전송 실패도 마찬가지다.
* **프로세스 경계를 넘는다** — Postgres 백엔드면 `pg_notify`로 보내고 `LISTEN` 전용 연결로
  받아 모든 워커에 전달한다. 안전망으로 20초마다 다시 보낸다.
* 구독 해제는 `async with hub.subscribe(...)`로 확정한다 — async generator로 두면
  `break`로 빠져나갈 때 `finally`가 미뤄져 구독자가 누적된다(테스트가 잡았다).

## 행위자

`X-Demo-Actor` 헤더(시연 역할 전환). **신뢰 경계가 아니다** — 인증이 없다. 엔진은 "그 사용자가
그 업무의 역할·담당인가"까지만 검사한다(403). 인증이 붙으면 헤더 대신 세션에서 꺼낸다.

## 환경 변수

| 이름 | 기본값 | 용도 |
|---|---|---|
| `DATABASE_URL` | (없음 → SQLite) | Postgres 백엔드 |
| `NOWVIEW_ENGINE_DB` | `engine-state.sqlite` | SQLite 파일 경로 |
| `NOWVIEW_AGENT_MODE` | `mock` | Agent 초안 — `mock` / `llm` (시연 사례 EX08은 항상 실패) |
| `OLLAMA_URL` · `OLLAMA_MODEL` | `http://localhost:11434` · `kimi-k3:cloud` | `llm` 모드 |
| `LOG_LEVEL` | `INFO` | |
