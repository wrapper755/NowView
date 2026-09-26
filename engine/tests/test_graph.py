"""
그래프 조립과 실행.

TS 테스트(`tests/bpm-engine.test.ts`)가 잠그는 것과 다르다 — 거기서는 파생 규칙을
확인했고, 여기서는 **실제로 멈추고 갈라지고 재개되는지**를 확인한다. 진행 지점이
정수였을 때는 존재하지 않던 성질이다.
"""

from __future__ import annotations

import pytest
from conftest import spec_with
from langgraph.types import Command

from app.graph import build_graph, required_flags_for
from app.instances import config_for, snapshot


def _create(store, *, cross_functional: bool):
    return store.create(spec_with(cross_functional), agent_mode="mock")


def _advance(instance, command=None):
    instance.graph.invoke(
        command if command is not None else {"scenario_id": instance.spec.scenario_id},
        config_for(instance.id),
    )
    return snapshot(instance)


class TestBuild:
    def test_나가는_엣지가_없는_노드를_경고로_알린다(self, store):
        """
        `op-control`에 나가는 엣지가 없다. TS에서는 `sequence`에 없어 조용히
        `skipped`가 되므로 아무도 눈치채지 못한다 — 실엔진은 이것을 드러낸다.
        """
        built = build_graph(spec_with(True), runner=_mock_runner(), checkpointer=store.checkpointer)
        assert any("op-control" in w for w in built.warnings)

    def test_게이트웨이가_읽는_플래그만_해당_Agent에_요구한다(self):
        spec = spec_with(True)
        # rca 다음이 게이트웨이다.
        assert required_flags_for(spec, "rca") == ["crossFunctional"]
        # sensing은 게이트웨이와 이어지지 않으므로 아무 판정도 요구받지 않는다.
        assert required_flags_for(spec, "sensing") == []

    def test_분기_대상이_명세에_없으면_조립이_실패한다(self, store):
        spec = spec_with(True)
        spec.gateways[0].when_true = "없는-노드"
        with pytest.raises(ValueError, match="분기 대상"):
            build_graph(spec, runner=_mock_runner(), checkpointer=store.checkpointer)


class TestEscalationPath:
    """부서 간 조정이 필요한 경우 — Management Review로 에스컬레이션된다."""

    def test_승인_지점에서_실제로_멈춘다(self, store):
        instance = _create(store, cross_functional=True)
        state = _advance(instance)

        assert state["status"] == "waiting"
        assert state["pendingApproval"]["nodeId"] == "review"
        assert state["pendingApproval"]["kind"] == "decision"
        assert state["nodeStatuses"]["review"] == "waiting"
        # 게이트웨이가 에스컬레이션 쪽을 골랐다.
        assert "simulate" in state["visited"]
        assert "op-control" not in state["visited"]

    def test_승인_전에는_뒤_노드의_산출물이_존재하지_않는다(self, store):
        """
        TS에서는 "숨기는" 규칙이었는데(CLAUDE.md 4.5, 두 경로로 새어 나갔다)
        여기서는 노드가 돌기 전이라 기록 자체가 없다 — 구조가 규칙을 대신한다.
        """
        instance = _create(store, cross_functional=True)
        state = _advance(instance)
        ran = {r["nodeId"] for r in state["runs"]}
        assert ran == {"sensing", "rca", "simulate"}
        assert "evolution" not in ran
        assert state["nodeStatuses"]["evolution"] == "pending"

    def test_안_간_분기는_게이트웨이를_지난_뒤에_미실행이_된다(self, store):
        instance = _create(store, cross_functional=True)
        state = _advance(instance)
        assert state["nodeStatuses"]["op-control"] == "skipped"

    def test_승인하면_끝까지_진행하고_결정이_기록된다(self, store):
        instance = _create(store, cross_functional=True)
        _advance(instance)
        state = _advance(instance, Command(resume={
            "alternativeId": "alt-1",
            "leverValue": 2,
            "rationale": "전환 투자비 22억 대비 연간 회수 18억으로 1.2년 내 회수된다.",
        }))

        # review 다음은 action(사람 확인 노드)이므로 거기서 다시 멈춘다.
        assert state["decision"]["alternativeId"] == "alt-1"
        assert state["decision"]["decidedBy"] == "경영진 (CFO)"
        assert state["nodeStatuses"]["review"] == "done"
        assert state["pendingApproval"]["nodeId"] == "action"
        assert state["pendingApproval"]["kind"] == "acknowledgement"

        final = _advance(instance, Command(resume={"acknowledgedBy": "사업기획팀 정하윤"}))
        assert final["status"] == "done"
        assert final["next"] == []
        assert final["visited"][-1] == "end"
        assert final["nodeStatuses"]["evolution"] == "done"


class TestOperationControlPath:
    """
    같은 명세, 다른 판정 — 현업 통제로 끝난다.

    **경로가 실행의 결과로 나온다는 증거다.** TS의 `sequence`는 미리 선언된
    한 경로였고, 이 갈림은 표현할 수 없었다.
    """

    def test_현업_통제로_갈라진다(self, store):
        instance = _create(store, cross_functional=False)
        state = _advance(instance)

        assert state["pendingApproval"]["nodeId"] == "op-control"
        assert "simulate" not in state["visited"]
        assert state["nodeStatuses"]["simulate"] == "skipped"
        assert state["nodeStatuses"]["review"] == "skipped"

    def test_확인하면_대안_선택_없이_종료된다(self, store):
        instance = _create(store, cross_functional=False)
        _advance(instance)
        final = _advance(instance, Command(resume={"acknowledgedBy": "생산본부 김상현"}))

        assert final["status"] == "done"
        assert final["decision"] is None
        assert final["acknowledged"] == ["op-control"]


class TestApprovalGate:
    """
    승인 검증은 엔진에도 있다 — UI 버튼 비활성은 편의일 뿐 강제가 아니다
    (CLAUDE.md 4.3과 같은 이유).
    """

    def test_사유가_짧으면_반려하고_같은_지점에_다시_멈춘다(self, store):
        instance = _create(store, cross_functional=True)
        _advance(instance)
        state = _advance(instance, Command(resume={
            "alternativeId": "alt-1", "leverValue": 2, "rationale": "승인",
        }))

        assert state["status"] == "waiting"
        assert state["pendingApproval"]["nodeId"] == "review"
        assert "10자 이상" in state["pendingApproval"]["error"]
        assert state["decision"] is None

    def test_반려는_아무것도_건너뛰지_않는다(self, store):
        """
        재개 후 같은 지점에 다시 멈추면 LangGraph가 `next`를 비운다. 그것만 보고
        도달 가능 집합을 계산하면 뒤 노드 전체가 `skipped`로 떨어진다 — 실제로 그렇게
        틀렸다. 캔버스에 "미실행"으로 나가므로 눈에 보이는 오류다.
        """
        instance = _create(store, cross_functional=True)
        _advance(instance)
        state = _advance(instance, Command(resume={
            "alternativeId": "alt-1", "rationale": "짧음",
        }))

        for node_id in ("action", "rolling", "evolution", "end"):
            assert state["nodeStatuses"][node_id] == "pending", node_id
        # 실제로 안 간 분기만 미실행이다.
        assert state["nodeStatuses"]["op-control"] == "skipped"

    def test_반려_후_올바른_입력으로_진행된다(self, store):
        instance = _create(store, cross_functional=True)
        _advance(instance)
        _advance(instance, Command(resume={"alternativeId": "alt-1", "rationale": "짧음"}))
        state = _advance(instance, Command(resume={
            "alternativeId": "alt-2", "leverValue": 20,
            "rationale": "보전비 이연은 즉시 실행 가능하고 설비 리스크가 낮다.",
        }))
        assert state["decision"]["alternativeId"] == "alt-2"

    def test_명세에_없는_대안은_거부한다(self, store):
        instance = _create(store, cross_functional=True)
        _advance(instance)
        state = _advance(instance, Command(resume={
            "alternativeId": "alt-99", "rationale": "충분히 긴 사유를 적었습니다.",
        }))
        assert "명세에 없는 대안" in state["pendingApproval"]["error"]


class TestPersistence:
    def test_캐시를_비워도_명세에서_인스턴스를_복구한다(self, store):
        """
        체크포인트만 저장하면 재시작 후 그래프를 다시 조립할 수 없다 —
        명세를 함께 저장해 둔 이유다.
        """
        instance = _create(store, cross_functional=True)
        _advance(instance)
        instance_id = instance.id

        store._cache.clear()
        recovered = store.get(instance_id)
        state = snapshot(recovered)

        assert state["pendingApproval"]["nodeId"] == "review"
        assert {r["nodeId"] for r in state["runs"]} == {"sensing", "rca", "simulate"}

    def test_인스턴스가_서로_독립이다(self, store):
        escalated = _create(store, cross_functional=True)
        local = _create(store, cross_functional=False)
        assert _advance(escalated)["pendingApproval"]["nodeId"] == "review"
        assert _advance(local)["pendingApproval"]["nodeId"] == "op-control"


def _mock_runner():
    from app.agents import MockRunner

    return MockRunner()
