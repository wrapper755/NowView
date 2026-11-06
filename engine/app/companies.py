"""
회사 — 공개 목록(`GET /companies`)과 관리자 모드(`/admin/*`).

NowView는 회사 사이트가 아니다. 두 가지 일을 한다(2026-10-31 사용자 정의,
`docs/worker-interfaces.md` §1):

* **일꾼** — Center에 올린 회사별 BPM 프로세스의 서비스 태스크 일감을 가져가 수행한다
  (`app/consumer.py`). 일꾼이 제공하는 작업은 기본 확장 `external`(External Service) 하나이고,
  어느 회사의 어느 BPM 프로세스를 맡는지는 **설정**이다(`app/config.py`).
* **회사별 대시보드** — N개 회사의 운영 현황을 그 회사의 BPM 진행 위에서 보여 준다.

**등록은 공개하지 않는다.** 공개 목록은 회사 이름·설명과 그 회사가 쓰는 업무 번호뿐이다 — BPM
프로세스 id·토픽·회사 시스템 주소·일꾼 상태는 관리자 모드(`/admin/*`)에만 있다. 관리
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
from .sc01.domain import DomainError

#: NowView가 아는 업무(장면) — 코드에 화면·처리기가 있다. 화면 쪽 사본은 `lib/companies.ts`의
#: `SCENES` (시험이 대조).
SCENE_WORKS: dict[int, str] = {
    1: "고객 생산계획 변경 대응",
    2: "외주 단가 인상 검토",
    3: "수익성 통합 분석",
    4: "개선안 검토·실행 승인",
    5: "결정 실행·계획 갱신",
    6: "완료·성과 검토",
    7: "관리모델 개선·적용",
    21: "납기 위험 조기 감지",
    22: "정형통제 실행과 주문별 분기",
    23: "잔여 납기 위험의 경영검토와 대응 합의",
    24: "실행 결과 확인과 관리기준 개선",
    31: "결산조정 업무 착수",
}
#: 업무 번호 → (시나리오, 그 시나리오의 장면) — 회차(세계)는 시나리오 하나에 속한다. 시나리오 2
#: 장면 N은 20 + N, 시나리오 3 장면 N은 30 + N이다(`docs/platform.md` §7 — 문자열 키로
#: 바꾸면 저장된 설정을 옮겨야 해서 번호 공간을 나눴다).
WORKS: dict[int, tuple[str, int]] = {n: ("s1", n) for n in range(1, 8)} | {
    21: ("s2", 1),
    22: ("s2", 2),
    23: ("s2", 3),
    24: ("s2", 4),
    31: ("s3", 1),
}


def works_of(scenario_id: str | None) -> list[int]:
    """그 시나리오의 업무 번호(장면 순)."""
    return [n for n, (s, _scene) in sorted(WORKS.items()) if s == (scenario_id or "s1")]


EXTENSION = Path(__file__).resolve().parents[2] / "chaeksas" / "external.extension.json"


class Settings:
    """
    지금 설정 — 관리자 모드가 고치면 바로 바뀐다(일꾼의 매핑·회사 시스템 주소). 토픽은 일꾼 파일을
    다시 지어 엔진·Center를 다시 띄워야 한다(Center가 그 파일의 토픽만 내준다).
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
    """
    공개 목록 — 이름·설명·업무 번호·회사 사이트(공개 웹) 주소. BPM 프로세스 id·회사 시스템
    주소는 내지 않는다.
    """
    return [
        {
            "id": c.id,
            "name": c.name,
            "description": c.description,
            "scenes": sorted({p.scene for p in config.processes if p.company == c.id}),
            "siteUrl": c.public_site_url(),
        }
        for c in config.companies
    ]


def build_router(
    settings: Settings,
    worker: Any,
    center: Any,
    poller: Any,
    systems: dict[str, Any],
    scenes: dict[int, Any] | None = None,
) -> APIRouter:
    """
    `GET /companies`(공개)와 `/admin/*`(관리자 모드). `systems` — 회사 id → 회사 시스템 클라이언트
    (`app/company.py`). `scenes` — 업무 번호 → 그 장면의 프로세스(문서 저장소를 읽는다).
    키·토큰 값은 어디에도 싣지 않는다.
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

    @router.get("/companies/{company_id}/dashboard")
    def dashboard(company_id: str, world: str | None = None) -> dict[str, Any]:
        """
        회사 대시보드 — 세계(시연 회차) 목록과, 고른 세계의 업무마다 BPM 진행·일꾼 일감·핵심 지표
        (`app/dashboard.py`). 세계는 회사 시스템의 것 중 이 엔진이 따라가는 것(장면 1 문서가 있다)만
        보이고, 사이트가 만든 세계(`origin: site`)를 최근에 만들거나 초기화한 순서로 앞에 둔다 —
        회사 시스템은 세계를 id 순서로 준다. `world`가 없으면 맨 앞 세계다. 회사 시스템에 닿지
        않으면 세계 없이 사유를 싣는다.
        """
        from app import dashboard as board  # dashboard가 SCENE_WORKS를 읽는다 — 순환을 피한다

        public = next((c for c in public_companies(settings.config) if c["id"] == company_id), None)
        if public is None:
            raise HTTPException(404, f"없는 회사: {company_id}")
        procs = scenes or {}
        system = systems.get(company_id)
        problem: str | None = None
        worlds: list[dict[str, Any]] = []
        try:
            listed = system.worlds() if system is not None else []
        except DomainError as exc:
            listed, problem = [], str(exc)

        def first_doc(w: dict[str, Any]) -> bool:
            """따라가는 세계 — 그 회차 시나리오의 첫 업무 문서가 있다."""
            mine = works_of(w.get("scenario_id"))
            proc = procs.get(mine[0]) if mine else None
            return proc is not None and proc.store.load(w["world_id"]) is not None

        followed = [w for w in listed if first_doc(w)]
        followed.sort(key=lambda w: w.get("reset_at") or "", reverse=True)
        followed.sort(key=lambda w: w.get("origin") != "site")
        for w in followed:
            worlds.append(
                {
                    "worldId": w["world_id"],
                    "scenarioId": w.get("scenario_id") or "s1",
                    "origin": w.get("origin"),
                    "caseId": w.get("case_id"),
                    "generation": w.get("generation"),
                    "clock": w.get("clock"),
                }
            )
        known = {w["worldId"] for w in worlds}
        chosen = world if world in known else (worlds[0]["worldId"] if worlds else None)
        if world is not None and world not in known:
            problem = problem or f"따라가는 세계가 아니다: {world} — 맨 앞 세계를 보인다"
        log_rows: list[dict[str, Any]] = []
        if chosen is not None and system is not None:
            try:
                log_rows = system.worker_log_entries(chosen)
            except DomainError as exc:
                problem = problem or str(exc)
        scenario = next((w["scenarioId"] for w in worlds if w["worldId"] == chosen), "s1")
        works = []
        for no in [n for n in public["scenes"] if n in works_of(scenario)]:
            proc = procs.get(no)
            found = proc.store.load(chosen) if proc is not None and chosen is not None else None
            works.append(
                {
                    **board.work(no, proc, found[0] if found else None),
                    # 일감 기록의 장면은 그 회차 시나리오의 장면 번호다
                    "worker": board.worker_entries(log_rows, WORKS[no][1]),
                }
            )
        return {
            "company": {k: public[k] for k in ("id", "name", "description", "siteUrl")},
            "worlds": worlds,
            "world": chosen,
            "problem": problem,
            "works": board.with_case_control(works),
        }

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
