"""
지정한 노드로 이동한다 — 데모 플레이어가 쓰는 원시 연산.

LangGraph는 노드마다 체크포인트를 남기므로 **과거 시점을 되짚어 볼 수 있다.** 다만 두
방향의 성격이 완전히 다르다:

* **뒤로 — 읽기 전용 조회다.** 그 시점의 체크포인트를 읽어 스냅샷만 만든다. 인스턴스는
  움직이지 않는다.
* **앞으로 — 실제 실행이다.** 사람 대기 지점마다 장면이 선언한 입력을 넣어 진행한다.

**뒤로 가기를 실행으로 구현하면 안 된다.** 과거 체크포인트의 config로 `invoke`하면 위치만
옮기는 게 아니라 **거기서부터 다시 실행된다** — Agent 노드는 멈추지 않으므로 다음 사람
대기까지 가 버리고, 그 과정에서 (1) LLM을 다시 호출하고 (2) 이미 내려진 승인이 사라진다.
스크러버를 앞뒤로 움직이는 데모에서는 치명적이다. 실제로 그렇게 만들었다가 테스트에서
드러났다.

읽기 전용이라도 **화면이 보는 것은 같다** — 승인 이전 시점을 보면 그 스냅샷에는 `decision`이
없으므로, "역방향으로 점프하면 승인이 지워진다"는 데모 규칙(CLAUDE.md 4.1)이 표시 수준에서
그대로 성립한다. 차이는 인스턴스의 실제 진행이 파괴되지 않는다는 것뿐이고, 그 편이 맞다.

**`seek`는 장면이 선언한 상태를 재현할 뿐 새로 판단하지 않는다.** 목표가 승인 노드보다
뒤라면 그 사이의 승인을 통과해야 하므로 호출자가 결정을 함께 줘야 한다 — 엔진이 임의로
승인해 버리면 Human-in-the-Loop이 무너진다.
"""

from __future__ import annotations

import logging
from typing import Any

from langgraph.types import Command

from .instances import Instance, config_for, snapshot, snapshot_of

log = logging.getLogger(__name__)

#: 진행 루프의 상한. 프로세스 노드 수보다 넉넉하면 충분하다 — 넘으면 설계가 잘못된 것이다.
MAX_ADVANCE_STEPS = 40


class SeekError(RuntimeError):
    """요청한 지점으로 이동할 수 없다."""


def current_node_id(instance: Instance) -> str | None:
    state = instance.graph.get_state(config_for(instance.id))
    return state.next[0] if state.next else None


def _past_state(instance: Instance, node_id: str) -> Any | None:
    """
    그 노드가 다음 차례였던 가장 **최근** 체크포인트.

    이력은 최신순이라 처음 만나는 것을 쓴다 — 같은 노드를 여러 번 지났다면 마지막으로
    지난 시점이 지금 보려는 그 장면이다.
    """
    for state in instance.graph.get_state_history(config_for(instance.id)):
        if state.next == (node_id,):
            return state
    return None


def seek(
    instance: Instance,
    *,
    target_node_id: str,
    decision: dict[str, Any] | None = None,
    acknowledged_by: str | None = None,
) -> dict[str, Any]:
    """
    목표 노드가 현재 지점이 되도록 이동한다.

    이미 그 지점이면 아무것도 하지 않는다 — 같은 장면을 다시 눌렀을 때 그래프를
    쓸데없이 다시 돌리지 않는다.
    """
    known = {node.id for node in instance.spec.nodes}
    if target_node_id not in known:
        raise SeekError(f"명세에 없는 노드다: {target_node_id}")

    if current_node_id(instance) == target_node_id:
        return snapshot(instance)

    # 1) 뒤로: 이미 지난 지점이면 그 체크포인트를 **읽기만** 한다.
    #    실행하면 LLM이 다시 불리고 승인이 사라진다(위 주석 참조).
    past = _past_state(instance, target_node_id)
    if past is not None:
        log.info("%s: %s 시점을 되짚어 본다 (읽기 전용)", instance.id, target_node_id)
        return snapshot_of(instance, past, historical=True)

    # 2) 앞으로: 사람 대기마다 주어진 입력을 넣어 진행한다.
    advanced = _advance_to(instance, target_node_id, decision, acknowledged_by)

    # **지나칠 수 있다.** 멈출 수 있는 곳은 사람 대기 지점뿐이라, 목표가 Agent·시스템
    # 노드면 그것을 지나 다음 대기(또는 종료)까지 간다. 그 상태를 그대로 돌려주면
    # 장면이 가리킨 지점이 아니라 그보다 앞선 화면이 보인다 — 지나친 지점을 되짚어 준다.
    if list(advanced.get("next") or [])[:1] != [target_node_id]:
        past = _past_state(instance, target_node_id)
        if past is not None:
            return snapshot_of(instance, past, historical=True)
    return advanced


def _advance_to(
    instance: Instance,
    target_node_id: str,
    decision: dict[str, Any] | None,
    acknowledged_by: str | None,
) -> dict[str, Any]:
    config = config_for(instance.id)

    for _ in range(MAX_ADVANCE_STEPS):
        state = snapshot(instance)
        if state["status"] == "done":
            # 목표가 실행되지 않은 분기에 있으면 여기 닿는다 — 도달할 수 없다고 알린다.
            if state["nodeStatuses"].get(target_node_id) == "skipped":
                raise SeekError(
                    f"{target_node_id}는 선택되지 않은 분기의 노드라 도달할 수 없다."
                )
            return state

        pending = state["pendingApproval"]
        if pending is None:
            # 사람 대기가 아니면 Agent·시스템 노드가 남아 있다는 뜻이다.
            instance.graph.invoke(None, config)
            if current_node_id(instance) == target_node_id:
                return snapshot(instance)
            continue

        if pending["nodeId"] == target_node_id:
            return state

        payload = _payload_for(pending, decision, acknowledged_by, target_node_id)
        instance.graph.invoke(Command(resume=payload), config)

        after = snapshot(instance)
        if after["pendingApproval"] and after["pendingApproval"]["nodeId"] == pending["nodeId"]:
            # 같은 지점에 다시 멈췄다 = 입력이 반려됐다. 반려 사유를 그대로 올린다 —
            # 장면이 선언한 결정이 규칙을 못 지킨다는 뜻이고, 조용히 넘기면 데모가
            # 진행되지 않는 이유를 알 수 없다.
            raise SeekError(
                f"{pending['nodeId']} 승인 입력이 반려됐다: "
                f"{after['pendingApproval'].get('error', '이유 없음')}"
            )
        if current_node_id(instance) == target_node_id:
            return snapshot(instance)

    raise SeekError(
        f"{MAX_ADVANCE_STEPS}단계 안에 {target_node_id}에 닿지 못했다 — "
        "그래프가 순환하는지 확인하라."
    )


def _payload_for(
    pending: dict[str, Any],
    decision: dict[str, Any] | None,
    acknowledged_by: str | None,
    target_node_id: str,
) -> dict[str, Any]:
    if pending["kind"] != "decision":
        return {"acknowledgedBy": acknowledged_by or pending.get("actor") or "담당자"}
    if decision is None:
        # 엔진이 임의로 승인하지 않는다 — 무엇을 골랐는지는 사람(또는 장면)이 정한다.
        raise SeekError(
            f"{target_node_id}로 가려면 {pending['nodeId']}의 승인을 통과해야 하는데 "
            "결정이 주어지지 않았다."
        )
    return decision
