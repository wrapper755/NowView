"""
SC06 업무 규칙 — 과제 완료와 성과 실현 검토(장면 6). 구현명세 v0.2 · 업무설계표 v0.2 · 화면구성
v0.2.

**장면 6은 이미 확인된 보고본(RPT61-v1)을 조회하는 시점(2028-01-14 11:00)에서 시작한다**(구현명세
11장). 자료 준비·
완료 판단·담당 임원 확인 → 경영관리 임원 종합 확인 → 보고본 확정 → 대표 보고(S01~S13)는 실제 업무로
끝나 있고, 그
기록(SC06완료판단·SC06Agent·SC06보고)을 적재한다. 시연은 두 화면·세 동작의 **조회**다 — 조회는
상태·이력을 바꾸지
않는다(J608, AT61-09). 결재를 다시 하지 않는다(P605).

* **장면 5 FC51과 잇는다.** 데모 실행 id가 장면 1~5와 같고, 장면 5 공식본 FC51 산정본의 Q4 과제
  효과가 BASE61 기대와
  원 단위로 같아야 적재한다(CK61-14) — 다르면 409. FC51 연간 전망·Target·부족은 그대로
  둔다(AT61-12).
* **적재는 검증 뒤 한 번에 한다**(구현명세 8장). 필수 칸·키 유일성·숫자형 — 숫자 칸에 오류값이
  있으면 적재 자체를
  거절한다(422, 일부만 적재된 상태를 내보내지 않는다). 연결·시간 순서가 어긋난 주문과 중복 키는
  **대사 대기**로 두고
  효과에 넣지 않는다(X61-03). 미확인 값(null)은 받되 0으로 바꾸지 않는다(X61-01).
* **수집 상태와 업무 판단은 따로다**(J601~605, M602 검토 의견). 미비가 있어도 대체 근거·영향
  판단·판단자가 있으면 검토
  가능이고, 미비 항목·담당·보완기한은 지우지 않는다. 대체 근거가 없으면 판단 보류다(X61-02).
* **보고본은 산정 버전에 묶인다.** 확정 뒤 수치가 바뀌면(재적재) 새 산정 버전이 생기고 RPT61-v1은
  그대로다 — 영향받는
  확인(담당 임원 → 종합 → 확정)을 다시 해야 한다고 표시한다(X61-05, AT61-06). 변경 저장 API는 열지
  않는다(9장).
* **Agent 기록은 후보와 사람 판단을 나눠 둔다**(AG61~63). 사람 보정이 없는 초안은 후보다(X61-04) —
  원인 집계는 거래마다의
  최종원인(사람 확인 결과)으로만 한다.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from app.sc01.domain import USERS, DomainError
from app.sc05 import domain as sc05_domain
from app.sc06 import calc
from app.sc06.seed import SEED_ID, Seed, kst

REVIEW_ID = "RV61"
REPORT_VERSION = "RPT61-v1"
BASELINE_VERSION = "FC51"
FOCUS_TASK = "ACT42"
FOCUS_ORDER = "PO61-1103"
SOURCE_HANDOFF = "HANDOFF51"
CASES = {"BASE": "기본 시연"}

#: 데이터의 가상 계정 → NowView 사용자(장면 5와 같은 대응)
ACCOUNTS = sc05_domain.ACCOUNTS
#: 검토건 RV61을 볼 수 있는 사람 — 검토·확인·보고에 참여한 조직(경영관리·구매·생산·품질·대표)과
# 시연관리자. 그 밖의
#: 역할(영업·자재 등)은 403이다(구현명세 9장 「허용된 조직·검토건 조회만」). 화면의 역할 선택은
# 신뢰 경계가 아니다(5.4).
READERS = frozenset(
    {
        *(
            ACCOUNTS[k]
            for k in ("USR-FIN", "USR-CFO", "USR-CEO", "USR-PROD", "USR-BUY", "USR-BUY2", "USR-QA")
        ),
        *(ACCOUNTS[k] for k in ("EX-PROD", "EX-BUY")),
        "u-fin-lead",
        "u-demo",
    }
)

#: AG62 초안이 가리킨 원인 후보 — 「주담당 확인 기록이 없어 확인 지연 가능성」(SC06Agent). 후보이지
# 판단이 아니다.
AGENT_CANDIDATE_CAUSE = {"AG62": "INTERNAL"}

#: 거래에 필요한 칸(구현명세 7장) — 원천 열 이름
ORDER_COLUMNS = (
    "order_id", "월", "model_id", "part_id", "change_ref", "수량", "긴급여부", "운송비", "할증",
    "최종원인", "발주_KST", "긴급승인자", "긴급승인_KST", "납기이상", "품질이상", "비용확인",
    "근거",
)  # fmt: skip
CHANGE_COLUMNS = (
    "change_id", "order_id", "접수_KST", "공유_KST", "확인_KST", "요구납기_KST", "정상공급가능_KST",
    "최종원인", "판단사유", "evidence_id",
)  # fmt: skip


class ReadError(DomainError):
    """
    조회 오류 — 화면이 갈라 보일 코드(ACCESS_DENIED·NOT_FOUND·VERSION_MISMATCH·DATA_INCOMPLETE)를
    싣는다.
    """

    def __init__(self, message: str, status: int, code: str) -> None:
        super().__init__(message, status)
        self.code = code


# ─────────────────────────── 값 읽기 ───────────────────────────


def _amount(value: Any, where: str) -> int | None:
    """
    원 정수. 쉼표 문자열은 읽고, 빈 칸은 미확인(None)이다. 숫자가 아니면 적재를 거절한다(8장 1단계).
    """
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise DomainError(f"{where}: 숫자 칸에 참/거짓 값", 422)
    if isinstance(value, int | float):
        if float(value) != int(value):
            raise DomainError(f"{where}: 원 단위 정수가 아니다({value})", 422)
        return int(value)
    text = str(value).replace(",", "").strip()
    if not re.fullmatch(r"-?\d+", text):
        raise DomainError(f"{where}: 숫자가 아니다({value!r})", 422)
    return int(text)


def _month(value: Any) -> str:
    return (kst(value) or "")[:10]


def _ids(value: Any) -> list[str]:
    return [v.strip() for v in str(value or "").split(";") if v.strip()]


def _require_columns(rows: list[dict[str, Any]], columns: tuple[str, ...], sheet: str) -> None:
    if rows and (missing := [c for c in columns if c not in rows[0]]):
        raise DomainError(f"{sheet}: 필수 열이 없다 — {', '.join(missing)}", 422)


def who(account: str | None) -> dict[str, Any] | None:
    """데이터 계정(USR-FIN …) → 화면에 보일 이름. 계정이 아닌 글(「품질담당」)은 그대로 둔다."""
    if not account:
        return None
    uid = ACCOUNTS.get(account)
    user = USERS.get(uid or "", {})
    return {
        "account": account,
        "userId": uid,
        "name": user.get("name", account),
        "role": user.get("role"),
    }


# ─────────────────────────── 적재 (구현명세 7·8장) ───────────────────────────


def load_batch(seed: Seed, rows: dict[str, list[dict[str, Any]]] | None = None) -> dict[str, Any]:
    """
    원천 시트 → 검증된 엔터티. `rows`는 시험이 예외 fixture(복제본)를 넣는 자리다 — 기본은 시드
    그대로다. 오류값·
    필수 열 누락은 422로 적재 전체를 거절하고, 키 중복·연결 누락·시간 역전은 해당 거래를 대사
    대기로 둔다.
    """
    src = {name: [dict(r) for r in seed.rows(name)] for name in seed.sheets}
    src.update(rows or {})
    problems: list[str] = []
    settings = {str(r["key"]): r["value"] for r in src["SC06설정"]}

    baselines = []
    for r in src["SC06기준"]:
        where = f"SC06기준 {r['baseline_id']}"
        baselines.append(
            {
                "baseline_id": r["baseline_id"],
                "task_id": r["task_id"],
                "month": _month(r["월"]),
                "qty": _amount(r["전망수량"], where) or 0,
                "avoid": _amount(r["회피단가"], where) or 0,
                "add": _amount(r["추가단가"], where) or 0,
                "logistics": _amount(r["물류단가"], where) or 0,
                "base_count": _amount(r["기준긴급건"], where) or 0,
                "forecast_count": _amount(r["전망긴급건"], where) or 0,
                "unit_cost": _amount(r["건당비용"], where) or 0,
                "support": _amount(r["지원비"], where) or 0,
                "one_off": _amount(r["일회성비"], where) or 0,
                "expected_sheet": _amount(r["기대순효과"], where),
                "source": r["원천"],
            }
        )
    if len({(b["task_id"], b["month"]) for b in baselines}) != len(baselines):
        raise DomainError("SC06기준: 과제·월 키가 겹친다 — 기대를 두 번 셀 수 있다", 422)

    actuals = []
    for r in src["SC06실행실적"]:
        where = f"SC06실행실적 {r['actual_id']}"
        actuals.append(
            {
                "actual_id": r["actual_id"],
                "task_id": r["task_id"],
                "month": _month(r["월"]),
                "qty": _amount(r["적용수량"], where),
                "avoid": _amount(r["회피단가"], where),
                "add": _amount(r["추가단가"], where),
                "logistics": _amount(r["물류단가"], where),
                "other": _amount(r["기타비용"], where) or 0,
                "fixed_saving": _amount(r["고정비절감"], where) or 0,
                "evidence_id": r["근거"],
            }
        )
    opcosts = [
        {
            "cost_id": r["cost_id"],
            "task_id": r["task_id"],
            "month": _month(r["귀속월"]),
            "amount": _amount(r["금액"], f"SC06운영비 {r['cost_id']}") or 0,
            "item": r["항목"],
            "evidence_id": r["근거"],
        }
        for r in src["SC06운영비"]
    ]

    _require_columns(src["SC06변경근거"], CHANGE_COLUMNS, "SC06변경근거")
    changes: dict[str, dict[str, Any]] = {}
    for r in src["SC06변경근거"]:
        c = {
            "change_id": r["change_id"],
            "order_id": r["order_id"],
            "received_at": kst(r["접수_KST"]),
            "shared_at": kst(r["공유_KST"]),
            "confirmed_at": kst(r["확인_KST"]),
            "required_at": kst(r["요구납기_KST"]),
            "supply_at": kst(r["정상공급가능_KST"]),
            "cause": r["최종원인"],
            "reason": r["판단사유"],
            "evidence_id": r["evidence_id"],
        }
        if c["change_id"] in changes:
            problems.append(f"{c['change_id']}: 변경근거 키 중복 — 뒤의 행은 대사 대기")
            continue
        times = [c["received_at"], c["shared_at"], c["confirmed_at"]]
        known = [t for t in times if t is not None]
        if known != sorted(known, key=datetime.fromisoformat):
            problems.append(f"{c['change_id']}: 수신 ≤ 공유 ≤ 확인 순서가 아니다")
            c["held"] = True
        changes[c["change_id"]] = {**c, **calc.change_minutes(c)}

    _require_columns(src["SC06구매거래"], ORDER_COLUMNS, "SC06구매거래")
    orders: dict[str, dict[str, Any]] = {}
    held: list[dict[str, Any]] = []
    for seq, r in enumerate(src["SC06구매거래"]):
        where = f"SC06구매거래 {r['order_id']}"
        o = {
            "order_id": str(r["order_id"]),
            "seq": seq,
            "task_id": FOCUS_TASK,
            "month": _month(r["월"]),
            "model_id": r["model_id"],
            "part_id": r["part_id"],
            "change_ref": r["change_ref"] or None,
            "qty": _amount(r["수량"], where) or 0,
            "urgent": bool(_amount(r["긴급여부"], where)),
            "freight": _amount(r["운송비"], where),
            "surcharge": _amount(r["할증"], where),
            "cause": r["최종원인"] or None,
            "ordered_at": kst(r["발주_KST"]),
            "approver": r["긴급승인자"] or None,
            "approved_at": kst(r["긴급승인_KST"]),
            "delivery_issue": _amount(r["납기이상"], where) or 0,
            "quality_issue": _amount(r["품질이상"], where) or 0,
            "cost_check": r["비용확인"],
            "evidence_id": r["근거"],
            "held": False,
            "hold_reasons": [],
        }
        if o["order_id"] in orders:
            # X61-03 — 같은 키가 또 오면 앞의 것을 지키고 뒤의 것은 효과에 넣지 않는다(이중 합산
            # 금지)
            held.append({**o, "hold_reasons": ["order_id 중복 — 대사 대기"]})
            problems.append(
                f"{o['order_id']}: 주문 키 중복 적재 — 뒤의 행을 대사 대기로 두고 효과에서 뺐다"
            )
            continue
        if o["urgent"]:
            for key, label in (
                ("change_ref", "변경근거 연결"),
                ("approver", "긴급 승인자"),
                ("approved_at", "긴급 승인시각"),
                ("evidence_id", "근거"),
            ):
                if not o[key]:
                    o["hold_reasons"].append(f"긴급 주문에 {label}이 없다")
            ch = changes.get(o["change_ref"] or "")
            if o["change_ref"] and (ch is None or ch["order_id"] != o["order_id"]):
                o["hold_reasons"].append(f"변경근거 {o['change_ref']}가 이 주문을 가리키지 않는다")
            if (
                o["approved_at"]
                and o["ordered_at"]
                and datetime.fromisoformat(o["approved_at"])
                > datetime.fromisoformat(o["ordered_at"])
            ):
                o["hold_reasons"].append("긴급 승인 전에 발주했다")
        if o["hold_reasons"]:
            o["held"] = True
            problems.extend(f"{o['order_id']}: {why} — 대사 대기" for why in o["hold_reasons"])
        orders[o["order_id"]] = o

    return {
        "batch_id": "IMP61-1",
        "seed_id": SEED_ID,
        "sha256": seed.sha256,
        "settings": {
            "review_id": settings["review_id"],
            "period_start": kst(settings["period_start"]),
            "period_end": kst(settings["period_end"]),
            "data_close": kst(settings["data_close"]),
            "as_of": kst(settings["as_of"]),
            "basis_version": settings["basis_version"],
            "share_minutes": int(settings["share_minutes"]),
            "confirm_minutes": int(settings["confirm_minutes"]),
            "base_count": int(settings["base_count"]),
            "unit_cost": int(settings["unit_cost"]),
            "monthly_support": int(settings["monthly_support"]),
            "report_version": settings["report_version"],
            "report_date": kst(settings["report_date"]),
            "next_review": kst(settings["next_review"]),
            "gap_due": kst(settings["gap_due"]),
            "source_status": settings["source_status"],
        },
        "baselines": baselines,
        "actuals": actuals,
        "opcosts": opcosts,
        "orders": orders,
        "held_orders": held,
        "changes": changes,
        "tasks": _tasks(src["SC06과제성과"]),
        "judgments": _judgments(src["SC06완료판단"]),
        "followups": _followups(src["SC06후속조치"]),
        "evidence": _evidence(src["SC06근거"]),
        "agent_runs": _agent_runs(src["SC06Agent"]),
        "report_records": _report_records(src["SC06보고"]),
        "problems": problems,
    }


def _tasks(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """
    과제 정보 — 이름·완료일·근거·후속 글. 숫자 칸(기대·실현·차이)은 읽지 않는다 — 계산한다. TOTAL은
    엔터티가 아니다.
    """
    return {
        r["task_id"]: {
            "task_id": r["task_id"],
            "name": r["과제명"],
            "completed_at": kst(r["완료일"]),
            "evidence_refs": _ids(r["근거"]),
            "followup": r["후속"],
        }
        for r in rows
        if r["task_id"] in calc.TASKS
    }


def _judgments(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out = {}
    for r in rows:
        found = re.search(r"ACT4\d", str(r["대상"]))
        out[r["judgment_id"]] = {
            "judgment_id": r["judgment_id"],
            "task_id": found.group(0) if found else None,
            "target": r["대상"],
            "collection_label": r["수집상태"],
            "collection_state": "COMPLETE" if r["수집상태"] == "수집 완료" else "PARTIAL",
            "missing": r["미비항목"] or None,
            "alternatives": _ids(r["대체근거"]),
            "impact": r["영향판단"] or None,
            "decision": r["업무판단"] or None,
            "judged_by": r["판단자"] or None,
            "judged_at": kst(r["판단_KST"]),
            "owner": r["담당"] or None,
            "due_at": kst(r["보완기한_KST"]),
            "evidence_id": r["근거"],
        }
    return out


def judgment_state(j: dict[str, Any]) -> dict[str, Any]:
    """
    업무 판단(J601~605). 수집 상태와 따로 본다 — 미비가 있어도 대체 근거·영향 판단·판단자·시각이
    있으면 검토 가능이다.
    대체 근거가 없거나 영향이 불명이면 판단 보류다(X61-02). 판단 기록이 없으면 자동 완료로 두지
    않는다.
    """
    reasons = []
    if not j["judged_by"] or not j["judged_at"] or not j["decision"]:
        reasons.append("판단자·판단 시각·업무 판단 기록이 없다 — 자동 완료로 두지 않는다")
    if j["collection_state"] == "PARTIAL":
        if not j["alternatives"]:
            reasons.append("미비 자료를 대신할 근거가 없다")
        if not j["impact"]:
            reasons.append("미비가 금액·이행 판단에 주는 영향이 판단되지 않았다")
        if not j["owner"] or not j["due_at"]:
            reasons.append("미비 보완 담당·기한이 없다")
    held = bool(reasons)
    return {
        "judgment_state": "HOLD" if held else "REVIEWABLE",
        "activity_state": "HOLD"
        if held
        else ("COMPLETION_CONFIRMED" if "완료 확인" in (j["decision"] or "") else "REVIEWED"),
        "hold_reasons": reasons,
    }


def _estimation(value: int | None, note: str | None) -> dict[str, Any]:
    """
    효과·예산 — null은 미산정·비해당이고, 확인된 0만 0이다(X61-06: 0원 승인으로 읽히면 안 된다).
    """
    text = str(note or "")
    if value is not None:
        return {"krw": value, "estimation_status": "CONFIRMED", "note": text or None}
    if "해당 없음" in text:
        return {"krw": None, "estimation_status": "NOT_APPLICABLE", "note": text}
    return {"krw": None, "estimation_status": "NOT_ESTIMATED", "note": text or None}


def _followups(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out = {}
    for seq, r in enumerate(rows):
        fid = r["followup_id"]
        out[fid] = {
            "followup_id": fid,
            "seq": seq,
            "kind": r["유형"],
            "links": _ids(r["연결"]),
            "causes": _ids(r["원인"]),
            "content": r["내용"],
            "owner": r["책임"],
            "cooperation": _ids(r["협조"]),
            "state": r["상태"],
            "registered_at": kst(r["등록_KST"]),
            "due_at": kst(r["기한_KST"]),
            "next_check_at": kst(r["다음확인_KST"]),
            "effect": _estimation(_amount(r["효과"], f"SC06후속조치 {fid} 효과"), r["효과상태"]),
            "budget": _estimation(_amount(r["예산"], f"SC06후속조치 {fid} 예산"), r["예산상태"]),
            "scope_check": r["중복·범위판단"],
        }
    return out


def _evidence(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        r["evidence_id"]: {
            "evidence_id": r["evidence_id"],
            "kind": r["유형"],
            "target": r["대상"],
            "written_at": kst(r["작성_KST"]),
            "written_by": r["작성자"],
            "body": r["본문"],
            "checked_by": r["확인자"],
            "checked_at": kst(r["확인_KST"]),
        }
        for r in rows
    }


def _agent_runs(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out = {}
    for seq, r in enumerate(rows):
        reviewed = bool(r["사람 보정·판단"]) and bool(r["확인자"]) and bool(r["확인_KST"])
        out[r["run_id"]] = {
            "run_id": r["run_id"],
            "seq": seq,
            "at": kst(r["시각_KST"]),
            "input_scope": r["입력범위"],
            "task": r["Agent 수행"],
            "draft": r["초안"],
            "candidate_cause": AGENT_CANDIDATE_CAUSE.get(r["run_id"]),
            "human": r["사람 보정·판단"] or None,
            "reviewed_by": r["확인자"] or None,
            "reviewed_at": kst(r["확인_KST"]),
            "links": _ids(r["연결"]),
            # 사람 확인 전 초안은 후보다 — Agent가 완료·원인·보고를 스스로 확정하지 않는다(X61-04)
            "state": "HUMAN_REVIEWED" if reviewed else "CANDIDATE",
            # 고정 데이터 재현이다 — 실시간 생성처럼 보이지 않는다(구현명세 11장 「Agent 검토
            # 이력」)
            "mode": "REPLAY",
        }
    return out


def _report_records(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        r["record_id"]: {
            "record_id": r["record_id"],
            "seq": seq,
            "version": r["대상버전"],
            "step": r["단계"],
            "actor": r["행위자"],
            "at": kst(r["시각_KST"]),
            "state": r["상태"],
            "content": r["내용·범위"],
            "refs": _ids(r["근거"]),
            "tasks": sorted(
                set(re.findall(r"ACT4\d", str(r["내용·범위"]).replace("ACT42·43", "ACT42 ACT43")))
            ),
        }
        for seq, r in enumerate(rows)
    }


# ─────────────────────────── 산정 · 보고 결합 ───────────────────────────


def sc05_link(sc05_doc: dict) -> dict[str, Any]:
    """
    장면 5 결과의 스냅샷 — FC51 공식본·산정본·HANDOFF51. 장면 5를 초기화해도 장면 6 근거는 그 시점
    것이다.
    """
    if sc05_doc.get("handoff") is None:
        raise DomainError(
            "결정 실행·계획 갱신이 완료(HANDOFF51)되지 않았다 — 완료·성과 검토는 결정 실행·계획 "
            "갱신 인계에서 시작한다", 409
        )
    official = sc05_doc["forecasts"][sc05_doc["official"]]
    run = sc05_doc["runs"][official["run_id"]]
    return {
        "handoff_id": sc05_doc["handoff"]["handoff_id"],
        "official": official["forecast_id"],
        "run_id": run["run_id"],
        "run_hash": official["run_hash"],
        "approved_at": official.get("approved_at"),
        "published_at": official.get("published_at"),
        "annual": run["annual"],
        "target": run["target"],
        "gap": run["gap"],
        "months": [
            {k: m[k] for k in ("period", "target", "profit", "effect")}
            for m in run["months"]
            if m["period"] in calc.MONTHS
        ],
        "effects": [
            {"task_id": e["task_id"], "month": e["month"], "net": e["net"]}
            for e in run["effects"]
            if e["month"] in calc.MONTHS
        ],
        "followups": [
            {k: f.get(k) for k in ("followup_id", "state", "owner", "due_at")}
            for f in sc05_doc["handoff"]["followups"]
        ],
        "risk": sc05_doc["handoff"]["state_snapshot"]["risk"],
        "case_id": sc05_doc["case_id"],
    }


def calculate(batch: dict[str, Any], sc05: dict[str, Any], version: str) -> dict[str, Any]:
    """거래 비용 → 월 효과 → 과제 효과 → 합계(결정적). 같은 입력이면 같은 지문이다."""
    orders = [o for o in batch["orders"].values() if not o["held"]]
    held = [o for o in batch["orders"].values() if o["held"]]
    # 대사 대기 긴급 주문은 비용을 모른다 — 그 달 ACT42 효과는 산정 보류다(0으로 넣지 않는다)
    counted = orders + [{**o, "freight": None} for o in held if o["urgent"]]
    try:
        months = calc.month_effects(batch["baselines"], batch["actuals"], counted, batch["opcosts"])
    except calc.CalcError as exc:
        raise DomainError(str(exc), 422) from exc
    tasks = calc.task_effects(months)
    s = batch["settings"]
    causes = calc.causes(counted)
    totals = calc.totals(tasks)
    profit = calc.quarter_profit(sc05["months"], months)
    metrics = calc.metrics(
        counted,
        list(batch["changes"].values()),
        batch["opcosts"],
        batch["baselines"],
        share_limit=s["share_minutes"],
        confirm_limit=s["confirm_minutes"],
    )
    residual = calc.snapshot_residual(batch["baselines"], sc05["effects"])
    pending = [m["effect_id"] for m in months if m["status"] == "PENDING"]
    inputs = {
        "baselines": batch["baselines"],
        "actuals": batch["actuals"],
        "opcosts": batch["opcosts"],
        "orders": sorted(
            (
                (o["order_id"], o["freight"], o["surcharge"], o["urgent"], o["cause"], o["held"])
                for o in counted
            ),
            key=str,
        ),
    }
    return {
        "calculation_version": version,
        "calculation_hash": calc.calculation_hash(inputs),
        "basis_version": BASELINE_VERSION,
        "months": months,
        "tasks": tasks,
        "totals": totals,
        "causes": causes,
        "metrics": metrics,
        "quarter_profit": profit,
        "snapshot_residual": residual,
        "pending_effects": pending,
        # 대사 대기(연결 누락·중복 키)가 하나라도 있으면 자료는 불완전이다 — 효과가 다 산정됐어도
        # 그렇게 말한다
        "reconcile_pending": [o["order_id"] for o in held + batch["held_orders"]],
        "data_status": "INCOMPLETE" if pending or held or batch["held_orders"] else "COMPLETE",
        "checks": _checks(batch, months, tasks, totals, causes, metrics, profit, residual),
    }


def _checks(
    batch, months, tasks, totals, causes, metrics, profit, residual
) -> list[dict[str, Any]]:
    """SC06검증 17항목을 계산으로 다시 낸다 — 검증표의 PASS 글을 옮기지 않는다(구현명세 8장)."""
    m = {x["metric_id"]: x["value"] for x in metrics}
    by_task = {t["task_id"]: t for t in tasks}
    act42 = {x["month"]: x for x in months if x["task_id"] == FOCUS_TASK}
    out = [
        ("CK61-01", "FC51 Q4 기대효과", totals["expected_krw"]),
        ("CK61-02", "Q4 확인 효과", totals["actual_krw"]),
        ("CK61-03", "ACT42 효과", by_task[FOCUS_TASK]["actual_krw"]),
        ("CK61-04", "기대차이", totals["variance_krw"]),
        ("CK61-05", "주문 건수", m["M61-01"]),
        ("CK61-06", "긴급건수", m["M61-02"]),
        ("CK61-07", "긴급비", m["M61-04"]),
        ("CK61-08", "원인금액 대사", causes["cost_residual"]),
        ("CK61-09", "고정비절감", sum(x["fixed_saving"] for x in months)),
        ("CK61-10", "10월 수량", act42[calc.MONTHS[0]]["qty"]),
        ("CK61-11", "11월 수량", act42[calc.MONTHS[1]]["qty"]),
        ("CK61-12", "12월 수량", act42[calc.MONTHS[2]]["qty"]),
        ("CK61-13", "확인 지연(복합 포함)", m["M61-07"]),
        ("CK61-14", "SC05 기대값과 스냅샷 대사", residual),
        ("CK61-15", "원인 건수 대사", causes["count_residual"]),
        ("CK61-16", "Q4 가상 관리손익", profit["quarter"]["profit"]),
        ("CK61-17", "과제 기여 기간 Q4", sum(1 for x in months if x["status"] == "CONFIRMED")),
    ]
    return [{"check_id": c, "label": label, "value": v} for c, label, v in out]


#: 원 → 「91.8백만원」처럼 보고 글에 쓰인 숫자
_MILLION = re.compile(r"(\d+(?:\.\d+)?)백만원")


def report_problems(
    report: dict[str, Any], calculation: dict[str, Any], records: dict[str, dict]
) -> list[str]:
    """
    보고본 정합성(CT611) — 모든 확인이 같은 보고 버전, 담당 임원 → 종합 → 확정 → 보고 순서, 보고
    글의 숫자가 묶인
    산정의 숫자와 같은지. LLM·사람이 쓴 문장의 숫자를 집계 원천으로 쓰지 않고, 거꾸로 산정과
    대조한다.
    """
    out = []
    version = report["report_version"]
    for r in records.values():
        if r["version"] != version:
            out.append(f"{r['record_id']}가 다른 보고 버전({r['version']})을 가리킨다")
    order = ["CF61-P", "CF61-B", "CF61-F", "CF61-R", "CF61-M"]
    times = [records[k]["at"] for k in order if k in records]
    if len(times) == len(order):
        confirm = max(datetime.fromisoformat(t) for t in times[:2])
        rest = [datetime.fromisoformat(t) for t in times[2:]]
        if not (confirm <= rest[0] <= rest[1] <= rest[2]):
            out.append("담당 임원 확인 → 종합 확인 → 보고본 확정 → 대표 보고 순서가 아니다")
    else:
        out.append("확인 이력이 다섯 단계가 아니다 — 한 단계 완료로 전체 확정을 표시하지 않는다")
    text = (records.get("TXT61") or {}).get("content") or ""
    said = {round(float(v) * 1_000_000) for v in _MILLION.findall(text)}
    tasks = {t["task_id"]: t for t in calculation["tasks"]}
    wanted = {
        calculation["totals"]["expected_krw"],
        calculation["totals"]["actual_krw"],
        tasks[FOCUS_TASK]["expected_krw"],
        tasks[FOCUS_TASK]["actual_krw"],
    }
    if None in wanted or not said <= wanted:
        out.append(
            "보고 결론의 숫자가 묶인 산정과 다르다 — 새 산정·보고 버전에서 문구를 다시 확인한다"
        )
    return out


# ─────────────────────────── 문서 ───────────────────────────


def new_review(
    seed: Seed, demo_run_id: str, sc05_doc: dict, *, created_at: datetime, batch=None
) -> dict:
    """
    RV61 검토 문서 — 장면 5 결과와 v0.6 장면 6 원천을 한 번에 적재한다. FC51과 BASE61이 어긋나면
    409(소급 보정 금지).
    """
    sc05 = sc05_link(sc05_doc)
    batch = batch or load_batch(seed)
    first = calculate(batch, sc05, "CALC61-v1")
    if first["snapshot_residual"] != 0:
        raise DomainError(
            "결정 실행·계획 갱신 공식본 FC51의 Q4 과제 효과가 완료·성과 검토 기준(BASE61)과 다르다 "
            "— "
            "기본 시연의 FC51에서만 완료·성과 검토를 "
            f"연다(차이 {first['snapshot_residual']:,}원, 결정 실행·계획 갱신 사례 "
            f"{sc05['case_id']})",
            409,
        )
    s = batch["settings"]
    records = batch["report_records"]
    report = {
        "report_version": s["report_version"],
        "review_id": REVIEW_ID,
        "calculation_version": first["calculation_version"],
        "calculation_hash": first["calculation_hash"],
        "basis_version": BASELINE_VERSION,
        "report_date": s["report_date"],
        "next_review": s["next_review"],
        # 대표 보고(CF61-M)까지 끝났다 — 보고 확정은 과제 실행·예산 승인이 아니다(CT612)
        "state": (records.get("CF61-M") or {}).get("state") or "DRAFT",
        "finalized_at": (records.get("CF61-R") or {}).get("at"),
    }
    report["problems"] = report_problems(report, first, records)
    doc = {
        "scene": "SC06",
        "demo_run_id": demo_run_id,
        "case_id": "BASE",
        "created_at": created_at.isoformat(),
        "clock": s["as_of"],
        # 저장소의 진행 지점 칸 — 장면 6은 보고본 조회 시점 하나뿐이다
        "step": "U601",
        "sc05": sc05,
        "batch": {k: batch[k] for k in ("batch_id", "seed_id", "sha256", "problems")}
        | {
            "loaded_at": s["as_of"],
            "counts": {
                "orders": len(batch["orders"]),
                "held_orders": len(batch["held_orders"])
                + sum(1 for o in batch["orders"].values() if o["held"]),
                "changes": len(batch["changes"]),
                "evidence": len(batch["evidence"]),
            },
        },
        "settings": s,
        **{
            k: batch[k]
            for k in (
                "baselines",
                "actuals",
                "opcosts",
                "orders",
                "held_orders",
                "changes",
                "tasks",
                "judgments",
                "followups",
                "evidence",
                "agent_runs",
                "report_records",
            )
        },
        "calculations": {first["calculation_version"]: first},
        "current_calculation": first["calculation_version"],
        "report": report,
        "risk": {"risk_id": "RISK61", "state": "OPEN", "source": sc05["risk"]},
        "audit": [],
    }
    audit(
        doc,
        actor="u-demo",
        action="sc06_loaded",
        batch=doc["batch"]["batch_id"],
        sha256=seed.sha256,
    )
    return doc


def reimport(
    doc: dict, seed: Seed, rows: dict[str, list[dict[str, Any]]], *, actor: str, reason: str
) -> dict:
    """
    확정 뒤의 수치 변경(X61-05·AT61-06) — 고친 원천을 다시 적재해 **새 산정 버전**을 만든다.
    RPT61-v1과 그 산정은
    그대로이고, 수치가 달라진 과제에 걸린 확인부터 다시 해야 한다고 표시한다. 변경 저장 API로 열지
    않는다 — 재적재는
    개발용 별도 권한이다(구현명세 11장).
    """
    if not reason.strip():
        raise DomainError("재적재 사유를 적는다", 422)
    batch = load_batch(seed, rows)
    version = f"CALC61-v{len(doc['calculations']) + 1}"
    new = calculate(batch, doc["sc05"], version)
    same = next(
        (
            c
            for c in doc["calculations"].values()
            if c["calculation_hash"] == new["calculation_hash"]
        ),
        None,
    )
    if same is not None:
        # 이미 있는 산정과 같은 입력이다 — 새 버전을 만들지 않고 그 산정을 현재로 돌린다
        if doc["current_calculation"] != same["calculation_version"]:
            doc["current_calculation"] = same["calculation_version"]
            audit(
                doc,
                actor=actor,
                action="calculation_restored",
                version=same["calculation_version"],
                reason=reason,
            )
        return doc
    old = doc["calculations"][doc["report"]["calculation_version"]]
    before = {t["task_id"]: t["actual_krw"] for t in old["tasks"]}
    changed = sorted(t["task_id"] for t in new["tasks"] if t["actual_krw"] != before[t["task_id"]])
    redo = [
        r["record_id"]
        for r in sorted(doc["report_records"].values(), key=lambda r: r["seq"])
        if r["record_id"].startswith("CF61-") and (not r["tasks"] or set(r["tasks"]) & set(changed))
    ]
    new["reason"] = reason
    new["changed_tasks"] = changed
    new["reconfirm"] = redo
    new["created_by"] = actor
    doc["calculations"][version] = new
    doc["current_calculation"] = version
    audit(
        doc,
        actor=actor,
        action="calculation_versioned",
        version=version,
        reason=reason,
        changed_tasks=changed,
        report=doc["report"]["report_version"],
    )
    return doc


def audit(doc: dict, *, actor: str, action: str, **detail: Any) -> None:
    user = USERS.get(actor, {"name": actor, "role": "system"})
    doc["audit"].append(
        {
            "at": doc["clock"],
            "actor": actor,
            "actorName": user["name"],
            "action": action,
            "detail": detail,
        }
    )


# ─────────────────────────── 조회 (구현명세 10장) ───────────────────────────


def check_reader(actor: str | None) -> None:
    if not actor:
        raise ReadError("X-Demo-Actor 헤더가 필요하다", 403, "ACCESS_DENIED")
    if actor not in READERS:
        # 근거 내용·금액을 오류 메시지에 싣지 않는다
        raise ReadError("이 검토건을 볼 권한이 없다", 403, "ACCESS_DENIED")


def check_version(doc: dict, report_version: str | None) -> None:
    if report_version is not None and report_version != doc["report"]["report_version"]:
        known = {doc["report"]["report_version"]}
        if report_version.startswith("RPT61-") and report_version not in known:
            raise ReadError(
                f"화면의 보고 버전({report_version})이 응답 버전"
                f"({doc['report']['report_version']})과 다르다 — 다시 조회한다",
                409,
                "VERSION_MISMATCH",
            )
        raise ReadError(f"없는 보고 버전: {report_version}", 404, "NOT_FOUND")


def check_review(review_id: str) -> None:
    if review_id != REVIEW_ID:
        raise ReadError(f"없는 검토건: {review_id}", 404, "NOT_FOUND")


def _context(doc: dict, calculation: dict) -> dict[str, Any]:
    newer = doc["current_calculation"] != calculation["calculation_version"]
    current = doc["calculations"][doc["current_calculation"]]
    return {
        "review_id": REVIEW_ID,
        "report_version": doc["report"]["report_version"],
        "calculation_version": calculation["calculation_version"],
        "calculation_hash": calculation["calculation_hash"],
        "as_of": doc["clock"],
        "data_status": calculation["data_status"],
        "basis_version": BASELINE_VERSION,
        # 보고본 뒤에 새 산정이 생겼다 — 이 보고본 숫자는 그대로 보이고, 새 버전의 확인이
        # 필요하다고 함께 알린다
        "newer_calculation": None
        if not newer
        else {
            "calculation_version": current["calculation_version"],
            "reason": current.get("reason"),
            "changed_tasks": current.get("changed_tasks", []),
            "reconfirm": current.get("reconfirm", []),
            "totals": current["totals"],
            "tasks": current["tasks"],
        },
    }


def _bound(doc: dict) -> dict:
    return doc["calculations"][doc["report"]["calculation_version"]]


def _task_rows(doc: dict, calculation: dict) -> list[dict[str, Any]]:
    by_task = {j["task_id"]: j for j in doc["judgments"].values()}
    rows = []
    for t in calculation["tasks"]:
        meta = doc["tasks"].get(t["task_id"], {})
        j = by_task.get(t["task_id"])
        state = (
            judgment_state(j)
            if j
            else {
                "judgment_state": "HOLD",
                "activity_state": "HOLD",
                "hold_reasons": ["완료 판단 기록이 없다"],
            }
        )
        rows.append(
            {
                **t,
                "name": meta.get("name"),
                "completed_at": meta.get("completed_at"),
                "activity_judgment": state["activity_state"],
                "judgment_id": j["judgment_id"] if j else None,
                "performance": calc.performance_word(t),
                "evidence_refs": meta.get("evidence_refs", []),
                "followup": meta.get("followup"),
                "focus": t["task_id"] == FOCUS_TASK,
            }
        )
    return rows


def _judgment_view(j: dict) -> dict[str, Any]:
    return {
        **j,
        **judgment_state(j),
        "judged_by": who(j["judged_by"]),
        "owner": who(j["owner"]),
    }


def _agent_view(run: dict) -> dict[str, Any]:
    return {**run, "reviewed_by": who(run["reviewed_by"])}


def summary(doc: dict, *, actor: str | None, report_version: str | None = None) -> dict[str, Any]:
    """U601 요약 — 기간·기준·3과제·합계·완료 판단·Agent 요약. 보고본에 묶인 산정의 숫자다."""
    check_reader(actor)
    check_version(doc, report_version)
    c = _bound(doc)
    s = doc["settings"]
    return {
        **_context(doc, c),
        "period": {"start": s["period_start"], "end": s["period_end"], "label": "2027 Q4"},
        "data_close": s["data_close"],
        "report_date": s["report_date"],
        "scope": {
            "plant": "울산",
            "product": "A제품",
            "models": "a~e",
            "unit": "KRW",
            "display": "백만원",
        },
        "tasks": _task_rows(doc, c),
        "totals": c["totals"],
        "judgments": [_judgment_view(j) for j in doc["judgments"].values()],
        "agent": [
            _agent_view(doc["agent_runs"][k]) for k in ("AG61", "AG63") if k in doc["agent_runs"]
        ],
        "cause_overview": [
            {k: g[k] for k in ("cause", "label", "count", "actual_urgent_cost_krw")}
            for g in c["causes"]["groups"]
        ],
        "batch": doc["batch"],
        "checks": c["checks"],
    }


def variance(
    doc: dict, task_id: str, *, actor: str | None, report_version: str | None = None
) -> dict[str, Any]:
    """
    U601 상세 — ACT42 원인별 건수·비용, 대표 주문 PO61-1103의 변경·근거, AG62 초안과 사람 보정.
    """
    check_reader(actor)
    check_version(doc, report_version)
    if task_id not in calc.TASKS:
        raise ReadError(f"없는 과제: {task_id}", 404, "NOT_FOUND")
    if task_id != FOCUS_TASK:
        raise ReadError(
            f"{task_id}는 요약과 근거만 본다 — 상세 차이는 {FOCUS_TASK}다", 404, "NOT_FOUND"
        )
    c = _bound(doc)
    order = doc["orders"].get(FOCUS_ORDER)
    change = doc["changes"].get((order or {}).get("change_ref") or "")
    task = next(t for t in c["tasks"] if t["task_id"] == task_id)
    metrics = {m["metric_id"]: m for m in c["metrics"]}
    return {
        **_context(doc, c),
        "task_id": task_id,
        "task": task,
        # 원인별 비용은 긴급 14건 전체의 실제 비용이다 — 기대 대비 차이(variance_krw)와 다른 지표다
        "cause_groups": c["causes"]["groups"],
        "cause_total": c["causes"]["total"],
        "cause_reconciliation": {
            k: c["causes"][k] for k in ("count_residual", "cost_residual", "problems")
        },
        "variance_krw": task["variance_krw"],
        "months": [m for m in c["months"] if m["task_id"] == task_id],
        "metrics": [
            metrics[k]
            for k in (
                "M61-01",
                "M61-02",
                "M61-04",
                "M61-05",
                "M61-06",
                "M61-07",
                "M61-08",
                "M61-09",
                "M61-10",
                "M61-11",
                "M61-12",
            )
        ],
        "limits": {
            "share_minutes": doc["settings"]["share_minutes"],
            "confirm_minutes": doc["settings"]["confirm_minutes"],
        },
        "order": None
        if order is None
        else {**order, "urgent_cost": calc.urgent_cost(order), "approver": who(order["approver"])},
        "change": change,
        "evidence": [
            doc["evidence"][e]["evidence_id"]
            for e in (order or {}).get("evidence_id", "").split(";")
            if e in doc["evidence"]
        ],
        "agent": _agent_view(doc["agent_runs"]["AG62"]) if "AG62" in doc["agent_runs"] else None,
        "urgent_orders": [
            {
                "order_id": o["order_id"],
                "month": o["month"],
                "cause": o["cause"],
                "urgent_cost": calc.urgent_cost(o),
                "held": o["held"],
                **{
                    k: (doc["changes"].get(o["change_ref"] or "") or {}).get(k)
                    for k in ("share_minutes", "confirm_minutes", "supply_gap_minutes")
                },
            }
            for o in sorted(doc["orders"].values(), key=lambda o: o["seq"])
            if o["urgent"]
        ],
    }


def evidence(
    doc: dict, evidence_id: str, *, actor: str | None, report_version: str | None = None
) -> dict[str, Any]:
    """근거 본문과 작성·확인 이력 — 가상 증빙이다(실제 첨부 다운로드처럼 보이지 않는다)."""
    check_reader(actor)
    check_version(doc, report_version)
    found = doc["evidence"].get(evidence_id)
    if found is None:
        raise ReadError(f"없는 근거: {evidence_id}", 404, "NOT_FOUND")
    return {
        **_context(doc, _bound(doc)),
        **found,
        "written_by": who(found["written_by"]),
        "checked_by": who(found["checked_by"]),
        "virtual": True,
    }


def _record_view(record: dict | None) -> dict[str, Any] | None:
    return None if record is None else {**record, "actor": who(record["actor"])}


def report(doc: dict, report_version: str, *, actor: str | None) -> dict[str, Any]:
    """U602 — 성과·확인 문구·FUP61·PROP61·FUP62·RISK61·확인 이력·다음 보고."""
    check_reader(actor)
    check_version(doc, report_version)
    c = _bound(doc)
    records = sorted(doc["report_records"].values(), key=lambda r: r["seq"])
    steps = [r for r in records if r["record_id"].startswith("CF61-")]
    tasks = {t["task_id"]: t for t in c["tasks"]}
    return {
        **_context(doc, c),
        "state": doc["report"]["state"],
        "finalized_at": doc["report"]["finalized_at"],
        "report_date": doc["report"]["report_date"],
        "next_review": doc["report"]["next_review"],
        "problems": doc["report"]["problems"],
        "totals": c["totals"],
        "focus": tasks[FOCUS_TASK],
        "conclusion": _record_view(doc["report_records"].get("TXT61")),
        "note": _record_view(doc["report_records"].get("NOTE61")),
        "confirmations": [_record_view(r) for r in steps],
        "followups": [
            {
                **f,
                "owner": who(f["owner"]),
                "cooperation": [who(x) for x in f["cooperation"]],
            }
            for f in sorted(doc["followups"].values(), key=lambda f: f["seq"])
        ],
        "proposal_evidence": doc["evidence"].get("DOC61-PROP"),
        "monitoring": doc["evidence"].get("DOC61-MON"),
        "judgment": _judgment_view(doc["judgments"]["JDG61"])
        if "JDG61" in doc["judgments"]
        else None,
        "risk": doc["risk"],
        "quarter_profit": c["quarter_profit"],
        # 연간 전망·목표는 장면 5 FC51 그대로다 — 장면 6이 고치지 않는다(J610)
        "annual": {k: doc["sc05"][k] for k in ("official", "annual", "target", "gap")},
        "agent": _agent_view(doc["agent_runs"]["AG63"]) if "AG63" in doc["agent_runs"] else None,
    }
