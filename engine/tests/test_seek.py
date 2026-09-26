"""
장면 이동(`seek`) — 데모 플레이어가 실엔진 위에서 성립하는 근거.

**"실행 중인 그래프는 시간을 되감을 수 없다"는 전제가 틀렸다.** LangGraph는 노드마다
체크포인트를 남기므로 과거 시점을 되짚어 볼 수 있다.

다만 **뒤로 가기는 읽기 전용이어야 한다.** 과거 체크포인트에서 `invoke`하면 거기서부터
다시 실행되어 LLM이 재호출되고 승인이 사라진다 — 스크러버를 앞뒤로 움직이는 데모에서는
치명적이다. 처음에 실행으로 만들었다가 여기 테스트에서 드러났다.

여기서 잠그는 것: **과거 시점에는 그때의 상태만 보이고(승인 이전이면 결정이 없다),
인스턴스의 실제 진행은 파괴되지 않는다.**
"""

from __future__ import annotations

import pytest
from conftest import spec_with

from app.instances import snapshot
from app.seek import MAX_ADVANCE_STEPS, SeekError, seek

APPROVAL = {
    "alternativeId": "alt-1",
    "leverValue": 2,
    "rationale": "장면이 선언한 결정이며 사유는 충분히 길다.",
}


def started(store, *, cross_functional: bool = True):
    instance = store.create(spec_with(cross_functional), agent_mode="mock")
    instance.graph.invoke({}, {"configurable": {"thread_id": instance.id}})
    return instance


class TestForward:
    def test_승인_노드까지_이동한다(self, store):
        instance = started(store)
        state = seek(instance, target_node_id="review")
        assert state["pendingApproval"]["nodeId"] == "review"
        # 목표가 승인 노드면 승인하지 않는다 — 결재는 사람이 한다.
        assert state["decision"] is None

    def test_승인_뒤의_노드로_가려면_결정이_필요하다(self, store):
        instance = started(store)
        with pytest.raises(SeekError, match="결정이 주어지지 않았다"):
            seek(instance, target_node_id="rolling")

    def test_결정을_주면_승인을_통과해_목표까지_간다(self, store):
        instance = started(store)
        state = seek(instance, target_node_id="rolling", decision=APPROVAL)
        assert state["decision"]["alternativeId"] == "alt-1"
        # 사이의 사람 확인 노드(action)도 지나왔다.
        assert "action" in state["visited"]

    def test_사람이_멈추지_않는_노드는_지나친_뒤_되짚어_준다(self, store):
        """
        멈출 수 있는 곳은 사람 대기 지점뿐이다. `rolling`은 시스템 노드라 통과하는데,
        그 상태를 그대로 주면 장면이 가리킨 지점이 아니라 그보다 앞선 화면이 보인다.
        """
        instance = started(store)
        state = seek(instance, target_node_id="rolling", decision=APPROVAL)

        assert state["historical"] is True
        assert state["next"] == ["rolling"]
        # 그 시점에는 rolling이 아직 실행 전이다.
        assert "rolling" not in state["visited"]
        # 인스턴스 자체는 더 진행되어 있다 — 되짚어 본 것일 뿐이다.
        assert snapshot(instance)["status"] == "done"

    def test_이미_그_지점이면_아무것도_하지_않는다(self, store):
        instance = started(store)
        before = snapshot(instance)
        after = seek(instance, target_node_id="review")
        assert after["visited"] == before["visited"]

    def test_반려되는_결정은_조용히_넘기지_않는다(self, store):
        # 장면이 선언한 결정이 규칙을 못 지키면 데모가 진행되지 않는데,
        # 조용히 멈추면 이유를 알 수 없다.
        instance = started(store)
        with pytest.raises(SeekError, match="반려"):
            seek(
                instance,
                target_node_id="rolling",
                decision={"alternativeId": "alt-1", "rationale": "짧음"},
            )

    def test_선택되지_않은_분기의_노드는_도달할_수_없다고_알린다(self, store):
        instance = started(store)
        with pytest.raises(SeekError, match="선택되지 않은 분기"):
            seek(instance, target_node_id="op-control", decision=APPROVAL)

    def test_명세에_없는_노드는_거부한다(self, store):
        instance = started(store)
        with pytest.raises(SeekError, match="명세에 없는 노드"):
            seek(instance, target_node_id="없는-노드")


class TestRewind:
    def test_승인_이전_시점에는_결정이_보이지_않는다(self, store):
        """
        데모 플레이어의 핵심 성질. 앞 장면을 찍었는데 결정이 남아 있으면
        "아직 승인 전"인 화면에 승인 결과가 보인다.
        """
        instance = started(store)
        seek(instance, target_node_id="rolling", decision=APPROVAL)
        assert snapshot(instance)["decision"] is not None

        state = seek(instance, target_node_id="review")

        assert state["historical"] is True
        assert state["pendingApproval"]["nodeId"] == "review"
        assert state["decision"] is None
        assert "action" not in state["visited"]

    def test_되짚어_봐도_인스턴스는_움직이지_않는다(self, store):
        """
        **읽기 전용이라는 것이 여기서 드러난다.** 실행으로 구현하면 LLM이 다시 불리고
        이미 내려진 승인이 사라진다.
        """
        instance = started(store)
        seek(instance, target_node_id="rolling", decision=APPROVAL)
        before = snapshot(instance)

        seek(instance, target_node_id="review")
        seek(instance, target_node_id="rca")

        after = snapshot(instance)
        assert after["visited"] == before["visited"]
        assert after["decision"] == before["decision"]
        assert after["historical"] is False

    def test_Agent_노드_시점도_되짚어_본다(self, store):
        instance = started(store)
        state = seek(instance, target_node_id="simulate")
        assert state["historical"] is True
        assert state["next"] == ["simulate"]
        # simulate가 아직 실행 전이므로 그 산출물은 없다 — 미완료 산출물 은닉(4.5).
        assert "simulate" not in {r["nodeId"] for r in state["runs"]}

    def test_과거_시점의_상태가_그때와_같다(self, store):
        instance = started(store)
        seek(instance, target_node_id="rolling", decision=APPROVAL)
        state = seek(instance, target_node_id="rca")

        # rca 이전까지만 실행된 시점이다.
        assert state["visited"] == ["start", "sensing"]
        assert {r["nodeId"] for r in state["runs"]} == {"sensing"}
        assert state["decision"] is None
        assert state["checkpointId"]


class TestOperationControlPath:
    def test_현업_통제_경로에서도_이동한다(self, store):
        # 같은 규칙이 다른 경로에서도 성립해야 한다 — 시나리오마다 승인 노드가 다르다.
        instance = started(store, cross_functional=False)
        state = seek(instance, target_node_id="op-control")
        assert state["pendingApproval"]["nodeId"] == "op-control"

    def test_에스컬레이션_경로의_노드는_도달할_수_없다(self, store):
        instance = started(store, cross_functional=False)
        with pytest.raises(SeekError, match="선택되지 않은 분기"):
            seek(instance, target_node_id="review", decision=APPROVAL)


def test_진행_상한이_노드_수보다_넉넉하다():
    # 상한이 너무 낮으면 정상 프로세스가 중간에 멈춘다.
    assert MAX_ADVANCE_STEPS > len(spec_with(True).nodes)
