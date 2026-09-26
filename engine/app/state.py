"""
프로세스 인스턴스의 상태.

TS 쪽은 진행 지점(정수) 하나로 모든 것을 파생했다(CLAUDE.md 4.5). 실엔진에서는
그럴 수 없다 — 경로가 미리 정해져 있지 않고 **실행의 결과로 나오기** 때문이다.
그래서 `visited`가 진실이 되고, TS의 `sequence`는 이제 "Mock이 예상한 경로"일 뿐이다.

`visited`를 누적으로 두는 이유: 노드가 자기 id만 돌려주면 LangGraph가 합쳐 준다.
노드가 전체 목록을 다시 쓰게 하면 동시 실행에서 서로를 덮어쓴다.
"""

import operator
from typing import Annotated, Any, TypedDict


def merge_flags(left: dict[str, bool], right: dict[str, bool]) -> dict[str, bool]:
    """
    나중 판정이 이긴다. Agent가 같은 플래그를 다시 판정하면 갱신되어야 한다 —
    먼저 쓴 값을 지키면 재분석 결과가 무시된다.
    """
    return {**left, **right}


class ProcessState(TypedDict, total=False):
    scenario_id: str
    #: 실제로 지나온 노드. 경로의 유일한 진실이다.
    visited: Annotated[list[str], operator.add]
    #: Agent 실행 기록. 완료된 것만 들어온다.
    runs: Annotated[list[dict[str, Any]], operator.add]
    #: Agent가 판정해 게이트웨이가 읽는 사실.
    flags: Annotated[dict[str, bool], merge_flags]
    #: 사람이 내린 결정. 승인 노드에서 `interrupt`로 받는다.
    decision: dict[str, Any] | None
    #: 사람이 확인만 한 노드들 (승인 대상이 아닌 `user-task`).
    acknowledged: Annotated[list[str], operator.add]
