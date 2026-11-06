"""
시나리오 3 장면 1 규칙 — 결산조정 항목의 입력자료 점검과 분석 준비 판정(구현명세 §1·§2).

입력 버전 하나(기간계 `close-inputs/{version}` — 허용 7개 시트)를 받아 항목마다 필수 점검을 돌린다.
**모든 필수 점검이 통과해야 분석 준비 완료**다. 누락·불일치·읽기 실패는 보완 필요이고 그 점검의
대상 시트·행(또는 근거 ID)·기대값·확인값·보완 담당 역할을 남긴다. 공란을 0으로 바꾸지 않는다.

* 공통 기준(C-0N)은 두 항목에 같이 들어간다 — 「공통 기준 누락은 양쪽 행에 표시」.
* 금액은 백만원이고 비교는 **원 단위 정수**로 한다 — 「표시 반올림 전 차이를 탐지한다」
  (인수시험 06). 전이율원천만 원이다.
* 손실률·충당금·상각비 계산은 장면 2다 — 여기서는 준비도와 기초 대사만 본다(업무설계표 자료점검).
* 항목의 입력 지문(`item_fingerprint`)은 그 항목이 쓰는 칸만 본다 — 원장은 행 단위다(감가상각비는
  감가상각비 행, 충당금은 충당금·제각·외상매출금 행). 자료 교체가 다른 항목을 재점검 대상으로 만들지
  않게 한다(인수시험 07 「충당금 상태는 유지」).
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, time, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

KST = timezone(timedelta(hours=9))
RULE_VERSION = "S3-SC01-CHECK-v0.1"
READY, NEEDS_FIX = "READY", "NEEDS_FIX"
ITEMS = ("DEP", "ALW")
#: 전이율원천 — 일반거래처 16개 분기(2021.1Q~2024.4Q). 구간은 자료 그대로 읽는다.
QUARTERS = tuple(f"{y}.{q}Q" for y in range(2021, 2025) for q in range(1, 5))
#: 감가상각비가 쓰는 원장 행 · 충당금이 쓰는 원장 행
LEDGER_OF = {
    "DEP": (("2026-12-31", "감가상각비"),),
    "ALW": (
        ("2025-12-31", "대손충당금"),
        ("2026-12-31", "당기 제각 사용"),
        ("2026-12-31", "대손충당금"),
        ("2026-12-31", "외상매출금"),
    ),
}
ASSET_REQUIRED = (
    ("kind", "종류"),
    ("allocation", "귀속"),
    ("opening_net", "기초 순액"),
    ("acquired", "당기취득"),
    ("disposed_net", "처분 순액"),
    ("impairment", "손상"),
    ("cost", "취득원가"),
    ("residual", "잔존가"),
    ("life_years", "연수"),
    ("in_service", "사용개시일"),
    ("prior_depreciation", "전기 상각"),
)


def dec(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    return Decimal(str(value))


def won(value: Any) -> int | None:
    """백만원 → 원(정수). 6자리 아래는 자료에 없다 — 반올림은 원 단위 경계만 정리한다."""
    d = dec(value)
    if d is None:
        return None
    return int((d * 1_000_000).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def mil(value: int | None) -> str | None:
    """원 → 백만원 글(소수 6자리까지, 뒤의 0은 뺀다)."""
    if value is None:
        return None
    d = (Decimal(value) / 1_000_000).normalize()
    return format(d, "f")


def _check(
    check_id: str,
    item: str,
    label: str,
    ok: bool,
    *,
    sheet: str,
    expected: Any,
    actual: Any,
    ref: str | None = None,
    owner: str,
    reason: str | None = None,
) -> dict[str, Any]:
    return {
        "check_id": check_id,
        "item": item,
        "label": label,
        "verdict": "PASS" if ok else "FAIL",
        "sheet": sheet,
        "ref": ref,
        "expected": expected,
        "actual": actual,
        "owner_role": owner,
        "reason": None if ok else reason,
    }


# ─────────────────────────── 공통 기준 ───────────────────────────


def common_checks(v: dict[str, Any], master: dict[str, Any], item: str) -> list[dict[str, Any]]:
    """
    C-01 허용 시트 · C-02 기준일·비교기간 · C-03 그 항목이 쓰는 시트의 단위(전이율원천만 원 —
    충당금만 쓰므로 그 단위 오류는 감가상각비를 막지 않는다, 인수시험 06).
    """
    close = master["close"]
    allowed = list(master["allowed_sheets"])
    have = list(v["sheets"])
    out = [
        _check(
            "C-01",
            item,
            "입력 시트 허용목록",
            sorted(have) == sorted(allowed),
            sheet="결산기준",
            expected=allowed,
            actual=have,
            owner="회계담당",
            reason="허용 7개 시트와 연결된 시트가 다르다",
        ),
        _check(
            "C-02",
            item,
            "결산 기준일·비교기간",
            v.get("period_end") == close["period_end"]
            and v.get("comparative_end") == close["comparative_end"],
            sheet="결산기준",
            expected=f"{close['period_end']} / 전기 {close['comparative_end']}",
            actual=f"{v.get('period_end')} / 전기 {v.get('comparative_end')}",
            owner="회계담당",
            reason="입력의 기준일·비교기간이 결산 건과 다르다",
        ),
    ]
    want = master["units"]
    mine = next(i["sheets"] for i in close["items"] if i["item_id"] == item)
    wrong = [s for s in mine if want.get(s) is not None and v["units"].get(s) != want[s]]
    out.append(
        _check(
            "C-03",
            item,
            "금액 단위",
            not wrong,
            sheet=wrong[0] if wrong else "결산기준",
            expected="전이율원천 원 · 그 외 백만원",
            actual="일치" if not wrong else ", ".join(f"{s} {v['units'].get(s)}" for s in wrong),
            owner="회계담당",
            reason="시트 단위가 결산기준과 다르다",
        )
    )
    return out


# ─────────────────────────── 감가상각비 ───────────────────────────


def _period(v: dict[str, Any]) -> tuple[str, str]:
    """당기 [1/1, 12/31] — 기준일의 해."""
    end = v.get("period_end") or "2026-12-31"
    return f"{end[:4]}-01-01", end


def _ledger(v: dict[str, Any], as_of: str, account: str) -> list[dict[str, Any]]:
    return [r for r in v["sheets"]["원장"] if r["as_of"] == as_of and r["account"] == account]


def depreciation_checks(v: dict[str, Any], master: dict[str, Any]) -> list[dict[str, Any]]:
    """
    DEP-01 자산 ID 유일 · DEP-02 자산별 필수값 · DEP-03 처분 대조 · DEP-04 당기 신규 자산의
    사용개시일 · DEP-05 원장 당기 기계상액.
    """
    assets = v["sheets"]["자산대장"]
    first, last = _period(v)
    out: list[dict[str, Any]] = []
    ids = [a.get("asset_id") for a in assets]
    dup = sorted({i for i in ids if ids.count(i) > 1 or i in (None, "")}, key=str)
    out.append(
        _check(
            "DEP-01",
            "DEP",
            "자산 ID 유일",
            not dup,
            sheet="자산대장",
            expected="자산 ID당 1행",
            actual=f"{len(assets)}행" if not dup else f"중복·공란: {', '.join(map(str, dup))}",
            ref=None if not dup else str(dup[0]),
            owner="자산담당",
            reason="같은 자산 ID가 여러 행이거나 비어 있다",
        )
    )
    for a in assets:
        missing = [label for key, label in ASSET_REQUIRED if a.get(key) in (None, "")]
        life = dec(a.get("life_years"))
        if life is not None and life <= 0:
            missing.append("연수(양수)")
        out.append(
            _check(
                f"DEP-02:{a.get('asset_id')}",
                "DEP",
                f"{a.get('asset_id')} 필수값",
                not missing,
                sheet="자산대장",
                expected="종류·귀속·원가·잔존가·양의 내용연수·개시일·전기 상각",
                actual="모두 있음" if not missing else f"누락: {', '.join(missing)}",
                ref=str(a.get("asset_id")),
                owner="자산담당",
                reason=None if not missing else f"{a.get('asset_id')} {', '.join(missing)} 누락",
            )
        )
        disposed_on = a.get("disposed_on")
        disposed = dec(a.get("disposed_net")) or Decimal(0)
        if disposed_on or disposed:
            opening = (dec(a.get("opening_net")) or Decimal(0)) + (
                dec(a.get("acquired")) or Decimal(0)
            )
            ok = (
                bool(disposed_on)
                and first <= str(disposed_on) <= last
                and Decimal(0) < disposed <= opening
            )
            out.append(
                _check(
                    f"DEP-03:{a.get('asset_id')}",
                    "DEP",
                    f"{a.get('asset_id')} 처분일·처분 순액",
                    ok,
                    sheet="자산대장",
                    expected=f"당기 처분일 · 0 < 처분 순액 ≤ 기초+취득({opening})",
                    actual=f"처분일 {disposed_on or '없음'} · 처분 순액 {a.get('disposed_net')}",
                    ref=str(a.get("asset_id")),
                    owner="자산담당",
                    reason="처분일과 처분 순액이 맞지 않는다",
                )
            )
    for a in assets:
        if (dec(a.get("acquired")) or Decimal(0)) <= 0:
            continue
        start = a.get("in_service")
        ok = bool(start) and first <= str(start) <= last
        out.append(
            _check(
                f"DEP-04:{a.get('asset_id')}",
                "DEP",
                f"신규 {a.get('asset_id')} 사용개시일",
                ok,
                sheet="자산대장",
                expected=f"당기 안({first} ~ {last})",
                actual=start or "없음",
                ref=str(a.get("asset_id")),
                owner="자산담당",
                reason=f"신규 {a.get('asset_id')}의 사용개시일이 없거나 당기 밖이다",
            )
        )
    rows = _ledger(v, last, "감가상각비")
    amount = rows[0]["amount"] if len(rows) == 1 else None
    out.append(
        _check(
            "DEP-05",
            "DEP",
            "원장 당기 감가상각비 기계상액",
            amount is not None,
            sheet="원장",
            expected="조정 전 당기 기계상액 1행",
            actual=None if amount is None else f"{amount}백만원",
            ref=f"{last} 감가상각비",
            owner="회계담당",
            reason="원장에 당기 감가상각비 기계상액이 없거나 여러 행이다",
        )
    )
    return out


# ─────────────────────────── 대손충당금 ───────────────────────────


def _receivables(v: dict[str, Any], as_of: str) -> list[dict[str, Any]]:
    return [r for r in v["sheets"]["채권명세"] if r["as_of"] == as_of]


def current_plan(v: dict[str, Any], customer: str = "A사") -> str | None:
    """당기 채권명세의 개별평가 행이 가리키는 계획 — 기준일 현재 유효한 문서 버전."""
    _first, last = _period(v)
    refs = {
        r.get("plan_ref")
        for r in _receivables(v, last)
        if r["customer"] == customer and r["pool"] == "개별"
    }
    refs.discard(None)
    return refs.pop() if len(refs) == 1 else None


def allowance_checks(v: dict[str, Any], master: dict[str, Any]) -> list[dict[str, Any]]:
    """
    ALW-01 당·전기 명세 · ALW-02 평가군 배타 · ALW-03 명세·원장 대사(원 단위) · ALW-04 조정 전
    충당금 · ALW-05 전이율원천 16분기·원 단위 · ALW-06 A사 당기 회수계획 회차 · ALW-07 영업
    회신 확인 · ALW-08 회계 평가 기록.
    """
    close = master["close"]
    _first, last = _period(v)
    prior_end = close["comparative_end"]
    out: list[dict[str, Any]] = []
    cur, pri = _receivables(v, last), _receivables(v, prior_end)
    out.append(
        _check(
            "ALW-01",
            "ALW",
            "당기·전기 채권명세",
            bool(cur) and bool(pri),
            sheet="채권명세",
            expected=f"{last} · {prior_end} 명세",
            actual=f"당기 {len(cur)}행 · 전기 {len(pri)}행",
            owner="채권담당",
            reason="당기 또는 전기 채권명세가 없다",
        )
    )
    clash = []
    for as_of in (last, prior_end):
        pools: dict[str, set[str]] = {}
        for r in _receivables(v, as_of):
            pools.setdefault(r["customer"], set()).add(r["pool"])
        clash += [f"{as_of} {c}" for c, p in sorted(pools.items()) if {"집합", "개별"} <= p]
    bad_ref = [
        f"{r['as_of']} {r['customer']}"
        for r in cur + pri
        if r["pool"] == "개별" and not r.get("plan_ref")
    ]
    out.append(
        _check(
            "ALW-02",
            "ALW",
            "집합·개별 평가군 배타",
            not clash and not bad_ref,
            sheet="채권명세",
            expected="같은 채권이 집합·개별에 함께 없음 · 개별은 계획 참조",
            actual="중복 없음"
            if not clash and not bad_ref
            else "; ".join(
                [*(f"중복 {c}" for c in clash), *(f"계획 참조 없음 {b}" for b in bad_ref)]
            ),
            ref=(clash or bad_ref or [None])[0],
            owner="채권담당",
            reason="같은 거래처가 집합·개별에 함께 있거나 개별평가의 계획 참조가 없다",
        )
    )
    total = None
    if cur and all(won(r.get("balance")) is not None for r in cur):
        total = sum(won(r["balance"]) for r in cur)
    rows = _ledger(v, last, "외상매출금")
    book = won(rows[0]["amount"]) if len(rows) == 1 else None
    diff = None if total is None or book is None else total - book
    out.append(
        _check(
            "ALW-03",
            "ALW",
            "채권명세·원장 대사",
            diff == 0,
            sheet="원장",
            expected=f"차이 0원 (원장 {mil(book) or '없음'}백만원)",
            actual=f"명세 {mil(total) or '산출 불가'}백만원 · 차이 "
            + ("미산출" if diff is None else f"{diff:,}원"),
            ref=f"{last} 외상매출금",
            owner="채권담당",
            reason="당기 채권명세 합계와 원장 외상매출금이 다르다",
        )
    )
    opening = _ledger(v, prior_end, "대손충당금")
    used = _ledger(v, last, "당기 제각 사용")
    before = _ledger(v, last, "대손충당금")
    vals = [won(x[0]["amount"]) if len(x) == 1 else None for x in (opening, used, before)]
    ok = None not in vals and vals[0] - vals[1] == vals[2]
    out.append(
        _check(
            "ALW-04",
            "ALW",
            "조정 전 충당금 = 전기말 − 당기 제각",
            ok,
            sheet="원장",
            expected="전기말 충당금 − 당기 제각 사용 = 조정 전 잔액",
            actual=" − ".join(mil(x) or "없음" for x in vals[:2])
            + f" → 조정 전 {mil(vals[2]) or '없음'}",
            ref=f"{prior_end} 대손충당금",
            owner="회계담당",
            reason="원장의 기초·제각·조정 전 충당금이 맞지 않는다",
        )
    )
    rates = v["sheets"]["전이율원천"]
    gaps = [q for q in QUARTERS if q not in rates.get("quarters", [])]
    blank, frac = [], []
    for row in rates.get("rows", []):
        for q in QUARTERS:
            value = row["balances"].get(q)
            if value is None:
                blank.append(f"{row['aging']} {q}")
            elif dec(value) != dec(value).to_integral_value():
                frac.append(f"{row['aging']} {q}")
    unit = v["units"].get("전이율원천")
    ok = not gaps and not blank and not frac and unit == "원" and bool(rates.get("rows"))
    detail = []
    if gaps:
        detail.append(f"분기 누락 {', '.join(gaps)}")
    if blank:
        detail.append(f"빈 칸 {len(blank)}개({blank[0]} …)")
    if unit != "원" or frac:
        detail.append(f"단위 {unit} · 원 단위가 아닌 값 {len(frac)}개")
    out.append(
        _check(
            "ALW-05",
            "ALW",
            "전이율원천 16분기·원 단위",
            ok,
            sheet="전이율원천",
            expected="일반거래처 2021.1Q~2024.4Q 16분기 · 원 단위 정수",
            actual=f"{len(rates.get('rows', []))}개 구간 × 16분기 · 원"
            if ok
            else "; ".join(detail),
            ref=(gaps or blank or frac or [None])[0],
            owner="회계담당",
            reason="전이율원천의 분기·단위가 결산기준과 다르다",
        )
    )
    plan_id = current_plan(v)
    plan = [r for r in v["sheets"]["회수계획"] if r["plan_id"] == plan_id]
    rounds = [r.get("round") for r in plan]
    dup = sorted({r for r in rounds if rounds.count(r) > 1}, key=str)
    stale = [r for r in plan if r.get("as_of") != last]
    plan_total = None
    if plan and not dup and all(won(r.get("amount")) is not None for r in plan):
        plan_total = sum(won(r["amount"]) for r in plan)
    ok = plan_id is not None and bool(plan) and not dup and not stale and plan_total is not None
    out.append(
        _check(
            "ALW-06",
            "ALW",
            "A사 당기 회수계획 회차",
            ok,
            sheet="회수계획",
            expected="기준일 현재 계획 1개 · 서로 다른 회차 합산",
            actual=(
                f"{plan_id} {len(plan)}회차 합계 {mil(plan_total)}백만원"
                if ok
                else f"{plan_id or '계획 없음'} · "
                + (f"회차 {', '.join(map(str, dup))} 중복" if dup else "")
                + (f"기준일 다른 행 {len(stale)}" if stale else "")
                + ("행 없음" if not plan else "")
            ),
            ref=plan_id,
            owner="영업담당",
            reason="당기 회수계획의 회차가 중복이거나 기준일이 다르다 — 합산하지 않는다",
        )
    )
    confs = [r for r in v["sheets"]["확인기록"] if r["customer"] == "A사"]
    sales = [r for r in confs if r.get("confirmed_by") == "영업담당" and r["confirmed_on"] <= last]
    sales = [r for r in sales if r["confirmed_on"] > prior_end]
    s_ok = len(sales) == 1 and sales[0].get("plan_ref") == plan_id
    out.append(
        _check(
            "ALW-07",
            "ALW",
            "영업 회신 확인",
            s_ok,
            sheet="확인기록",
            expected=f"당기 영업 확인 1건 · 근거 {plan_id}",
            actual=", ".join(f"{r['confirmation_id']}({r.get('plan_ref')})" for r in sales)
            or "없음",
            ref=sales[0]["confirmation_id"] if sales else None,
            owner="영업담당",
            reason="영업의 당기 회신 확인이 없거나 다른 계획 버전에 연결됐다",
        )
    )
    acct = [r for r in confs if r.get("confirmed_by") == "회계담당" and r["confirmed_on"] <= last]
    acct = [r for r in acct if r["confirmed_on"] > prior_end]
    f = acct[0] if len(acct) == 1 else None
    amount = won(f.get("amount")) if f else None
    a_ok = (
        f is not None
        and f.get("plan_ref") == plan_id
        and plan_total is not None
        and amount == plan_total
    )
    if f is None:
        actual = "회계 평가 기록 없음" if not acct else f"{len(acct)}건 — 하나여야 한다"
    else:
        actual = f"{f['confirmation_id']} 근거 {f.get('plan_ref')} · 확인액 {mil(amount)}백만원"
    out.append(
        _check(
            "ALW-08",
            "ALW",
            "회계 평가 기록 = 계획 합계",
            a_ok,
            sheet="확인기록",
            expected=f"근거 {plan_id} · 확인액 = 회차 합계 {mil(plan_total) or '미산출'}백만원",
            actual=actual,
            ref=f["confirmation_id"] if f else None,
            owner="회계담당",
            reason=(
                "회계의 기준일 평가 기록이 없거나 계획 버전·금액이 맞지 않는다 — "
                "추정액으로 채우지 않는다"
            ),
        )
    )
    return out


def check_item(v: dict[str, Any], master: dict[str, Any], item: str) -> list[dict[str, Any]]:
    own = depreciation_checks(v, master) if item == "DEP" else allowance_checks(v, master)
    return [*common_checks(v, master, item), *own]


def verdict(checks: list[dict[str, Any]]) -> str:
    return READY if all(c["verdict"] == "PASS" for c in checks) else NEEDS_FIX


# ─────────────────────────── 근거 요약(화면) ───────────────────────────


def evidence(v: dict[str, Any], item: str) -> dict[str, Any]:
    """
    화면 우측 근거 패널 — 감가상각비는 신규 E2·원장 기계상액, 충당금은 대사·기초·모형 자료·A사
    계획과 두 확인 기록. 판정은 `check_item`이고 이것은 보이기만 한다.
    """
    _first, last = _period(v)
    if item == "DEP":
        new = [a for a in v["sheets"]["자산대장"] if (dec(a.get("acquired")) or 0) > 0]
        rows = _ledger(v, last, "감가상각비")
        return {
            "assets": len(v["sheets"]["자산대장"]),
            "new_assets": [
                {
                    "asset_id": a["asset_id"],
                    "kind": a.get("kind"),
                    "acquired": a.get("acquired"),
                    "in_service": a.get("in_service"),
                }
                for a in new
            ],
            "booked_depreciation": rows[0]["amount"] if len(rows) == 1 else None,
        }
    cur = _receivables(v, last)
    plan_id = current_plan(v)
    plans = {}
    for r in v["sheets"]["회수계획"]:
        plans.setdefault(r["plan_id"], []).append(
            {"round": r["round"], "due": r["due"], "amount": r["amount"]}
        )
    rates = v["sheets"]["전이율원천"]
    ledger = {
        f"{r['as_of']} {r['account']}": r["amount"]
        for r in v["sheets"]["원장"]
        if (r["as_of"], r["account"]) in LEDGER_OF["ALW"]
    }
    return {
        "receivables": {
            "current_total": mil(sum(won(r["balance"]) or 0 for r in cur)),
            "rows": len(cur),
            "individual": [r["customer"] for r in cur if r["pool"] == "개별"],
        },
        "ledger": ledger,
        "rates": {
            "segments": [r["aging"] for r in rates.get("rows", [])],
            "quarters": len(rates.get("quarters", [])),
            "unit": v["units"].get("전이율원천"),
        },
        "plan": {"current": plan_id, "rounds": plans.get(plan_id or "", []), "all": plans},
        "confirmations": [
            {
                "confirmation_id": r["confirmation_id"],
                "confirmed_on": r["confirmed_on"],
                "confirmed_by": r.get("confirmed_by"),
                "plan_ref": r.get("plan_ref"),
                "amount": r.get("amount"),
            }
            for r in v["sheets"]["확인기록"]
        ],
    }


# ─────────────────────────── 지문·기한 ───────────────────────────


def item_fingerprint(v: dict[str, Any], master: dict[str, Any], item: str) -> str:
    """
    그 항목이 쓰는 입력만의 지문 — 원장은 그 항목의 행만, 시트는 내용·단위·추출 참조. 이 값이
    바뀌면 그 항목만 재점검 대상이다.
    """
    sheets = next(i["sheets"] for i in master["close"]["items"] if i["item_id"] == item)
    parts: dict[str, Any] = {"period": [v.get("period_end"), v.get("comparative_end")]}
    for s in sheets:
        if s == "원장":
            parts[s] = [
                r for r in v["sheets"]["원장"] if (r["as_of"], r["account"]) in LEDGER_OF[item]
            ]
        else:
            parts[s] = [v["sheets"].get(s), v["units"].get(s), v["source_refs"].get(s)]
    text = json.dumps(parts, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def at(value: str) -> datetime:
    return datetime.fromisoformat(value)


def next_business_day_18(now: str) -> str:
    """보완 기한 — 다음 영업일(월~금) 18:00(가안)."""
    d: date = at(now).astimezone(KST).date() + timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return datetime.combine(d, time(18, 0), tzinfo=KST).isoformat()


def remaining_days(now: str, due: str) -> int:
    """잔여일 — 기한 날짜 − 오늘 날짜(달력일). 음수면 기한 경과다."""
    return (at(due).astimezone(KST).date() - at(now).astimezone(KST).date()).days


__all__ = [
    "ITEMS",
    "NEEDS_FIX",
    "READY",
    "RULE_VERSION",
    "check_item",
    "evidence",
    "item_fingerprint",
    "verdict",
]
