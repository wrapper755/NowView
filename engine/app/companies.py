"""
회사 — 공개 목록(`GET /companies`)과 관리자 모드(`/admin/*`).

NowView는 회사 사이트가 아니다. 두 가지 일을 한다(2026-10-31 사용자 정의,
`docs/worker-interfaces.md` §0.1):

* **일꾼** — Center에 올린 회사별 BPM 프로세스의 서비스 태스크 일감을 가져가 수행한다
  (`app/consumer.py`). 일꾼이 제공하는 작업은 NowView 고정 확장 `nowview` 하나이고, 어느 회사의 어느
  BPM 프로세스를 맡는지는 **설정**이다(`app/config.py`).
* **회사별 대시보드** — N개 회사의 운영 현황을 그 회사의 BPM 진행 위에서 보여 준다.

**등록은 공개하지 않는다.** 공개 목록은 회사 이름·설명과 그 회사가 쓰는 업무 번호뿐이다 — BPM
프로세스 id·토픽·회사 시스템 주소·들이기 상태(요청 코드)는 관리자 모드(`/admin/*`)에만 있다. 관리
API는 BFF만 아는 키(`NOWVIEW_ADMIN_KEY`, 헤더 `X-Admin-Key`)로 막고, 공개 BFF 경로는 그것을 중계하지
않는다. 키가 없으면 관리자 모드는 꺼져 있다(503).
"""

from __future__ import annotations

import hmac
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import ValidationError

from .config import ConfigStore, NowViewConfig

#: NowView가 아는 업무(장면) — 코드에 화면·처리기가 있다. 화면 쪽 사본은 `lib/companies.ts`의
#: `SCENES` (시험이 대조).
SCENE_WORKS: dict[int, str] = {
    1: "고객 생산계획 변경 대응",
    2: "외주 단가 인상 검토",
    3: "수익성 통합 분석",
    4: "개선안 검토·실행 승인",
    5: "결정 실행·계획 갱신",
    6: "완료·성과 검토",
}

EXTENSION = Path(__file__).resolve().parents[2] / "chaeksas" / "nowview.extension.json"


class Settings:
    """
    지금 설정 — 관리자 모드가 고치면 바로 바뀐다(일꾼의 매핑·회사 시스템 주소). 토픽은 엔진을 다시
    띄워야 한다(일꾼이 들이기 때 Center에 알린 값이다).
    """

    def __init__(self, store: ConfigStore) -> None:
        self.store = store
        self.config, self.updated_at = store.load()
        self.started_topics = list(self.config.topics)
        self._listeners: list[Callable[[NowViewConfig], None]] = []

    def on_change(self, listener: Callable[[NowViewConfig], None]) -> None:
        self._listeners.append(listener)
        listener(self.config)

    def replace(self, config: NowViewConfig) -> None:
        self.updated_at = self.store.save(config)
        self.config = config
        for listener in self._listeners:
            listener(config)

    def scene_of(self, bpm_process_id: str | None) -> int | None:
        found = self.config.mapping(bpm_process_id)
        return found.scene if found else None


def public_companies(config: NowViewConfig) -> list[dict[str, Any]]:
    """공개 목록 — 이름·설명·업무 번호만. BPM 프로세스 id·주소는 내지 않는다."""
    return [
        {
            "id": c.id,
            "name": c.name,
            "description": c.description,
            "scenes": sorted({p.scene for p in config.processes if p.company == c.id}),
        }
        for c in config.companies
    ]


def build_router(
    settings: Settings,
    worker: Any,
    center: Any,
    poller: Any,
    systems: dict[str, Any],
) -> APIRouter:
    """
    `GET /companies`(공개)와 `/admin/*`(관리자 모드). `systems` — 회사 id → 회사 시스템 클라이언트
    (`app/company.py`). 키·토큰 값은 어디에도 싣지 않는다.
    """
    router = APIRouter()

    def admin(x_admin_key: str | None = Header(default=None)) -> None:
        key = os.getenv("NOWVIEW_ADMIN_KEY") or ""
        if not key:
            raise HTTPException(503, "관리자 모드가 꺼져 있다 — NOWVIEW_ADMIN_KEY가 없다")
        if not hmac.compare_digest(x_admin_key or "", key):
            raise HTTPException(401, "관리자 키가 없거나 틀렸다")

    @router.get("/companies")
    def companies() -> list[dict[str, Any]]:
        return public_companies(settings.config)

    @router.get("/admin/status", dependencies=[Depends(admin)])
    def status() -> dict[str, Any]:
        return {
            "consumer": worker.describe(),
            "recent": worker.recent_tasks(),
            "center": {**center.config.describe(), "polling": poller.running},
            "companies": {
                cid: {**client.describe(), "reachable": client.reachable()}
                for cid, client in systems.items()
            },
            "restartRequired": settings.config.topics != settings.started_topics,
        }

    @router.get("/admin/config", dependencies=[Depends(admin)])
    def get_config() -> dict[str, Any]:
        return {
            "config": settings.config.model_dump(),
            "updatedAt": settings.updated_at,
            "scenes": SCENE_WORKS,
            # 고정 확장의 작업 — 읽기만 한다(NowView 판과 함께 바뀐다)
            "extension": _extension_summary(),
        }

    @router.put("/admin/config", dependencies=[Depends(admin)])
    def put_config(body: dict[str, Any]) -> dict[str, Any]:
        try:
            config = NowViewConfig.model_validate(body)
        except ValidationError as exc:
            reasons = [_reason(e) for e in exc.errors()]
            raise HTTPException(422, {"message": "설정이 맞지 않는다", "reasons": reasons}) from exc
        unknown = [c.id for c in config.companies if c.id not in systems]
        if unknown:
            # 회사의 업무 코드(회사 시스템 클라이언트·장면 처리기)가 없으면 매핑해도 처리할 수 없다
            raise HTTPException(
                422,
                {
                    "message": "NowView에 그 회사의 업무 코드가 없다",
                    "reasons": [f"companies: {', '.join(unknown)}"],
                },
            )
        settings.replace(config)
        return {
            "config": config.model_dump(),
            "updatedAt": settings.updated_at,
            "restartRequired": config.topics != settings.started_topics,
        }

    return router


def _extension_summary() -> dict[str, Any]:
    raw = json.loads(EXTENSION.read_text("utf-8"))
    return {
        "id": raw["id"],
        "version": raw["version"],
        "operations": [op["name"] for op in raw["service"]["adapter"]["operations"]],
    }


def _reason(error: Any) -> str:
    """Pydantic 오류 한 줄 — 위치가 없는(설정 전체의) 검사는 사유만 보인다."""
    message = str(error["msg"]).removeprefix("Value error, ")
    where = ".".join(map(str, error["loc"]))
    return f"{where}: {message}" if where else message
