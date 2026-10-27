"""
장면 시작의 배경 진행 — 장면 2~6의 `POST /scN/demo-runs`.

장면 N을 시작하면 앞 장면들을 각본으로 **끝까지 실제로 실행**한다(역할 검사·업무 규칙
그대로). Center 실행이면 대리 답마다 실행기를 기다리므로 장면 3 시작이 약 7분이었다 —
BFF의 `fetch`가 300초에 503을 냈고(로컬 실측), 운영계는 Cloudflare가 약 100초에
끊는다(CLAUDE.md 4.15). 시간을 늘려서는 안 된다.

그래서 시작 요청은 `wait_s`(기본 20초)만 기다린다. 그 안에 끝나면(문서가 이미 있거나 내장
실행) 지금처럼 문서를 돌려주고, 아니면 **202와 준비 상태**를 돌려준 뒤 배경 스레드가 계속
진행한다. 화면은 `…/preparation`을 짧게 읽다가 끝나면 문서를 받는다.

* **준비 상태는 이 프로세스의 메모리에만 있다.** 운영 엔진은 워커 하나다
  (deploy/nowview-engine.service). 엔진이 다시 뜨면 진행 중이던 준비는 사라지고(조회 404)
  배경 진행도 멈춘다 — 다시 시작하면 앞 장면의 남은 단계부터 잇는다(각본은 지난 단계를
  건너뛴다). DB에 두지 않은 이유: 끝나면 남는 것은 장면 문서뿐이고, 준비 상태는 그 사이의
  진행 표시일 뿐이다.
* 같은 장면·데모 실행의 시작이 겹치면(두 번 누름·StrictMode) 진행 중인 것을 함께 기다린다 —
  두 번 돌리지 않는다.
* 실패는 그 사유·상태 코드를 그대로 남긴다(조용히 내장으로 돌거나 숨기지 않는다). 다음
  시작이 다시 해 본다.
"""

from __future__ import annotations

import logging
import os
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from app.sc01.domain import DomainError

log = logging.getLogger(__name__)

#: 시작 요청이 응답 전에 기다리는 시간(초). Cloudflare 원본 응답 시한(약 100초)보다 한참 짧게 둔다.
PREPARE_WAIT_S = float(os.environ.get("NOWVIEW_PREPARE_WAIT_S", "20"))

#: 장면 → 앞 장면 프로세스 속성 이름. 진행 표시는 이 사슬을 따라 앞 장면 문서의 단계를 읽는다.
PREVIOUS = {"sc06": "sc05", "sc05": "sc04", "sc04": "sc03", "sc03": "sc02", "sc02": "sc01"}


class Preparations:
    """장면 시작의 배경 진행과 그 상태(장면·데모 실행마다 하나)."""

    def __init__(self, wait_s: float | None = None) -> None:
        self.wait_s = PREPARE_WAIT_S if wait_s is None else wait_s
        self._lock = threading.Lock()
        self._entries: dict[tuple[str, str], dict[str, Any]] = {}

    def begin(self, scene: str, demo_run_id: str, run: Callable[[], dict]) -> dict | None:
        """
        `run`(장면 N 만들기)을 배경에서 시작하고 `wait_s`까지 기다린다. 끝났으면 문서를
        돌려주고, 실패했으면 그 예외를 그대로 낸다. 아직이면 None — 호출자는 202와
        `state()`를 돌려준다.
        """
        key = (scene, demo_run_id)
        with self._lock:
            entry = self._entries.get(key)
            if entry is None or entry["state"] != "running":
                entry = {
                    "scene": scene,
                    "demoRunId": demo_run_id,
                    "state": "running",
                    "startedAt": datetime.now(UTC).isoformat(),
                    "finishedAt": None,
                    "error": None,
                    "status": None,
                    "_done": threading.Event(),
                    "_doc": None,
                    "_exc": None,
                }
                self._entries[key] = entry
                threading.Thread(
                    target=self._run,
                    args=(entry, run),
                    name=f"prepare-{scene}-{demo_run_id}",
                    daemon=True,
                ).start()
        if not entry["_done"].wait(self.wait_s):
            return None
        if entry["_exc"] is not None:
            raise entry["_exc"]
        return entry["_doc"]

    def _run(self, entry: dict[str, Any], run: Callable[[], dict]) -> None:
        try:
            entry["_doc"] = run()
            entry["state"] = "done"
        except DomainError as exc:
            entry.update(_exc=exc, state="failed", error=str(exc), status=exc.status)
        except Exception as exc:  # 배경 실패는 상태로 남긴다 — 조용히 사라지면 화면이 영영 기다린다
            log.exception("장면 시작 준비 실패: %s %s", entry["scene"], entry["demoRunId"])
            entry.update(_exc=exc, state="failed", error=f"{type(exc).__name__}: {exc}", status=500)
        finally:
            entry["finishedAt"] = datetime.now(UTC).isoformat()
            entry["_done"].set()

    def state(self, scene: str, demo_run_id: str) -> dict[str, Any] | None:
        """준비 상태(밑줄 칸 제외). 이 프로세스가 모르는 준비면 None."""
        entry = self._entries.get((scene, demo_run_id))
        if entry is None:
            return None
        return {k: v for k, v in entry.items() if not k.startswith("_")}


def root_sc01(process: Any) -> Any:
    """장면 N 프로세스에서 앞 장면 사슬을 따라 장면 1 프로세스를 찾는다."""
    for name in ("sc05", "sc04", "sc03", "sc02", "sc01"):
        previous = getattr(process, name, None)
        if previous is not None:
            return root_sc01(previous)
    return process


def progress(scene: str, process: Any, demo_run_id: str) -> list[dict[str, Any]]:
    """앞 장면 문서들의 지금 단계(「외주 단가 인상 검토 D08」). 아직 없는 장면은 빠진다."""
    out: list[dict[str, Any]] = []
    current, name = process, scene
    while name in PREVIOUS:
        name = PREVIOUS[name]
        current = getattr(current, name)
        found = current.store.load(demo_run_id)
        if found is not None:
            doc = found[0]
            bpm = doc.get("bpm") or {}
            out.append({"scene": name, "step": doc.get("step"), "bpm": bpm.get("state")})
    return list(reversed(out))


def begin_scene(
    preparations: Preparations,
    scene: str,
    process: Any,
    *,
    demo_run_id: str | None,
    case_id: str,
    cases: Any,
    actor: str,
    executor: str,
    create: Callable[[str], dict],
) -> tuple[dict | None, str]:
    """
    장면 N 시작(`create(데모실행ID)`). 문서가 이미 있으면 곧바로(같은 사례면 그대로, 다르면
    409), 아니면 배경 진행 — `wait_s` 안에 끝나면 문서, 아니면 None. 데모 실행 id가 없으면
    **장면 1 실행을 먼저 만든다** — 화면이 준비 상태를 물을 id가 있어야 한다(장면 1 실행을
    만드는 것 자체는 BPM을 돌리지 않아 금방이다).
    """
    if case_id not in cases:
        raise DomainError(f"모르는 시연 사례: {case_id} (가능: {', '.join(cases)})", 422)
    if demo_run_id is None:
        demo_run_id = root_sc01(process).create(actor=actor, executor=executor)["demo_run_id"]
    rid = demo_run_id
    if process.store.load(rid) is not None:
        return create(rid), rid
    return preparations.begin(scene, rid, lambda: create(rid)), rid


def preparing(preparations: Preparations, scene: str, process: Any, demo_run_id: str) -> dict:
    """준비 상태 + 앞 장면 진행. 이 프로세스가 모르면(엔진이 다시 떴다) 문서가 있는지로 답한다."""
    state = preparations.state(scene, demo_run_id)
    if state is None:
        if process.store.load(demo_run_id) is not None:
            return {"preparing": False, "scene": scene, "demoRunId": demo_run_id, "state": "done"}
        raise DomainError(
            "이 엔진이 모르는 준비다 — 엔진이 다시 떴으면 진행이 멈췄다. "
            "다시 시작하면 앞 장면의 남은 단계부터 잇는다",
            404,
        )
    return {
        "preparing": state["state"] == "running",
        **state,
        "progress": progress(scene, process, demo_run_id),
    }
