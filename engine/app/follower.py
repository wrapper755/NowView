"""
세계 따라가기 — 회사 사이트가 몰고 NowView 일꾼이 따라간다(`docs/role-split.md` §5.3).

세계(= 데모 실행)를 만들고 초기화하고 시계를 옮기는 쪽은 회사 사이트다. 사이트는 NowView를 부르지
않으므로 그 사이는 기간계다: 사이트가 기간계에 세계·시계·원천·명령을 남기고, 일꾼이 2초마다 읽는다.

* 처음 보는 세계 → 장면 1 데모 실행을 **그 id로** 만든다(사례 `case_id`, 실행 위치 Center).
  **사이트가 만든 세계(`origin: site`)만** 들인다 — 기간계는 여러 엔진(작업 사본)이 함께 쓸 수
  있다. 처음 띄웠을 때 예전 세계를 집어 그 수신함으로 Center 작업 다섯을 기동해 장면 1 상한
  (`per_bot_limit`)을 채웠다(실측).
* 초기화 회차(`generation`)가 바뀌었다 → 장면 1을 처음으로, 장면 2~7 문서는 지운다(다시 `open`).
* 세계 시각이 장면 문서보다 앞이다 → 장면마다 따라간다(기한 초과 알림·장면 5 배경 원천).
  **NowView는 기간계 시계를 쓰지 않는다** — 읽기만 한다.
* 수신함의 새 원천 → 장면 1 수신 · 장면 2 접수(장면 2 문서가 아직 없으면 생길 때까지 둔다).
* 대기 명령 → 수행 → 결과(DONE·REJECTED, 엔진 거절 그대로)를 기간계에 적는다.

일감(서비스 태스크)을 처리하기 전에도 그 데모 실행의 시각을 먼저 따라간다(`synced`) — 사이트가
시계를 옮기고 곧바로 답하면 폴링보다 일감이 먼저 올 수 있다. 그래야 기록이 옮긴 시각에 적힌다.

회사 사이트가 몰 때만 돈다(`engine_drives()`가 거짓). 엔진 시험은 엔진이 몰고(각본·시계), 이것을
따로 불러 시험한다(`tests/test_follower.py`).
"""

from __future__ import annotations

import inspect
import logging
import threading
import uuid
from collections.abc import Callable, Mapping
from typing import Any

from app.company import CompanyClient, CompanyUnavailable
from app.sc01.domain import DomainError, parse_at

log = logging.getLogger("nowview.follower")

INTERVAL_S = 2.0
#: 일꾼이 사이트 명령을 수행할 때의 행위자 — 명령 자체의 `actor`를 쓴다. 시계·초기화는 시연관리자다.
SYSTEM_ACTOR = "u-demo"
#: 이 엔진이 맡는 시나리오 — 회사 사이트 카탈로그의 시나리오 1(장면 1~7).
#: 회차는 시나리오 하나에 속한다.
SCENARIO = "s1"

#: 데모 실행마다 일감(서비스 태스크)을 처리한 세계 시각 — 노드 id → 시각. 결재는 앞 기록 작업
#: 바로 뒤에 열리지만 Center에 오르기까지 10초 남짓 걸려, 폴러가 그 결재를 읽을 때는 사이트가 이미
#: 시계를 다음 단계로 옮겼다(생산·자재 업무가 11:00이 아니라 11:05에 열렸다 — 로컬 실측). 그래서
#: 업무는 실행 기록에서 그 결재 앞에 끝난 노드 중 가장 가까운 것의 처리 시각에 연다
#: (`sync_opened`). 메모리다(엔진이 다시 뜨면 지금 시각으로 연다).
PROGRESS_AT: dict[str, dict[str, str]] = {}


def sync_opened(
    doc: dict[str, Any],
    request_ids: list[str],
    before: Mapping[str, list[str]],
    open_tasks: Callable[[list[str]], None],
) -> None:
    """
    폴러가 새 결재의 업무를 연다 — 결재마다 연 시각(앞 기록 작업 처리 시각, 지금보다 앞일 때만)으로
    묶어 시각 순서대로 `open_tasks(묶음)`을 부른다. 그동안 문서 시각을 그 시각으로 둔다.
    """
    seen = PROGRESS_AT.get(doc.get("demo_run_id", ""), {})
    now = doc["clock"]
    groups: dict[str, list[str]] = {}
    for rid in request_ids:
        at = next((seen[n] for n in before.get(rid, []) if n in seen), None)
        if at is None or parse_at(at) >= parse_at(now):
            at = now
        groups.setdefault(at, []).append(rid)
    try:
        for at in sorted(groups, key=parse_at):
            doc["clock"] = at
            open_tasks(groups[at])
    finally:
        doc["clock"] = now


class Follower:
    def __init__(
        self,
        company: CompanyClient,
        scenes: Mapping[int, Any],
        *,
        interval_s: float = INTERVAL_S,
    ) -> None:
        self.company = company
        self.scenes = dict(scenes)
        self.interval_s = interval_s
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._guard = threading.RLock()
        #: 세계마다 본 것 — 회차·수신함 번호(장면 1·2). 엔진이 다시 뜨면 문서에서 되살린다.
        self._seen: dict[str, dict[str, Any]] = {}
        self.last_error: str | None = None

    # ───────────── 돌기 ─────────────

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running or not self.company.configured:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="world-follower", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def _loop(self) -> None:
        while not self._stop.wait(self.interval_s):
            try:
                self.tick()
                self.last_error = None
            except CompanyUnavailable as exc:
                self.last_error = str(exc)
            except Exception as exc:  # 한 번 실패로 따라가기를 멈추지 않는다
                self.last_error = str(exc)
                log.exception("세계 따라가기 실패")

    def describe(self) -> dict[str, Any]:
        return {"running": self.running, "worlds": len(self._seen), "last_error": self.last_error}

    def tick(self) -> None:
        """세계를 한 바퀴 — 시험은 이것을 직접 부른다."""
        self.company.ensure_roster()
        worlds = self.company.worlds()
        for summary in worlds:
            with self._guard:
                self._follow(summary)
        with self._guard:
            self._sweep({w["world_id"] for w in worlds})

    def _sweep(self, present: set[str]) -> None:
        """
        사이트가 지운 세계 — 그 데모 실행(장면 1~7 문서·이력)을 거둔다. 세계를 따라 만든 문서
        (`world_generation`이 있다)만 본다 — 엔진 시험이 만든 문서·세계 전의 문서는 둔다. 목록을
        읽지 못한 바퀴(예외)는 여기까지 오지 않는다.
        """
        sc01 = self.scenes[1]
        for row in sc01.store.list():
            rid = row["demoRunId"]
            if rid in present:
                continue
            found = sc01.store.load(rid)
            if found is None or found[0].get("world_generation") is None:
                continue
            log.info("세계 %s가 지워졌다 — 데모 실행을 거둔다", rid)
            for n in sorted(self.scenes, reverse=True):
                if self.scenes[n].store.load(rid) is not None:
                    self.scenes[n].discard(rid)
            self._seen.pop(rid, None)
            PROGRESS_AT.pop(rid, None)

    # ───────────── 한 세계 ─────────────

    def _follow(self, w: dict[str, Any]) -> None:
        rid = w["world_id"]
        sc01 = self.scenes[1]
        seen = self._seen.setdefault(rid, {})
        found = sc01.store.load(rid)
        if found is None and w.get("origin") != "site":
            return  # 사이트가 만든 세계가 아니다 — 예전 엔진·다른 엔진(작업 사본)의 세계
        if found is None and w.get("scenario_id", SCENARIO) != SCENARIO:
            return  # 다른 시나리오의 회차 — 장면 1~7(시나리오 1)만 맡는다
        if found is None:
            sc01.create(
                demo_run_id=rid,
                case_id=w.get("case_id") or "BASE",
                executor="center",
                world_generation=w["generation"],
            )
            seen.update(generation=w["generation"], inbox=0, price_inbox=0)
        elif found[0].get("world_generation", 1) != w["generation"]:
            self._reset(rid, w)
            seen.update(generation=w["generation"], inbox=0, price_inbox=0)
        else:
            seen.setdefault("generation", w["generation"])
            seen.setdefault("inbox", found[0].get("world_inbox_seq", 0))
        self._clock(rid, w["clock"])
        self._inboxes(rid, w, seen)
        if w.get("pending_commands"):
            for command in self.company.commands(rid, "PENDING"):
                self._run_command(rid, command)

    def _reset(self, rid: str, w: dict[str, Any]) -> None:
        """사이트가 세계를 초기화했다 — 장면 1은 S0로, 장면 2~7 문서는 지운다(다시 연다)."""
        log.info("세계 %s 초기화 회차 %s — 데모 실행을 처음으로", rid, w["generation"])
        for n in sorted(self.scenes, reverse=True):
            if n == 1:
                continue
            store = self.scenes[n].store
            if store.load(rid) is not None:
                self.scenes[n].discard(rid)
        self.scenes[1].reset(
            rid,
            actor=SYSTEM_ACTOR,
            case_id=w.get("case_id") or "BASE",
            executor="center",
            world_generation=w["generation"],
        )

    def _clock(self, rid: str, at: str) -> None:
        for n in sorted(self.scenes):
            process = self.scenes[n]
            found = process.store.load(rid)
            if found is None or parse_at(at) <= parse_at(found[0]["clock"]):
                continue
            process.follow_clock(rid, at)

    def synced(self, demo_run_id: str, node_id: str | None = None) -> None:
        """일감·명령 전에 — 그 세계의 시각을 먼저 따라간다(사이트가 옮긴 시각에 기록이 적히게)."""
        try:
            at = self.company.world(demo_run_id)["clock"]
        except (CompanyUnavailable, DomainError) as exc:
            log.info("세계 %s 시각을 못 읽었다 — 문서 시각으로 간다: %s", demo_run_id, exc)
            return
        with self._guard:
            self._clock(demo_run_id, at)
        if node_id:
            PROGRESS_AT.setdefault(demo_run_id, {})[node_id] = at

    def _inboxes(self, rid: str, w: dict[str, Any], seen: dict[str, Any]) -> None:
        if w.get("received", 0) > seen.get("inbox", 0):
            for item in self.company.inbox(rid, after=seen.get("inbox", 0)):
                self.scenes[1].receive_inbox(rid, item["doc_id"], actor="u-sales")
                seen["inbox"] = item["seq"]
        sc02 = self.scenes.get(2)
        if sc02 is None or not w.get("price_requests"):
            return
        if sc02.store.load(rid) is None:
            return  # 장면 2를 아직 열지 않았다 — 열리면 들인다
        if w["price_requests"] > seen.get("price_inbox", 0):
            for item in self.company.price_inbox(rid, after=seen.get("price_inbox", 0)):
                sc02.receive_inbox(rid, item["doc_id"], actor="u-buy")
                seen["price_inbox"] = item["seq"]

    # ───────────── 명령 ─────────────

    def _run_command(self, rid: str, command: dict[str, Any]) -> None:
        scene = command["scene"]
        process = self.scenes.get(scene)
        try:
            if process is None:
                raise DomainError(f"모르는 업무(장면): {scene}", 404)
            handler = COMMANDS.get(command["kind"])
            if handler is None:
                raise DomainError(f"모르는 명령: {command['kind']}", 422)
            result = handler(self, process, rid, command) or {}
            self.company.command_result(rid, command["command_id"], state="DONE", result=result)
        except DomainError as exc:
            detail = getattr(exc, "detail", None)
            result = detail if isinstance(detail, dict) else {}
            self.company.command_result(
                rid,
                command["command_id"],
                state="REJECTED",
                status=getattr(exc, "status", 409),
                reason=str(exc),
                result=result,
            )


def _open(f: Follower, p: Any, rid: str, c: dict[str, Any]) -> dict[str, Any]:
    body = c["body"]
    kwargs: dict[str, Any] = {"sc01_demo_run_id": rid, "executor": "center"}
    if "actor" in inspect.signature(p.create).parameters:  # 장면 6·7 적재는 행위자를 받지 않는다
        kwargs["actor"] = c["actor"]
    if "case_id" in body:
        kwargs["case_id"] = body["case_id"]
    doc = p.create(**kwargs)
    return {"scene": doc.get("scene"), "clock": doc.get("clock")}


def _start(f: Follower, p: Any, rid: str, c: dict[str, Any]) -> dict[str, Any]:
    doc = p.start(rid, actor=c["actor"])
    return {"scene": doc.get("scene")}


def _record(f: Follower, p: Any, rid: str, c: dict[str, Any]) -> dict[str, Any]:
    b = c["body"]
    p.meeting_record(
        rid,
        record_type=b["record_type"],
        subject=b.get("subject", ""),
        content=b.get("content", ""),
        related=b.get("related", ""),
        actor=c["actor"],
    )
    return {}


def _agent(f: Follower, p: Any, rid: str, c: dict[str, Any]) -> dict[str, Any]:
    p.agent(rid, c["body"]["kind"], actor=c["actor"])
    return {}


def _regenerate(f: Follower, p: Any, rid: str, c: dict[str, Any]) -> dict[str, Any]:
    p.regenerate(rid, c["body"]["run_id"], actor=c["actor"])
    return {}


def _adopt(f: Follower, p: Any, rid: str, c: dict[str, Any]) -> dict[str, Any]:
    p.adopt(rid, c["body"]["output_id"], actor=c["actor"])
    return {}


def _review(f: Follower, p: Any, rid: str, c: dict[str, Any]) -> dict[str, Any]:
    from app.sc05.demo import latest_output

    b = c["body"]
    output = b.get("output_id") or latest_output(p.get(rid), b["kind"])
    if output is None:
        raise DomainError(f"{b['kind']} 초안이 없다 — 수동으로 진행한다", 404)
    p.review_agent(rid, output, actor=c["actor"], note=b.get("note", ""))
    return {"output_id": output}


def _task_draft(f: Follower, p: Any, rid: str, c: dict[str, Any]) -> dict[str, Any]:
    b = c["body"]
    changes = b.get("changes") or {}
    p.edit_task(rid, b["task_id"], changes, reason=b.get("reason", ""), actor=c["actor"])
    return {}


def _forecast_revision(f: Follower, p: Any, rid: str, c: dict[str, Any]) -> dict[str, Any]:
    p.revise_forecast(rid, reason=c["body"].get("reason", ""), actor=c["actor"])
    return {}


def _negotiation_due(f: Follower, p: Any, rid: str, c: dict[str, Any]) -> dict[str, Any]:
    b = c["body"]
    p.change_due(rid, due=b["due"], reason=b.get("reason", ""), actor=c["actor"])
    return {}


def _budget_policy(f: Follower, p: Any, rid: str, c: dict[str, Any]) -> dict[str, Any]:
    return p.budget_policy(rid, c["body"])


def _reset_scene(f: Follower, p: Any, rid: str, c: dict[str, Any]) -> dict[str, Any]:
    doc = p.reset(rid, actor=SYSTEM_ACTOR, executor="center")
    return {"scene": doc.get("scene")}


def _rewind(f: Follower, p: Any, rid: str, c: dict[str, Any]) -> dict[str, Any]:
    """
    사이트가 장면 N부터 다시 했다(기간계 `rewind` — 기록·명령·회사 자료·시각은 거기서 걷었다).
    N 이상 장면의 데모 실행을 거두고 Center 작업을 취소한다. 그 장면은 사이트가 다시 연다.
    """
    n = int(c["body"].get("scene") or c["scene"])
    gone = []
    for m in sorted(f.scenes, reverse=True):
        if m >= n and m >= 2 and f.scenes[m].store.load(rid) is not None:
            f.scenes[m].discard(rid)
            gone.append(m)
    if n <= 2:
        f._seen.get(rid, {})["price_inbox"] = 0  # 기간계가 단가 요청 수신함을 비웠다
    return {"discarded": sorted(gone)}


#: 명령 종류 → 수행(role-split §5.2). 각 장면 프로세스의 같은 이름 조작을 부른다 — 장면에 없으면
#: AttributeError가 아니라 422로 돌려준다(`_run_command` 앞에서 거른다).
COMMANDS: dict[str, Callable[[Follower, Any, str, dict[str, Any]], dict[str, Any] | None]] = {
    "open": _open,
    "start": _start,
    "record": _record,
    "agent": _agent,
    "agent_regenerate": _regenerate,
    "adopt": _adopt,
    "review": _review,
    "task_draft": _task_draft,
    "forecast_revision": _forecast_revision,
    "negotiation_due": _negotiation_due,
    "budget_policy": _budget_policy,
    "reset_scene": _reset_scene,
    "rewind": _rewind,
}


class Synced:
    """
    일감 처리기 앞뒤에 끼운다 — 앞에서 세계 시각을 따라가고(사이트가 옮긴 시각에 기록이 적히게),
    뒤에서 일감 기록을 기간계에 적는다(`worker-log` — 그 기록 작업이 적는 결재와 함께). 사이트 자동
    모드는 자기가 답한 결재의 기록이 오기 전에 시계를 옮기지 않는다(role-split §5.3).
    """

    def __init__(self, process: Any, follower: Follower, scene: int | None = None) -> None:
        self._process = process
        self._follower = follower
        self._scene = scene
        #: 기록 태스크 → 그 앞 결재(결재 하나 뒤에 기록 태스크 하나가 있다 — 그림 규칙)
        self._approval_of: dict[str, str] = {}
        bpmn = getattr(process, "process", None)
        if bpmn is not None:
            for node in bpmn.of_kind("userTask"):
                for flow in bpmn.outgoing(node.id):
                    target = bpmn.node(flow.target)
                    if target is not None and target.kind == "serviceTask":
                        self._approval_of[target.id] = node.id

    def operate(self, demo_run_id: str, operation: str, *args: Any, **kwargs: Any) -> dict:
        self._follower.synced(demo_run_id, kwargs.get("node_id"))
        try:
            out = self._process.operate(demo_run_id, operation, *args, **kwargs)
        except DomainError as exc:
            self._log(demo_run_id, operation, kwargs, ok=False, reason=str(exc))
            raise
        self._log(demo_run_id, operation, kwargs, ok=True)
        return out

    def _log(
        self, rid: str, operation: str, kwargs: dict[str, Any], *, ok: bool, reason: str = ""
    ) -> None:
        if self._scene is None:
            return
        node_id = kwargs.get("node_id")
        try:
            self._follower.company.worker_log(
                rid,
                {
                    "scene": self._scene,
                    "operation": operation,
                    "node_id": node_id,
                    "approval_node": self._approval_of.get(node_id or ""),
                    "run_id": kwargs.get("external_run_id"),
                    "ok": ok,
                    "reason": reason[:500],
                    "ref": uuid.uuid4().hex,
                },
            )
        except (CompanyUnavailable, DomainError) as exc:
            # 일감은 이미 끝났다 — 기록만 못 남겼다(사이트 자동 모드가 그 결재에서 기다린다)
            log.warning("일감 기록을 못 남겼다 %s %s: %s", rid, operation, exc)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._process, name)
