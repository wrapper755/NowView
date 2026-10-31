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
from importlib.metadata import version
from typing import Any

from fastapi import FastAPI

from .companies import Settings
from .companies import build_router as build_companies_router
from .company import CompanyClient
from .config import ConfigStore
from .consumer import ConsumerHost, routed_by
from .events import hub
from .notify import build_notifier
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
from .store import build_backend

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

app = FastAPI(
    title="NowView BPM Engine",
    version="0.2.0",
    description=(
        "회사별 BPM 프로세스(Chaeksas Center)의 서비스 태스크를 수행하는 일꾼과 회사별 대시보드의 "
        "자료. 지금 회사는 가상 자동차 부품사(autopart1) 하나 — 시나리오 1의 장면 1~6. "
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
# 설정에서, 키는 환경(`COMPANY_AUTOPART1_KEY`)에서 온다. 관리자 모드가 주소를 바꾸면 바로 따른다.
company = CompanyClient.from_env("autopart1")
settings.on_change(
    lambda config: company.set_url(getattr(config.company("autopart1"), "system_url", None))
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
# 도는 center 데모 실행의 진행을 2초마다 읽는다 — Center에는 push가 없다(요청서 R3 거절). 여섯 장면
# 모두.
poller = CenterPoller(sc01, sc02, sc03, sc04, sc05, sc06)
# 서비스 태스크의 일감을 Center에서 가져간다(C15, ADR-0102) — Center 주소가 있을 때만 뜬다. 토픽은
# 설정에서, 일감마다 보낸 BPM 프로세스 id → 설정의 업무(장면) → 그 장면의 프로세스다.
_SCENES = {1: sc01, 2: sc02, 3: sc03, 4: sc04, 5: sc05, 6: sc06}
consumer = ConsumerHost.from_env(settings.config.topics, routed_by(settings.scene_of, _SCENES))
app.include_router(
    build_companies_router(settings, consumer, center, poller, {"autopart1": company})
)


@app.on_event("startup")
async def _start_notifications() -> None:
    # 변경 알림은 스레드풀(동기 엔드포인트)에서 오므로 루프 참조가 필요하다.
    hub.bind_loop(asyncio.get_running_loop())
    await notifier.start()
    poller.start()
    consumer.start()


@app.on_event("shutdown")
async def _stop_notifications() -> None:
    # LISTEN 연결을 정리하지 않으면 재시작 때 Postgres에 유령 세션이 남는다.
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
            ],
        },
        "demoRuns": len(sc01.store.list()),
        # C15 일꾼 — 승인 대기(요청 코드)·가져가는 중·꺼짐. 토큰은 싣지 않는다.
        # 일꾼은 상태만 — 토픽·요청 코드는 관리자 모드(`/admin/status`)에만 있다.
        "consumer": {"state": consumer.describe()["state"]},
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
