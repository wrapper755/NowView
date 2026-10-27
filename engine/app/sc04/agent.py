"""
SC04 Agent 지원 — AG41 효과 검증·비교 요약 · AG42 대표 질의 후보 · AG43 회의록·승인서·인계
초안(구현명세 15장,
AC417).

**계산 결과와 근거 ID를 인용할 뿐이다**(P413). 없는 원가·시장 원인·절감액을 만들지 않고,
추천·판단·승인·인수를
대행하지 않는다. 장면 2·3과 같은 계약 검증을 쓴다 — 본문의 숫자가 입력에 있는 값인지, 근거 id가
입력의 근거
목록에 있는지 본다. 통과하지 못한 응답은 초안으로 내지 않는다. 우려 사항은 「확인 필요」로 낸다 —
사실로
확정하지 않는다.

* AG41은 효과 검증이 통과하면 서비스 태스크가 만든다 — 기다리지 않는다.
* AG42·AG43은 경영관리가 회의 전·결정 뒤에 요청한다(BPM 밖 명령). 실패(E408)하면 수동 작성으로 간다
  —
  계산·기존 기록·권한은 그대로다.

러너는 `mock`(결정론, 기본)과 `fail`(E408 재현)뿐이다 — 장면 2·3과 같은 사정이다.
"""

from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal
from typing import Any

PROMPT_VERSION = "sc04-review-v1"
KINDS = {
    "AG41": "효과 검증·대안 비교 요약",
    "AG42": "대표 질의 후보",
    "AG43": "회의록·승인서·인계 초안",
}
EVIDENCE = (
    "EVDC41",
    "EVDC42",
    "EVDC43",
    "EVDC44",
    "EVDC45",
    "EVDC46",
    "EVDC47",
    "EVDC48",
    "EVDC49",
)


class AgentFailure(Exception):
    pass


def _won(value: str | None) -> str:
    return "미산정" if value is None else f"{int(Decimal(value)):,}원"


def build_input(doc: dict, kind: str) -> dict[str, Any]:
    """
    입력은 결과 버전·계산 실행·근거·확인된 회의 기록으로 한정한다 — 지금 시연 시각에 보이는 자료만.
    """
    runs = sorted(doc["runs"].values(), key=lambda r: r["seq"])
    run = next((r for r in reversed(runs) if r["result"]["passed"]), None)
    if run is None:
        raise AgentFailure("검증을 통과한 효과 계산이 없다")
    y = run["result"]["periods"]["year"]
    payload: dict[str, Any] = {
        "kind": kind,
        "demo_run_id": doc["demo_run_id"],
        "run_id": run["run_id"],
        "result_versions": [
            r["versions"][-1]["ref"]
            for r in sorted(doc["results"].values(), key=lambda r: r["seq"])
            if r["versions"]
        ],
        "evidence_refs": list(EVIDENCE),
        "numbers": {
            "target": y["target"],
            "base": y["base"],
            "gap_before": y["gap_before"],
            "effect": y["effect"],
            "gap": y["gap"],
            "duplicate_total": run["result"]["duplicate_total"],
            "normal_annual_total": run["result"]["normal_annual_total"],
        },
        "alts": [
            {"id": a["alt_id"], "name": a["name"], "net_2027": a["net_2027"], "start": a["start"]}
            for a in run["result"]["alts"]
        ],
    }
    if kind in ("AG42", "AG43"):
        meeting = doc.get("meeting") or {}
        payload["meeting_records"] = [
            {"id": r["record_id"], "type": r["record_type"], "content": r["content"]}
            for r in meeting.get("records", [])
        ]
        payload["reports"] = sorted(doc["reports"])
    if kind == "AG43":
        dec = doc.get("decision")
        if dec is None:
            raise AgentFailure("대표 결정 전이다 — 승인서 초안을 만들 자료가 없다")
        payload["decision"] = {
            "id": dec["decision_id"],
            "items": {a: it["outcome"] for a, it in dec["items"].items()},
            "approved_effect": dec["approved_effect"],
            "gap": dec["gap"],
        }
        payload["directives"] = [
            {"id": x["directive_id"], "content": x["content"]}
            for x in sorted(doc["directives"].values(), key=lambda x: x["seq"])
        ]
    return payload


def input_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def _refs(payload: dict[str, Any]) -> set[str]:
    out = {payload["run_id"], *payload["result_versions"], *payload["evidence_refs"]}
    out.update(a["id"] for a in payload["alts"])
    out.update(r["id"] for r in payload.get("meeting_records", []))
    out.update(payload.get("reports", []))
    out.update(x["id"] for x in payload.get("directives", []))
    if payload.get("decision"):
        out.add(payload["decision"]["id"])
    return out


def mock(payload: dict[str, Any]) -> dict[str, Any]:
    n = payload["numbers"]
    run = payload["run_id"]
    alts = payload["alts"]
    if payload["kind"] == "AG41":
        findings = [
            {
                "text": f"{a['id']} {a['name']} 당해연도 순효과 {_won(a['net_2027'])} — 효과 시작 "
                f"{a['start'][:7]}",
                "evidence_refs": [run, a["id"]],
            }
            for a in alts
        ]
        findings.append(
            {
                "text": f"중복 제거 {_won(n['duplicate_total'])} — 구매조건 초안 할인은 대체 "
                "공급업체 "
                "가격차에 포함된다. 확인 필요: 같은 품목·물량·기간인지",
                "evidence_refs": ["EVDC44"],
            }
        )
        findings.append(
            {
                "text": "기존 감가상각비는 잔존 고정비로 기준 손익에 남는다 — 회피 비용·추가 "
                "지출이 아니다",
                "evidence_refs": ["EVDC45"],
            }
        )
        summary = (
            f"검증된 3개 대응안의 당해연도 순효과 {_won(n['effect'])}, 대응 전 부족 "
            f"{_won(n['gap_before'])}에서 "
            f"반영 후 부족 {_won(n['gap'])}. 정상 연간 {_won(n['normal_annual_total'])}은 "
            "참고값이고 합산하지 않는다."
        )
        questions = [
            "효과 시작 시점이 늦어지면 당해연도 효과가 얼마나 줄어드는가 — 월별로 다시 계산한다"
        ]
        draft = ""
    elif payload["kind"] == "AG42":
        findings = [
            {
                "text": "확인 필요: 긴급구매 축소안은 생산 변경정보 공유 없이 납기를 지킬 수 "
                "있는가",
                "evidence_refs": ["EVDC47", "ALT42"],
            },
            {
                "text": "확인 필요: 외주로 돌린 뒤에도 남는 비용과 실제로 줄어드는 항목은 무엇인가",
                "evidence_refs": ["EVDC41", "EVDC45"],
            },
            {
                "text": "확인 필요: 기존 승인 업체의 이번 품목·증량 공급능력 근거는 무엇인가",
                "evidence_refs": ["EVDC46", "ALT43"],
            },
        ]
        summary = (
            f"질의 후보 3건 — 남는 부족 {_won(n['gap'])}의 관리 방안도 묻는다. 후보는 Agent "
            "초안이며 "
            "현업 답변이 아니다."
        )
        questions = ["착수가 한 달 늦어지면 올해 효과는 얼마나 줄어드는가"]
        draft = ""
    else:
        d = payload["decision"]
        findings = [
            {"text": f"{r['id']} {r['content']}", "evidence_refs": [r["id"]]}
            for r in payload.get("meeting_records", [])
        ]
        findings += [
            {"text": f"{x['id']} {x['content']}", "evidence_refs": [x["id"]]}
            for x in payload.get("directives", [])
        ]
        summary = (
            f"{d['id']} — 승인 범위 효과 {_won(d['approved_effect'])}, 남는 부족 {_won(d['gap'])}. "
            "승인서 확정·책임 인수는 사람이 한다."
        )
        questions = []
        draft = (
            "회의록 초안 — 보고(REP) · 대표 질의·답변 · 효과 시점 조정(판단본) · 과제별 결정 · "
            "조건·지원·추가 발굴 지시. "
            "승인서 초안 — 전체 책임 경영관리 임원, 개별 책임 담당 임원, 총괄·과제 한도와 두 기한, "
            "위임 조항. "
            "효과는 예상치이며 실적이 아니다."
        )
    return {"summary": summary, "findings": findings, "questions": questions, "draft_text": draft}


_NUM = re.compile(r"-?\d[\d,]*(?:\.\d+)?")


def _allowed(payload: dict[str, Any]) -> set[Decimal]:
    out: set[Decimal] = set()

    def walk(v: Any) -> None:
        if isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)
        elif isinstance(v, str):
            for m in _NUM.findall(v):
                d = Decimal(m.replace(",", ""))
                out.update({d, abs(d)})

    walk(payload)
    return out


def validate(output: dict[str, Any], payload: dict[str, Any]) -> list[str]:
    """형식 · 근거 id · **본문의 숫자가 입력에 있는가**(계산은 계산 서비스만 한다)."""
    problems = [
        f"{k} 없음" for k in ("summary", "findings", "questions", "draft_text") if k not in output
    ]
    if problems:
        return problems
    refs = _refs(payload)
    allowed = _allowed(payload)
    texts = [output["summary"], output["draft_text"], *output["questions"]]
    for f in output["findings"]:
        texts.append(f["text"])
        problems += [f"없는 근거: {r}" for r in f.get("evidence_refs", []) if r not in refs]
    for t in texts:
        # 식별자(RUN-SC04-01·ALT41·DEC41-v2)의 숫자는 숫자가 아니다
        plain = re.sub(r"[A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9.]+)*", " ", t)
        for m in _NUM.findall(plain):
            v = abs(Decimal(m.replace(",", "")))
            if (v <= 31 and v == v.to_integral_value()) or v in (2027, 2028):
                continue  # 날짜·월·연도·개수
            if v not in allowed:
                problems.append(f"입력에 없는 숫자: {m}")
    return problems


def run(payload: dict[str, Any], mode: str) -> dict[str, Any]:
    if mode == "fail":
        raise AgentFailure("시연 사례 E408 — 초안 생성 실패(수동 작성으로 전환)")
    return mock(payload)
