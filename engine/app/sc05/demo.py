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

import re
from dataclasses import dataclass, field, replace
from datetime import date
from typing import Any

from app.sc01.domain import USERS, DomainError, parse_at
from app.sc04.seed import load_seed as load_sc04_seed
from app.sc05 import domain
from app.sc05.process import Sc05Process
from app.sc05.seed import Seed, kst, load_seed


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


def _user(account: Any) -> str:
    return domain.ACCOUNTS[str(account).strip()]


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


def _window_start(seed: Seed, plan_ref: str) -> str:
    """원문에서 납품이 앞당겨진(늘어난) 첫 구간의 시작일 — 필요일이다."""
    starts = (date(2027, 9, 1), date(2027, 9, 8), date(2027, 9, 15), date(2027, 9, 22))
    for line in domain.customer_plan(seed, plan_ref):
        for i, (b, a) in enumerate(zip(line["before"], line["after"], strict=True)):
            if a > b:
                return starts[i].isoformat()
    raise ValueError(f"{plan_ref}: 앞당겨진 구간이 없다")


def _md(text: str, word: str) -> str:
    m = re.search(rf"{word}\s*(\d+)/(\d+)", text)
    if m is None:
        raise ValueError(f"{word} 날짜가 없다: {text}")
    return date(2027, int(m.group(1)), int(m.group(2))).isoformat()


def base_steps(seed: Seed) -> list[Step]:
    ev = seed.by_id("SC05이벤트")
    ag = seed.by_id("SC05Agent")
    plans = seed.by_id("SC05계획")
    changes = seed.by_id("SC05변경공유")
    orders = seed.by_id("SC05구매표본")
    opl = seed.by_id("SC05운영계획")
    docs = seed.by_id("SC05근거")
    s4 = load_sc04_seed().by_id("SC04가정")

    def at(event_id: str) -> str:
        return kst(ev[event_id]["발생_KST"])  # type: ignore[return-value]

    def agent(run: str, code: str, requester: str) -> Step:
        return Step(
            code,
            kst(ag[run]["실행_KST"]),
            requester,
            "agent",
            answer={"kind": run},  # type: ignore[arg-type]
            label=f"Agent {run} — {ag[run]['Agent가 수행한 일']}",
        )

    def review(run: str, code: str) -> Step:
        r = ag[run]
        return Step(
            code,
            kst(r["확인_KST"]),
            _user(r["사람확인자"]),
            "review",
            answer={"kind": run, "note": str(r["담당자 수정·판단"])},  # type: ignore[arg-type]
            label=f"{run} 제안 검토",
        )

    def act(
        code: str, event: str, node: str, answer: dict[str, Any], label: str, at_: str | None = None
    ) -> Step:
        return Step(
            code, at_ or at(event), _user(ev[event]["actor"]), "act", node, answer, label, event
        )

    replay = {
        "AG51": domain.replay_activities(seed, "PL51-v1"),
        "AG52": domain.replay_activities(seed, "PL51-v2"),
    }
    v2 = plans["PL51-v2"]
    budget = str(v2["승인예산"])
    ch51, ch52 = changes["CH51"], changes["CH52"]
    po1, po10 = orders[str(ch51["대표주문"])], orders[str(ch52["대표주문"])]
    o51, o52, o53 = opl["OPL51"], opl["OPL52"], opl["OPL53"]
    settings = {
        k: seed.setting(k)
        for k in ("oct_urgent_forecast", "nov_urgent_forecast", "dec_urgent_forecast")
    }
    recon = [
        r
        for r in seed.rows("SC05변경대사")
        if r["원인"] not in ("종전 공식 FC50", "변경후 전망", "RUN51 대사차이")
    ]
    followups = "\n".join(
        " | ".join(
            [
                str(r["id"]),
                str(r["대상"]),
                _name(_user(r["담당"])),
                kst(r["후속기한_KST"]) or "",
                str(r["종료기준·남는사항"]),
            ]
        )
        for r in seed.rows("SC05인계")
        if r["id"] != domain.HANDOFF_ID
    )

    def respond(change: dict[str, Any], order: dict[str, Any], urgent: bool, event: str) -> Step:
        note = str(change["협의·판단"])
        return act(
            "D511" if not urgent else "D512",
            event,
            "Respond_Change",
            {
                "대응결정": "긴급기안" if urgent else "정상대응",
                "재고": "0" if urgent else re.search(r"재고\s*(\d+)", note).group(1),  # type: ignore[union-attr]
                "기발주": "0" if urgent else re.search(r"기발주\s*(\d+)", note).group(1),  # type: ignore[union-attr]
                "필요일": _md(note, "필요")
                if urgent
                else _window_start(seed, str(change["plan_ref"])),
                "정상조달일": _md(note, "정상조달") if urgent else "",
                "주문번호": str(order["order_id"]),
                "주문수량": str(order["수량"]),
                "긴급운송비": str(order["긴급운송비"]) if urgent else "",
                "할증": str(order["할증"]) if urgent else "",
                "판단근거": note,
            },
            ("긴급 기안 — " if urgent else "정상 대응 — ") + note,
        )

    def opl_confirm(pid: str, event: str, answer: dict[str, Any], label: str) -> Step:
        return act("D514", event, f"Confirm_{pid}", answer, label)

    def opl_verify(pid: str, row: dict[str, Any], last: bool) -> Step:
        return Step(
            "D514",
            kst(row["경영관리확인_KST"]),
            domain.CFO,
            "act",
            f"Verify_{pid}",  # type: ignore[arg-type]
            {
                f"{pid}관리확인": "확인",
                f"{pid}관리의견": "부서 가정·마감 경계·효과 중복 정합성 확인",
            },
            f"{pid} 경영관리 확인",
            "EV51-41" if last else None,
        )

    return [
        Step(
            "D501",
            at("EV51-01"),
            domain.FIN,
            "start",
            label="결정 실행·계획 갱신 착수 — HANDOFF41·APR41-v1·ACT41~43 연결",
            event="EV51-01",
        ),
        agent("AG51", "D502", domain.BUY_LEAD),
        act(
            "D502",
            "EV51-03",
            "Draft_Plan",
            {
                "계획활동": activity_lines(replay["AG51"]),
                "효과확인기준": EFFECT_RULE,
                "계획초안출처": "@AG51",
                "계획작성메모": str(ag["AG51"]["담당자 수정·판단"]),
            },
            "상세 계획 초안 PL51-v1 — Agent 초안을 담당자가 수정",
        ),
        act(
            "D503",
            "EV51-04",
            "Coordinate_Plan",
            {
                "협조결정": "확인",
                "협의내용": "정례 협의만으로는 회의 이후 생산계획 변경을 구매가 늦게 알 수 있다 — "
                "수시 "
                "공유의 기본 방향과 생산 "
                "협조 창구를 정한다. 모든 변경을 긴급 대응하지 않고 납기 영향 예외만 구분한다",
                "협조창구": _name(domain.PROD_LEAD),
                "협조근거": "",
            },
            "생산 협조 확인 — 수시 공유 기본 방향",
        ),
        act(
            "D504",
            "EV51-05",
            "Confirm_Plan",
            {
                "확정결정": "확정",
                "범위영향": f"예산 {int(budget):,}원·효과 개시 2027-09·과제 기한 9/30 18:00 유지 — "
                "승인 범위 안",
                "확정의견": str(plans["PL51-v1"]["변경사유"]),
            },
            "PL51-v1 구매 임원 확정",
        ),
        act(
            "D504",
            "EV51-06",
            "Verify_Plan",
            {
                "관리확인": "확인",
                "관리의견": "승인 조건·예산·손익 가정 정합 — 조건 충족 전이라 착수 대기",
            },
            "PL51-v1 경영관리 확인 — 착수 대기",
        ),
        Step(
            "D504",
            "2027-07-16T16:05:00+09:00",
            "u-demo",
            "view",
            label="착수 요건 — 계획 확정·확인 완료, CON41·SUP41·품의 대기",
        ),
        agent("AG52", "D505", domain.BUY_LEAD),
        act(
            "D505",
            "EV51-10",
            "Request_Change",
            {
                "변경여부": "변경요청",
                "변경활동": activity_lines(replay["AG52"]),
                "변경사유": str(v2["변경사유"]),
                "변경영향": f"예산 {int(budget):,}원·효과 개시 2027-09·최종 기한 9/30 유지 — 대표 "
                "재승인 대상 아님",
                "변경예산": budget,
                "변경개시": v2["효과개시"].date().isoformat(),
                "변경기한": kst(v2["과제기한"]),
                "변경초안출처": "@AG52",
            },
            "준비 중 계획 변경 요청 — 대행·수시 확인, 교육 8/18→8/19",
        ),
        act(
            "D506",
            "EV51-11",
            "Coordinate_Change",
            {
                "변경협조결정": "확인",
                "변경협의내용": "부재 시 구매 대행·정례회의 이후 수시 공유 경로와 교육일 8/19를 "
                "생산이 수용",
                "변경협조창구": _name(domain.PROD_LEAD),
                "변경협조근거": "",
            },
            "변경 생산 협조 확인",
        ),
        act(
            "D506",
            "EV51-12",
            "Confirm_Change",
            {
                "변경확정결정": "확정",
                "변경범위영향": "예산·효과 개시·최종 기한 유지 — 승인 범위 안",
                "변경확정의견": "범위 내 변경 확정",
            },
            "PL51-v2 범위 내 변경 확정 — 대표 재승인 없음",
        ),
        act(
            "D506",
            "EV51-13",
            "Verify_Change",
            {"변경관리확인": "확인", "변경관리의견": "예산·손익 가정 변동 없음 — 유효 계획 교체"},
            "PL51-v2 경영관리 확인 — 유효 계획 교체",
        ),
        act(
            "D507",
            "EV51-14",
            "Evidence_CON41",
            {"CON41근거": "DOC51;DOC53-P", "CON41준비내용": str(docs["DOC51"]["가상 증빙 본문"])},
            "CON41 공동 기준 근거 등록",
        ),
        Step(
            "D507",
            kst(seed.by_id("SC05조건품의")["SUP41"]["상신·이행_KST"]),
            domain.PROD_EXEC,
            "act",
            "Register_SUP41",  # type: ignore[arg-type]
            {"SUP41근거": "DOC52", "SUP41이행내용": str(docs["DOC52"]["가상 증빙 본문"])},
            "SUP41 생산 지원 이행 등록",
        ),
        act(
            "D507",
            "EV51-15",
            "Ready_CON41",
            {
                "CON41준비확인": "확인",
                "CON41준비의견": "생산 창구·구매 대행 지정과 수시 공유 준비 확인",
                "CON41생산근거": "DOC52",
            },
            "CON41 양 부서 준비 확인",
        ),
        agent("AG53", "D507", domain.BUY_EXEC),
        review("AG53", "D507"),
        act(
            "D507",
            "EV51-16",
            "Confirm_CON41",
            {"CON41충족": "충족", "CON41충족의견": "공동 기준·창구·대행·교육 준비 확인"},
            "CON41 충족 확인",
        ),
        act(
            "D507",
            "EV51-17",
            "Verify_SUP41",
            {"SUP41확인": "확인", "SUP41확인의견": "생산 창구 지정·대행 배정 이행 확인"},
            "SUP41 이행 확인",
        ),
        act(
            "D508",
            "EV51-18",
            "Submit_REQ51",
            {
                "REQ51요청액": str(seed.by_id("SC05조건품의")["REQ51"]["금액"]),
                "REQ51사유": str(seed.by_id("SC05조건품의")["REQ51"]["범위"]) + " — 외부 운영 검증",
                "REQ51근거": "DOC53-P",
            },
            "REQ51 일회성 검증비 상신",
        ),
        Step(
            "D508",
            kst(seed.by_id("SC05조건품의")["OP51"]["상신·이행_KST"]),
            domain.BUY_LEAD,
            "act",
            "Submit_OP51",  # type: ignore[arg-type]
            {
                "OP51요청액": str(seed.by_id("SC05조건품의")["OP51"]["금액"]),
                "OP51사유": str(seed.by_id("SC05조건품의")["OP51"]["근거·원승인"]),
                "OP51근거": "",
            },
            "OP51 운영지원비 상신",
        ),
        act(
            "D508",
            "EV51-19",
            "Func_REQ51",
            {"REQ51현업결정": "승인", "REQ51현업의견": "외부 운영 검증 필요 — 계획 활동 05"},
            "REQ51 현업 승인",
        ),
        Step(
            "D508",
            kst(seed.by_id("SC05조건품의")["OP51"]["1차확인_KST"]),
            domain.BUY_EXEC,
            "act",
            "Func_OP51",  # type: ignore[arg-type]
            {"OP51현업결정": "승인", "OP51현업의견": "9~12월 운영지원 — 별도 운영예산"},
            "OP51 현업 승인",
        ),
        act(
            "D508",
            "EV51-20",
            "Budget_REQ51",
            {"REQ51예산결정": "승인", "REQ51예산의견": "ACT42 일회성 한도 6백만원 안 — 약정"},
            "REQ51 예산 승인 · 약정",
        ),
        act(
            "D508",
            "EV51-21",
            "Budget_OP51",
            {"OP51예산결정": "승인", "OP51예산의견": "운영지원 원장 — 일회성 한도와 섞지 않는다"},
            "OP51 예산 승인 · 약정",
        ),
        Step(
            "D508",
            "2027-08-20T15:15:00+09:00",
            "u-demo",
            "view",
            label="착수 요건 — 모두 충족, 적용일 9/1 전이라 착수 불가(READY)",
        ),
        act(
            "D509",
            "EV51-22",
            "Start_Operation",
            {
                "착수확인": "착수",
                "착수계획버전": "@PLAN",
                "착수의견": "요건 재확인 — 9/1 운영 적용",
            },
            "START51 운영 적용 착수",
        ),
        act(
            "D510",
            "EV51-23",
            "Receive_Change",
            {"고객원문": str(ch51["plan_ref"]), "접수메모": "CP51 고객 생산계획 수신"},
            "고객 변경 접수 — CP51",
        ),
        agent("AG54", "D510", domain.PROD_LEAD),
        act(
            "D510",
            "EV51-24",
            "Share_Change",
            {
                "공유내용": str(ch51["협의·판단"]),
                "공유수신": _name(domain.BUY_LEAD),
                "공유초안출처": "@AG54",
            },
            "생산 공유 — 원문 대조 후",
        ),
        act(
            "D510",
            "EV51-25",
            "Ack_Change",
            {"구매확인": "확인", "구매확인메모": "납품 일정·조달 가능성 검토 시작"},
            "구매 내용 확인",
        ),
        respond(ch51, po1, False, "EV51-26"),
        act(
            "D511",
            "EV51-27",
            "Execute_Order",
            {"발주시각": kst(po1["발주_KST"]), "실행근거": str(po1["근거ID"])},
            "정상 발주 기록 — 14시 발주·15시 처리",
        ),
        act(
            "D512",
            "EV51-29",
            "Receive_Change",
            {"고객원문": str(ch52["plan_ref"]), "접수메모": "CP52 별도 요청창 수신"},
            "고객 변경 접수 — CP52",
        ),
        act(
            "D512",
            "EV51-30",
            "Share_Change",
            {
                "공유내용": str(ch52["협의·판단"]),
                "공유수신": _name(domain.BUY_LEAD),
                "공유초안출처": "",
            },
            "생산 공유",
        ),
        act(
            "D512",
            "EV51-31",
            "Ack_Change",
            {"구매확인": "확인", "구매확인메모": "가용 재고·기발주 확인"},
            "구매 내용 확인",
        ),
        respond(ch52, po10, True, "EV51-32"),
        act(
            "D512",
            "EV51-33",
            "Approve_Urgent",
            {
                "긴급결정": "승인",
                "승인추가비": str(po10["추가비합계"]),
                "납기품질영향": "정상조달(9/15)로는 필요일(9/13) 불가 — 긴급 운송으로 납기 준수, "
                "품질 영향 없음",
                "긴급의견": str(docs["DOC57"]["가상 증빙 본문"]),
            },
            "긴급 예외 승인 — 구매 임원 전결",
        ),
        act(
            "D512",
            "EV51-34",
            "Execute_Order",
            {"발주시각": kst(po10["발주_KST"]), "실행근거": str(po10["근거ID"])},
            "긴급 발주 기록",
        ),
        agent("AG55", "D513", domain.BUY_LEAD),
        review("AG55", "D513"),
        act(
            "D513",
            "EV51-37",
            "Confirm_Observation",
            {"결과확인": "확인", "결과의견": str(docs["DOC58"]["가상 증빙 본문"])},
            "9월 초기 결과 확인",
        ),
        agent("AG56", "D514", domain.BUY_EXEC),
        opl_confirm(
            "OPL51",
            "EV51-38",
            {
                "OPL51확정": "확정",
                "OPL51잔여계획": str(o51["잔여계획"]),
                "OPL51가정": str(o51["효과가정"]),
                "OPL5110월": str(settings["oct_urgent_forecast"]),
                "OPL5111월": str(settings["nov_urgent_forecast"]),
                "OPL5112월": str(settings["dec_urgent_forecast"]),
                "OPL51진행": str(o51["진행상태"]),
                "OPL51초안출처": "@AG56",
            },
            "OPL51 구매 운영계획 확정 — 10월 4건, 11·12월 3건",
        ),
        opl_confirm(
            "OPL52",
            "EV51-39",
            {
                "OPL52확정": "확정",
                "OPL52잔여계획": str(o52["잔여계획"]),
                "OPL52가정": str(o52["효과가정"]),
                "OPL52적용량": str(s4["ALT41"]["월 대상량"]),
                "OPL52고정비절감": "0",
                "OPL52진행": str(o52["진행상태"]),
            },
            "OPL52 ACT41 운영계획 확인",
        ),
        opl_confirm(
            "OPL53",
            "EV51-40",
            {
                "OPL53확정": "확정",
                "OPL53잔여계획": str(o53["잔여계획"]),
                "OPL53가정": str(o53["효과가정"]),
                "OPL53공급량": str(s4["ALT43"]["월 대상량"]),
                "OPL53안정화확인": kst(plans["PL53-v1"]["과제기한"]),
                "OPL53진행": str(o53["진행상태"]),
            },
            "OPL53 ACT43 운영계획 확인",
        ),
        opl_verify("OPL51", o51, False),
        opl_verify("OPL52", o52, False),
        opl_verify("OPL53", o53, True),
        agent("AG57", "D515", domain.FIN),
        review("AG57", "D515"),
        act(
            "D515",
            "EV51-42",
            "Draft_Forecast",
            {
                "산정방식": "마감 실적+잔여 전망",
                "전망변경사유": " · ".join(f"{r['원인']} {int(r['전망변화']):+,}원" for r in recon),
                "전망초안출처": "",
            },
            "RUN51 · FC51-D 작성·대사",
        ),
        act(
            "D516",
            "EV51-43",
            "Confirm_FC_BUY",
            {"BUY가정확인": "확인", "BUY가정의견": "9월 긴급 5건 실적, 10월 4건·11~12월 3건 가정"},
            "구매 가정 확인",
        ),
        act(
            "D516",
            "EV51-44",
            "Confirm_FC_PROD",
            {"PROD가정확인": "확인", "PROD가정의견": "ACT41 월 3,000대분·고정비 절감 0"},
            "생산 가정 확인",
        ),
        act(
            "D516",
            "EV51-45",
            "Confirm_FC_SALES",
            {"SALES가정확인": "확인", "SALES가정의견": "판매 물량 가정 변동 없음"},
            "판매 물량 가정 확인",
        ),
        act(
            "D516",
            "EV51-46",
            "Submit_Forecast",
            {"제출확인": "제출", "제출의견": "대사 차이 0, 부서 확인 완료"},
            "대표 승인 요청",
        ),
        act(
            "D517",
            "EV51-47",
            "Approve_Forecast",
            {"대표결정": "승인", "대표의견": str(docs["DOC61"]["가상 증빙 본문"])},
            "공식 Forecast 승인 — FC51",
        ),
        act(
            "D517",
            "EV51-48",
            "Publish_Forecast",
            {"게시대상": "구매·생산·영업 임원, 경영관리 — 내부 공유(외부 발송 없음)"},
            "공식본 게시·공유",
        ),
        agent("AG58", "D518", domain.CFO),
        review("AG58", "D518"),
        act(
            "D518",
            "EV51-49",
            "Complete_Scene",
            {
                "후속목록": followups,
                "완료메모": (
                    "확정 계획·조건·품의·착수·초기 결과·공식 전망 연결 — Risk OPEN, 과제 운영 추적 "
                    "지속"
                ),
            },
            "결정 실행·계획 갱신 인계 완료 · HANDOFF51",
        ),
    ]


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
    if step.kind == "agent":
        return process.agent(demo_run_id, step.answer["kind"], actor=step.actor, **mark)
    if step.kind == "review":
        output = latest_output(process.get(demo_run_id), step.answer["kind"])
        if output is None:
            return process.mark(
                demo_run_id, note=f"{step.answer['kind']} 초안 없음 — 수동 진행", **mark
            )
        return process.review_agent(
            demo_run_id, output, actor=step.actor, note=step.answer["note"], **mark
        )
    current = process.get(demo_run_id)
    answer = resolve(current, step.answer)
    return process.act(
        demo_run_id,
        step.node_id or "",
        answer,
        actor=step.actor,
        expect=_expect(current, step.node_id or ""),
        **mark,
    )


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
