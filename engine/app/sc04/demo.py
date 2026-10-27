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

from dataclasses import dataclass, field, replace
from typing import Any

from app.sc01.domain import USERS, DomainError, parse_at
from app.sc04 import domain
from app.sc04.process import Sc04Process
from app.sc04.seed import Seed, kst, load_seed


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


def _user(account: Any) -> str:
    return domain.ACCOUNTS[str(account).strip()]


def _name(account: Any) -> str:
    return USERS[_user(account)]["name"]


def _names(accounts: Any) -> str:
    return ";".join(_name(a) for a in str(accounts or "").split(";") if a.strip())


def base_steps(seed: Seed) -> list[Step]:
    ev = seed.by_id("SC04이벤트")
    res = seed.by_id("SC04분석결과")
    evd = seed.by_id("SC04근거")
    cmp = seed.by_id("SC04비교")
    meet = seed.by_id("SC04회의")
    cond = seed.by_id("SC04조건지시")
    budget = seed.by_id("SC04예산과제")
    asm = seed.by_id("SC04가정")

    def at(event_id: str) -> str:
        return kst(ev[event_id]["event_at_KST"])  # type: ignore[return-value]

    def submit(tid: str, rid: str, event: str) -> list[Step]:
        r = res[rid]
        refs = str(r["근거"])
        first = evd[refs.split(";")[0]]
        excluded = tid == "AT33"
        spec = domain.RESULTS[tid]
        return [
            Step(
                "D402",
                at(event),
                spec["writer"],
                "act",
                f"Submit_{tid}",
                {
                    f"{tid}결과": "제외" if excluded else "제출",
                    f"{tid}결론": str(r["결론"]),
                    f"{tid}근거": refs,
                    f"{tid}애로": "" if excluded else str(first["해석·제약"]),
                    f"{tid}제외사유": f"{first['가상 근거·내역']} {first['해석·제약']}"
                    if excluded
                    else "",
                },
                f"{rid} 제출 — {r['보고대상']}",
            ),
            Step(
                "D402",
                at(event),
                spec["confirmer"],
                "act",
                f"Confirm_{tid}",
                {f"{tid}확인": "확인", f"{tid}확인의견": str(r["쟁점처리"])},
                f"{rid} 임원 확인",
                event,
            ),
        ]

    rec: dict[str, Any] = {
        "EXCL44제외사유": str(cmp["EXCL44"]["시점·리스크·조건"]),
        "현업임원확인": "확인",
    }
    for alt in domain.ALTS:
        c = cmp[alt]
        rec[f"추천{alt}"] = "추천"
        rec[f"{alt}우선순위"] = str(c["우선순위"])
        rec[f"{alt}사유"] = str(c["시점·리스크·조건"])

    def qa(rid: str, code: str, record_type: str) -> Step:
        r = meet[rid]
        return Step(
            code,
            kst(r["시각_KST"]),  # type: ignore[arg-type]
            _user(r["발언·결정자"]),
            "record",
            answer={
                "record_type": record_type,
                "subject": str(r["유형"]),
                "content": str(r["본문"]),
                "related": str(r["관련대상"]),
            },
            label=f"{rid} {r['유형']}",
        )

    c41, s41, d41 = cond["CON41"], cond["SUP41"], cond["DIR41"]
    draft_decision = {
        "변경대안": "ALT42",
        "변경항목": "효과 시작",
        "변경값": asm["ALT42"]["판단 시작"].date().isoformat(),
        "변경사유": str(meet["QA414"]["본문"]),
        "변경확인임원": _name("EX-BUY"),
        "조건내용": str(c41["내용"]),
        "조건책임": _name(c41["책임"]),
        "조건협조": _names(c41["협조"]),
        "조건확인자": _name(c41["충족확인자"]),
        "조건기한": kst(c41["기한_KST"]),
        "지원내용": str(s41["내용"]),
        "지원책임": _name(s41["책임"]),
        "지원협조": _names(s41["협조"]),
        "지원확인자": _name(s41["충족확인자"]),
        "지원기한": kst(s41["기한_KST"]),
    }
    outcome = {
        "APPROVED": "승인",
        "CONDITIONAL": "조건부승인",
        "HOLD": "보류",
        "REJECTED": "미승인",
    }
    decide: dict[str, Any] = {
        "조건연결": "CON41",
        "발굴지시": str(d41["내용"]),
        "발굴책임자": _name(d41["책임"]),
        "발굴협조": _names(d41["협조"]),
        "발굴기한": kst(d41["기한_KST"]),
    }
    for alt in domain.ALTS:
        decide[f"{alt}결정"] = outcome[str(cmp[alt]["대표결정"])]
        decide[f"{alt}결정사유"] = str(cmp[alt]["시점·리스크·조건"])
    tot = budget["TOTAL"]
    approval: dict[str, Any] = {
        "전체책임자": _name(tot["책임임원"]),
        "총괄한도": str(tot["승인한도"]),
        "계획제출기한": kst(budget["ACT41"]["계획제출_KST"]),
        "위임조항": str(meet["POL41"]["본문"]),
        "회의록초안": str(meet["MIN41-v1"]["본문"]),
    }
    for act in ("ACT41", "ACT42", "ACT43"):
        approval[f"{act}한도"] = str(budget[act]["승인한도"])
        approval[f"{act}완료기한"] = kst(budget[act]["과제완료_KST"])

    def acc(target: str, node: str, event: str, actor: str) -> Step:
        return Step(
            "D412",
            at(event),
            actor,
            "act",
            node,
            {f"{target}결정": "인수", f"{target}사유": ""},
            f"{target} 인수",
            event,
        )

    return [
        Step(
            "D401",
            at("EV41-01"),
            domain.FIN,
            "start",
            label="개선안 검토·실행 승인 착수 — HANDOFF31·AT31~34 연결",
            event="EV41-01",
        ),
        *submit("AT31", "RES41", "EV41-02"),
        *submit("AT32", "RES42", "EV41-03"),
        *submit("AT33", "RES43", "EV41-04"),
        *submit("AT34", "RES44", "EV41-05"),
        Step(
            "D403",
            "2027-07-07T14:00:00+09:00",
            "u-demo",
            "view",
            label="외주 조정 비용 상세 — 잔존 고정비·회피 비용",
        ),
        Step(
            "D404",
            at("EV41-06"),
            domain.FIN,
            "act",
            "Verify_Effects",
            {"검증기준": "확인", "검증메모": str(evd["EVDC44"]["해석·제약"])},
            "비용·중복 검증",
            "EV41-06",
        ),
        Step(
            "D405",
            at("EV41-07"),
            domain.CFO,
            "act",
            "Recommend",
            rec,
            "우선 실행안 3개 공동 제안",
            "EV41-07",
        ),
        Step(
            "D406",
            at("EV41-08"),
            domain.CFO,
            "act",
            "Freeze_Report",
            {
                "보고결론": "3개 실행안을 우선 추진하되 생산·구매 협조와 일회성 준비 예산이 "
                "필요하다 — "
                "실행 뒤에도 목표 미달 가능성이 남아 추가 과제 발굴이 필요하다",
                "배포메모": "MT41 참석 역할에 내부 배포 — 외부 발송 없음",
            },
            "REP41-v1 확정·배포",
            "EV41-08",
        ),
        Step(
            "D406",
            at("EV41-09"),
            domain.CFO,
            "act",
            "Report_Meeting",
            {"보고요지": str(meet["MT41"]["본문"])},
            "MT41 보고",
            "EV41-09",
        ),
        Step(
            "D406",
            "2027-07-12T10:05:00+09:00",
            domain.FIN,
            "agent",
            answer={"kind": "AG42"},
            label="Agent 질의 후보(AG42)",
        ),
        qa("QA411", "D407", "QUESTION"),
        qa("QA412", "D408", "ANSWER"),
        qa("QA413", "D408", "ANSWER"),
        qa("QA414", "D409", "DIRECTIVE"),
        Step(
            "D409",
            "2027-07-12T10:30:00+09:00",
            domain.FIN,
            "act",
            "Draft_Decision",
            draft_decision,
            "판단 초안 — ALT42 효과 9월 시작 · CON41 · SUP41",
        ),
        Step(
            "D409",
            at("EV41-14"),
            domain.CFO,
            "act",
            "Confirm_Decision",
            {"판단확인": "확인", "판단확인의견": str(meet["CONF41"]["본문"])},
            "DEC41-v2 확인",
            "EV41-14",
        ),
        Step(
            "D410",
            at("EV41-15"),
            domain.CEO,
            "act",
            "Decide",
            decide,
            "REV41 — 승인 2 · 조건부 1",
            "EV41-15",
        ),
        Step(
            "D410",
            "2027-07-12T14:00:00+09:00",
            domain.FIN,
            "agent",
            answer={"kind": "AG43"},
            label="Agent 회의록·승인서 초안(AG43)",
        ),
        Step(
            "D410",
            "2027-07-12T14:30:00+09:00",
            domain.FIN,
            "act",
            "Draft_Approval",
            approval,
            "승인서·회의록 초안",
        ),
        Step(
            "D411",
            at("EV41-16"),
            domain.CEO,
            "act",
            "Finalize_Approval",
            {"승인결정": "확정", "승인의견": str(meet["APR41-v1"]["본문"])},
            "APR41-v1 · MIN41-v1 확정",
            "EV41-16",
        ),
        Step(
            "D411",
            "2027-07-12T15:05:00+09:00",
            "u-demo",
            "view",
            label="위임 조항 — 전용·총괄 초과 규칙 조회(E407)",
        ),
        Step(
            "D412",
            at("EV41-17"),
            domain.FIN,
            "act",
            "Register_Actions",
            {
                "등록확인": "등록",
                "등록메모": "ACT41~43 · CON41 · SUP41 · DIR41 등록 — 상세 계획은 결정 실행·계획 "
                            "갱신",
            },
            "실행과제·조건·지시 등록",
            "EV41-17",
        ),
        acc("ACT41", "Accept_ACT41", "EV41-18", domain.PROD_EXEC),
        acc("SUP41", "Accept_SUP41", "EV41-19", domain.PROD_EXEC),
        acc("ACT42", "Accept_ACT42", "EV41-20", domain.BUY_EXEC),
        acc("ACT43", "Accept_ACT43", "EV41-21", domain.BUY_EXEC),
        acc("TOTAL", "Accept_Overall", "EV41-22", domain.CFO),
        Step(
            "D413",
            at("EV41-23"),
            domain.FIN,
            "act",
            "Complete_Scene",
            {
                "완료메모": "승인·인수 완료 — 결정 실행·계획 갱신 상세 실행계획 대기. CON41 "
                            "미충족·위험 미해소 "
                "유지"
            },
            "개선안 검토·실행 승인 완료 · HANDOFF41",
            "EV41-23",
        ),
    ]


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
    if step.kind == "record":
        return process.meeting_record(demo_run_id, actor=step.actor, **step.answer, **mark)
    if step.kind == "agent":
        return process.agent(demo_run_id, step.answer["kind"], actor=step.actor, **mark)
    expect = _expect(process.get(demo_run_id), step.node_id or "")
    return process.act(
        demo_run_id, step.node_id or "", dict(step.answer), actor=step.actor, expect=expect, **mark
    )


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
