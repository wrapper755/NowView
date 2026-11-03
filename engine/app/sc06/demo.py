"""
SC06 확인 절차 각본 — D601 착수 → D602~D607 담당 임원 확인 2 · 종합 확인 · 보고 결론 · 확정 · 대표
보고.

장면 1~5와 같다: **단계 진행은 실제 상태 전환을 실행한다.** 각본은 누가·무엇을만 들고, 실행은 사람이
버튼을 누른 것과 같은 길(`Sc06Process.start`·`act`)이다. **답은 데이터의 확인 기록(SC06보고)에서
읽는다** — 끝난 문서가 그 시트와 같아야 한다(시험). 시각은 기록 작업이 일정대로
옮긴다(`confirm._at`). 그 뒤의 세 조회 동작(U601 → 차이 상세 → U602)은 화면 상태만 바꾸므로 각본에
없다 — 화면 플레이어가 이어서 보인다.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app import scenarios
from app.sc01.domain import DomainError
from app.sc06 import confirm
from app.sc06.process import Sc06Process
from app.sc06.seed import Seed
from app.script_wait import after_record


@dataclass(frozen=True)
class Step:
    code: str
    actor: str
    kind: str  # start · act
    node_id: str | None = None
    answer: dict[str, Any] = field(default_factory=dict)
    label: str = ""
    record: str | None = None  # 남길 기록(SC06보고 record_id)


def steps_for(case_id: str = "BASE", seed: Seed | None = None) -> list[Step]:
    """
    확인 절차 각본 — 원본은 Company1 `scenarios/sc06.json`(답은 통합가상데이터의 확인 기록 글)이고
    여기는 사본을 읽는다(`app/scenarios.py`). 시험 전용 실행기다 — 운영·로컬은 회사 사이트가 몬다.
    """
    return scenarios.steps(6, Step)


def run_step(process: Sc06Process, demo_run_id: str, index: int) -> dict:
    """각본의 `index`번째 단계. 이미 지나간 단계면 현재 문서를 돌려준다(장면 1~5와 같다)."""
    doc = process.get(demo_run_id)
    if not confirm.is_bpm(doc):
        raise DomainError(
            "이 검토건은 확인 기록을 끝난 것으로 적재했다 — 초기화하면 확인 전으로 돌아간다", 409
        )
    if (doc.get("bpm") or {}).get("executor") == "studio":
        raise DomainError(
            "Studio 시험 실행의 데모 실행은 각본을 돌리지 않는다 — 결재는 Studio에서 답한다", 409
        )
    steps = steps_for(doc["case_id"], process.seed)
    if not 0 <= index < len(steps):
        raise DomainError(f"각본에 없는 단계: {index}", 404)
    done = max(doc.get("script_index", -1), done_index(doc, steps))
    if index <= done:
        return doc
    if index != done + 1:
        raise DomainError(f"단계를 건너뛸 수 없다 — 다음은 {done + 1}번이다", 409)
    step = steps[index]
    mark = {"event_code": step.code, "script_index": index}
    if step.kind == "start":
        return process.start(demo_run_id, actor=step.actor, **mark)
    center = (doc.get("bpm") or {}).get("executor") == "center"
    since = len(doc["audit"])  # 장면 6 감사 이력에는 seq가 없다 — 길이로 가른다
    try:
        done_doc = _after_record(
            process,
            center,
            lambda: process.act(
                demo_run_id, step.node_id or "", dict(step.answer), actor=step.actor, **mark
            ),
        )
    except DomainError:
        # 기다리는 동안 바깥 답(회사 사이트·콘솔)의 기록이 이 단계를 지나갔으면 각본은 할 일이
        # 없다 — 장면 5와 같다.
        now = process.get(demo_run_id)
        if done_index(now, steps) >= index:
            return now
        raise
    if not center:
        return done_doc
    return _await_own_record(process, demo_run_id, step.node_id or "", since)


def _await_own_record(process: Sc06Process, demo_run_id: str, node_id: str, since: int) -> dict:
    """
    Center 실행이면 이 단계 결재의 기록 작업이 들어올 때까지 기다린다(기록 또는 거절) — 장면 4·5의
    같은 이름 함수와 같다. 기다리지 않으면 다음 「다음」이 이 단계를 아직 남은 단계로 보고, 그
    사이 회사 사이트가 답해 둔 결재를 다시 대리 답하려다 409였다(섞어 진행 실측: 생산 확인 직후
    구매 확인 단계). 끝내 오지 않으면 지금 문서를 돌려준다.
    """
    deadline = time.monotonic() + process.center_wait_s * 3
    while True:
        doc = process.get(demo_run_id)
        tasks = doc["tasks"]
        for a in doc["audit"][since:]:
            detail = a.get("detail") or {}
            if a["action"] == "answer_rejected" and detail.get("node_id") == node_id:
                return doc
            task = tasks.get(detail.get("task_id") or "")
            if a["action"] == "task_completed" and task and task["node_id"] == node_id:
                return doc
        if time.monotonic() >= deadline:
            return doc
        time.sleep(min(1.0, process.center_wait_s))


def done_index(doc: dict, steps: list[Step] | None = None) -> int:
    """
    상태로 본 각본 위치 — 착수했으면 0, 그 뒤 기록이 남은 단계까지. 화면에서 직접 답해도 플레이어의
    「다음」이 409가 되지 않게 각본이 따라간다(장면 2 `_follow_script`와 같은 뜻). 재확인·보완으로
    기록이 이력으로 가면 그 단계는 다시 남은 단계다.
    """
    if not confirm.is_bpm(doc) or doc["scene_info"]["started_at"] is None:
        return -1
    done = 0
    for i, step in enumerate(steps or steps_for(doc["case_id"]), start=0):
        if step.kind == "start":
            continue
        if step.record not in doc["report_records"]:
            break
        done = i
    return done


def _after_record(process: Sc06Process, center: bool, run: Callable[[], dict]) -> dict:
    """Center 실행이면 앞 결재의 기록 작업을 기다린다(`app.script_wait`, 장면 3 실측)."""
    return after_record(process.center_wait_s, center, run, gated=(confirm.PrerequisiteError,))
