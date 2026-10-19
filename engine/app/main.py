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

from .events import hub
from .notify import build_notifier
from .sc01.api import build_router as build_sc01_router
from .sc01.process import Sc01Process
from .sc01.store import build_sc01_store
from .store import build_backend

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

app = FastAPI(
    title="NowView BPM Engine",
    version="0.2.0",
    description="Chaeksas BPM(BPMN 2.0) 위의 SC01 장면 1. 업무 흐름은 processes/*.bpmn이다.",
)

# `DATABASE_URL`이 있으면 Postgres, 없으면 파일 SQLite다. 연결 실패를 SQLite로
# 되돌리지 않는다 — 운영에서 DB가 안 붙었다면 즉시 드러나야 한다(store.py 참조).
backend = build_backend()

# 변경 전파. Postgres면 LISTEN/NOTIFY로 **다른 워커까지** 간다(notify.py).
notifier = build_notifier(hub, backend, os.getenv("DATABASE_URL"))

sc01 = Sc01Process(build_sc01_store(backend), publish=notifier.publish)
app.include_router(build_sc01_router(sc01, hub))


@app.on_event("startup")
async def _start_notifications() -> None:
    # 변경 알림은 스레드풀(동기 엔드포인트)에서 오므로 루프 참조가 필요하다.
    hub.bind_loop(asyncio.get_running_loop())
    await notifier.start()


@app.on_event("shutdown")
async def _stop_notifications() -> None:
    # LISTEN 연결을 정리하지 않으면 재시작 때 Postgres에 유령 세션이 남는다.
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
        },
        "demoRuns": len(sc01.store.list()),
        "eventSubscribers": hub.subscriber_count,
        # 전파 방식을 드러내지 않으면 "여러 워커인데 알림이 로컬"인 상태를 눈치챌 수 없다.
        "notify": {
            "kind": notifier.kind,
            "listening": getattr(notifier, "listening", None),
        },
    }
