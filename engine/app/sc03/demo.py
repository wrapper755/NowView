"""
SC03 기본 시연 각본 — D30 → D31~D41 (화면구성·시연순서 「기본시연」, 데이터 「SC03이벤트」
EV31-01~22),
그리고 E 사례의 변형(「분기시연」·「SC03예외」).

장면 1·2와 같다: **단계 진행은 실제 상태 전환을 실행한다.** 각본은 누가·언제·무엇을만 들고, 실행은
사람이
버튼을 누른 것과 같은 길(`Sc03Process.start`·`act`·`meeting_record`…)이다.

**입력 문장은 시드에서 읽는다** — 회신 문장(SC03사실확인)·쟁점 처리(SC03쟁점)·질의(SC03회의)·후보
판단
(SC03후보)을 각본에 옮겨 적지 않는다. 시각은 「SC03이벤트」의 event_at_KST다.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import Any

from app.sc01.domain import DomainError, parse_at
from app.sc03 import domain
from app.sc03.process import Sc03Process
from app.sc03.seed import Seed, kst, load_seed
from app.script_wait import after_record


@dataclass(frozen=True)
class Step:
    code: str
    at: str  # KST 가상시각
    actor: str
    kind: str  # start · act · view · record · agent · revision · clock
    node_id: str | None = None
    answer: dict[str, Any] = field(default_factory=dict)
    label: str = ""
    event: str | None = None  # SC03이벤트 id


def _user(account: Any) -> str:
    return domain.ACCOUNTS[str(account).strip()]


def base_steps(seed: Seed) -> list[Step]:
    ev = seed.by_id("SC03이벤트")
    fact = seed.by_id("SC03사실확인")
    q = seed.by_id("SC03쟁점")
    meeting = seed.by_id("SC03회의")
    basis = seed.by_id("SC03기준")

    def at(event_id: str) -> str:
        return kst(ev[event_id]["event_at_KST"])  # type: ignore[return-value]

    def s(f: str, key: str) -> str:
        return str(fact[f][key])

    def reply(
        label: str,
        f_fact: str,
        *,
        assumption: str | None = None,
        unconfirmed: str | None = None,
        question: str | None = None,
    ) -> dict[str, Any]:
        refs = [s(f_fact, "evidence_ref")] + [
            s(x, "evidence_ref") for x in (assumption, unconfirmed) if x
        ]
        return {
            f"{label}회신": "확인",
            f"{label}사실": s(f_fact, "statement"),
            f"{label}가정": s(assumption, "statement") if assumption else "",
            f"{label}미확인": s(unconfirmed, "statement") if unconfirmed else "",
            f"{label}질문": str(q[question]["question"]) if question else "",
            f"{label}근거": " · ".join(refs),
            f"{label}의견": "",
        }

    judge: dict[str, Any] = {}
    for qid in domain.QUESTION_SLOTS:
        row = q[qid]
        judge.update(
            {
                f"{qid}차단": "차단" if row["blocking"] else "비차단",
                f"{qid}담당자": _user(row["owner"]),
                f"{qid}기한": kst(row["due_at"]),
                f"{qid}처리방향": str(row["treatment"]),
            }
        )
    rev = meeting["REV31"]
    decide: dict[str, Any] = {
        "결론": "조건부수용" if rev["state"] == "CONDITIONAL_ACCEPT" else "수용",
        "결론내용": str(rev["content"]),
        "조건": "Q31·Q32는 7/6 18시까지 AT31·AT34로 확인한다 — 현재 손익 계산 오류는 없다",
    }
    for c in seed.rows("SC03후보"):
        cid = str(c["candidate_id"])
        decide[f"{cid}판단"] = "상세분석" if c["decision"] == "INCLUDE" else "이번제외"
        decide[f"{cid}사유"] = str(c["decision_reason"])

    def qa(rid: str, code: str) -> Step:
        r = meeting[rid]
        return Step(
            code,
            kst(r["event_at"]),  # type: ignore[arg-type]
            _user(r["actor_id"]),
            "record",
            answer={
                "record_type": str(r["record_type"]),
                "subject": str(r["subject"]),
                "content": str(r["content"]),
                "related": str(r["related_ref"]),
            },
            label=f"{rid} {r['subject']}",
        )

    accepts = []
    for t in seed.rows("SC03과제"):
        tid = str(t["task_id"])
        event = next(
            e for e in ev.values() if e["action"] == "과제 인수" and e["object_ref"] == tid
        )
        accepts.append(
            Step(
                "D40",
                at(str(event["event_id"])),
                _user(t["owner_id"]),
                "act",
                f"Accept_{tid}",
                {f"{tid}결정": "인수", f"{tid}사유": ""},
                f"{tid} 인수 — {t['title']}",
                str(event["event_id"]),
            )
        )
    return [
        Step(
            "D31",
            at("EV31-01"),
            domain.FIN,
            "start",
            label="검토 착수 — 두 사건 연결",
            event="EV31-01",
        ),
        Step(
            "D32",
            at("EV31-02"),
            domain.FIN,
            "act",
            "Save_Analysis",
            {"기준확인": "확인", "분석메모": str(basis["RUN-SC03-01"]["설명"])},
            "통합 분석 저장 — 손익 브리지",
            "EV31-02",
        ),
        Step("D33", at("EV31-02"), "u-demo", "view", label="기간·모델·원가 근거 조회"),
        Step(
            "D34",
            at("EV31-03"),
            domain.FIN,
            "act",
            "Request_Confirm",
            {
                "회신기한": domain.SCHEDULE["confirm_due"],
                "요청메모": str(basis["REP31-v0"]["설명"]),
            },
            "영업·구매·생산 확인 요청",
            "EV31-03",
        ),
        Step(
            "D35",
            at("EV31-04"),
            domain.SALES,
            "act",
            "Confirm_Sales",
            reply("영업", "F31", assumption="F32"),
            "영업 회신",
            "EV31-04",
        ),
        Step(
            "D35",
            at("EV31-05"),
            domain.BUY,
            "act",
            "Confirm_Buy",
            reply("구매", "F33", assumption="F34"),
            "구매 회신",
            "EV31-05",
        ),
        Step(
            "D35",
            at("EV31-06"),
            domain.PROD,
            "act",
            "Confirm_Prod",
            reply("생산", "F35", unconfirmed="F36", question="Q31"),
            "생산 회신 — 회피가능 고정비 미확인",
            "EV31-06",
        ),
        Step(
            "D36",
            at("EV31-07"),
            domain.FINLEAD,
            "act",
            "Register_Gap",
            {
                "부족확인결과": "미확인등록",
                "부족내용": s("F37", "statement"),
                "부족근거": s("F37", "evidence_ref"),
                "부족질문": str(q["Q32"]["question"]),
            },
            "기존 부족 쟁점 등록",
            "EV31-07",
        ),
        Step(
            "D36",
            at("EV31-08"),
            domain.CFO,
            "act",
            "Judge_Questions",
            judge,
            "Q31·Q32 비차단 처리",
            "EV31-08",
        ),
        Step(
            "D36",
            at("EV31-09"),
            domain.CFO,
            "act",
            "Freeze_Report",
            {"확정의견": str(basis["REP31-v1"]["설명"])},
            "REP31-v1 확정",
            "EV31-09",
        ),
        Step(
            "D36",
            at("EV31-10"),
            domain.FIN,
            "act",
            "Distribute",
            {"배포메모": "MT31 참석 역할에 내부 배포 — 외부 발송 없음"},
            "회의자료 배포",
            "EV31-10",
        ),
        Step(
            "D37",
            at("EV31-11"),
            domain.FIN,
            "act",
            "Report_Meeting",
            {"보고요지": str(meeting["MT31"]["content"])},
            "MT31 개회 · 통합 영향 보고",
            "EV31-11",
        ),
        qa("QA31", "D37"),
        qa("QA32", "D37"),
        qa("QA33", "D38"),
        qa("QA34", "D38"),
        Step(
            "D38",
            "2027-06-29T10:40:00+09:00",
            domain.FIN,
            "agent",
            answer={"kind": "AG31"},
            label="Agent 회의 요약·과제 초안(AG31)",
        ),
        Step(
            "D38",
            at("EV31-12"),
            domain.CFO,
            "act",
            "Decide_Review",
            decide,
            "조건부 수용 · 후보 4개 포함 · 2개 제외",
            "EV31-12",
        ),
        Step(
            "D39",
            at("EV31-13"),
            domain.CFO,
            "act",
            "Confirm_Minutes",
            {"회의록확인의견": str(meeting["MIN31-v1"]["content"])},
            "MIN31-v1 확인",
            "EV31-13",
        ),
        Step(
            "D39",
            at("EV31-14"),
            domain.CFO,
            "act",
            "Assign_Tasks",
            {"통보메모": "AT31~AT34 배정·내부 통보 — 인수기한 6/30 12시, 제출 7/6 18시"},
            "AT31~AT34 배정·통보",
            "EV31-14",
        ),
        *accepts,
        Step(
            "D41",
            at("EV31-22"),
            domain.FIN,
            "act",
            "Complete_Scene",
            {"완료메모": "통합 영향 검토 완료 · 대응안 분석 책임·기한 확정 — 7/12 MT41 보고"},
            "수익성 통합 분석 완료 · MT41 연결",
            "EV31-22",
        ),
    ]


def _after(steps: list[Step], pick, extra: list[Step]) -> list[Step]:
    i = max(i for i, s in enumerate(steps) if pick(s))
    return [*steps[: i + 1], *extra, *steps[i + 1 :]]


def steps_for(case_id: str, seed: Seed | None = None) -> list[Step]:
    seed = seed or load_seed()
    steps = base_steps(seed)
    if case_id == "E31":
        # 구매가 복제 초안의 적용월 오류에 이견 → 경영관리 보완(새 버전) → 구매 재확인. 승인 원천은
        # 그대로.
        buy = next(s for s in steps if s.node_id == "Confirm_Buy")
        dispute = replace(
            buy,
            code="E31",
            label="구매 이견 — 적용월 표기 오류",
            answer={
                **buy.answer,
                "구매회신": "이견",
                "구매사실": (
                    "초안의 승인단가 적용월이 8/1로 적혀 있다 — 승인 기록 PV-APP01은 7/1 적용"
                ),
                "구매가정": "",
                "구매의견": "적용월을 승인 원천대로 정정한 뒤 재확인을 요청한다",
                "구매근거": "PV-APP01 / RUN-APP01",
            },
        )
        fix = Step(
            "E31",
            "2027-06-25T16:00:00+09:00",
            domain.FIN,
            "act",
            "Revise_Buy",
            {"구매보완내용": "적용월 7/1로 정정 — 승인 원천 PV-APP01 그대로, 수치 변경 없음"},
            "초안 보완 — 새 버전",
        )
        again = replace(buy, code="E31", at="2027-06-25T17:00:00+09:00", label="구매 재확인")
        i = steps.index(buy)
        return [*steps[:i], dispute, fix, again, *steps[i + 1 :]]
    if case_id == "E32":
        # AT31 책임자가 의존관계 누락으로 반려 → 임원이 Q31·구매 협조를 보완해 재배정 → 새 버전
        # 재인수
        returned = Step(
            "E32",
            "2027-06-29T16:00:00+09:00",
            domain.PROD,
            "act",
            "Accept_AT31",
            {
                "AT31결정": "반려",
                "AT31사유": "자료 의존관계 누락 — 구매 외주비 자료·Q31 연결이 과제에 없다",
            },
            "AT31 반려",
        )
        fixed = Step(
            "E32",
            "2027-06-29T17:00:00+09:00",
            domain.CFO,
            "act",
            "Reassign_AT31",
            {
                "AT31변경사유": "Q31·구매 협조 보완",
                "AT31의존관계": "Q31 · AT32 외주비 자료(구매 협조)",
                "AT31협조추가": "",
                "AT31산출물": "",
                "AT31변경담당자": "",
            },
            "AT31 보완 재배정 — 배정버전 2",
        )
        steps = _after(steps, lambda s: s.node_id == "Assign_Tasks", [returned, fixed])
        return [
            replace(s, label="AT31 새 배정버전 재인수")
            if s.node_id == "Accept_AT31" and s.code == "D40"
            else s
            for s in steps
        ]
    if case_id == "E33":
        fix = Step(
            "E33",
            "2027-06-24T15:30:00+09:00",
            domain.FIN,
            "act",
            "Fix_Calc",
            {"정정내용": "고정비 중복 입력(계수 2) 정정 — FC01 월 370,000,000원을 공장 합계에 1회"},
            "계산 정정 · 재검증",
        )
        return _after(steps, lambda s: s.node_id == "Save_Analysis", [fix])
    if case_id == "E34":
        new = Step(
            "E34",
            "2027-06-29T09:30:00+09:00",
            domain.FIN,
            "revision",
            answer={"reason": "b모델 7월 고객 추가 감소 신호 — 8,800 → 8,700 (검수용 변형)"},
            label="자료 확정 뒤 새 전망 버전",
        )
        return _after(steps, lambda s: s.node_id == "Distribute", [new])
    if case_id == "E37":
        return [
            *steps,
            Step(
                "E37",
                "2027-07-06T18:01:00+09:00",
                "u-demo",
                "clock",
                label="7/6 18:01 — 제출기한 경과 조회",
            ),
        ]
    return steps


def run_step(process: Sc03Process, demo_run_id: str, index: int) -> dict:
    """각본의 `index`번째 단계. 이미 지나간 단계면 현재 문서를 돌려준다(장면 1·2와 같다)."""
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
    if step.kind == "clock":
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
    if step.kind == "revision":
        return _after_record(
            process,
            center,
            lambda: process.revise_forecast(
                demo_run_id, reason=step.answer["reason"], actor=step.actor, **mark
            ),
        )
    node_id = step.node_id or ""
    # 화면이 보는 버전은 시도마다 다시 읽는다 — 배정 기록이 들어오기 전에 읽으면
    # 버전 0을 싣는다(실측).
    return _after_record(
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


def _after_record(process: Sc03Process, center: bool, run: Callable[[], dict]) -> dict:
    """Center 실행이면 앞 결재의 기록 작업을 기다린다(`app.script_wait`, 실측)."""
    return after_record(process.center_wait_s, center, run, gated=(domain.PrerequisiteError,))


def _expect(doc: dict, node_id: str) -> dict[str, Any] | None:
    """화면이 보는 것과 같은 버전을 싣는다 — 확정은 최신 초안, 결론은 확정본, 인수는 배정버전."""
    if node_id == "Freeze_Report":
        d = domain.current_draft(doc)
        return None if d is None else {"report": d["report_id"]}
    if node_id == "Decide_Review":
        f = domain.frozen_report(doc)
        return None if f is None else {"report": f["report_id"]}
    spec = domain.NODE_ROLES.get(node_id, {})
    if "owner_of" in spec:
        a = doc["assignments"].get(spec["owner_of"])
        return None if a is None else {"assignment": a["assignment_version"]}
    return None
