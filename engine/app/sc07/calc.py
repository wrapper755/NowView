"""
SC07 규칙 계산 — 개선 Agent(AGT71-v2)의 근거 결합·원인 후보(구현명세 3장), Agent 입력 투영(4장),
검증 세트
TS71-v1 실행(TC701~708), 적용 상태 판정(5장). **숫자·상태는 여기서만 만든다** — 엑셀의 `SC07판단`·
`SC07검증결과`·`SC07요약`은 기대값이다(시험이 대조한다).

* **대행 확인**(BR701) — 주담당 확인, 또는 업무 범위·유효기간이 맞는 대행의 **실제** 확인 로그. 둘
  다
  유효하면 먼저 한 확인이다. 위임 지정만 있고 확인이 없으면 미확인이다. 대행 유효 플래그는 데모
  적재값이다.
* **소요시간**(BR702) — 최초 공유 → 최초 유효 확인의 달력 시간. 재공유로 시작을 바꾸지 않는다. 시각
  역전은 DATA_INVALID — 원인 판단을 멈춘다. **초 단위로 비교한다**(120분 1초는 초과) — 엑셀은 분으로
  반올림하지만 지금 데이터는 분 단위라 결과가 같다(구현명세 3장).
* **지연**(BR703) — 120분 **초과**(120분은 기준 내). 발주 마감 충족은 따로 본다 — 120분 안이어도
  마감을
  넘길 수 있다(AT706 — 「내부 영향 추가 검토」를 함께 낸다).
* **원인 후보**(BR704~707) — 유효 확인이 없거나 공급 가능일이 없으면 NEED_EVIDENCE(사유를 따로
  낸다).
  내부 제약(120분 초과 **이고** 발주 마감 초과 — `SC07판단` 식과 같다)·적시 주문에도 남는 공급
  제약의
  조합으로 INTERNAL·SUPPLY·MIXED·NO_CONSTRAINT. 비용은 원인에 배분하지 않는다. **후보이지 판단이
  아니다**
  — 확정은 업무 담당자가 한다.
* 누락은 0분·정상이 아니다(BR707) — 없는 기록(MISSING)·조회 권한
  없음(ACCESS_DENIED)·미결합(NOT_JOINED)·
  무효 위임(INVALID_DELEGATION)을 갈라 돌려준다.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

#: 원인 후보 코드 → 화면 말(구현명세 1장 「공통 표시와 예외」)
CAUSE_LABELS = {
    "SUPPLY": "조달 제약",
    "INTERNAL": "내부 지연",
    "MIXED": "복합 제약",
    "NEED_EVIDENCE": "근거 보완 필요",
    "NO_CONSTRAINT": "제약 미확인",
}
#: 근거가 없는 사유(구현명세 6장 예외 계약)
MISSING_REASONS = {
    "MISSING": "자료 누락",
    "ACCESS_DENIED": "조회 권한 없음",
    "NOT_JOINED": "미결합",
    "INVALID_DELEGATION": "유효하지 않은 대행",
    "NOT_CONFIRMED": "확인 기록 없음",
}
#: 근거 칸 → 보완 담당(BR707 「필요한 근거와 확인 담당을 제시」). 데이터 계정이다.
FIELD_OWNERS = {
    "confirmation": "USR-BUY",
    "required_at": "USR-BUY",
    "timely_supply_at": "USR-BUY",
    "order_cutoff_at": "USR-BUY",
    "shared_at": "USR-BUY",
}
FIELD_LABELS = {
    "confirmation": "유효 확인 기록(주담당·대행)",
    "required_at": "요구 납기",
    "timely_supply_at": "적시 주문 공급일",
    "order_cutoff_at": "발주 마감",
    "shared_at": "공유 시각",
}

#: Agent 입력 투영(구현명세 4장). v1은 AG62 당시 조회 동작의 비교용 별칭이다(EV76 — 주담당
#: 확인란·주문
#: 비용). v2는 허용 원시 필드만 — 근거 본문 전체·최종 원인·인적 수정·기대값·사례 이름은 넣지 않는다.
PROJECTIONS: dict[str, tuple[str, ...]] = {
    "PR71-v1": (
        "input_id",
        "order_id",
        "change_id",
        "shared_at",
        "primary_confirmed_at",
        "order_cost",
    ),
    "PR71-v2": (
        "input_id",
        "order_id",
        "change_id",
        "shared_at",
        "primary_confirmed_at",
        "deputy_confirmed_at",
        "delegation",
        "required_at",
        "timely_supply_at",
        "order_cutoff_at",
        "evidence_refs",
        "evidence_status",
        "version_bundle",
    ),
}
#: 정답 유입 차단(BR708·TC706) — Agent 입력에 있으면 안 되는 칸
FORBIDDEN_FIELDS = frozenset(
    {
        "final_cause",  # SC06변경근거 J열
        "judgment_reason",  # SC06변경근거 K열
        "human_correction",  # SC06Agent F열
        "expected",  # SC07검증결과 D열
        "candidate_cause",  # SC07판단 — 재판단 입력이 아니다
        "case_label",  # 「독립 합성: 대행 기간 만료」 같은 사례 이름
        "next_action",
    }
)


def _at(value: str | None) -> datetime | None:
    return None if value is None else datetime.fromisoformat(value)


def _minutes(seconds: int) -> int:
    """화면 표시용 분 — 엑셀 ROUND(…*1440, 0)과 같게 반올림한다. 판정은 초로 한다."""
    return int((Decimal(seconds) / 60).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _status(over: bool | None) -> str:
    return "UNKNOWN" if over is None else ("OVER" if over else "WITHIN")


def assess(case: dict[str, Any], *, threshold_min: int = 120) -> dict[str, Any]:
    """
    검증 입력 하나(IN71…) → 유효 확인·소요시간·지연·마감·공급 제약·원인 후보(`SC07판단` 한 행).
    입력의
    `field_status`가 칸마다 누락 사유(ACCESS_DENIED·NOT_JOINED)를 줄 수 있다 — 없으면 MISSING이다.
    """
    status = dict(case.get("field_status") or {})
    missing: list[dict[str, str]] = []

    def gone(field: str, default: str = "MISSING") -> None:
        reason = status.get(field, default)
        missing.append(
            {
                "field": field,
                "label": FIELD_LABELS[field],
                "reason": reason,
                "reason_label": MISSING_REASONS[reason],
                "owner": FIELD_OWNERS[field],
            }
        )

    shared = _at(case.get("shared_at"))
    primary = _at(case.get("primary_confirmed_at"))
    deputy = _at(case.get("deputy_confirmed_at"))
    deputy_valid = bool(case.get("deputy_valid"))
    candidates: list[tuple[datetime, str]] = []
    if primary is not None:
        candidates.append((primary, "PRIMARY"))
    if deputy is not None and deputy_valid:
        candidates.append((deputy, "DEPUTY"))
    confirmed_at, confirmed_kind = min(candidates) if candidates else (None, None)
    if confirmed_at is None:
        if deputy is not None and not deputy_valid:
            gone("confirmation", "INVALID_DELEGATION")
        elif deputy_valid and deputy is None:
            # 대행 지정만 있고 실제 확인 로그가 없다 — 확인 완료로 인정하지 않는다(BR701·AT703)
            gone("confirmation", "NOT_CONFIRMED")
        else:
            gone("confirmation")
    if shared is None:
        gone("shared_at")

    required = _at(case.get("required_at"))
    supply = _at(case.get("timely_supply_at"))
    cutoff = _at(case.get("order_cutoff_at"))
    if required is None:
        gone("required_at")
    if supply is None:
        gone("timely_supply_at")
    if cutoff is None:
        gone("order_cutoff_at")

    invalid: list[str] = []
    seconds: int | None = None
    if confirmed_at is not None and shared is not None:
        seconds = int((confirmed_at - shared).total_seconds())
        if seconds < 0:
            invalid.append("확인 시각이 공유 시각보다 앞이다(시각 역전)")
    over_threshold = None if seconds is None or invalid else seconds > threshold_min * 60
    over_cutoff = (
        None if confirmed_at is None or cutoff is None or invalid else confirmed_at > cutoff
    )
    supply_late = None if supply is None or required is None else supply > required

    if invalid:
        cause = None
    elif confirmed_at is None or supply_late is None:
        cause = "NEED_EVIDENCE"
    else:
        internal = bool(over_threshold) and bool(over_cutoff)
        if internal:
            cause = "MIXED" if supply_late else "INTERNAL"
        else:
            cause = "SUPPLY" if supply_late else "NO_CONSTRAINT"
    # 120분 안이어도 발주 마감을 넘겼다 — 함께 표시하고 내부 영향의 추가 검토를 요청한다(AT706)
    internal_review = over_threshold is False and over_cutoff is True
    return {
        "input_id": case["input_id"],
        "confirmed_at": None if confirmed_at is None else confirmed_at.isoformat(),
        "confirmed_by": confirmed_kind,
        "elapsed_seconds": seconds if not invalid else None,
        "elapsed_minutes": None if seconds is None or invalid else _minutes(seconds),
        "deadline_status": _status(over_threshold),
        "cutoff_status": _status(over_cutoff),
        "supply_status": _status(supply_late),
        "supply_gap_minutes": (
            None
            if supply is None or required is None
            else _minutes(int((supply - required).total_seconds()))
        ),  # fmt: skip
        "candidate_cause": cause,
        "data_status": "DATA_INVALID" if invalid else ("INCOMPLETE" if missing else "COMPLETE"),
        "invalid": invalid,
        "missing_fields": missing,
        "internal_review": internal_review,
        "threshold_min": threshold_min,
    }


# ─────────────────────────── Agent 입력 투영 ───────────────────────────


def project(case: dict[str, Any], version: str, *, bundle: str | None = None) -> dict[str, Any]:
    """
    검증 입력 → Agent에 넘길 페이로드(허용 칸만). 사례 이름은 원자료 ID일 때만 싣는다 — 「독립 합성:
    대행
    기간 만료」처럼 기대 원인이 드러나는 글은 넣지 않는다(구현명세 4장 「정답 유입 차단」).
    """
    allowed = PROJECTIONS[version]
    source = case.get("change_id")
    full = {
        "input_id": case["input_id"],
        "order_id": case.get("order_id"),
        "change_id": source if source and str(source).startswith("CH") else None,
        "shared_at": case.get("shared_at"),
        "primary_confirmed_at": case.get("primary_confirmed_at"),
        "deputy_confirmed_at": case.get("deputy_confirmed_at"),
        "delegation": {"valid": bool(case.get("deputy_valid"))},
        "required_at": case.get("required_at"),
        "timely_supply_at": case.get("timely_supply_at"),
        "order_cutoff_at": case.get("order_cutoff_at"),
        "evidence_refs": list(case.get("evidence_refs") or []),
        "evidence_status": case.get("evidence_status"),
        "version_bundle": bundle,
        "order_cost": case.get("order_cost"),
    }
    return {k: full[k] for k in allowed}


def leaks(payload: dict[str, Any], expected_codes: set[str]) -> list[str]:
    """페이로드에 정답이 섞였나 — 금지 칸, 그리고 값에 기대 원인 코드가 그대로 있는가(TC706)."""
    found = [f"금지 칸 {k}" for k in payload if k in FORBIDDEN_FIELDS]
    text = json.dumps(payload, ensure_ascii=False)
    found += [f"기대 원인 {code}" for code in sorted(expected_codes) if f'"{code}"' in text]
    return found


def fingerprint(value: Any) -> str:
    """원본 보존 대조용 해시(TC707) — 같은 내용이면 같은 값이다."""
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ─────────────────────────── 검증 세트 ───────────────────────────


def verify(
    cases: list[dict[str, Any]],
    inputs: dict[str, dict[str, Any]],
    *,
    agent_version: str,
    projection: str,
    target_version: str | None,
    preserved: bool,
    threshold_min: int,
    bundle: str,
) -> list[dict[str, Any]]:
    """
    TS71-v1 실행 — 사례마다 관측값을 **규칙으로 다시 계산해** 기대값과 대조한다. 데이터의 가상
    결과·일치
    여부(SIMULATED_HISTORY)는 함께 싣되 판정에 쓰지 않는다(구현명세 5장 「Excel의 PASS 셀을 신뢰하지
    말라」). TC706 정답 차단 · TC707 원본 보존 · TC708 버전 일치는 각각 별도 검사다.
    """
    expected_codes = {c["expected"] for c in cases if c["expected"] in CAUSE_LABELS}
    out = []
    for c in cases:
        ref = c["input_ref"]
        evidence: list[str] = []
        detail: dict[str, Any] = {}
        if ref in inputs:
            a = assess(inputs[ref], threshold_min=threshold_min)
            observed = a["candidate_cause"]
            evidence = list(inputs[ref].get("evidence_refs") or [])
            detail = {"assessment": a}
        elif c["check"] == "TC706":
            found = [
                (iid, leak)
                for iid, case in inputs.items()
                for leak in leaks(project(case, projection, bundle=bundle), expected_codes)
            ]
            observed = "EXCLUDED" if not found else "LEAKED"
            detail = {"projection": projection, "leaks": [f"{i}: {m}" for i, m in found]}
        elif c["check"] == "TC707":
            observed = "UNCHANGED" if preserved else "CHANGED"
        elif c["check"] == "TC708":
            observed = target_version if target_version == agent_version else "MISMATCH"
            detail = {"agent_version": agent_version, "target_version": target_version}
        else:
            observed = None
        out.append(
            {
                **c,
                "observed": observed,
                "status": "PASS" if observed is not None and observed == c["expected"] else "FAIL",
                "evidence_refs": evidence or [ref],
                "agent_version": agent_version,
                **detail,
            }
        )
    return out


# ─────────────────────────── 적용 상태 ───────────────────────────

STATE_LABELS = {
    "ST703": "검증 중 또는 보완 필요",
    "ST704": "검증 완료 — 업무 확인 대기",
    "ST705": "확인 완료 — 적용 대기·예정",
    "ST706": "설정 반영 — 확인 대기",
    "ST707": "운영 설정 반영 확인",
}
#: 확인해야 하는 두 역할(CT704) — 데이터 계정. 구매 임원은 업무 타당성, 경영관리 임원은 측정 기준
#: 일관성과
#: 과거 이력 보존(구현명세 5장).
REQUIRED_CONFIRMERS = {"EX-BUY": "구매 임원", "USR-CFO": "경영관리 임원"}


def application_state(
    *,
    verification: list[dict[str, Any]] | None,
    confirmations: dict[str, dict[str, Any]],
    setting: dict[str, Any] | None,
    target_version: str,
    scope: str,
    as_of: str,
) -> dict[str, Any]:
    """
    적용 상태(ST703~ST707)와 「설정 반영 확인」의 다섯 조건(구현명세 5장). 건수가 아니라 연결된
    레코드로
    본다 — 같은 역할의 두 확인, 다른 버전의 확인, 예약만 된 설정, 미래 시각의 확인은 인정하지
    않는다.
    **운영 실행은 따로다** — 설정 반영을 확인해도 실행 상태는 NOT_CONFIRMED다(실행 id가 없다).
    """
    checks: list[dict[str, Any]] = []
    attention: list[str] = []

    def check(key: str, ok: bool, label: str, detail: str = "") -> bool:
        checks.append({"key": key, "ok": ok, "label": label, "detail": detail})
        return ok

    passed = bool(verification) and all(v["status"] == "PASS" for v in verification or [])
    failed = [v["check"] for v in verification or [] if v["status"] != "PASS"]
    check(
        "verification",
        passed,
        "① 필수 검증 TC701~708이 대상 버전에서 모두 통과",
        "실행 전" if not verification else ("" if passed else f"미충족 {', '.join(failed)}"),
    )
    good = {
        account: c
        for account, c in confirmations.items()
        if account in REQUIRED_CONFIRMERS and c["state"] == "CONFIRMED"
    }
    stale = [a for a, c in good.items() if c["version"] != target_version]
    roles = {a for a, c in good.items() if c["version"] == target_version}
    if stale:
        attention.append("VERSION_MISMATCH")
    confirmed = check(
        "confirmations",
        roles == set(REQUIRED_CONFIRMERS),
        "② 서로 다른 두 필수 역할의 확인 — 대상 버전 일치",
        ", ".join(
            f"{REQUIRED_CONFIRMERS[a]} "
            + ("확인" if a in roles else ("다른 버전" if a in stale else "미확인"))
            for a in REQUIRED_CONFIRMERS
        ),
    )
    applied = setting is not None and setting.get("applied_at") is not None
    version_ok = applied and setting["active_version"] == target_version
    scope_ok = applied and setting.get("scope") == scope
    if applied and not version_ok:
        attention.append("VERSION_MISMATCH")
    if applied and not scope_ok:
        attention.append("SCOPE_MISMATCH")
    check(
        "setting",
        bool(version_ok and scope_ok),
        "③ 설정의 active_version이 대상 버전이고 적용 범위가 같다",
        "설정 기록 없음"
        if not applied
        else f"active_version {setting['active_version']} · "
        f"범위 {'일치' if scope_ok else '불일치'}",
    )
    snapshot = applied and setting.get("evidence_type") == "SETTINGS_SNAPSHOT"
    check(
        "evidence",
        bool(snapshot),
        "④ 증적 유형이 SETTINGS_SNAPSHOT",
        "" if not applied else str(setting.get("evidence_type")),
    )
    now = datetime.fromisoformat(as_of)
    read_ok = False
    detail = "읽기 확인 없음"
    if applied and setting.get("checked_at"):
        a, c = (
            datetime.fromisoformat(setting["applied_at"]),
            datetime.fromisoformat(setting["checked_at"]),
        )
        read_ok = a <= c <= now and setting.get("check_result") == "MATCH"
        detail = (
            "확인이 반영보다 앞이다"
            if c < a
            else "확인이 기준시각 뒤다"
            if c > now
            else "설정 불일치"
            if setting.get("check_result") != "MATCH"
            else ""
        )
    check("read_check", read_ok, "⑤ 반영 뒤·기준시각 전에 읽기 확인", detail)

    if not passed:
        state = "ST703"
    elif not confirmed:
        state = "ST704"
    elif not applied or not snapshot:
        state = "ST705"
    elif all(c["ok"] for c in checks):
        state = "ST707"
    else:
        state = "ST706"
    return {
        "state": state,
        "label": STATE_LABELS[state],
        "checks": checks,
        "attention": sorted(set(attention)),
        "verification_passed": passed,
        "confirmed": confirmed,
        "setting_reflected": state == "ST707",
        # 운영 실행은 미확인 — 실행 id가 생기기 전에는 실행 확인으로 표시하지 않는다(UI707)
        "execution_status": "NOT_CONFIRMED",
        "operation_run_id": None,
        "reserved_only": applied and not snapshot,
    }


__all__ = [
    "CAUSE_LABELS",
    "PROJECTIONS",
    "STATE_LABELS",
    "application_state",
    "assess",
    "fingerprint",
    "leaks",
    "project",
    "verify",
]
