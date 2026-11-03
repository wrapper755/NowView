"""
SC04 기본 시연 각본 — D400 → D401~D413(화면구성·시연순서 「기본시연」, 데이터 「SC04이벤트」
EV41-01~23),
그리고 E 사례의 변형(「분기시연」·「SC04예외」).

장면 1~3과 같다: **단계 진행은 실제 상태 전환을 실행한다.** 각본은 누가·언제·무엇을만 들고, 실행은
사람이
버튼을 누른 것과 같은 길(`Sc04Process.start`·`act`·`meeting_record`…)이다.

**입력 문장은 시드에서 읽는다** — 결과 결론(SC04분석결과)·근거 해석(SC04근거)·추천
사유(SC04비교)·질의
(SC04회의)·조건·지시(SC04조건지시)·예산·기한(SC04예산과제)을 각본에 옮겨 적지 않는다. 시각은
「SC04이벤트」의
event_at_KST다. 이벤트가 없는 중간 단계(판단 초안·승인서 초안·Agent 요청)는 그 사이 시각에 둔다.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import Any

from app import scenarios
from app.sc01.domain import DomainError, parse_at
from app.sc04 import domain
from app.sc04.process import Sc04Process
from app.sc04.seed import Seed, load_seed
from app.script_wait import after_record


@dataclass(frozen=True)
class Step:
    code: str
    at: str  # KST 가상시각
    actor: str
    kind: str  # start · act · view · record · agent · clock
    node_id: str | None = None
    answer: dict[str, Any] = field(default_factory=dict)
    label: str = ""
    event: str | None = None  # SC04이벤트 id


def base_steps(seed: Seed | None = None) -> list[Step]:
    """
    기본 시연 — 각본의 원본은 Company1 `scenarios/sc04.json`이고 여기는 사본을 읽는다
    (`app/scenarios.py`). 운영·로컬에서는 회사 사이트가 이 각본으로 몬다 — 이 실행기는
    시험 전용이다.
    """
    return scenarios.steps(4, Step)


def _after(steps: list[Step], pick, extra: list[Step]) -> list[Step]:
    i = max(i for i, s in enumerate(steps) if pick(s))
    return [*steps[: i + 1], *extra, *steps[i + 1 :]]


def steps_for(case_id: str, seed: Seed | None = None) -> list[Step]:
    seed = seed or load_seed()
    steps = base_steps(seed)
    verify = next(s for s in steps if s.node_id == "Verify_Effects")
    if case_id in ("E401", "E402"):
        # 복제 제출 초안의 오류(감가상각 회피 · 중복 제거 0)를 검증이 막는다 → 담당 임원 보완 →
        # 재검증
        owner, content = (
            (
                domain.PROD_EXEC,
                "기존 감가상각비 120백만원/월 제거 — 잔존 고정비로 기준 손익에 유지(EVDC45)",
            )
            if case_id == "E401"
            else (
                domain.BUY_EXEC,
                "10~12월 P-MAT02 할인 중복 1,800,000원 제거 — ALT43 가격차에 포함(EVDC44)",
            )
        )
        blocked = replace(
            verify, code=case_id, at="2027-07-07T14:30:00+09:00", event=None, label="검증 — 차단"
        )
        fix = Step(
            case_id,
            "2027-07-07T14:45:00+09:00",
            owner,
            "act",
            "Correct_Effects",
            {"보완내용": content},
            "검증 보완·재확인",
        )
        i = steps.index(verify)
        return [*steps[:i], blocked, fix, *steps[i:]]
    if case_id == "E403":
        # 대표 질의에서 대체 공급업체의 증량 능력 근거가 확인되지 않는다 → ALT43 보류, 과제 미생성
        extra = [
            Step(
                "E403",
                "2027-07-12T10:27:00+09:00",
                domain.CEO,
                "record",
                answer={
                    "record_type": "QUESTION",
                    "subject": "대표질문",
                    "content": "기존 승인 업체가 이번 품목을 월 6,000개 공급할 수 있다는 근거는 "
                    "무엇입니까?",
                    "related": "ALT43",
                },
                label="ALT43 공급능력 질의",
            ),
            Step(
                "E403",
                "2027-07-12T10:28:00+09:00",
                domain.BUY_EXEC,
                "record",
                answer={
                    "record_type": "ANSWER",
                    "subject": "구매답변",
                    "content": "SUP-M02의 증량 공급능력 확인서는 아직 받지 못했습니다 — 7/30까지 "
                    "확인하겠습니다.",
                    "related": "ALT43",
                },
                label="ALT43 근거 미확인 답변",
            ),
        ]
        steps = _after(steps, lambda s: s.kind == "record" and "QA414" in s.label, extra)
        out = []
        for s in steps:
            if s.node_id == "Decide":
                s = replace(
                    s,
                    label="REV41 — 승인 1 · 조건부 1 · 보류 1",
                    answer={
                        **s.answer,
                        "ALT43결정": "보류",
                        "ALT43결정사유": "SUP-M02 증량 공급능력 근거 미확인 — 구매 임원이 7/30까지 "
                        "확인 보고",
                    },
                )
            if s.node_id == "Draft_Approval":
                s = replace(
                    s,
                    answer={
                        **s.answer,
                        "총괄한도": "14000000",
                        "ACT43한도": "",
                        "ACT43완료기한": "",
                    },
                )
            if s.node_id == "Accept_ACT43":
                continue
            out.append(s)
        return out
    if case_id == "E404":
        # 승인서 초안이 총괄 한도·계획 제출기한을 비웠다 → 대표가 보완 요청 → 채운 초안을 확정
        draft = next(s for s in steps if s.node_id == "Draft_Approval")
        final = next(s for s in steps if s.node_id == "Finalize_Approval")
        missing = replace(
            draft,
            code="E404",
            at="2027-07-12T14:20:00+09:00",
            label="승인서 초안 — 총괄 한도·계획기한 누락",
            answer={**draft.answer, "총괄한도": "", "계획제출기한": ""},
        )
        back = replace(
            final,
            code="E404",
            at="2027-07-12T14:25:00+09:00",
            event=None,
            label="대표 보완 요청 — 누락 항목",
            answer={
                "승인결정": "보완요청",
                "승인의견": "총괄 한도와 계획 제출기한이 비어 있다 — 채워서 다시 올린다",
            },
        )
        i = steps.index(draft)
        return [*steps[:i], missing, back, *steps[i:]]
    if case_id == "E405":
        # ACT43 책임자가 불명확한 조건으로 반려 → 전체 책임 임원이 승인 범위 안에서 보완 → 새
        # 배정버전 재인수
        a43 = next(s for s in steps if s.node_id == "Accept_ACT43")
        returned = replace(
            a43,
            code="E405",
            event=None,
            label="ACT43 반려",
            answer={
                "ACT43결정": "반려",
                "ACT43사유": "P-MAT02 전환 검증 범위와 SUP-M02 물류 조건이 과제에 명확하지 않다",
            },
        )
        revise = Step(
            "E405",
            "2027-07-13T09:25:00+09:00",
            domain.CFO,
            "act",
            "Revise_ACT43",
            {
                "ACT43보완사유": "반려 사유 — 검증 범위·물류 조건 명확화",
                "ACT43보완내용": "전환 검증은 EVDC46 범위(P-MAT02 월 6,000개)로 한정, 추가물류 "
                "100원/개는 승인 가정 그대로",
            },
            "ACT43 보완 — 배정버전 2",
        )
        again = replace(a43, at="2027-07-13T09:28:00+09:00", label="ACT43 새 배정버전 재인수")
        i = steps.index(a43)
        return [*steps[:i], returned, revise, again, *steps[i + 1 :]]
    return steps


def run_step(process: Sc04Process, demo_run_id: str, index: int) -> dict:
    """각본의 `index`번째 단계. 이미 지나간 단계면 현재 문서를 돌려준다(장면 1~3과 같다)."""
    doc = process.get(demo_run_id)
    if (doc["bpm"] or {}).get("executor") == "studio":
        raise DomainError(
            "Studio 시험 실행의 데모 실행은 각본을 돌리지 않는다 — 결재는 Studio에서 답한다", 409
        )
    steps = steps_for(doc["case_id"], process.seed)
    if not 0 <= index < len(steps):
        raise DomainError(f"각본에 없는 단계: {index}", 404)
    done = doc.get("script_index", -1)
    if index <= done:
        return doc
    if index != done + 1:
        raise DomainError(f"단계를 건너뛸 수 없다 — 다음은 {done + 1}번이다", 409)
    step = steps[index]
    if parse_at(step.at) > parse_at(doc["clock"]):
        process.set_clock(demo_run_id, step.at, actor="u-demo", event_code=step.code)
    mark = {"event_code": step.code, "script_index": index}
    if step.kind == "start":
        return process.start(demo_run_id, actor=step.actor, **mark)
    if step.kind in ("view", "clock"):
        return process.mark(demo_run_id, note=step.label, **mark)
    center = (doc["bpm"] or {}).get("executor") == "center"
    if step.kind == "record":
        return _after_record(
            process,
            center,
            lambda: process.meeting_record(demo_run_id, actor=step.actor, **step.answer, **mark),
        )
    if step.kind == "agent":
        return _after_record(
            process,
            center,
            lambda: process.agent(demo_run_id, step.answer["kind"], actor=step.actor, **mark),
        )
    node_id = step.node_id or ""
    since = max((a["seq"] for a in doc["audit"]), default=0)
    # 화면이 보는 버전은 시도마다 다시 읽는다 — 앞 기록이 들어오기 전에 읽으면 낡은 버전이다.
    done_doc = _after_record(
        process,
        center,
        lambda: process.act(
            demo_run_id,
            node_id,
            dict(step.answer),
            actor=step.actor,
            expect=_expect(process.get(demo_run_id), node_id),
            **mark,
        ),
    )
    return _await_own_record(process, demo_run_id, node_id, since) if center else done_doc


def _after_record(process: Sc04Process, center: bool, run: Callable[[], dict]) -> dict:
    """
    Center 실행이면 앞 결재의 기록 작업을 기다린다(`app.script_wait`, 장면 3 실측).

    대리 답 대기의 세 배다 — 인수 다섯 건의 기록 작업을 서버 실행기가 차례로 불러 완료 조건이
    30초 안에 서지 않았다(2026-10-28 로컬 Center 실측, 약 50초).
    """
    wait_s = process.center_wait_s * 3
    return after_record(wait_s, center, run, gated=(domain.PrerequisiteError,))


def _await_own_record(process: Sc04Process, demo_run_id: str, node_id: str, since: int) -> dict:
    """
    Center 실행이면 이 단계 결재의 기록 작업이 들어올 때까지 기다린다(기록 또는 거절).

    대리 답은 결재만 닫는다 — 기다리지 않으면 다음 단계가 시계를 먼저 옮겨 기록이 뒤 시각으로
    적히고, 지난 시점을 되감으면 그 단계의 효과가 없다(TOTAL 인수 단계에 인수 0/3, 인수 시각이
    전부 완료 시각 — 2026-10-28 로컬 Center 실측). 끝내 오지 않으면 지금 문서를 돌려준다 — 다음
    단계의 대기가 거절 사유를 낸다.
    """
    deadline = time.monotonic() + process.center_wait_s * 3
    while True:
        doc = process.get(demo_run_id)
        if any(
            a["seq"] > since
            and a["action"] in ("answer_via", "answer_rejected")
            and (a.get("detail") or {}).get("node_id") == node_id
            for a in doc["audit"]
        ):
            return doc
        if time.monotonic() >= deadline:
            return doc
        time.sleep(min(1.0, process.center_wait_s))


def _expect(doc: dict, node_id: str) -> dict[str, Any] | None:
    """화면이 보는 것과 같은 버전을 싣는다 — 판단본·승인서 초안·배정버전."""
    if node_id == "Confirm_Decision":
        d = domain.decision_report(doc, confirmed=False)
        return None if d is None else {"report": d["report_id"]}
    if node_id == "Decide":
        d = domain.decision_report(doc, confirmed=True)
        return None if d is None else {"report": d["report_id"]}
    if node_id == "Finalize_Approval":
        draft = doc["approval_draft"]
        return None if draft is None else {"approval": draft["version"]}
    target = domain.NODE_ROLES.get(node_id, {}).get("owner_of")
    if target in domain.ACCEPT_NODES:
        a = doc["assignments"].get(target)
        return None if a is None else {"assignment": a["assignment_version"]}
    return None
