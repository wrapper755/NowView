"""
Chaeksas Center 연동(N3) — 엔진 안의 클라이언트. 키는 **엔진만 쥔다**(브라우저·BFF에 없다).

* `CHAEKSAS_CENTER_URL` — Center 주소(`…/api/v1`을 붙이지 않는다)
* `CHAEKSAS_INTEGRATION_KEY` — 연동용 키: SC01 기동(`POST /jobs`), 정정본(`POST /messages`),
  진행(`GET /runs/{id}/events`), 대체된 작업 거두기(`DELETE /jobs/{id}`)
* `CHAEKSAS_RELAY_KEY` — 대리 답용 키: 결재 읽기·답(`X-CHK-On-Behalf-Of` = 행위자 이름, C6·ADR-0081)
* `CHAEKSAS_SC01_PACKAGE` — SC01 패키지 id(기본 `nowview.sc01`). 실행 기록은 패키지 id로 말한다
  (ADR-0086)
* `CHAEKSAS_INTAKE_WORKER` — 고객계획 접수 가상 직원 id(N5, 예: `nowview-intake`). 있으면 원천
  수신이 SC01을 직접 기동하지 않고 메시지(`고객계획접수`)로 그 가상 직원의 접수 Bot을 깨운다.
  감독자가 승인한 건만 접수 Bot이 SC01을 위임해 기동한다. 읽기(`GET /virtual-workers/{id}`)는
  연동용 키로 한다.

**설정이 없으면 조용히 다른 길로 가지 않는다.** center 데모 실행에서 그 설정이 필요한 조작은 503과
빠진 이름을 낸다(`problem`). Center 콘솔에서 답하는 길(N2·N6)은 이 설정 없이도 돈다.

키가 둘인 것은 Chaeksas의 권한표 그대로다 — 대리 답용 키는 결재만 읽고 답하고(`require_read`가
막는다), 연동용 키는 결재를 읽지 못한다(`require_approval_read`).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

from app.sc01.domain import DomainError

API = "/api/v1"
#: 한 요청의 상한. 조작 하나가 Center를 기다리는 동안 그 데모 실행의 잠금을 쥐는 일이 있다.
TIMEOUT_S = 10.0


class CenterError(Exception):
    """Center가 거절했거나 닿지 못했다. `status`·`code`는 Center의 것(C6 오류 표)이다."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status, self.code, self.message = status, code, message

    def as_domain(self, what: str) -> DomainError:
        """화면에 낼 사유. 키·설정 문제(401·키 상태 403)는 사람이 고칠 것이 아니라 503이다."""
        if self.code == "unreachable":
            return DomainError(f"{what} — Center에 닿지 못했다: {self.message}", 503)
        if self.status == 401 or self.code.startswith("key_") or self.code == "forbidden":
            return DomainError(
                f"{what} — Center 연동 키가 받아들여지지 않았다: {self.message}", 503
            )
        status = self.status if self.status in (403, 404, 409, 422) else 502
        return DomainError(f"{what} — Center: {self.message} ({self.code})", status)


@dataclass(frozen=True)
class CenterConfig:
    url: str | None = None
    integration_key: str | None = None
    relay_key: str | None = None
    package: str = "nowview.sc01"
    intake_worker: str | None = None

    @classmethod
    def from_env(cls) -> CenterConfig:
        return cls(
            url=(os.getenv("CHAEKSAS_CENTER_URL") or "").rstrip("/") or None,
            integration_key=os.getenv("CHAEKSAS_INTEGRATION_KEY") or None,
            relay_key=os.getenv("CHAEKSAS_RELAY_KEY") or None,
            package=os.getenv("CHAEKSAS_SC01_PACKAGE") or "nowview.sc01",
            intake_worker=os.getenv("CHAEKSAS_INTAKE_WORKER") or None,
        )

    def missing(self, *, relay: bool = False, integration: bool = False) -> str | None:
        """그 일에 빠진 설정의 사유. 다 있으면 `None`."""
        names = [
            name
            for name, value, wanted in (
                ("CHAEKSAS_CENTER_URL", self.url, True),
                ("CHAEKSAS_INTEGRATION_KEY", self.integration_key, integration),
                ("CHAEKSAS_RELAY_KEY", self.relay_key, relay),
            )
            if wanted and not value
        ]
        if not names:
            return None
        return "Center 연동이 설정되지 않았다 (" + "·".join(names) + ")"

    def describe(self) -> dict[str, Any]:
        """`/health`용 — 키 값은 싣지 않는다."""
        return {
            "url": self.url,
            "integration": bool(self.integration_key),
            "relay": bool(self.relay_key),
            "package": self.package,
            "intakeWorker": self.intake_worker,
        }


class CenterClient:
    """
    Center REST(C3·C5·C6·C12)의 NowView가 쓰는 몫. `transport`는 시험이 가짜 Center를 끼우는 자리다.
    """

    def __init__(
        self, config: CenterConfig, *, transport: httpx.BaseTransport | None = None
    ) -> None:
        self.config = config
        self._transport = transport

    # ───────────── 연동용 키 ─────────────

    def start_job(self, inputs: dict[str, Any], *, idempotency_key: str, on_behalf: str) -> dict:
        """SC01 기동 — 서버 실행기에 맡긴다(대상 id는 Center가 고른다)."""
        return self._call(
            "POST",
            "/jobs",
            self._need("integration"),
            on_behalf=on_behalf,
            json={
                "bpm_process_id": self.config.package,
                "target": {"type": "server_runner"},
                "inputs": inputs,
                "idempotency_key": idempotency_key,
                "note": "NowView SC01 — 고객계획 수신",
            },
        )

    def send_message(
        self,
        name: str,
        *,
        correlation: str | None = None,
        payload: dict[str, Any],
        idempotency_key: str,
        on_behalf: str,
        virtual_worker: str | None = None,
    ) -> dict:
        """
        메시지 하나(C12 §메시지). 상관 키가 있으면 기다리는 실행에(정정본 EX03), 없으면
        **메시지 시작**만 깨운다 — 접수 Bot(N5). `virtual_worker`는 메시지 시작으로 만들 작업의
        가상 직원 id다(ADR-0099 — 그 가상 직원의 `intake`가 이 Bot이 아니면 422
        `virtual_worker_mismatch`).
        """
        body: dict[str, Any] = {
            # 메시지는 `schema`가 있는 계약이다(`MessageRequest`) — 빠지면 422 input_invalid(실측).
            "schema": 1,
            "name": name,
            "payload": payload,
            "idempotency_key": idempotency_key,
        }
        if correlation is not None:
            body["correlation"] = correlation
        if virtual_worker is not None:
            body["virtual_worker"] = virtual_worker
        return self._call(
            "POST", "/messages", self._need("integration"), on_behalf=on_behalf, json=body
        )

    def virtual_worker(self, worker_id: str) -> dict:
        """가상 직원 하나 + 최근 일괄 20개(C5 CON-13). 연동용 키는 전부 읽는다(ADR-0098 §4)."""
        return self._call("GET", f"/virtual-workers/{quote(worker_id)}", self._need("integration"))

    def job(self, job_id: str) -> dict:
        """NowView가 만든 작업 하나(C5 `JobInfo`) — `state`·`state_reason`·`run_status`."""
        return self._call("GET", f"/jobs/{quote(job_id)}", self._need("integration"))

    def cancel_job(self, job_id: str) -> dict:
        """NowView가 기동한 작업을 거둔다(정정·초기화로 대체됐다). 도는 서버 실행도 멈춘다."""
        return self._call("DELETE", f"/jobs/{quote(job_id)}", self._need("integration"))

    def run_events(self, run_id: str) -> list[dict[str, Any]]:
        """그 실행의 C3 이벤트 전부, `seq` 차례로."""
        body = self._call("GET", f"/runs/{quote(run_id)}/events", self._need("integration"))
        return list(body.get("events") or [])

    # ───────────── 대리 답용 키 ─────────────

    def approval(self, request_id: str, *, on_behalf: str) -> dict | None:
        """결재 하나. 그 사람이 담당이 아니면 Center가 404로 숨긴다 — `None`."""
        try:
            return self._call(
                "GET", f"/approvals/{quote(request_id)}", self._need("relay"), on_behalf=on_behalf
            )
        except CenterError as exc:
            if exc.status == 404:
                return None
            raise

    def open_approvals(self, *, on_behalf: str) -> list[dict]:
        """그 사람이 담당인 열린 결재(최신순)."""
        found = self._call(
            "GET",
            "/approvals",
            self._need("relay"),
            on_behalf=on_behalf,
            params={"state": "open", "assignee": on_behalf},
        )
        return list(found or [])

    def answer(
        self, request_id: str, answer: dict[str, Any], *, on_behalf: str, digest: str | None
    ) -> dict:
        """대리 답. `digest`는 사람이 본 결재의 지문 — 그 사이 바뀌었으면 409 `review_changed`."""
        body: dict[str, Any] = {"answer": answer}
        if digest:
            body["if_review_digest"] = digest
        return self._call(
            "POST",
            f"/approvals/{quote(request_id)}/answer",
            self._need("relay"),
            on_behalf=on_behalf,
            json=body,
        )

    # ───────────── 속 ─────────────

    def _need(self, which: str) -> str:
        problem = self.config.missing(relay=which == "relay", integration=which == "integration")
        if problem:
            raise CenterError(503, "unconfigured", problem)
        key = self.config.relay_key if which == "relay" else self.config.integration_key
        assert key is not None  # missing()가 본다
        return key

    def _call(
        self,
        method: str,
        path: str,
        key: str,
        *,
        on_behalf: str | None = None,
        json: Any = None,
        params: dict[str, str] | None = None,
    ) -> Any:
        headers = {"Authorization": f"Bearer {key}"}
        if on_behalf is not None:
            # UTF-8 퍼센트 인코딩 — Center가 풀어 담당자와 같은 정규화로 맞춘다(C6).
            headers["X-CHK-On-Behalf-Of"] = quote(on_behalf, safe="")
        try:
            with httpx.Client(
                base_url=f"{self.config.url}{API}", timeout=TIMEOUT_S, transport=self._transport
            ) as client:
                response = client.request(method, path, headers=headers, json=json, params=params)
        except httpx.HTTPError as exc:
            raise CenterError(503, "unreachable", type(exc).__name__) from exc
        if response.status_code >= 400:
            try:
                err = response.json()
            except ValueError:
                err = {}
            raise CenterError(
                response.status_code,
                str(err.get("code") or "http_error"),
                str(err.get("message") or err.get("detail") or response.status_code),
            )
        return response.json() if response.content else None
