"""
회사 등록부 — NowView가 대시보드를 보여 주는 회사와, 그 회사의 BPM 프로세스(장면)가 Center에 어떤
이름으로 올라가 있는지.

NowView는 회사 사이트가 아니다. 두 가지 일을 한다(2026-10-31 사용자 정의):

* **일꾼** — 회사마다 Center에 올린 BPM 프로세스의 서비스 태스크 일감을 가져가 수행한다
  (`app/consumer.py`). 토픽에 회사가 들어간다(`autoparts-sc01`) — 일감 입력에 회사를 싣지 않는다.
* **회사별 대시보드** — N개 회사의 운영 현황을 그 회사의 BPM 진행 위에서 보여 준다.

지금 회사는 하나다 — 가상 자동차 부품사(가칭, `autoparts`). 장면은 하나씩 회사 이름으로 옮긴다:
옮긴 장면은 `autoparts-scN`·`autoparts.scN`이고, 아직 옮기지 않은 장면은 예전 이름(`nowview-scN`)
그대로다(`migrated`). 화면 쪽 등록부는 `lib/companies.ts`이고 시험이 둘을 대조한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter


@dataclass(frozen=True)
class Scene:
    """회사의 BPM 프로세스 하나 — 시연 순서(`no`), 업무 이름, Center의 일꾼 토픽·패키지 id."""

    no: int
    work: str
    topic: str
    package: str

    @property
    def migrated(self) -> bool:
        """회사 이름으로 옮겨 Center에 다시 올린 장면인가."""
        return not self.topic.startswith("nowview-")


@dataclass(frozen=True)
class Company:
    id: str
    name: str
    description: str
    scenes: tuple[Scene, ...]


COMPANIES: tuple[Company, ...] = (
    Company(
        id="autoparts",
        name="가상 자동차 부품사",
        description=(
            "매출 약 1조원 · 현대·기아 주요 고객 · A제품 울산공장 a~e 모델 — 2027년 시나리오 1"
        ),
        scenes=(
            Scene(1, "고객 생산계획 변경 대응", "autoparts-sc01", "autoparts.sc01"),
            Scene(2, "외주 단가 인상 검토", "nowview-sc02", "nowview.sc02"),
            Scene(3, "수익성 통합 분석", "nowview-sc03", "nowview.sc03"),
            Scene(4, "개선안 검토·실행 승인", "nowview-sc04", "nowview.sc04"),
            Scene(5, "결정 실행·계획 갱신", "nowview-sc05", "nowview.sc05"),
            Scene(6, "완료·성과 검토", "nowview-sc06", "nowview.sc06"),
        ),
    ),
)


def company(company_id: str) -> Company | None:
    return next((c for c in COMPANIES if c.id == company_id), None)


def describe(c: Company) -> dict[str, Any]:
    return {
        "id": c.id,
        "name": c.name,
        "description": c.description,
        "scenes": [
            {
                "no": s.no,
                "work": s.work,
                "topic": s.topic,
                "package": s.package,
                "migrated": s.migrated,
            }
            for s in c.scenes
        ],
    }


def build_router(
    worker: Any, center: Any, poller: Any, systems: dict[str, Any] | None = None
) -> APIRouter:
    """
    `/companies`(등록부 + 회사 시스템 연결)와 `/worker`(일꾼 상태). 키·토큰 값은 싣지 않는다.
    `systems` — 회사 id → 회사 시스템 클라이언트(`app/company.py`).
    """
    router = APIRouter()
    systems = systems or {}

    @router.get("/companies")
    def companies() -> list[dict[str, Any]]:
        return [{**describe(c), "system": _system(systems.get(c.id))} for c in COMPANIES]

    @router.get("/worker")
    def worker_status() -> dict[str, Any]:
        return {
            "consumer": worker.describe(),
            "recent": worker.recent_tasks(),
            "center": {**center.config.describe(), "polling": poller.running},
        }

    return router


def _system(client: Any) -> dict[str, Any] | None:
    """회사 시스템 연결 — 설정이 있으면 `/health`를 물어 닿는지 본다(짧게)."""
    if client is None:
        return None
    info = dict(client.describe())
    info["reachable"] = client.reachable() if client.configured else False
    return info
