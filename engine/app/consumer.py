"""
C15 일꾼 — Center에 쌓인 NowView 서비스 태스크의 일감을 가져가 이 프로세스에서
수행한다.

Chaeksas는 바깥 기능을 부르는 길을 모두 Pull로 바꿨다(ADR-0102, 계약 C15). 서버
실행기·Studio는 `chk:serviceCall`을 **Center에 외부 작업으로 올리고**, 토픽(`app_id` =
`nowview-sc01`~`sc06`)을 맡은 일꾼이 롱폴링으로 가져가 끝냈다고 알린다. 연결은 늘
NowView → Center다 — Center는 NowView 주소도 키도 모른다.

```
서버 실행기·Studio ─올리기─▶ Center(외부 작업) ◀─가져가기·끝내기─ 이 일꾼 ─▶ 장면 N operate
```

예전에는 Center 쪽 HTTP 어댑터가 BFF의 `/operations/…`를 키(N6)로 찔렀다. 그 길은 없다:

* **실행 위치는 일감의 `origin`이 말한다** — Studio 시험 실행은 `test`, 서버 실행은
  `run`이다. Center가 올린 쪽을 인증하고(Studio는 `test_…` 실행만 올린다) 붙이는 값이라
  부르는 쪽이 지어낼 수 없다. 시험용 키 ↔ 운영 키로 가르던 것을 이것이 맡는다
  (`domain.link_external_run`의 `via`).
* **본문은 그림의 입력 그대로다** — `task.input`이 `chk:serviceCall.input`이고 실행 id·
  노드 id는 멱등 칸에 있다. 확장 정의의 요청 템플릿(경로·본문)은 이 길에서 쓰지 않는다
  — 정의는 작업 목록·스키마(Studio가 고를 거리, Center가 대조할 manifest)로만 읽는다.
* **거절 사유가 그대로 간다** — 어댑터는 4xx 본문을 버렸다(「…이 409를 돌려줬다」).
  이제 `fail`의 `message`가 업무 규칙의 글이다.
* **최소 한 번 실행이다**(C15). 잠금이 지나 같은 일감이 다시 오면 `service_kit`의 멱등
  저장소가 저장한 결과를 다시 준다. 저장소는 메모리다 — 엔진이 다시 뜨면 비고, 그 사이
  다시 온 일감은 한 번 더 돈다.

설정 — `CHAEKSAS_CENTER_URL`(N3와 같은 값)이 있으면 뜬다. 끄려면 `NOWVIEW_CONSUMER=off`.

* 토큰은 `NOWVIEW_CONSUMER_DIR`(기본 `engine/.consumer`)의 파일에 둔다. 처음에는
  **들이기 요청**을 보내고 요청 코드를 로그·`/health.consumer.requestCode`에 보인다 —
  관리자가 Center CON-07 「일꾼 승인 대기」에서 같은 코드를 승인하면 토큰이 내려온다.
  `NOWVIEW_CONSUMER_TOKEN`이 있으면 그것이 이긴다.
* 확장 정의는 `NOWVIEW_EXTENSIONS_DIR`(기본 리포의 `chaeksas/`)에서 읽는다.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import platform
import threading
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from chaeksas.contracts.service_app import OpRequest, ServiceAppManifest
from chaeksas.service_kit import Consumer, Enrollment, TokenFile
from chaeksas.service_kit.app import OpError, Service

from app.sc01.domain import DomainError

log = logging.getLogger("nowview.consumer")

#: 일감의 `origin` → 데모 실행의 실행 위치(`bpm.executor`).
EXECUTOR_OF_ORIGIN = {"test": "studio", "run": "center"}
#: 업무 규칙 위반의 상태 코드 → C15 실패 코드. 모두 다시 불러도 같은 답이라 `retryable`이 아니다.
CODE_OF_STATUS = {403: "forbidden", 404: "not_found", 409: "conflict", 422: "input_invalid"}
#: 들이기 요청의 상태를 다시 묻는 간격(초).
ENROLL_EVERY_S = 5.0

DEFAULT_EXTENSIONS_DIR = Path(__file__).resolve().parents[2] / "chaeksas"
DEFAULT_TOKEN_DIR = Path(__file__).resolve().parents[1] / ".consumer"


class Operates(Protocol):
    """장면 N의 프로세스 — 시스템 작업 하나를 문서에 적는다(`ScNProcess.operate`)."""

    def operate(
        self,
        demo_run_id: str,
        operation: str,
        args: dict[str, Any],
        *,
        external_run_id: str | None,
        node_id: str | None = None,
        via: str | None = None,
    ) -> dict[str, Any]: ...


def extensions_dir() -> Path:
    found = os.getenv("NOWVIEW_EXTENSIONS_DIR")
    return Path(found) if found else DEFAULT_EXTENSIONS_DIR


def manifest_of(topic: str, folder: Path | None = None) -> ServiceAppManifest:
    """
    확장 정의(`chaeksas/{topic}.extension.json`)의 작업 → C11 manifest 모양. Center가
    이것으로 일감의 작업·모드를 대조하고 출력의 필수 칸을 막는다(C15). 어댑터 일꾼이
    정의에서 manifest를 짓는 것과 같다.
    """
    raw = json.loads(((folder or extensions_dir()) / f"{topic}.extension.json").read_text("utf-8"))
    adapter = raw["service"]["adapter"]
    limit = adapter.get("limits", {}).get("timeout_s")
    operations = []
    for op in adapter["operations"]:
        keys = ("name", "description", "modes", "input_schema", "output_schema")
        one = {k: op[k] for k in keys if k in op}
        if limit:
            one["timeout_s"] = limit
        operations.append(one)
    return ServiceAppManifest.model_validate(
        {
            "schema": 1,
            "app_id": raw["id"],
            "name": raw.get("name") or raw["id"],
            "version": raw["version"],
            "category": "business",
            "console_url": "",
            "operations": operations,
        }
    )


def scene_service(topic: str, process: Operates, folder: Path | None = None) -> Service:
    """토픽 하나 = 장면 하나의 `operate`. 작업마다 같은 처리기다 — 작업 이름으로 가른다."""
    manifest = manifest_of(topic, folder)

    def handler_for(operation: str):
        def handle(req: OpRequest, mode: str) -> dict[str, Any]:
            del mode  # 결정론 작업뿐이다
            args = dict(req.input)
            demo_run_id = args.pop("demo_run_id", None)
            if not demo_run_id:
                raise OpError("input_invalid", "입력에 demo_run_id가 없다", status=422)
            via = EXECUTOR_OF_ORIGIN.get(req.origin or "run", "center")
            try:
                return process.operate(
                    str(demo_run_id),
                    operation,
                    args,
                    external_run_id=req.run_id,
                    node_id=req.node_id,
                    via=via,
                )
            except DomainError as exc:
                code = CODE_OF_STATUS.get(exc.status, "rejected")
                raise OpError(code, str(exc), status=exc.status) from exc

        return handle

    handlers = {op.name: handler_for(op.name) for op in manifest.operations}
    return Service(manifest=manifest, handlers=handlers)


@dataclass
class ConsumerHost:
    """엔진 안에서 도는 일꾼 하나 — 들이기 → manifest 올리기 → 가져가기 루프(데몬 스레드)."""

    center_url: str | None
    services: list[Service]
    tokens: TokenFile
    enabled: bool = True
    name: str = "NowView 엔진"
    client: Any = None  # httpx.Client (시험이 끼운다)
    enroll_every_s: float = ENROLL_EVERY_S
    _stop: threading.Event = field(default_factory=threading.Event, init=False)
    _thread: threading.Thread | None = field(default=None, init=False)
    _consumer: Consumer | None = field(default=None, init=False)
    _state: str = field(default="off", init=False)
    _code: str | None = field(default=None, init=False)
    _problem: str | None = field(default=None, init=False)

    @classmethod
    def from_env(cls, processes: Mapping[str, Operates]) -> ConsumerHost:
        folder = Path(os.getenv("NOWVIEW_CONSUMER_DIR") or DEFAULT_TOKEN_DIR)
        tokens = TokenFile(
            path=folder / "consumer-token.json",
            env_value=os.getenv("NOWVIEW_CONSUMER_TOKEN") or None,
        )
        center_url = (os.getenv("CHAEKSAS_CENTER_URL") or "").rstrip("/") or None
        enabled = os.getenv("NOWVIEW_CONSUMER", "").lower() != "off"
        # 뜨지 않을 때는 확장 정의를 읽지 않는다 — 정의가 없는 자리(내장 시험·화면만)에서 엔진이
        # 기동조차 못 하면 안 된다. 뜰 때 정의가 없으면 기동에서 바로 드러난다.
        services = (
            [scene_service(topic, proc) for topic, proc in processes.items()]
            if enabled and center_url
            else []
        )
        return cls(center_url=center_url, services=services, tokens=tokens, enabled=enabled)

    @property
    def topics(self) -> list[str]:
        return [one.app_id for one in self.services]

    def start(self) -> None:
        if self._thread is not None:
            return
        if not self.enabled or not self.center_url:
            self._state = "off"
            return
        self._thread = threading.Thread(target=self._run, name="nowview-consumer", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _machine_id(self) -> str:
        where = self.tokens.path.resolve() if self.tokens.path is not None else "env"
        return hashlib.sha256(f"{platform.node()}|{where}".encode()).hexdigest()

    def _enroll(self) -> bool:
        """토큰을 받을 때까지 — 요청 코드가 바뀔 때만 로그에 찍는다. 멈추라고 하면 거짓."""
        step = Enrollment(
            center_url=self.center_url or "",
            name=self.name,
            topics=self.topics,
            manifests=[one.manifest.to_json_dict() for one in self.services],
            tokens=self.tokens,
            machine_id=self._machine_id(),
            client=self.client,
        )
        while not self._stop.is_set():
            try:
                code = step.step()
            except Exception as exc:  # noqa: BLE001 — Center가 잠시 없어도 엔진은 산다
                self._problem = f"들이기 실패: {exc}"
                log.warning("일꾼 들이기: %s", self._problem)
                self._stop.wait(self.enroll_every_s)
                continue
            if code is None:
                self._code = None
                self._problem = None
                return True
            if code != self._code:
                log.warning(
                    "Center CON-07 「일꾼 승인 대기」에서 요청 코드 %s를 승인하라 (토픽 %s)",
                    code,
                    ", ".join(self.topics),
                )
            self._state, self._code, self._problem = "enrolling", code, None
            self._stop.wait(self.enroll_every_s)
        return False

    def _run(self) -> None:
        self._state = "enrolling"
        if not self._enroll():
            return
        self._consumer = Consumer(
            services=self.services,
            center_url=self.center_url or "",
            tokens=self.tokens,
            client=self.client,
        )
        self._state = "running"
        log.info("일꾼이 토픽 %s를 가져간다", ", ".join(self.topics))
        self._consumer.run(self._stop)

    def describe(self) -> dict[str, Any]:
        """`/health`용 — 토큰은 싣지 않는다. 요청 코드는 관리자가 승인할 때 대조할 값이라 싣는다."""
        registration = self._consumer.registration() if self._consumer is not None else None
        return {
            "state": self._state,
            "topics": self.topics,
            "requestCode": self._code,
            "problem": self._problem,
            "lastFetch": registration.last_reported_at if registration is not None else None,
        }
