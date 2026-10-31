"""
회사 시스템 클라이언트 — 일꾼이 회사의 자료를 읽고 확정 기록을 돌려 적는
길(`docs/worker-interfaces.md` §3.2).

NowView는 회사 사이트가 아니다. 회사의 조직·계획·실적·원가·고객계획 원천은 회사 시스템에 있고,
NowView는 그것을 읽어 규칙 계산(R01)을 하고 경영 기록(이슈·업무·검토)을 남긴다. 지금 회사는 가상
자동차 부품사(`autoparts`) 하나 — 그 회사 시스템은 별도 서버로 도는 시뮬레이터다(`company-sim/`).

* **연결은 늘 NowView → 회사다.** 회사 시스템은 NowView 주소를 모른다 — 받은 원천은 수신함에 쌓이고
  NowView가 묻는다.
* **세계(world) = 데모 실행.** 시연을 처음부터 다시 돌릴 수 있게 회사의 변하는 기록(수신함·원천
  상태·시각)은 세계마다 따로다. 불변 기록(T01·F01·C01·FC01)은 세계와 무관하다 — 한 번 읽어
  캐시한다(버전은 지워지지 않는다).
* **회사가 늦거나 죽으면 `CompanyUnavailable`(503)이다** — 업무 규칙 위반이 아니다. 일꾼은 C15
  `dependency_down` (다시 내줄 일)으로 돌려준다. 조용히 엑셀 시드로 되돌아가지 않는다.

설정 — `COMPANY_AUTOPARTS_URL`(예 `http://localhost:8091`) · `COMPANY_AUTOPARTS_KEY`(회사 시스템
키).
"""

from __future__ import annotations

import os
import threading
from datetime import date
from decimal import Decimal
from typing import Any

import httpx

from app.sc01.domain import DomainError
from app.sc01.seed import Key, Seed, SourceRow, UnitCost, load_rules

#: 엔진이 쓰는 회사 기록 버전 — 계산 run이 `versions`로 남긴다.
PLAN_VERSIONS = ("T01", "F01")
COST_VERSION = "C01"
FIXED_VERSION = "FC01"
BASELINE_PLAN = "CP01"


class CompanyUnavailable(DomainError):
    """회사 시스템에 닿지 않는다 — 다시 해 볼 일이다."""

    def __init__(self, message: str) -> None:
        super().__init__(message, 503)


def _key(r: dict[str, Any]) -> Key:
    return (r["customer_id"], r["plant_id"], r["model_id"], date.fromisoformat(r["period"]))


def source_row(r: dict[str, Any]) -> SourceRow:
    return SourceRow(
        source_id=r["source_id"],
        customer_plan_id=r["customer_plan_id"],
        customer_id=r["customer_id"],
        plant_id=r["plant_id"],
        model_id=r["model_id"],
        period=date.fromisoformat(r["period"]),
        quantity=r["quantity"],
        unit=r["unit"],
        quantity_scope=r["quantity_scope"],
        allocation_scope=r["allocation_scope"],
    )


class CompanyClient:
    def __init__(
        self,
        url: str | None,
        key: str | None = None,
        *,
        company_id: str = "autoparts",
        client: httpx.Client | None = None,
        timeout_s: float = 10.0,
    ) -> None:
        self.url = (url or "").rstrip("/") or None
        self.key = key or None
        self.company_id = company_id
        self._client = client
        self.timeout_s = timeout_s
        self._seed: Seed | None = None
        self._worlds: set[str] = set()
        self._guard = threading.Lock()

    @classmethod
    def from_env(cls, company_id: str = "autoparts") -> CompanyClient:
        prefix = f"COMPANY_{company_id.upper()}"
        return cls(
            os.getenv(f"{prefix}_URL"), os.getenv(f"{prefix}_KEY"), company_id=company_id
        )

    @property
    def configured(self) -> bool:
        return self.url is not None or self._client is not None

    def describe(self) -> dict[str, Any]:
        """`/health`·`/worker`용 — 키 값은 싣지 않는다."""
        return {"company": self.company_id, "url": self.url, "key": self.key is not None}

    def reachable(self) -> bool:
        """회사 시스템 `/health`가 응답하나 — 대시보드의 연결 표시용(업무 판단에 쓰지 않는다)."""
        try:
            return self._http().get("/health", timeout=2.0).status_code == 200
        except (httpx.HTTPError, CompanyUnavailable):
            return False

    # ───────────── HTTP ─────────────

    def _http(self) -> httpx.Client:
        if self._client is None:
            if self.url is None:
                raise CompanyUnavailable(
                    f"회사 시스템 주소가 없다(COMPANY_{self.company_id.upper()}_URL)"
                )
            self._client = httpx.Client(base_url=self.url, timeout=self.timeout_s)
        return self._client

    def _call(self, method: str, path: str, body: Any = None) -> Any:
        headers = {"authorization": f"Bearer {self.key}"} if self.key else {}
        try:
            response = self._http().request(method, path, json=body, headers=headers)
        except httpx.HTTPError as exc:
            raise CompanyUnavailable(f"회사 시스템에 닿지 않는다: {exc}") from exc
        if response.status_code >= 500 or response.status_code in (401, 403):
            raise CompanyUnavailable(
                f"회사 시스템이 {response.status_code}를 돌려줬다: {_detail(response)}"
            )
        if response.status_code >= 400:
            raise DomainError(f"회사 시스템: {_detail(response)}", response.status_code)
        return response.json()

    # ───────────── 불변 기록 ─────────────

    def load_seed(self) -> Seed:
        """
        엔진 계산이 쓰는 회사 자료(T01·F01·실적·C01·FC01·CP01)를 읽어 `Seed` 모양으로 엮는다.
        규칙(R01)은
        NowView 것이라 엔진 시드에서 읽는다. 버전은 불변이라 한 번 읽어 둔다.
        """
        with self._guard:
            if self._seed is not None:
                return self._seed
        plans = {}
        for v in PLAN_VERSIONS:
            rows = self._call("GET", f"/company/plans/{v}")["rows"]
            plans[v] = {_key(r): int(r["quantity"]) for r in rows}
        actuals: dict[Key, int] = {}
        cutoffs: dict[Key, date] = {}
        for r in self._call("GET", "/company/actuals")["rows"]:
            actuals[_key(r)] = int(r["quantity"])
            cutoffs[_key(r)] = date.fromisoformat(r["cutoff_date"])
        costs = {
            _key(r): UnitCost(
                price=Decimal(r["unit_price"]),
                variable_cost=Decimal(r["unit_variable_cost"]),
                cm=Decimal(r["unit_cm"]),
            )
            for r in self._call("GET", f"/company/costs/{COST_VERSION}")["rows"]
        }
        fixed = {
            (r["plant_id"], date.fromisoformat(r["period"])): Decimal(r["total_fixed"])
            for r in self._call("GET", f"/company/fixed-costs/{FIXED_VERSION}")["rows"]
        }
        baseline = self._call("GET", f"/company/customer-plans/{BASELINE_PLAN}")["rows"]
        versions = {v["version_id"]: v for v in self._call("GET", "/company/versions")}
        seed = Seed(
            versions=versions,
            plans=plans,
            customer_plans={BASELINE_PLAN: [source_row(r) for r in baseline]},
            actuals=actuals,
            actual_cutoffs=cutoffs,
            costs=costs,
            fixed_costs=fixed,
            rules=load_rules(),
            models=self._call("GET", "/company/master")["models"],
        )
        with self._guard:
            self._seed = seed
        return seed

    # ───────────── 세계 ─────────────

    def ensure_world(self, world_id: str) -> None:
        """세계를 만든다(멱등). 이 프로세스에서 이미 만든 세계는 다시 묻지 않는다."""
        if world_id in self._worlds:
            return
        self._call("POST", "/worlds", {"world_id": world_id})
        self._worlds.add(world_id)

    def reset_world(self, world_id: str) -> None:
        self.ensure_world(world_id)
        self._call("POST", f"/worlds/{world_id}/reset")

    def set_clock(self, world_id: str, at: str) -> None:
        self.ensure_world(world_id)
        self._call("POST", f"/worlds/{world_id}/clock", {"at": at})

    def customer_sends(self, world_id: str, fixture_id: str) -> dict[str, Any]:
        """시연 — 고객이 원천을 보냈다. 회사 수신함에 들어간 접수 요약을 돌려준다."""
        self.ensure_world(world_id)
        return self._call(
            "POST", f"/worlds/{world_id}/sim/customer-plans", {"fixture_id": fixture_id}
        )

    def customer_plan(self, world_id: str, doc_id: str) -> dict[str, Any]:
        return self._call("GET", f"/worlds/{world_id}/customer-plans/{doc_id}")

    def inbox(self, world_id: str, after: int = 0) -> list[dict[str, Any]]:
        self.ensure_world(world_id)
        return self._call("GET", f"/worlds/{world_id}/customer-plans/inbox?after={after}")

    def set_plan_status(self, world_id: str, doc_id: str, **record: Any) -> dict[str, Any]:
        """원천 확인 결정을 회사에 적는다 — `ref`가 같으면 회사가 다시 적지 않는다(멱등)."""
        return self._call("POST", f"/worlds/{world_id}/customer-plans/{doc_id}/status", record)


def _detail(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text[:200]
    return str(body.get("detail", body)) if isinstance(body, dict) else str(body)


#: 시험이 끼운다 — 같은 프로세스의 시뮬레이터(`tests/conftest.py`).
_override: CompanyClient | None = None


def default_client() -> CompanyClient:
    return _override or CompanyClient.from_env()
