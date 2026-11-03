"""
SC05 기본 시연 각본 — D500 → D501~D518(화면구성·시연순서 「시연순서」, 데이터 「SC05이벤트」
EV51-01~49), 그리고 X
사례의 변형(「SC05예외」).

장면 1~4와 같다: **단계 진행은 실제 상태 전환을 실행한다.** 각본은 누가·언제·무엇을만 들고, 실행은
사람이 버튼을
누른 것과 같은 길(`Sc05Process.start`·`act`·`agent`…)이다. 배경 이력(BACKGROUND 행)은 각본에 없다 —
시계가 그 시각을
지나면 원천에서 들어온다.

**입력은 시드에서 읽는다** — 계획 변경 사유(SC05계획)·변경
공유(SC05변경공유)·주문(SC05구매표본)·운영계획(SC05운영계획)·
변경 대사(SC05변경대사)·근거(SC05근거)·후속(SC05인계). 시각은 「SC05이벤트」의 발생_KST, Agent는
「SC05Agent」의 실행_KST다.
데이터에 없는 활동의 협조·비용과 대응 판단의 날짜는 **구현용 보완**이다(구현명세 12장 — 활동 비용은
내부 교육 0원·
승인 후 외부 검증 2백만원) — `COOPERATION`·`COSTS`에 모았다.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import Any

from app import scenarios
from app.sc01.domain import USERS, DomainError, parse_at
from app.sc05 import domain
from app.sc05.process import Sc05Process
from app.sc05.seed import Seed, load_seed
from app.script_wait import after_record


@dataclass(frozen=True)
class Step:
    code: str
    at: str  # KST 가상시각
    actor: str
    kind: str  # start · act · view · agent · review
    node_id: str | None = None
    answer: dict[str, Any] = field(default_factory=dict)
    label: str = ""
    event: str | None = None  # SC05이벤트 id


#: 구현용 보완 — 활동별 협조(데이터에 없다). AG51 초안은 비워 두고 구매 담당이 채운다(사람 수정,
#: D502).
COOPERATION = {
    "01": "생산팀장",
    "02": "구매팀장",
    "03": "생산팀장",
    "04": "생산임원",
    "05": "생산팀장",
    "06": "생산팀장",
}
#: 구현용 보완 — 활동 비용(원). 내부 교육 0원, 승인 후 외부 운영 검증 2백만원(REQ51)을 운영 적용
#: 준비에 둔다.
COSTS = {"01": "0", "02": "0", "03": "0", "04": "0", "05": "2000000", "06": "0"}
EFFECT_RULE = (
    "9월부터 A-b·P-COM01 긴급구매 건수와 추가비(운송·할증)를 주문 ID 단위로 월별 확인 — 비교 "
    "기준은 개선안 검토·실행 승인 정규화 "
    "월 12건×건당 비용. 원천: 구매 주문·긴급 승인·운영지원 집행. 연간 효과는 별도 검증"
)


def _name(user_id: str) -> str:
    return USERS[user_id]["name"]


def activity_lines(activities: list[dict[str, Any]]) -> str:
    """활동 → 폼의 활동 목록 글(번호|활동|담당|시작|종료|선행|협조|비용|완료근거|근거ID)."""
    rows = []
    for a in activities:
        coop = a["cooperation"] or COOPERATION.get(a["activity_id"], "")
        coop_name = next((u["name"] for u in USERS.values() if u["role"] == coop), coop)
        cost = a["cost"] if a["cost"] is not None else COSTS.get(a["activity_id"], "")
        rows.append(
            " | ".join(
                [
                    a["activity_id"],
                    a["name"],
                    _name(a["owner"]),
                    a["start"],
                    a["end"],
                    ",".join(a["predecessors"]) or "-",
                    coop_name,
                    cost,
                    a["completion"],
                    a["evidence"],
                ]
            )
        )
    return "\n".join(rows)


def base_steps(seed: Seed | None = None) -> list[Step]:
    """
    기본 시연 — 각본의 원본은 Company1 `scenarios/sc05.json`이고 여기는 사본을 읽는다
    (`app/scenarios.py`). 운영·로컬에서는 회사 사이트가 이 각본으로 몬다 — 이 실행기는
    시험 전용이다.
    """
    return scenarios.steps(5, Step)


def steps_for(case_id: str, seed: Seed | None = None) -> list[Step]:
    seed = seed or load_seed()
    steps = base_steps(seed)
    if case_id == "X502":
        # 총괄 한도를 넘는 변경안 → 시행 보류(별도 대표 승인 필요) → 범위 안의 변경안을 다시 요청
        base = next(s for s in steps if s.node_id == "Request_Change")
        over = replace(
            base,
            code="X502",
            at="2027-08-10T09:50:00+09:00",
            event=None,
            label="총괄 한도 초과 변경안 — 시행 보류",
            answer={
                **base.answer,
                "변경예산": "20000000",
                "변경영향": "외부 교육 확대로 예산 2천만원 — 총괄 한도 초과",
                "변경초안출처": "",
            },
        )
        i = steps.index(base)
        return [*steps[:i], over, *steps[i:]]
    if case_id == "X506":
        # 종전 공식본에 장면 4 승인효과를 다시 더한 검토안 → 대사 실패 → 마감+잔여 방식으로 다시
        # 작성
        base = next(s for s in steps if s.node_id == "Draft_Forecast")
        wrong = replace(
            base,
            code="X506",
            at="2027-10-05T09:45:00+09:00",
            event=None,
            label="승인효과 재가산 검토안 — 대사 실패",
            answer={**base.answer, "산정방식": "종전 공식본+승인효과"},
        )
        i = steps.index(base)
        return [*steps[:i], wrong, *steps[i:]]
    if case_id == "X507":
        # 대표 반려 → FC50 유지 → 보완 검토안을 다시 작성·확인·제출 → 승인·게시
        approve = next(s for s in steps if s.node_id == "Approve_Forecast")
        i = steps.index(approve)
        returned = replace(
            approve,
            code="X507",
            event=None,
            label="대표 반려 — FC50 유지",
            answer={
                "대표결정": "반려",
                "대표의견": "11~12월 3건 가정의 근거(대행·수시 공유 정착)를 보완해 다시 올린다",
            },
        )
        redo = []
        for k, node in enumerate(
            (
                "Draft_Forecast",
                "Confirm_FC_BUY",
                "Confirm_FC_PROD",
                "Confirm_FC_SALES",
                "Submit_Forecast",
            )
        ):
            s = next(x for x in steps if x.node_id == node)
            ans = dict(s.answer)
            if node == "Draft_Forecast":
                ans["전망변경사유"] += (
                    " · 보완: 11~12월 3건은 9월 대행 확인 1건·지연 1건 재발 점검을 전제로 한 가정"
                )
            redo.append(
                replace(
                    s,
                    code="X507",
                    at=f"2027-10-06T10:{20 + k * 5:02d}:00+09:00",
                    event=None,
                    label=f"보완 — {s.label}",
                    answer=ans,
                )
            )
        again = replace(
            approve, at="2027-10-06T11:00:00+09:00", event=None, label="보완 검토안 승인 — FC51"
        )
        publish = next(s for s in steps if s.node_id == "Publish_Forecast")
        publish = replace(publish, at="2027-10-06T11:05:00+09:00", event=None)
        rest = [s for s in steps[i + 1 :] if s.node_id != "Publish_Forecast"]
        return [*steps[:i], returned, *redo, again, publish, *rest]
    if case_id == "X508":
        # 11월 긴급 전망 3 → 4건 — 마감 Actual은 그대로, 11월·연간 전망 120만원 감소
        return [
            replace(s, label=s.label + " (11월 4건)", answer={**s.answer, "OPL5111월": "4"})
            if s.node_id == "Confirm_OPL51"
            else s
            for s in steps
        ]
    return steps


def run_step(process: Sc05Process, demo_run_id: str, index: int) -> dict:
    """각본의 `index`번째 단계. 이미 지나간 단계면 현재 문서를 돌려준다(장면 1~4와 같다)."""
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
    if step.kind == "view":
        return process.mark(demo_run_id, note=step.label, **mark)
    center = (doc["bpm"] or {}).get("executor") == "center"
    if step.kind == "agent":
        return _after_record(
            process,
            center,
            lambda: process.agent(demo_run_id, step.answer["kind"], actor=step.actor, **mark),
        )
    if step.kind == "review":
        output = latest_output(process.get(demo_run_id), step.answer["kind"])
        if output is None:
            return process.mark(
                demo_run_id, note=f"{step.answer['kind']} 초안 없음 — 수동 진행", **mark
            )
        return _after_record(
            process,
            center,
            lambda: process.review_agent(
                demo_run_id, output, actor=step.actor, note=step.answer["note"], **mark
            ),
        )

    def act() -> dict:
        # 답·버전은 시도마다 다시 읽는다 — 앞 기록이 들어오기 전에 읽으면 낡은 값이다.
        current = process.get(demo_run_id)
        return process.act(
            demo_run_id,
            step.node_id or "",
            resolve(current, step.answer),
            actor=step.actor,
            expect=_expect(current, step.node_id or ""),
            **mark,
        )

    since = max((a["seq"] for a in doc["audit"]), default=0)
    try:
        done_doc = _after_record(process, center, act)
    except DomainError:
        # 기다리는 동안 바깥 답(회사 사이트·콘솔)의 기록이 이 단계를 지나갔으면 각본은 할 일이
        # 없다 — 사이트에서 답한 직후 「다음」을 누르면 결재가 이미 닫혀 409였다(섞어 진행 실측).
        now = process.get(demo_run_id)
        if now.get("script_index", -1) >= index:
            return now
        raise
    if not center:
        return done_doc
    return _await_own_record(process, demo_run_id, step.node_id or "", since)


def _await_own_record(process: Sc05Process, demo_run_id: str, node_id: str, since: int) -> dict:
    """
    Center 실행이면 이 단계 결재의 기록 작업이 들어올 때까지 기다린다(기록 또는 거절).

    대리 답은 결재만 닫는다 — 기다리지 않으면 다음 단계가 먼저 간다. 상신 기록 전의 현업 승인이
    「없는 품의」였다(2026-10-28 로컬 Center 실측). 장면 4의 같은 이름 함수와 같다. 끝내 오지
    않으면 지금 문서를 돌려준다 — 다음 단계의 대기가 거절 사유를 낸다.
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


def _after_record(process: Sc05Process, center: bool, run: Callable[[], dict]) -> dict:
    """Center 실행이면 앞 결재의 기록 작업을 기다린다(`app.script_wait`, 장면 3 실측)."""
    return after_record(process.center_wait_s, center, run, gated=(domain.PrerequisiteError,))


def latest_output(doc: dict, kind: str) -> str | None:
    """그 종류의 가장 새 **성공** 초안 — 실패한 초안은 인용하지 않는다(수동 작성)."""
    found = [
        o for o in doc["agent_outputs"].values() if o["kind"] == kind and o["status"] == "SUCCEEDED"
    ]
    return max(found, key=lambda o: o["seq"])["output_id"] if found else None


def resolve(doc: dict, answer: dict[str, Any]) -> dict[str, Any]:
    """
    `@AG51` 같은 자리표시 → 실제 초안 id(없으면 빈 글 — Agent 없이 진행한다). `@PLAN` → 지금 유효
    계획(화면이 보는 것).
    """

    def one(v: Any) -> Any:
        if v == "@PLAN":
            return doc["plan_pointer"] or ""
        if isinstance(v, str) and v.startswith("@AG"):
            return latest_output(doc, v[1:]) or ""
        return v

    return {k: one(v) for k, v in answer.items()}


def _expect(doc: dict, node_id: str) -> dict[str, Any] | None:
    """화면이 보는 것과 같은 버전을 싣는다 — 계획·검토안·산정본."""
    if node_id in ("Confirm_Plan", "Verify_Plan", "Confirm_Change", "Verify_Change"):
        p = domain.current_plan(doc)
        return None if p is None else {"plan": p["plan_id"]}
    if node_id.startswith("Confirm_FC_") or node_id in ("Submit_Forecast", "Approve_Forecast"):
        f = domain.review_forecast(doc)
        return None if f is None else {"forecast": f["forecast_id"], "run": f["run_id"]}
    return None
