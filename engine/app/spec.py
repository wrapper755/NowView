"""
프로세스 명세 — Next(TypeScript)가 인스턴스 생성 요청에 담아 보내는 계약.

**왜 엔진이 토폴로지를 들고 있지 않은가.** 노드·엣지·Agent 정의는 `lib/mock-data/`가
유일한 진실이다(CLAUDE.md 4.13). 엔진이 같은 것을 따로 들고 있으면 두 벌이 되고,
시나리오를 추가할 때 양쪽을 손대야 한다 — "레지스트리에 한 항목 더하면 끝"이 깨진다.

그래서 엔진은 **토폴로지를 모르는 범용 런타임**이다. 명세를 받아 그래프를 그때 조립한다.
시나리오 2·3도 코드 수정 없이 돈다.

경영 규칙도 마찬가지다 — 사유 최소 길이는 TS의 `DECISION_RATIONALE_MIN_LENGTH`가
원천이고, 여기서는 `decision_rules`로 **받아서** 적용한다. 숫자를 다시 적으면
UI·API·엔진 세 곳이 갈라진다.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

NodeKind = Literal["start", "end", "agent-task", "user-task", "service-task", "gateway"]


class _Base(BaseModel):
    """
    TS는 camelCase, Python은 snake_case로 쓴다.

    별칭으로 경계에서만 바꾼다 — 한쪽 관례를 다른 쪽에 밀어넣으면 그쪽 코드가
    내내 어색해지고, 결국 변환 코드가 사람 손으로 흩어진다.
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class NodeSpec(_Base):
    id: str
    kind: NodeKind
    label: str
    actor: str | None = None
    stage: str | None = None
    #: 완료 시 산출물 요약. 미완료 노드에서는 노출하지 않는다(CLAUDE.md 4.5).
    outcome: str | None = None
    duration: str | None = None
    #: `agent-task`에만 있다.
    agent_id: str | None = None


class EdgeSpec(_Base):
    id: str
    source: str
    target: str
    label: str | None = None


class AgentSpec(_Base):
    id: str
    name: str
    role: str
    capability: str


class GatewaySpec(_Base):
    """
    배타 분기의 라우팅 규칙.

    **분기는 결정론적이다** — 상태의 플래그 하나를 읽어 경로를 고른다.
    그 플래그를 만드는 것은 선행 Agent이고(확률적), 고르는 것은 게이트웨이다(결정론적).
    기획안의 "Deterministic BPM + Probabilistic AI"가 여기서 갈린다.

    플래그가 없으면 `when_false`로 간다 — 판정되지 않은 것을 "조정 필요"로 보면
    에스컬레이션이 기본값이 되어 현업 통제 경로가 죽는다.
    """

    node_id: str
    #: 이 분기가 읽는 플래그 이름. Agent 산출물의 `flags`에 담겨 온다.
    flag: str
    when_true: str
    when_false: str


class DecisionRules(_Base):
    """승인 게이트. 값의 원천은 TS(`DECISION_RATIONALE_MIN_LENGTH`)다."""

    rationale_min_length: int = 10


class AgentOutputSpec(_Base):
    """
    Mock 모드에서 Agent가 돌려줄 산출물. `lib/mock-data`의 `AgentRun`을 그대로 받는다.

    LLM 모드에서는 쓰이지 않지만 `sources`는 계속 쓴다 — 어떤 데이터를 근거로 보라고
    지시할지가 프롬프트에 필요하고, 근거 없는 결론을 만들지 않게 하는 장치다.
    """

    agent_id: str
    node_id: str
    output: str
    sources: list[dict] = Field(default_factory=list)
    duration: str = "0분 00초"
    confidence: Literal["high", "medium", "low"] = "high"
    confidence_note: str | None = None
    escalations: list[dict] = Field(default_factory=list)
    #: 이 Agent가 판정해 게이트웨이에 넘기는 플래그.
    flags: dict[str, bool] = Field(default_factory=dict)


class AlternativeSpec(_Base):
    """승인 화면이 제시하는 선택지. 엔진은 제시하고 고른 값을 검증할 뿐, 금액을 계산하지 않는다."""

    id: str
    title: str
    recommended: bool = False


class ProcessSpec(_Base):
    scenario_id: str
    subject: str
    risk_id: str
    kri: dict = Field(default_factory=dict)
    nodes: list[NodeSpec]
    edges: list[EdgeSpec]
    agents: list[AgentSpec] = Field(default_factory=list)
    gateways: list[GatewaySpec] = Field(default_factory=list)
    decision_rules: DecisionRules = Field(default_factory=DecisionRules)
    #: Mock 모드에서 쓸 산출물. 노드 id로 찾는다.
    agent_outputs: list[AgentOutputSpec] = Field(default_factory=list)
    #: 대안 선택이 필요한 `user-task`. **엔진이 추측하지 않는다** — 단계 이름이나
    #: stage로 짚으면 시나리오마다 승인 단계 이름이 달라 깨진다(CLAUDE.md 4.13).
    #: TS가 `approvalStepIndex`로 이미 계산하므로 그 결과를 받는다.
    decision_node_id: str | None = None
    alternatives: list[AlternativeSpec] = Field(default_factory=list)

    def node(self, node_id: str) -> NodeSpec:
        for n in self.nodes:
            if n.id == node_id:
                return n
        raise KeyError(f"명세에 없는 노드: {node_id}")

    def outgoing(self, node_id: str) -> list[EdgeSpec]:
        return [e for e in self.edges if e.source == node_id]

    def gateway(self, node_id: str) -> GatewaySpec | None:
        for g in self.gateways:
            if g.node_id == node_id:
                return g
        return None

    def output_for(self, node_id: str) -> AgentOutputSpec | None:
        for o in self.agent_outputs:
            if o.node_id == node_id:
                return o
        return None
