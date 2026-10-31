"""
C15 일꾼 — Center에 쌓인 NowView 서비스 태스크의 일감을 가져가 이 프로세스에서
수행한다.

Chaeksas는 바깥 기능을 부르는 길을 모두 Pull로 바꿨다(ADR-0102, 계약 C15). 서버 실행기·Studio는
`chk:serviceCall`을 **Center에 외부 작업으로 올리고**, 토픽(`app_id` — 고정 확장 `external`,
옮기기 전 업무는 `nowview-sc02`~`sc06`, 설정 `topics`)을 맡은 일꾼이 롱폴링으로 가져가 끝냈다고
알린다. 일감을 보낸 BPM 프로세스 id로 설정에서 회사·업무를 찾는다(`routed_by`). 연결은 늘 NowView →
Center다 — Center는 NowView 주소도 키도 모른다.

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

설정 — `CHAEKSAS_CENTER_URL`(N3와 같은 값)과 `WORKER_CONSUMER_TOKEN`이 있으면 뜬다. 끄려면
`WORKER_CONSUMER=off`.

* **승인 없는 일꾼이다**(Chaeksas ADR-0121, C15 §일꾼 들이기). 배포가 Center의 일꾼 폴더에
  일꾼 파일(`worker.consumer.json` — 이름 `worker`·토픽·토큰 해시, `app/worker_file.py`)을
  두면 Center가 뜰 때 이 일꾼을 처음부터 안다. 요청 코드·콘솔 승인은 없다. 일꾼은 토큰
  원문을 `Authorization: Bearer`로 싣는다. 토픽은 그 파일에 적은 것으로 고정이다 — 설정의
  토픽을 바꾸면 파일도 다시 지어 Center를 다시 띄운다.
* **확장 정의는 일꾼이 올린다** — 뜰 때 토픽마다 `chaeksas/{topic}.extension.json`을
  `PUT /consumers/self/extension`으로 올린 뒤 manifest를 올리고 가져가기를 시작한다.
  콘솔 등록은 없다.
* 지켜볼 것은 로그다 — 엔진 로그(`nowview.consumer`)와 Center 로그(일꾼 이름·일감·토픽·작업·오류
  코드). 관리자 모드(`/admin`)의 최근 일감은 엔진 메모리의 사본이다.
* 확장 정의는 `NOWVIEW_EXTENSIONS_DIR`(기본 리포의 `chaeksas/`)에서 읽는다.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import httpx
from chaeksas.contracts.service_app import OpRequest, ServiceAppManifest
from chaeksas.service_kit import Consumer, TokenFile
from chaeksas.service_kit.app import OpError, Service

from app.sc01.domain import DomainError

log = logging.getLogger("nowview.consumer")

#: 일감의 `origin` → 데모 실행의 실행 위치(`bpm.executor`).
EXECUTOR_OF_ORIGIN = {"test": "studio", "run": "center"}
#: 업무 규칙 위반의 상태 코드 → C15 실패 코드. 모두 다시 불러도 같은 답이라 `retryable`이 아니다.
CODE_OF_STATUS = {403: "forbidden", 404: "not_found", 409: "conflict", 422: "input_invalid"}
#: 회사 시스템이 닿지 않으면(`app/company.py`, 503) 업무 규칙 위반이 아니다 — C15
#: `dependency_down`은 Center가 다시 내주는(retryable) 코드다.
CODE_OF_STATUS[503] = "dependency_down"
#: 확장 정의를 올리지 못했을 때 다시 해 보는 간격(초).
RETRY_S = 5.0

DEFAULT_EXTENSIONS_DIR = Path(__file__).resolve().parents[2] / "chaeksas"


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


#: 일감 → 그것을 처리할 장면 프로세스. 운영은 설정의 BPM 프로세스 매핑(`routed_by`), 시험은 고정.
Resolve = Callable[[OpRequest], Operates]


def routed_by(
    mapping: Callable[[str | None], int | None], scenes: Mapping[int, Operates]
) -> Resolve:
    """
    일감을 보낸 BPM 프로세스 id(`caller.bpm_process_id`) → 설정의 업무(장면) → 그 장면의 프로세스.
    NowView는 고정 프로그램이고 어느 회사의 어느 BPM 프로세스를 맡는지는 설정이다(`app/config.py`) —
    매핑에 없으면 거절한다.
    """

    def resolve(req: OpRequest) -> Operates:
        scene = mapping(req.caller.bpm_process_id)
        if scene is None:
            raise OpError(
                "not_found",
                f"NowView 설정에 없는 BPM 프로세스다: {req.caller.bpm_process_id} — 관리자 "
                "모드에서 회사·업무에 매핑하라",
                status=404,
            )
        return scenes[scene]

    return resolve


def scene_service(
    topic: str,
    process: Operates | Resolve,
    folder: Path | None = None,
    journal: Callable[[dict[str, Any]], None] | None = None,
) -> Service:
    """
    토픽 하나의 처리기. `process`가 장면 프로세스면 늘 그것이고, 함수면 일감마다
    고른다(`routed_by`). 작업마다 같은 처리기다 — 작업 이름으로 가른다. `journal`이 있으면 일감마다
    결과를 한 줄 남긴다 (관리자 모드의 최근 일감).
    """
    manifest = manifest_of(topic, folder)

    def resolve(req: OpRequest) -> Operates:
        return process if hasattr(process, "operate") else process(req)  # type: ignore[operator,return-value]

    def note(req: OpRequest, operation: str, outcome: str, reason: str | None = None) -> None:
        if journal is None:
            return
        journal(
            {
                "at": datetime.now(UTC).isoformat(timespec="seconds"),
                "topic": topic,
                "operation": operation,
                "origin": req.origin,
                "runId": req.run_id,
                "nodeId": req.node_id,
                "demoRunId": req.input.get("demo_run_id"),
                "outcome": outcome,
                "reason": reason,
            }
        )

    def handler_for(operation: str):
        def handle(req: OpRequest, mode: str) -> dict[str, Any]:
            del mode  # 결정론 작업뿐이다
            args = dict(req.input)
            demo_run_id = args.pop("demo_run_id", None)
            if not demo_run_id:
                raise OpError("input_invalid", "입력에 demo_run_id가 없다", status=422)
            via = EXECUTOR_OF_ORIGIN.get(req.origin or "run", "center")
            try:
                target = resolve(req)
            except OpError as exc:
                note(req, operation, exc.code, exc.message)
                raise
            try:
                out = target.operate(
                    str(demo_run_id),
                    operation,
                    args,
                    external_run_id=req.run_id,
                    node_id=req.node_id,
                    via=via,
                )
            except DomainError as exc:
                code = CODE_OF_STATUS.get(exc.status, "rejected")
                note(req, operation, code, str(exc))
                raise OpError(code, str(exc), status=exc.status) from exc
            note(req, operation, "complete")
            return out

        return handle

    handlers = {op.name: handler_for(op.name) for op in manifest.operations}
    return Service(manifest=manifest, handlers=handlers)


@dataclass
class ConsumerHost:
    """엔진 안에서 도는 일꾼 하나 — manifest 올리기 → 가져가기 루프(데몬 스레드). 들이기는 없다."""

    center_url: str | None
    services: list[Service]
    tokens: TokenFile
    enabled: bool = True
    name: str = "NowView 엔진"
    client: Any = None  # httpx.Client (시험이 끼운다)
    _stop: threading.Event = field(default_factory=threading.Event, init=False)
    _thread: threading.Thread | None = field(default=None, init=False)
    _consumer: Consumer | None = field(default=None, init=False)
    _state: str = field(default="off", init=False)
    #: 최근 일감(새것이 앞) — 엔진 메모리에만 있다. 다시 뜨면 빈다.
    _recent: deque[dict[str, Any]] = field(default_factory=lambda: deque(maxlen=50), init=False)
    _problem: str | None = field(default=None, init=False)

    @classmethod
    def from_env(cls, topics: list[str], resolve: Resolve) -> ConsumerHost:
        """`topics` — 설정의 일꾼 토픽. `resolve` — 일감 → 장면 프로세스(`routed_by`)."""
        tokens = TokenFile(path=None, env_value=os.getenv("WORKER_CONSUMER_TOKEN") or None)
        center_url = (os.getenv("CHAEKSAS_CENTER_URL") or "").rstrip("/") or None
        enabled = os.getenv("WORKER_CONSUMER", "").lower() != "off"
        # 뜨지 않을 때는 확장 정의를 읽지 않는다 — 정의가 없는 자리(내장 시험·화면만)에서 엔진이
        # 기동조차 못 하면 안 된다. 뜰 때 정의가 없으면 기동에서 바로 드러난다.
        host = cls(center_url=center_url, services=[], tokens=tokens, enabled=enabled)
        if enabled and center_url:
            host.services = [
                scene_service(topic, resolve, journal=host.remember) for topic in topics
            ]
        return host

    def remember(self, entry: dict[str, Any]) -> None:
        self._recent.appendleft(entry)

    def recent_tasks(self) -> list[dict[str, Any]]:
        return list(self._recent)

    @property
    def topics(self) -> list[str]:
        return [one.app_id for one in self.services]

    def start(self) -> None:
        if self._thread is not None:
            return
        if not self.enabled or not self.center_url:
            self._state = "off"
            return
        if not self.tokens.token():
            self._state = "off"
            self._problem = (
                "WORKER_CONSUMER_TOKEN이 없다 — 일꾼 토큰을 환경에 두고, 같은 토큰의 "
                "해시로 지은 worker.consumer.json을 Center 일꾼 폴더에 둔다"
                "(engine `python -m app.worker_file`)"
            )
            log.warning("일꾼을 띄우지 않는다: %s", self._problem)
            return
        self._thread = threading.Thread(target=self._run, name="nowview-consumer", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _put_extensions(self) -> bool:
        """
        토픽마다 확장 정의를 올린다(C15 §외부 확장 정의 올리기). 409(같은 판 다른 내용·
        철회된 판·더 높은 판)는 사람이 판을 올릴 일이라 경고만 하고 넘어간다. Center가 없거나
        거절하면 기다렸다 다시 한다. 멈추라고 하면 거짓.
        """
        http = self.client or httpx.Client(base_url=self.center_url or "", timeout=30.0)
        headers = {"Authorization": f"Bearer {self.tokens.token()}"}
        pending = list(self.topics)
        while pending and not self._stop.is_set():
            topic = pending[0]
            try:
                definition = json.loads(
                    (extensions_dir() / f"{topic}.extension.json").read_text("utf-8")
                )
                answer = http.put(
                    "/api/v1/consumers/self/extension",
                    json={"definition": definition},
                    headers=headers,
                )
                if answer.status_code == 409:
                    log.warning(
                        "Center가 확장 %s의 정의를 받지 않았다: %s", topic, answer.text[:300]
                    )
                else:
                    answer.raise_for_status()
                    log.info("확장 %s %s판을 올렸다", topic, definition.get("version"))
                pending.pop(0)
                self._problem = None
            except Exception as exc:  # noqa: BLE001 — Center가 잠시 없어도 엔진은 산다
                self._problem = f"확장 {topic} 정의를 올리지 못했다: {exc}"
                log.warning("%s", self._problem)
                self._stop.wait(RETRY_S)
        return not self._stop.is_set()

    def _run(self) -> None:
        self._state = "starting"
        if not self._put_extensions():
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
        """`/health`·관리자 모드용 — 토큰은 싣지 않는다."""
        registration = self._consumer.registration() if self._consumer is not None else None
        return {
            "state": self._state,
            "topics": self.topics,
            "problem": self._problem,
            "lastFetch": registration.last_reported_at if registration is not None else None,
        }
