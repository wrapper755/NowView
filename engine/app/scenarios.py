"""
각본 사본 — 원본은 Company1 리포 `scenarios/sc0N.json`이다(회사 사이트의 자동 모드·결재 예시
값이 쓴다, `docs/role-split.md` §5). NowView는 `engine/scenarios/`에 사본을 두고
(`scripts/sync-scenarios.sh`) **시험 전용** 각본 실행기의 기본(BASE) 단계로 읽는다 — 운영·로컬에서는
회사 사이트가 각본을 몬다.

한 줄 = `{code, at, actor, kind, node_id, answer, label}` + 엔진 전용 칸(`event` 데이터 사건
번호 · `expect_proposal` · `record` 확인 기록 id). 장면마다 `Step`의 칸만 골라 짓는다(장면 6·7의
`Step`은 시각을 확인 일정에서 읽어 `at`이 없다). 시험 사례(EX·X·E…)는 각 장면 `demo.steps_for`가
이 위에 바꾼다.
"""

from __future__ import annotations

import dataclasses
import json
import os
from functools import cache
from pathlib import Path
from typing import Any

DEFAULT_DIR = Path(__file__).resolve().parents[1] / "scenarios"


@cache
def _rows(scene: int, directory: str) -> tuple[dict[str, Any], ...]:
    doc = json.loads((Path(directory) / f"sc0{scene}.json").read_text(encoding="utf-8"))
    return tuple(doc["steps"])


def steps(scene: int, step_type: type) -> list[Any]:
    """그 장면의 기본 각본 — `step_type`(장면의 `Step`)의 칸만 넣어 새로 짓는다(호출마다 새로)."""
    names = {f.name for f in dataclasses.fields(step_type)}
    directory = os.getenv("NOWVIEW_SCENARIOS_DIR") or str(DEFAULT_DIR)
    return [
        step_type(**{k: _copy(v) for k, v in row.items() if k in names})
        for row in _rows(scene, directory)
    ]


def _copy(value: Any) -> Any:
    """답은 사례가 고쳐 쓴다 — 담아 둔 원본이 바뀌지 않게 새로 만든다."""
    return json.loads(json.dumps(value)) if isinstance(value, dict | list) else value
