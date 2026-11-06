"""
시나리오 3 장면 2 규칙 — 결산조정 두 항목의 계산(구현명세 §2, 결산기준 시트).

입력은 장면 1이 분석 준비 완료로 판정한 입력 버전(허용 7개 시트)이다. **숫자는 여기서만 만든다** —
Agent 문안·Excel·화면 요약은 이 결과의 칸을 가리킨다. 기대값(계산근거 견본 v0.1·검수기준)은 시험만
대조한다.

* 금액은 백만원이고 거래처·구간별 충당금과 자산별 상각은 **원 단위(백만원 소수 6자리)로 반올림**한
  뒤 합산한다(결산기준 「반올림」). 대사는 원 단위 정수로 한다 — 표시 반올림 전 차이를 잡는다.
* 전이율은 2024년 말 일반거래처 모형(전이율원천 16분기, 원 단위)을 두 시연 기간에 똑같이 쓴다.
  시작 분기 잔액 대비 다음 분기 한 단계 장기화된 잔액, 상한 1, 분모 0은 미산출. 최근 12개 관측
  (2021.4Q → 2022.1Q부터 2024.3Q → 2024.4Q까지)의 시작잔액 가중평균 = Σ min(시작, 다음) ÷ Σ 시작.
  누적 PD = 그 구간부터 9~12개월까지의 가중 전이율 곱 × 12개월 초과 PD 100%, LGD 100%.
* 개별평가(A사)는 사람이 확인한 회수예상액(회계 평가 기록)을 쓴다 — 계획 회차 합계·영업 확인과
  버전·금액이 맞지 않으면 계산하지 않고 보완 대상으로 남긴다(공란을 0이나 추정액으로 채우지 않는다).
* 감가상각비는 정액법·월할 — (취득원가 − 잔존가) ÷ 내용연수 × 당기 사용월수 ÷ 12, 상각 가능 잔액
  (기초 순액 + 취득 − 처분 순액 − 손상 − 잔존가) 한도. 사용개시월 포함, 처분월 제외, 내용연수가
  끝난 달부터 0. 전기 상각은 자산대장의 확정값(전기 상각)이다.
* **승인 요청액과 전기 대비 증감은 다른 숫자다** — 감가상각비는 당기 계산액 − 기계상액, 대손충당금은
  기말 필요액 − 조정 전 잔액(전기말 − 당기 제각).
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from app.s3.sc01.calc import QUARTERS, dec, mil, mil_text, won

RULE_VERSION = "S3-SC02-CALC-v0.1"
ITEMS = ("DEP", "ALW")
#: 집합평가에 적용하는 구간 — 원천의 마지막 두 구간(12~15개월·15개월 초과)은 「12개월 초과」로 합산
SEGMENTS = ("미연체", "3개월 이내", "3~6개월", "6~9개월", "9~12개월")
OVER = "12개월 초과"
OVER_SOURCE = ("12~15개월", "15개월 초과")
#: 가중평균 관측 — 시작 분기 2021.4Q~2024.3Q(12개)
WINDOW = QUARTERS[3:15]
MODEL_QUARTER = QUARTERS[-1]
LGD = Decimal(1)
SIX = Decimal("0.000001")
OK, NEEDS_FIX = "DONE", "NEEDS_FIX"
KIND_ORDER = ("건물", "기계장치", "설비", "비품")
ALLOCATIONS = ("제조원가", "판매관리비")


def r6(value: Decimal) -> Decimal:
    """원 단위(백만원 소수 6자리) 반올림."""
    return value.quantize(SIX, rounding=ROUND_HALF_UP)


def m(value: Decimal | None) -> str | None:
    """백만원 Decimal → 글(뒤의 0을 뺀다). 원 단위 아래는 버린 뒤다."""
    return None if value is None else mil(won(value))


def _f(x: Decimal | None) -> str | None:
    """비율 글 — 소수 16자리까지(화면·Excel 대조용, 판정은 Decimal 그대로 한다)."""
    if x is None:
        return None
    return format(x.quantize(Decimal("1e-16"), rounding=ROUND_HALF_UP).normalize(), "f")


# ─────────────────────────── 전이율 · PD ───────────────────────────


def transition_model(v: dict[str, Any]) -> dict[str, Any]:
    """
    2024년 말 일반거래처 모형 — 분기 전이율(15개 관측)·단순·가중 전이율·누적 PD·설정률과 원본 재현
    충당금(2024.4Q 잔액 × 설정률, 합산 후 원 단위 반올림).
    """
    rows = {r["aging"]: r["balances"] for r in v["sheets"]["전이율원천"]["rows"]}
    order = [*SEGMENTS, *OVER_SOURCE]
    quarterly: dict[str, dict[str, str | None]] = {}
    weighted: dict[str, Decimal] = {}
    simple: dict[str, Decimal | None] = {}
    for i, seg in enumerate(SEGMENTS):
        nxt = order[i + 1]
        quarterly[seg] = {}
        num = den = Decimal(0)
        window_rates = []
        for t, q in enumerate(QUARTERS[:-1]):
            start = Decimal(rows[seg][q])
            end = Decimal(rows[nxt][QUARTERS[t + 1]])
            rate = None if start == 0 else min(Decimal(1), end / start)
            quarterly[seg][q] = _f(rate)
            if q in WINDOW and start != 0:
                num += min(start, end)
                den += start
                window_rates.append(rate)
        weighted[seg] = num / den if den else Decimal(0)
        simple[seg] = sum(window_rates) / len(window_rates) if window_rates else None
    pd: dict[str, Decimal] = {OVER: Decimal(1)}
    for i in range(len(SEGMENTS) - 1, -1, -1):
        nxt = SEGMENTS[i + 1] if i + 1 < len(SEGMENTS) else OVER
        pd[SEGMENTS[i]] = weighted[SEGMENTS[i]] * pd[nxt]
    rates = {seg: pd[seg] * LGD for seg in [*SEGMENTS, OVER]}
    model_balance = {seg: Decimal(rows[seg][MODEL_QUARTER]) for seg in SEGMENTS}
    model_balance[OVER] = sum(Decimal(rows[s][MODEL_QUARTER]) for s in OVER_SOURCE)
    reproduced = sum(model_balance[s] * rates[s] for s in rates)
    return {
        "model_quarter": MODEL_QUARTER,
        "window": [WINDOW[0], WINDOW[-1]],
        "quarterly": quarterly,
        "segments": [
            {
                "aging": seg,
                "simple_rate": _f(simple.get(seg)),
                "weighted_rate": _f(weighted.get(seg)),
                "pd": _f(pd[seg]),
                "lgd": _f(LGD),
                "rate": _f(rates[seg]),
                "model_balance_won": int(model_balance[seg]),
            }
            for seg in [*SEGMENTS, OVER]
        ],
        "rates": rates,
        #: 검수기준 「2024년말 일반거래처 충당금 302,527,880원(합계 원 단위 반올림)」
        "reproduced_won": int(reproduced.quantize(Decimal(1), rounding=ROUND_HALF_UP)),
    }


# ─────────────────────────── 대손충당금 ───────────────────────────


def _ledger(v: dict[str, Any], as_of: str, account: str) -> Decimal | None:
    rows = [r for r in v["sheets"]["원장"] if r["as_of"] == as_of and r["account"] == account]
    return dec(rows[0]["amount"]) if len(rows) == 1 else None


def _confirmation(
    v: dict[str, Any], plan_id: str | None, by: str, after: str | None, until: str
) -> list[dict[str, Any]]:
    return [
        r
        for r in v["sheets"]["확인기록"]
        if r.get("plan_ref") == plan_id
        and r.get("confirmed_by") == by
        and r["confirmed_on"] <= until
        and (after is None or r["confirmed_on"] > after)
    ]


def _individual(
    v: dict[str, Any], row: dict[str, Any], prior_end: str | None, findings: list
) -> dict[str, Any]:
    """
    개별평가 한 행 — 회계 평가 기록(그 기준일·그 계획 버전)의 확인액이 회수예상액이다. 계획 회차
    합계와 같아야 하고, 당기는 영업 확인도 같은 버전이어야 한다. 아니면 계산하지 않는다.
    """
    as_of, plan_id = row["as_of"], row.get("plan_ref")
    plan = [r for r in v["sheets"]["회수계획"] if r["plan_id"] == plan_id and r["as_of"] == as_of]
    rounds = [r["round"] for r in plan]
    plan_total = sum((dec(r["amount"]) or Decimal(0)) for r in plan) if plan else None
    acct = _confirmation(v, plan_id, "회계담당", prior_end, as_of)
    sales = _confirmation(v, plan_id, "영업담당", prior_end, as_of) if prior_end else []
    problems: list[tuple[str, str]] = []
    if not plan or len(set(rounds)) != len(rounds):
        problems.append(("영업담당", f"{plan_id or '계획 없음'} 회차 중복·누락"))
    if len(acct) != 1:
        problems.append(("회계담당", "회계 평가 기록이 없거나 여럿"))
    elif plan_total is not None and dec(acct[0]["amount"]) != plan_total:
        problems.append(
            ("회계담당", f"회계 확인액 {acct[0]['amount']} ≠ 계획 합계 {m(plan_total)}")
        )
    if prior_end and len(sales) != 1:
        problems.append(("영업담당", "영업 회신 확인이 없거나 다른 계획 버전"))
    balance = dec(row["balance"]) or Decimal(0)
    if problems:
        findings.append(
            {
                "item": "ALW",
                "ref": plan_id,
                "sheet": "확인기록",
                "reason": f"{row['customer']} {as_of} 개별평가 근거 — "
                + "; ".join(p for _, p in problems),
                "owner_role": problems[0][0],
            }
        )
        recovery = allowance = None
    else:
        recovery = dec(acct[0]["amount"])
        allowance = r6(balance - recovery)
    return {
        "customer": row["customer"],
        "as_of": as_of,
        "balance": m(balance),
        "plan_ref": plan_id,
        "plan_rounds": [
            {"round": r["round"], "due": r["due"], "amount": m(dec(r["amount"]))} for r in plan
        ],
        "plan_total": m(plan_total),
        "sales_confirmation": sales[0]["confirmation_id"] if len(sales) == 1 else None,
        "accounting_confirmation": acct[0]["confirmation_id"] if len(acct) == 1 else None,
        "confirmed_by": acct[0].get("confirmed_by") if len(acct) == 1 else None,
        "recovery": m(recovery),
        "allowance": m(allowance),
        "basis": acct[0].get("note") if len(acct) == 1 else None,
        "_allowance": allowance,
    }


def _period_rows(
    v: dict[str, Any], as_of: str, rates: dict[str, Decimal], prior_end: str | None, findings: list
) -> list[dict[str, Any]]:
    out = []
    for row in v["sheets"]["채권명세"]:
        if row["as_of"] != as_of:
            continue
        balance = dec(row["balance"]) or Decimal(0)
        if row["pool"] == "개별":
            ind = _individual(v, row, prior_end, findings)
            out.append(
                {
                    "customer": row["customer"],
                    "pool": "개별",
                    "aging": row.get("aging"),
                    "balance": balance,
                    "rate": None,
                    "allowance": ind.pop("_allowance"),
                    "individual": ind,
                }
            )
            continue
        rate = rates.get(row["aging"])
        if rate is None:
            findings.append(
                {
                    "item": "ALW",
                    "ref": f"{as_of} {row['customer']}",
                    "sheet": "채권명세",
                    "reason": f"모형에 없는 연령구간: {row['aging']}",
                    "owner_role": "채권담당",
                }
            )
        out.append(
            {
                "customer": row["customer"],
                "pool": "집합",
                "aging": row["aging"],
                "balance": balance,
                "rate": rate,
                "allowance": None if rate is None else r6(balance * rate),
                "individual": None,
            }
        )
    return out


def _sum(values: list[Decimal | None]) -> Decimal | None:
    return None if any(x is None for x in values) else sum(values, Decimal(0))


def allowance(v: dict[str, Any], master: dict[str, Any]) -> dict[str, Any]:
    """대손충당금 — 기간별 평가행·평가군 합계·상위 거래처·주석·요청액·대사."""
    close = master["close"]
    cur_end, pri_end = close["period_end"], close["comparative_end"]
    model = transition_model(v)
    findings: list[dict[str, Any]] = []
    cur = _period_rows(v, cur_end, model["rates"], pri_end, findings)
    pri = _period_rows(v, pri_end, model["rates"], None, findings)

    def by_pool(rows: list, pool: str | None) -> Decimal | None:
        return _sum([r["allowance"] for r in rows if pool is None or r["pool"] == pool])

    def bal(rows: list, pool: str | None = None) -> Decimal:
        return sum((r["balance"] for r in rows if pool is None or r["pool"] == pool), Decimal(0))

    methods = []
    for pool, label in (("집합", "집합"), ("개별", "개별"), (None, "합계")):
        p, c = by_pool(pri, pool), by_pool(cur, pool)
        methods.append(
            {
                "method": label,
                "prior": m(p),
                "current": m(c),
                "change": m(None if p is None or c is None else c - p),
                "current_balance": m(bal(cur, pool)),
            }
        )
    required = by_pool(cur, None)
    prior_required = by_pool(pri, None)
    # 거래처별(평가행 합산) — 당기 충당금 순위
    customers: dict[str, dict[str, Any]] = {}
    for period, rows in (("prior", pri), ("current", cur)):
        for r in rows:
            c = customers.setdefault(
                r["customer"],
                {"customer": r["customer"], "pool": r["pool"], "prior": [], "current": []},
            )
            c[period].append(r)
    ranked = []
    for c in customers.values():
        p = _sum([r["allowance"] for r in c["prior"]]) if c["prior"] else Decimal(0)
        n = _sum([r["allowance"] for r in c["current"]]) if c["current"] else Decimal(0)
        ranked.append(
            {
                "customer": c["customer"],
                "pool": c["pool"],
                "aging": (c["current"] or c["prior"])[0]["aging"],
                "prior_balance": m(bal(c["prior"])),
                "current_balance": m(bal(c["current"])),
                "rate": _f((c["current"] or c["prior"])[0]["rate"]),
                "prior": m(p),
                "current": m(n),
                "change": m(None if p is None or n is None else n - p),
                "_current": n,
            }
        )
    ranked.sort(key=lambda r: -(r["_current"] or Decimal(0)))
    for i, r in enumerate(ranked, start=1):
        r["rank"] = i
        r.pop("_current")
    # 원장 — 기초(전기말)·당기 제각·조정 전 잔액·외상매출금
    opening = _ledger(v, pri_end, "대손충당금")
    used = _ledger(v, cur_end, "당기 제각 사용")
    before = _ledger(v, cur_end, "대손충당금")
    book_receivable = _ledger(v, cur_end, "외상매출금")
    request = None if required is None or before is None else required - before
    ending = None
    if None not in (opening, used, request):
        ending = opening + max(request, Decimal(0)) - max(-request, Decimal(0)) - used
    receivable_diff = won(bal(cur)) - won(book_receivable) if book_receivable is not None else None
    note_diff = None if ending is None or required is None else won(ending) - won(required)
    opening_diff = None if None in (opening, used, before) else won(opening - used) - won(before)
    if receivable_diff not in (0, None):
        findings.append(
            {
                "item": "ALW",
                "ref": f"{cur_end} 외상매출금",
                "sheet": "원장",
                "reason": f"채권명세 합계와 원장 차이 {receivable_diff:,}원",
                "owner_role": "채권담당",
            }
        )
    individual = [r["individual"] for r in [*pri, *cur] if r["individual"]]
    return {
        "unit": "백만원",
        "model": {k: model[k] for k in model if k != "rates"},
        "rows": {
            "prior": [_row_out(r) for r in pri],
            "current": [_row_out(r) for r in cur],
        },
        "individual": individual,
        "methods": methods,
        "customers": ranked,
        "top3": [r["customer"] for r in ranked[:3]],
        "counts": {
            "current": {
                "collective": len({r["customer"] for r in cur if r["pool"] == "집합"}),
                "individual": len({r["customer"] for r in cur if r["pool"] == "개별"}),
            },
            "prior": {
                "collective": len({r["customer"] for r in pri if r["pool"] == "집합"}),
                "individual": len({r["customer"] for r in pri if r["pool"] == "개별"}),
            },
        },
        "note": {
            "opening": m(opening),
            "provision": m(None if request is None else max(request, Decimal(0))),
            "reversal": m(None if request is None else max(-request, Decimal(0))),
            "written_off": m(used),
            "ending": m(ending),
            "diff_won": note_diff,
        },
        "summary": {
            "prior": m(prior_required),
            "current": m(required),
            "change": m(
                None if required is None or prior_required is None else required - prior_required
            ),
            "book": m(before),
            "request": m(request),
            "request_label": _label("ALW", request),
        },
        "reconciliation": [
            _recon("기초 충당금", opening, opening),
            _recon(
                "조정 전 충당금 = 기초 − 당기 제각",
                before,
                None if opening is None or used is None else opening - used,
            ),
            _recon("외상매출금 잔액", book_receivable, bal(cur)),
            _recon("주석 충당금 = 평가표 기말", required, ending),
        ],
        "diffs": {
            "receivable_won": receivable_diff,
            "opening_won": opening_diff,
            "note_won": note_diff,
        },
        "findings": findings,
        "state": OK if not findings and required is not None else NEEDS_FIX,
    }


def _row_out(r: dict[str, Any]) -> dict[str, Any]:
    return {
        "customer": r["customer"],
        "pool": r["pool"],
        "aging": r["aging"],
        "balance": m(r["balance"]),
        "rate": _f(r["rate"]),
        "allowance": m(r["allowance"]),
    }


def _recon(label: str, book: Decimal | None, calc: Decimal | None) -> dict[str, Any]:
    diff = None if book is None or calc is None else won(calc) - won(book)
    return {"label": label, "book": m(book), "calculated": m(calc), "diff_won": diff}


def _label(item: str, request: Decimal | None) -> str | None:
    if request is None:
        return None
    if item == "DEP":
        return "추가 계상" if request > 0 else ("감액 조정" if request < 0 else "조정 없음")
    return "추가 설정" if request > 0 else ("환입" if request < 0 else "조정 없음")


# ─────────────────────────── 감가상각비 ───────────────────────────


def _month(value: str) -> int:
    d = date.fromisoformat(str(value)[:10])
    return d.year * 12 + d.month - 1


def months_in(asset: dict[str, Any], year: int) -> int:
    """
    그 해의 사용월수 — [사용개시월, min(내용연수 끝난 달, 처분월)) ∩ 그 해. 개시월 포함,
    처분월 제외.
    """
    start = _month(asset["in_service"])
    end = start + int(dec(asset["life_years"]) * 12)
    if asset.get("disposed_on"):
        end = min(end, _month(asset["disposed_on"]))
    lo, hi = max(start, year * 12), min(end, (year + 1) * 12)
    return max(0, hi - lo)


def depreciation(v: dict[str, Any], master: dict[str, Any]) -> dict[str, Any]:
    """감가상각비 — 자산별 계산·자산 종류별·비용 귀속별 비교·유형자산 주석·요청액·대사."""
    close = master["close"]
    year = int(close["period_end"][:4])
    assets = []
    findings: list[dict[str, Any]] = []
    for a in v["sheets"]["자산대장"]:
        cost, residual = dec(a["cost"]), dec(a["residual"])
        life = dec(a["life_years"])
        opening = dec(a["opening_net"]) or Decimal(0)
        acquired = dec(a["acquired"]) or Decimal(0)
        disposed = dec(a["disposed_net"]) or Decimal(0)
        impairment = dec(a["impairment"]) or Decimal(0)
        if None in (cost, residual, life) or not a.get("in_service"):
            findings.append(
                {
                    "item": "DEP",
                    "ref": a.get("asset_id"),
                    "sheet": "자산대장",
                    "reason": f"{a.get('asset_id')} 원가·잔존가·연수·사용개시일 누락",
                    "owner_role": "자산담당",
                }
            )
            continue
        months = months_in(a, year)
        annual = (cost - residual) / life
        limit = max(Decimal(0), opening + acquired - disposed - impairment - residual)
        current = r6(min(annual * months / 12, limit))
        prior = dec(a["prior_depreciation"]) or Decimal(0)
        closing = opening + acquired - disposed - impairment - current
        assets.append(
            {
                "asset_id": a["asset_id"],
                "kind": a["kind"],
                "allocation": a["allocation"],
                "opening_net": m(opening),
                "acquired": m(acquired),
                "disposed_net": m(disposed),
                "impairment": m(impairment),
                "cost": m(cost),
                "residual": m(residual),
                "life_years": m(life),
                "in_service": a["in_service"],
                "disposed_on": a.get("disposed_on"),
                "months": months,
                "annual": m(r6(annual)),
                "limit": m(limit),
                "current": m(current),
                "prior": m(prior),
                "change": m(current - prior),
                "closing_net": m(closing),
                "_v": (opening, acquired, disposed, impairment, current, prior, closing),
            }
        )

    def total(rows: list, idx: int) -> Decimal:
        return sum((r["_v"][idx] for r in rows), Decimal(0))

    kinds = [k for k in KIND_ORDER if any(r["kind"] == k for r in assets)]
    kinds += sorted({r["kind"] for r in assets} - set(kinds))
    by_kind = []
    for k in kinds:
        rows = [r for r in assets if r["kind"] == k]
        p, c = total(rows, 5), total(rows, 4)
        by_kind.append(
            {"group": k, "prior": m(p), "current": m(c), "change": m(c - p), "rate": _rate(c, p)}
        )
    by_alloc = []
    for k in ALLOCATIONS:
        rows = [r for r in assets if r["allocation"] == k]
        p, c = total(rows, 5), total(rows, 4)
        by_alloc.append(
            {"group": k, "prior": m(p), "current": m(c), "change": m(c - p), "rate": _rate(c, p)}
        )
    cur, pri = total(assets, 4), total(assets, 5)
    alloc_total = sum((dec(r["current"]) for r in by_alloc), Decimal(0))
    note_rows = []
    for k in kinds:
        rows = [r for r in assets if r["kind"] == k]
        note_rows.append(
            {
                "kind": k,
                "opening": m(total(rows, 0)),
                "acquired": m(total(rows, 1)),
                "disposed": m(total(rows, 2)),
                "impairment": m(total(rows, 3)),
                "depreciation": m(total(rows, 4)),
                "closing": m(total(rows, 6)),
            }
        )
    note_total = {
        "kind": "합계",
        "opening": m(total(assets, 0)),
        "acquired": m(total(assets, 1)),
        "disposed": m(total(assets, 2)),
        "impairment": m(total(assets, 3)),
        "depreciation": m(cur),
        "closing": m(total(assets, 6)),
    }
    book = _ledger(v, close["period_end"], "감가상각비")
    request = None if book is None else cur - book
    note_dep, closing = dec(note_total["depreciation"]), dec(note_total["closing"])
    rollforward = (
        dec(note_total["opening"])
        + dec(note_total["acquired"])
        - dec(note_total["disposed"])
        - dec(note_total["impairment"])
        - cur
    )
    for r in assets:
        r.pop("_v")
    changes = [
        {"asset_id": r["asset_id"], "kind": r["kind"], "change": r["change"], "months": r["months"]}
        for r in assets
        if dec(r["change"]) != 0
    ]
    if book is None:
        findings.append(
            {
                "item": "DEP",
                "ref": f"{close['period_end']} 감가상각비",
                "sheet": "원장",
                "reason": "원장 당기 기계상액이 없다",
                "owner_role": "회계담당",
            }
        )
    return {
        "unit": "백만원",
        "assets": assets,
        "by_kind": by_kind
        + [
            {
                "group": "자산 합계",
                "prior": m(pri),
                "current": m(cur),
                "change": m(cur - pri),
                "rate": _rate(cur, pri),
            }
        ],
        "by_allocation": by_alloc
        + [
            {
                "group": "귀속 합계",
                "prior": m(pri),
                "current": m(alloc_total),
                "change": m(alloc_total - pri),
                "rate": _rate(alloc_total, pri),
            }
        ],
        "note": {"rows": note_rows, "total": note_total},
        "changes": changes,
        "summary": {
            "prior": m(pri),
            "current": m(cur),
            "change": m(cur - pri),
            "book": m(book),
            "request": m(request),
            "request_label": _label("DEP", request),
        },
        "reconciliation": [
            _recon("상각비 분류 대사(자산 종류 = 비용 귀속)", cur, alloc_total),
            _recon("주석 상각 대사", cur, note_dep),
            _recon("기말 순액 = 기초 + 취득 − 처분 − 손상 − 상각", closing, rollforward),
        ],
        "diffs": {
            "allocation_won": won(alloc_total) - won(cur),
            "note_won": won(note_dep) - won(cur),
            "closing_won": won(rollforward) - won(closing),
        },
        "findings": findings,
        "state": OK if not findings else NEEDS_FIX,
    }


def _rate(cur: Decimal, pri: Decimal) -> str | None:
    return None if pri == 0 else _f((cur - pri) / pri)


# ─────────────────────────── 두 항목 · 요약 · 문안 ───────────────────────────


def calculate(v: dict[str, Any], master: dict[str, Any]) -> dict[str, Any]:
    """두 항목의 결과 — 승인 요약(항목별 한 행)·대사·보완 대상. 숫자의 유일한 출처."""
    dep = depreciation(v, master)
    alw = allowance(v, master)
    findings = [*dep["findings"], *alw["findings"]]
    diffs = [*dep["diffs"].values(), *alw["diffs"].values()]
    summary = []
    for item, name, res in (("DEP", "감가상각비", dep), ("ALW", "대손충당금", alw)):
        s = res["summary"]
        summary.append(
            {"item": item, "name": name, **s, "change_rate": _ratio(s["change"], s["prior"])}
        )
    return {
        "rule_version": RULE_VERSION,
        "input_version": v["version"],
        "period_end": master["close"]["period_end"],
        "comparative_end": master["close"]["comparative_end"],
        "unit": "백만원",
        "depreciation": dep,
        "allowance": alw,
        "summary": summary,
        "findings": findings,
        "max_diff_won": max((abs(d) for d in diffs if d is not None), default=0),
        "diffs_missing": sum(1 for d in diffs if d is None),
        "state": OK if not findings and all(d == 0 for d in diffs) else NEEDS_FIX,
    }


def _ratio(change: str | None, prior: str | None) -> str | None:
    if change is None or prior in (None, "0"):
        return None
    return _f(r6(Decimal(change) / Decimal(prior)))


def _fmt(value: str | None, sign: bool = False) -> str:
    if value is None:
        return "미산출"
    d = Decimal(value)
    text = mil_text(won(abs(d)))
    if sign:
        return ("+" if d > 0 else "−" if d < 0 else "") + text
    return ("−" if d < 0 else "") + text


def draft(result: dict[str, Any]) -> dict[str, Any]:
    """
    Agent 문안(승인 요약 초안) — **이번 판은 규칙 문안이다**: 계산 결과의 칸을 정해진 문장에
    이어 붙인다(LLM 호출 없음). 문장의 숫자마다 결과 칸을 가리킨다(구현명세 §3 「각 수치에 결과 필드
    또는 계산 행을 연결한다」). 팀장의 판단을 지시하는 문구는 넣지 않는다.
    """
    dep, alw = result["depreciation"], result["allowance"]
    ds, als = dep["summary"], alw["summary"]
    ups = [c for c in dep["changes"] if Decimal(c["change"]) > 0]
    downs = [c for c in dep["changes"] if Decimal(c["change"]) < 0]
    dep_parts = []
    refs_dep = []
    for c in ups:
        dep_parts.append(
            f"{c['asset_id']}({c['kind']}) {c['months']}개월 상각으로 {_fmt(c['change'])} 증가"
        )
        refs_dep.append(
            {"value": c["change"], "field": f"depreciation.assets[{c['asset_id']}].change"}
        )
    for c in downs:
        dep_parts.append(f"{c['asset_id']}({c['kind']}) 상각 종료로 {_fmt(c['change'][1:])} 감소")
        refs_dep.append(
            {"value": c["change"], "field": f"depreciation.assets[{c['asset_id']}].change"}
        )
    alloc = {r["group"]: r["current"] for r in dep["by_allocation"]}
    dep_text = (
        f"전기 {_fmt(ds['prior'])} → 당기 {_fmt(ds['current'])}({_fmt(ds['change'], True)}): "
        + ", ".join(dep_parts)
        + f". 제조원가 {_fmt(alloc.get('제조원가'))} + 판매관리비 {_fmt(alloc.get('판매관리비'))}"
        + f" = 주석 상각액 {_fmt(dep['note']['total']['depreciation'])}."
        + f" 기계상 {_fmt(ds['book'])} 대비 {ds['request_label']} {_fmt(ds['request'])}."
    )
    refs_dep += [
        {"value": ds["prior"], "field": "depreciation.summary.prior"},
        {"value": ds["current"], "field": "depreciation.summary.current"},
        {"value": alloc.get("제조원가"), "field": "depreciation.by_allocation[제조원가].current"},
        {
            "value": alloc.get("판매관리비"),
            "field": "depreciation.by_allocation[판매관리비].current",
        },
        {"value": ds["book"], "field": "depreciation.summary.book"},
        {"value": ds["request"], "field": "depreciation.summary.request"},
    ]
    methods = {r["method"]: r for r in alw["methods"]}
    cur_ind = [i for i in alw["individual"] if i["as_of"] == result["period_end"]]
    pri_ind = {
        i["customer"]: i for i in alw["individual"] if i["as_of"] == result["comparative_end"]
    }
    ind_parts, refs_alw = [], []
    for i in cur_ind:
        p = pri_ind.get(i["customer"])
        if p is None:
            continue
        ind_parts.append(
            f"{i['customer']} 채권 {_fmt(i['balance'])}의 회수예상액 {_fmt(p['recovery'])} → "
            f"{_fmt(i['recovery'])}({i['accounting_confirmation']} 확인)에 따라 개별 충당금 "
            f"{_fmt(p['allowance'])} → {_fmt(i['allowance'])}"
        )
        refs_alw += [
            {
                "value": i["recovery"],
                "field": f"allowance.individual[{i['customer']} {i['as_of']}].recovery",
            },
            {
                "value": i["allowance"],
                "field": f"allowance.individual[{i['customer']} {i['as_of']}].allowance",
            },
        ]
    movers = [
        c
        for c in alw["customers"]
        if c["pool"] == "집합" and c["change"] is not None and Decimal(c["change"]) != 0
    ]
    col = methods["집합"]
    mover_text = ", ".join(
        f"{c['customer']}({c['aging']}) {_fmt(c['change'], True)}" for c in movers
    )
    note = alw["note"]
    alw_text = (
        f"기말 필요액 {_fmt(als['current'])} = 집합 {_fmt(col['current'])}"
        + f" + 개별 {_fmt(methods['개별']['current'])}. "
        + "; ".join(ind_parts)
        + f". 집합평가는 {_fmt(col['prior'])} → {_fmt(col['current'])}"
        + (f"({mover_text})" if mover_text else "")
        + f". 전기 대비 {_fmt(als['change'], True)}."
        + f" 기초 {_fmt(note['opening'])} − 당기 제각 {_fmt(note['written_off'])}"
        + f" = 조정 전 {_fmt(als['book'])},"
        + f" {als['request_label']} {_fmt(als['request'])} → 기말 {_fmt(note['ending'])}."
    )
    refs_alw += [
        {"value": als["current"], "field": "allowance.summary.current"},
        {"value": col["current"], "field": "allowance.methods[집합].current"},
        {"value": methods["개별"]["current"], "field": "allowance.methods[개별].current"},
        {"value": als["change"], "field": "allowance.summary.change"},
        {"value": note["opening"], "field": "allowance.note.opening"},
        {"value": note["written_off"], "field": "allowance.note.written_off"},
        {"value": als["book"], "field": "allowance.summary.book"},
        {"value": als["request"], "field": "allowance.summary.request"},
    ]
    return {
        "mode": "rule-template",
        "note": (
            "규칙 문안 — 계산 결과의 칸을 정해진 문장에 이어 붙였다(LLM 호출 없음). "
            "숫자는 계산 기능의 것이다"
        ),
        "sections": [
            {
                "item": "DEP",
                "title": "감가상각비 및 유형자산 주석",
                "text": dep_text,
                "refs": refs_dep,
            },
            {
                "item": "ALW",
                "title": "외상매출금 대손충당금 및 관련 주석",
                "text": alw_text,
                "refs": refs_alw,
            },
        ],
    }


__all__ = ["ITEMS", "NEEDS_FIX", "OK", "RULE_VERSION", "calculate", "draft", "transition_model"]
