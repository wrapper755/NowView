"""
SC02 Agent 검토 지원 — AG21 사전 검토 · AG22 협상 비교 · AG23 기안 문안 · AG24 인계 요약.

**규칙 결과를 인용할 뿐이다**(AG-21). 산식·위험 등급·승인선·결재·원가 등록·인수를 하지 않는다.
SC01(`app/sc01/agent.py`)과 같은 계약 검증을 쓴다 — 본문의 숫자가 입력(규칙 결과)에 있는 값인지,
근거 id가 근거 목록에 있는지 본다. 통과하지 못한 응답은 화면에 초안으로 내지 않는다.

러너는 `mock`(결정론, 기본)과 `fail`(X09-B — 요약 실패 재현)뿐이다. **LLM 러너는 SC02에 아직 없다**
—
SC01의 ollama 러너는 SC01 계약(검토 의견·근거·질문)에 맞춰져 있어 그대로 쓸 수 없다. mock도 같은
검증을
통과해야 한다. mock은 순간에 끝나므로 서비스 태스크 안에서 만든다(SC01은 LLM 때문에 잠금 밖이다).
"""

from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal
from typing import Any

PROMPT_VERSION = "sc02-review-v1"
KINDS = {
    "AG21": "사전 검토",
    "AG22": "협상 비교·기안 초안",
    "AG24": "인계 요약",
}


class AgentFailure(Exception):
    pass


def _won(value: str | None) -> str:
    return "미산출" if value is None else f"{int(Decimal(value)):,}원"


def _pct(value: str | None) -> str:
    if value is None:
        return "미산출"
    v = Decimal(value) * 100
    return f"{v.normalize():f}%"


RISK = {"NORMAL": "기준 이내", "ATTENTION": "관심", "CRITICAL": "중요", None: "판정 보류"}


def build_input(doc: dict, kind: str, run: dict) -> dict[str, Any]:
    """AG-22 입력 — demo_run_id·request_id·run_ids·근거·규칙 결과·가정·미해결 질문."""
    r = run["result"]
    year = next((p for p in r["periods"] if p["kind"] == "year"), None)
    next12 = next((p for p in r["periods"] if p["kind"] == "next12"), None)
    sources = [s for s in ("DOC-REQ01", "NOTE-REPORT01", "NOTE-NEG01") if s in doc["evidence_ids"]]
    return {
        "demo_run_id": doc["demo_run_id"],
        "request_id": (doc["request"] or {}).get("request_id"),
        "kind": kind,
        "run_ids": [run["run_id"], doc["sc01"]["run_id"]],
        "source_refs": sources,
        "calculation_result": {
            "version_id": r["version_id"],
            "old_price": r["old_price"],
            "new_price": r["new_price"],
            "effective_date": r["effective_date"],
            "rate": r["rate"],
            "rate_risk": r["rate_risk"],
            "amount_risk": r["amount_risk"],
            "risk": r["risk"],
            "ceo_required": r["ceo_required"],
            "remaining_increase": r["remaining"]["increase"],
            "next12_increase": r["next12"]["increase"],
            "next12_qty": r["next12"]["purchase_qty"],
            "reduction": (r["comparison"] or {}).get("reduction"),
            "year_volume": None if not year or not year["computable"] else year["volume_effect"],
            "year_cost": None if not year or not year["computable"] else year["cost_effect"],
            "year_gap": None if not year or not year["computable"] else year["target_gap"],
            "next12_profit": None
            if not next12 or not next12["computable"]
            else next12["profit_combined"],
        },
        "assumptions": r["assumptions"],
        "unresolved_questions": [
            "2028년 물량은 내부가정이다 — 고객 계획으로 재확인이 필요한가",
            "공급사 원가 상승 근거(원재료·가공비)가 제공되지 않았다",
        ],
    }


def input_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def mock(payload: dict[str, Any]) -> dict[str, Any]:
    """결정론 초안 — 규칙 결과의 값만 쓴다."""
    c = payload["calculation_result"]
    run, sc01_run = payload["run_ids"]
    kind = payload["kind"]
    price = f"{_won(c['old_price'])} → {_won(c['new_price'])}"
    findings = [
        {
            "text": f"공통부품 단가 {price}, 기존 대비 {_pct(c['rate'])} 인상 — 인상률 위험 "
            f"{RISK[c['rate_risk']]}.",
            "evidence_refs": [run],
        },
        {
            "text": f"향후 12개월 구매 증가액 {_won(c['next12_increase'])}"
            + ("" if c["next12_qty"] is None else f"(부품 {c['next12_qty']:,}개)")
            + f", 당해연도 잔여 {_won(c['remaining_increase'])} — "
            f"금액 위험 {RISK[c['amount_risk']]}.",
            "evidence_refs": [run],
        },
    ]
    if c["year_cost"] is not None:
        findings.append(
            {
                "text": f"2027년 물량 감소 영향 {_won(c['year_volume'])}에 원가 증가 "
                f"{_won(c['year_cost'])}가 더해져 Target 대비 {_won(c['year_gap'])} 부족 전망.",
                "evidence_refs": [run, sc01_run],
            }
        )
    if kind in ("AG22", "AG24") and c["reduction"] is not None:
        findings.append(
            {
                "text": f"요청안 대비 12개월 부담 감소 {_won(c['reduction'])} — 기존 대비 원가 "
                "상승은 남는다. 인상률 감소를 위험 해소로 보지 않는다.",
                "evidence_refs": [run],
            }
        )
    ceo = {True: "대표 승인 대상", False: "대표 비대상", None: "승인선 판정 보류"}[
        c["ceo_required"]
    ]
    summary = (
        f"{price}({_pct(c['rate'])}). 12개월 구매 증가 {_won(c['next12_increase'])}, "
        f"종합 위험 {RISK[c['risk']]}, {ceo}."
    )
    questions = list(payload["unresolved_questions"])
    if kind == "AG21":
        questions.append("적용일 7/1 이전 기발주분이 정말 없는가")
    draft = ""
    if kind == "AG22":
        draft = (
            f"공통부품 P-COM01 단가를 {price}으로 조정하는 가격인상을 보고드립니다. "
            f"향후 12개월 구매 증가액은 {_won(c['next12_increase'])}이며 {ceo}입니다. "
            "손익 영향은 참고자료로 첨부합니다."
        )
    if kind == "AG24":
        draft = (
            f"승인 단가 {_won(c['new_price'])} 기준 2027년 원가 영향 {_won(c['year_cost'])}, "
            f"물량 영향 {_won(c['year_volume'])}. 장면 3에서 통합 손익과 대응 필요성 검토 바람."
        )
    return {"summary": summary, "findings": findings, "questions": questions, "draft_text": draft}


_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _allowed(payload: dict[str, Any]) -> set[Decimal]:
    out: set[Decimal] = set()

    def walk(v: Any) -> None:
        if isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            out.add(Decimal(str(v)))
        elif isinstance(v, str):
            for m in _NUM.findall(v):
                out.add(Decimal(m.replace(",", "")))
            try:
                d = Decimal(v)
            except Exception:  # noqa: BLE001 — 숫자가 아닌 글자
                return
            out.update({d, abs(d), d * 100})

    walk(payload)
    return out


def validate(output: dict[str, Any], payload: dict[str, Any]) -> list[str]:
    """형식 · 근거 id · **본문의 숫자가 규칙 결과에 있는가**(AG-22 「숫자 근거 없는 문장」)."""
    problems: list[str] = []
    for key in ("summary", "findings", "questions", "draft_text"):
        if key not in output:
            problems.append(f"{key} 없음")
    if problems:
        return problems
    refs = set(payload["run_ids"]) | set(payload["source_refs"])
    allowed = _allowed(payload)
    texts = [output["summary"], output["draft_text"]]
    for f in output["findings"]:
        texts.append(f["text"])
        for ref in f.get("evidence_refs", []):
            if ref not in refs:
                problems.append(f"없는 근거: {ref}")
    for t in texts:
        for m in _NUM.findall(t):
            v = Decimal(m.replace(",", ""))
            # 31 이하 정수는 날짜·월로 보고, 연도(2027·2028)는 기간이다(SC01과 같은 허용).
            if (v <= 31 and v == v.to_integral_value()) or v in (2027, 2028):
                continue
            if v not in allowed:
                problems.append(f"규칙 결과에 없는 숫자: {m}")
    return problems


def run(payload: dict[str, Any], mode: str) -> dict[str, Any]:
    if mode == "fail":
        raise AgentFailure("시연 사례 X09-B — 요약 생성 실패")
    return mock(payload)
