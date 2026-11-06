"""
FastAPI — BPM 엔진의 HTTP 경계.

Next의 `/api/engine/*`가 이것을 프록시한다(BFF). 브라우저가 직접 부르지 않는다 — CORS를
만들지 않고, 화면이 계속 `/api/*`만 알게 하려는 것이다.

BPM은 **Chaeksas**(`chaeksas-core`, BPMN 2.0 해석기)다. 업무는 `app/sc01/`에 있고, 여기서는
저장소·변경 알림을 준비해 라우터를 붙일 뿐이다(CLAUDE.md 4.5).
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from importlib.metadata import version
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .companies import Settings
from .companies import build_router as build_companies_router
from .company import CompanyClient, engine_drives
from .config import ConfigStore
from .consumer import ConsumerHost, routed_by
from .events import hub
from .follower import Follower, Synced
from .notify import build_notifier
from .s2.sc01.process import S2Sc01Process
from .s2.sc02.process import S2Sc02Process
from .s2.sc03.process import S2Sc03Process
from .s2.sc04.process import S2Sc04Process
from .sc01.api import build_router as build_sc01_router
from .sc01.center import CenterClient, CenterConfig
from .sc01.poller import CenterPoller
from .sc01.process import Sc01Process
from .sc01.store import build_sc01_store
from .sc02.api import build_router as build_sc02_router
from .sc02.process import Sc02Process
from .sc03.api import build_router as build_sc03_router
from .sc03.process import Sc03Process
from .sc04.api import build_router as build_sc04_router
from .sc04.process import Sc04Process
from .sc05.api import build_router as build_sc05_router
from .sc05.process import Sc05Process
from .sc06.api import build_router as build_sc06_router
from .sc06.process import Sc06Process
from .sc07.api import build_router as build_sc07_router
from .sc07.process import Sc07Process
from .store import build_backend

_SCENE_PATH = re.compile(r"^/sc0[1-7]/")

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

app = FastAPI(
    title="NowView BPM Engine",
    version="0.2.0",
    description=(
        "회사별 BPM 프로세스(Chaeksas Center)의 서비스 태스크를 수행하는 일꾼과 회사별 대시보드의 "
        "자료. 지금 회사는 가상 자동차 부품사(company1) 하나 — 시나리오 1의 장면 1~7과 "
        "시나리오 2(납기)의 장면 1. "
        "업무 흐름은 processes/*.bpmn이다."
    ),
)

# `DATABASE_URL`이 있으면 Postgres, 없으면 파일 SQLite다. 연결 실패를 SQLite로
# 되돌리지 않는다 — 운영에서 DB가 안 붙었다면 즉시 드러나야 한다(store.py 참조).
backend = build_backend()

# 변경 전파. Postgres면 LISTEN/NOTIFY로 **다른 워커까지** 간다(notify.py).
notifier = build_notifier(hub, backend, os.getenv("DATABASE_URL"))

# Center 연동(N3) — 키는 엔진만 쥔다. 설정이 없으면 center 데모 실행의 대리 답·기동이 503이다.
center = CenterClient(CenterConfig.from_env())
# NowView 설정(엔진 DB) — 회사·회사 시스템 주소·BPM 프로세스 매핑·일꾼 토픽. 관리자 모드에서
# 고친다.
settings = Settings(ConfigStore(backend))
# 회사 시스템(가상 자동차 부품사 시뮬레이터, `company-sim/`) — 장면 1의 회사 자료·원천·상태. 주소는
# 설정에서, 키는 환경(`COMPANY_COMPANY1_KEY`)에서 온다. 관리자 모드가 주소를 바꾸면 바로 따른다.
company = CompanyClient.from_env("company1")
settings.on_change(
    lambda config: company.set_url(getattr(config.company("company1"), "system_url", None))
)
sc01 = Sc01Process(
    build_sc01_store(backend), publish=notifier.publish, center=center, company=company
)
app.include_router(build_sc01_router(sc01, hub))
# 장면 2 — 장면 1 인계 결과에서 시작한다. 같은 데모 실행 id, 다른 테이블(`sc02_*`). 내장 실행만.
sc02 = Sc02Process(build_sc01_store(backend, "sc02"), sc01, publish=notifier.publish)
app.include_router(build_sc02_router(sc02, hub))
# 장면 3 — 장면 2 인수 결과에서 시작한다. 같은 데모 실행 id, 다른 테이블(`sc03_*`).
sc03 = Sc03Process(build_sc01_store(backend, "sc03"), sc02, publish=notifier.publish)
app.include_router(build_sc03_router(sc03, hub))
# 장면 4 — 장면 3 인계(HANDOFF31)에서 시작한다. 같은 데모 실행 id, 다른 테이블(`sc04_*`).
sc04 = Sc04Process(build_sc01_store(backend, "sc04"), sc03, publish=notifier.publish)
app.include_router(build_sc04_router(sc04, hub))
# 장면 5 — 장면 4 인계(HANDOFF41)에서 시작한다. 같은 데모 실행 id, 다른 테이블(`sc05_*`).
sc05 = Sc05Process(build_sc01_store(backend, "sc05"), sc04, publish=notifier.publish)
app.include_router(build_sc05_router(sc05, hub))
# 장면 6 — 장면 5 인계(HANDOFF51)에서 RV61 검토 문서를 적재하고, 확인 절차(담당 임원 확인 → 종합 →
# 확정 →
# 대표 보고)를 BPM으로 돈다. 같은 데모 실행 id, 다른 테이블(`sc06_*`).
sc06 = Sc06Process(build_sc01_store(backend, "sc06"), sc05, publish=notifier.publish)
app.include_router(build_sc06_router(sc06, hub))
# 장면 7 — 장면 6 대표 보고(RPT61-v1)에서 관리모델 개선 IMP71을 적재하고, 확인·적용 절차
# (검증 → 구매 임원·경영관리 임원 확인 → 운영 설정 반영 → 설정 확인 → 후속 점검)를 BPM으로
# 돈다. 테이블은 `sc07_*`.
sc07 = Sc07Process(build_sc01_store(backend, "sc07"), sc06, publish=notifier.publish)
app.include_router(build_sc07_router(sc07, hub))
# 서비스 태스크의 일감을 Center에서 가져간다(C15, ADR-0102) — Center 주소가 있을 때만 뜬다. 토픽은
# 설정에서, 일감마다 보낸 BPM 프로세스 id → 설정의 업무(장면) → 그 장면의 프로세스다.
_S1 = {1: sc01, 2: sc02, 3: sc03, 4: sc04, 5: sc05, 6: sc06, 7: sc07}
# 시나리오 2 장면 1(공통 플랫폼 첫 업무, `docs/platform.md`) — 구매 개정 하나 = BPM 실행 하나.
# 결재가 없어 진행은 일감이 알려 준다. 폴러는 일감 전에 실패한 실행의 끝만 읽는다. 업무 번호 21.
s2sc01 = S2Sc01Process(
    build_sc01_store(backend, "s2sc01"), company=company, center=center, publish=notifier.publish
)
# 시나리오 2 장면 2 — 장면 1 인계(HAND-01)에서 사이트의 「장면 열기」로 연다. 공통 BPM 수행계획 구성
# 호출 → 변경안 → H03 확인 결재(사이트가 대리 답) → 반영·재조회 → 재평가 → 장면 3 인계. 업무 번호
# 22.
s2sc02 = S2Sc02Process(
    build_sc01_store(backend, "s2sc02"),
    company=company,
    sc01=s2sc01,
    center=center,
    publish=notifier.publish,
)
# 시나리오 2 장면 3 — 장면 2 인계(HAND-02)에서 「장면 열기」로 연다. 수행계획 v2 호출 → 기존 운송
# 문의 연결(근거가 오면 메시지로 깨운다) → 대안 비교 → 팀장 권고·재보고 → H05 결정 → H04 인수. 업무
# 번호 23.
s2sc03 = S2Sc03Process(
    build_sc01_store(backend, "s2sc03"),
    company=company,
    sc02=s2sc02,
    center=center,
    publish=notifier.publish,
)
# 시나리오 2 장면 4 — 장면 3 인계(HAND-03)에서 연다. 결정·실적 대조(증빙이 오면 메시지로 깨운다) →
# H06 개선 착수 → 당시 자료 재현·H04 요청·영향 확인 → H07 시험 판정 → H06 적용 확인 → H07 설정. 업무
# 번호 24.
s2sc04 = S2Sc04Process(
    build_sc01_store(backend, "s2sc04"),
    company=company,
    sc03=s2sc03,
    center=center,
    publish=notifier.publish,
)
_SCENES = {**_S1, 21: s2sc01, 22: s2sc02, 23: s2sc03, 24: s2sc04}
# 도는 center 데모 실행의 진행을 2초마다 읽는다 — Center에는 push가 없다(요청서 R3 거절). 시나리오 1
# 일곱 장면과 시나리오 2 장면 1.
poller = CenterPoller(sc01, sc02, sc03, sc04, sc05, sc06, sc07, s2sc01, s2sc02, s2sc03, s2sc04)
# 세계 따라가기 — 회사 사이트가 기간계에 만든 세계·시계·원천·명령을 읽어 따라간다(role-split §5.3).
# 일감은 처리 전에 그 세계의 시각을 먼저 따라간다(`Synced`). 회차의 시나리오로 갈라 따라간다.
follower = Follower(company, _S1, s2=s2sc01, s2_scenes={2: s2sc02, 3: s2sc03, 4: s2sc04})
# 일감 기록의 장면은 그 회차 시나리오의 장면 번호다(시나리오 2 장면 1 → 1)
_WORKERS = {n: Synced(p, follower, n) for n, p in _S1.items()} | {
    21: Synced(s2sc01, follower, 1),
    22: Synced(s2sc02, follower, 2),
    23: Synced(s2sc03, follower, 3),
    24: Synced(s2sc04, follower, 4),
}
consumer = ConsumerHost.from_env(settings.config.topics, routed_by(settings.scene_of, _WORKERS))
app.include_router(
    build_companies_router(settings, consumer, center, poller, {"company1": company}, _SCENES)
)


@app.middleware("http")
async def _scene_inputs_are_for_tests(request: Request, call_next):
    """
    장면의 쓰기 경로(결재 답·각본·시계·초기화·수신·명령)는 **엔진 시험 전용**이다(role-split §5.5) —
    시연 조작과 결재는 회사 사이트가 하고, NowView는 기간계를 읽어 따라간다(`app/follower.py`).
    엔진 시험(`NOWVIEW_TEST_INPUTS=1`)이 아니면 405다. 읽기(GET·SSE)는 그대로다.
    """
    if (
        request.method not in ("GET", "HEAD")
        and _SCENE_PATH.match(request.url.path)
        and not engine_drives()
    ):
        return JSONResponse(
            {"detail": "업무 행위·시연 조작은 회사 사이트에서 한다 — NowView는 읽기 전용이다"},
            status_code=405,
        )
    return await call_next(request)


@app.on_event("startup")
async def _start_notifications() -> None:
    # 변경 알림은 스레드풀(동기 엔드포인트)에서 오므로 루프 참조가 필요하다.
    hub.bind_loop(asyncio.get_running_loop())
    await notifier.start()
    poller.start()
    consumer.start()
    if not engine_drives():  # 엔진 시험은 엔진이 몬다 — 따라가기를 띄우지 않는다
        follower.start()


@app.on_event("shutdown")
async def _stop_notifications() -> None:
    # LISTEN 연결을 정리하지 않으면 재시작 때 Postgres에 유령 세션이 남는다.
    follower.stop()
    poller.stop()
    consumer.stop()
    await notifier.stop()


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        # 어느 백엔드로 돌고 있는지 드러내지 않으면 "SQLite로 운영에 올렸다"를
        # 눈치챌 방법이 없다. 자격증명은 빼고 호스트·DB만 싣는다.
        "storage": {"kind": backend.kind, "describe": backend.describe},
        "bpm": {
            "engine": "chaeksas-core",
            "version": version("chaeksas-core"),
            "process": sc01.process.id,
            "processes": [
                sc01.process.id,
                sc02.process.id,
                sc03.process.id,
                sc04.process.id,
                sc05.process.id,
                sc06.process.id,
                sc07.process.id,
                s2sc01.process.id,
                s2sc02.process.id,
                s2sc03.process.id,
                s2sc04.process.id,
            ],
        },
        "demoRuns": len(sc01.store.list()),
        # C15 일꾼 — 승인 대기(요청 코드)·가져가는 중·꺼짐. 토큰은 싣지 않는다.
        # 일꾼은 상태만 — 토픽·요청 코드는 관리자 모드(`/admin/status`)에만 있다.
        "consumer": {"state": consumer.describe()["state"]},
        "follower": follower.describe(),
        # 회사 시스템 — 키 값은 싣지 않는다.
        "companies": len(settings.config.companies),
        # Center 연동(N3) — 키 값은 싣지 않는다. 폴러가 없으면 center 실행의 진행이 멈춰 보인다.
        "center": {**center.config.describe(), "polling": poller.running},
        "eventSubscribers": hub.subscriber_count,
        # 전파 방식을 드러내지 않으면 "여러 워커인데 알림이 로컬"인 상태를 눈치챌 수 없다.
        "notify": {
            "kind": notifier.kind,
            "listening": getattr(notifier, "listening", None),
        },
    }
