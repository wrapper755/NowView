"""
SC02 기본 시연 각본 — D00 → D01~D12 (통합 가상 데이터 「업무이력」 시트), 그리고 X 사례의 변형.

SC01 각본(`app/sc01/demo.py`)과 같다: **단계 진행은 실제 상태 전환을 실행한다.** 각본은 누가·언제·
무엇을 했나만 들고, 실행은 사람이 버튼을 누른 것과 같은 길(`Sc02Process.receive`·`act`)이다.

**단가·기한은 시드에서 읽는다**(설정 시트의 내부제시가·협상가·기안가·협상기한) — 각본에 숫자를 옮겨
적지 않는다. X 사례는 그 값을 바꿔 같은 길을 탄다(ERR-21: 별도 데모 실행).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from app.sc01.domain import DomainError, parse_at
from app.sc02.process import Sc02Process
from app.sc02.seed import Seed, load_seed


@dataclass(frozen=True)
class Step:
    code: str
    at: str  # KST 가상시각
    actor: str
    node_id: str | None  # None이면 요청 접수
    answer: dict[str, Any] = field(default_factory=dict)
    label: str = ""
    expect_proposal: bool = False


def _iso(value: Any) -> str:
    # 설정 시트의 「2027-06-21 18:00:00 KST」 → ISO8601 +09:00
    text = str(value).replace(" KST", "").strip()
    return parse_at(text.replace(" ", "T")).isoformat()


def base_steps(seed: Seed) -> list[Step]:
    s = seed.settings
    eff = seed.setting_date("effective_date").isoformat()
    approve = {"결정": "승인"}
    return [
        Step(
            "D01",
            "2027-06-17T09:00:00+09:00",
            "u-buy",
            None,
            {"fixture_id": "REQ-2706-01"},
            "단가 인상 요청 접수",
        ),
        Step(
            "D01",
            "2027-06-17T09:20:00+09:00",
            "u-buy",
            "Verify_Request",
            {
                "확인결과": "확인완료",
                "확인의견": "공문 원본과 대조 — 공급사·품목·기존가 2,000원·요청가 2,200원·"
                "7/1 적용·VAT 별도 일치",
            },
            "공문 원문 대조 확인",
        ),
        Step(
            "D02",
            "2027-06-17T10:00:00+09:00",
            "u-buy",
            "Report_Lead",
            {
                "참여자": "구매담당 윤채원 · 구매팀장 서도현",
                "요청요약": "SUP-01 P-COM01 2,000→2,200원(10%), 7/1 적용 희망",
                "검토필요성": "검토진행",
                "협상방향": "사전 손익분석 후 1차 협상",
                "보고결론": seed.evidence["NOTE-REPORT01"]["내용"],
            },
            "팀장 구두보고 기록",
        ),
        Step(
            "D03",
            "2027-06-18T11:00:00+09:00",
            "u-buy",
            "Confirm_Analysis",
            {
                "내부제시단가": int(s["internal_offer"]),
                "협상기한": _iso(s["negotiation_due"]),
                "분석메모": "요청안·내부 제시안 동일 F02·C01 기준",
            },
            "요청안 영향분석",
        ),
        Step(
            "D04",
            "2027-06-21T15:00:00+09:00",
            "u-buy",
            "Record_Negotiation",
            {
                "협상결과": "잠정합의",
                "협상단가": int(s["negotiated_price"]),
                "협상적용일": eff,
                "협상참석자": "구매담당 윤채원 · SUP-01 영업담당",
                "미합의사항": seed.evidence["NOTE-NEG01"]["내용"],
            },
            "1차 협상 결과 입력",
        ),
        Step(
            "D05",
            "2027-06-22T10:00:00+09:00",
            "u-buy",
            "Confirm_Reanalysis",
            {"재분석메모": "협상안 vs 요청안 같은 12개월"},
            "협상안 재분석",
        ),
        Step(
            "D06",
            "2027-06-22T11:00:00+09:00",
            "u-buy",
            "Draft_Proposal",
            {
                "기안단가": int(s["proposal_price"]),
                "기안적용일": eff,
                "인상필요성": seed.evidence["DOC-PROP01"]["내용"],
                "차이사유": "",
            },
            "기안 상신",
        ),
        Step(
            "D07",
            "2027-06-22T14:00:00+09:00",
            "u-buy-lead",
            "Approve_Lead",
            {**approve, "결재의견": seed.evidence["APP-T01"]["내용"]},
            "구매팀장 승인",
            expect_proposal=True,
        ),
        Step(
            "D08",
            "2027-06-23T10:00:00+09:00",
            "u-buy-exec",
            "Approve_Exec",
            {**approve, "결재의견": seed.evidence["APP-E01"]["내용"]},
            "구매임원 승인·대표 판정",
            expect_proposal=True,
        ),
        Step(
            "D09",
            "2027-06-23T14:00:00+09:00",
            "u-ceo",
            "Approve_CEO",
            {**approve, "결재의견": seed.evidence["APP-C01"]["내용"]},
            "대표이사 승인",
            expect_proposal=True,
        ),
        Step(
            "D10",
            "2027-06-23T15:00:00+09:00",
            "u-buy",
            "Register_Cost",
            {"대조결과": "일치", "등록메모": "7/1 적용예정 · C01 보존"},
            "원가 등록",
        ),
        Step(
            "D11",
            "2027-06-23T16:00:00+09:00",
            "u-buy",
            "Request_Handoff",
            {"경영관리담당자": "u-fin", "인계메모": "물량·원가 별도 사건으로 MR-2706-01에 연결"},
            "통합 영향 확인 · 인계 요청",
        ),
        Step(
            "D12",
            "2027-06-24T10:00:00+09:00",
            "u-fin",
            "Accept_Handoff",
            {"인수의견": "장면 3에서 통합 손익과 대응 필요성 검토 착수"},
            "경영관리 인수",
        ),
    ]


def _answer(steps: list[Step], node: str, **change: Any) -> list[Step]:
    return [replace(s, answer={**s.answer, **change}) if s.node_id == node else s for s in steps]


def _until(steps: list[Step], code: str) -> list[Step]:
    """그 단계 코드까지 — 예외 사례는 거기서 끝난다."""
    last = max(i for i, s in enumerate(steps) if s.code == code)
    return steps[: last + 1]


def steps_for(case_id: str, seed: Seed | None = None) -> list[Step]:
    seed = seed or load_seed()
    steps = base_steps(seed)
    if case_id == "X01":
        # D08 기본 승인 대신 추가 협상지시 — 승인 완료로 남지 않는다(ERR-21). 원문은 INSTR-RENEG01.
        steps = _answer(
            _until(steps, "D08"),
            "Approve_Exec",
            결정="추가협상지시",
            결재의견=seed.evidence["INSTR-RENEG01"]["내용"],
            지시요구조건="대체 공급처 견적과 인상 사유 증빙 확보",
            지시기한="2027-06-25T18:00:00+09:00",
        )
        return [
            replace(s, code="X01", label="추가 협상지시") if s.node_id == "Approve_Exec" else s
            for s in steps
        ]
    if case_id == "X02":
        # 협상·기안 2,050원 — 12개월 증가 7,840,600원, 대표 비대상(임원 최종 승인)
        steps = _answer(steps, "Record_Negotiation", 협상단가=2050)
        steps = _answer(steps, "Draft_Proposal", 기안단가=2050)
        return [s for s in steps if s.node_id != "Approve_CEO"]
    if case_id == "X04":
        steps = _answer(steps, "Record_Negotiation", 협상적용일="2027-08-01")
        return _answer(steps, "Draft_Proposal", 기안적용일="2027-08-01")
    if case_id == "X05":
        return _answer(
            steps,
            "Draft_Proposal",
            기안단가=2130,
            차이사유="공급사 회신 지연분 반영 — 협상가와 다르다",
        )
    if case_id == "X06":
        steps = _answer(
            _until(steps, "D04"),
            "Record_Negotiation",
            협상결과="미합의",
            협상단가=None,
            미합의사항="공급사가 2,200원 유지 — 팀장 협의 필요",
        )
        return steps
    if case_id == "X07J":
        return _answer(
            _until(steps, "D07"), "Approve_Lead", 결정="반려", 결재의견="인상 사유 증빙 부족 — 반려"
        )
    if case_id == "X07R":
        # 팀장 보완 → 같은 조건으로 재상신(PROP01-v2) → 팀장부터 다시. 이전 승인은 승계하지 않는다.
        head = _until(steps, "D07")
        head = _answer(head, "Approve_Lead", 결정="보완", 결재의견="물량 가정 근거를 첨부해 재상신")
        draft = next(s for s in steps if s.node_id == "Draft_Proposal")
        lead = next(s for s in steps if s.node_id == "Approve_Lead")
        tail = [s for s in steps if s.code in ("D08", "D09", "D10", "D11", "D12")]
        return [
            *head,
            replace(
                draft,
                code="X07",
                at="2027-06-22T16:00:00+09:00",
                label="보완 재상신",
                answer={
                    **draft.answer,
                    "인상필요성": draft.answer["인상필요성"] + " (물량 가정 근거 첨부)",
                },
            ),
            replace(lead, code="X07", at="2027-06-22T17:00:00+09:00", label="재상신 팀장 승인"),
            *tail,
        ]
    if case_id in ("X09A", "X10"):
        # 12개월 물량 누락·중복 — 분석은 미산출로 남는다. 각본은 재분석에서 멈춘다: 상신은 409로
        # 막히므로(T33) 화면에서 기안을 눌러 거절 사유를 본다.
        return _until(steps, "D05")
    return steps


def run_step(process: Sc02Process, demo_run_id: str, index: int) -> dict:
    """각본의 `index`번째 단계. 이미 지나간 단계면 현재 문서를 돌려준다(SC01과 같다)."""
    doc = process.get(demo_run_id)
    if (doc["bpm"] or {}).get("executor") == "studio":
        # Studio 시험 실행의 결재는 Studio 대화상자만 받는다. Center는 각본이 대리 답한다.
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
    if step.node_id is None:
        return process.receive(
            demo_run_id,
            step.answer["fixture_id"],
            actor=step.actor,
            event_code=step.code,
            script_index=index,
        )
    expect = None
    if step.expect_proposal:
        current = process.get(demo_run_id)["proposals"]
        key = max(current.values(), key=lambda p: p["seq"])["proposal_key"] if current else None
        expect = {"proposal": key}
    answer = {k: v for k, v in step.answer.items() if v is not None and v != ""}
    return process.act(
        demo_run_id,
        step.node_id,
        answer,
        actor=step.actor,
        expect=expect,
        event_code=step.code,
        script_index=index,
    )
