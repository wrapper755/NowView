"""
SC03 Agent 지원 — AG30 통합 손익 설명 · AG31 회의 질의·후보 요약과 과제 초안(구현명세 12장).

**규칙 결과와 기록을 인용할 뿐이다**(P39). 절감액·원인·시장정보를 만들지 않고, 주재자 결론·후보
판단·
과제 인수를 대행하지 않는다. 장면 2(`app/sc02/agent.py`)와 같은 계약 검증을 쓴다 — 본문의 숫자가
입력에
있는 값인지, 근거 id가 입력의 근거 목록에 있는지 본다. 통과하지 못한 응답은 초안으로 내지 않는다.

* AG30(손익 설명)은 통합 분석이 정합을 통과하면 서비스 태스크가 만든다 — 기다리지 않는다.
* AG31(회의 요약)은 「SC03데이터계약」의 AG31이다 — 6/29 10:40 경영관리 담당이 회의 중에 요청한다
  (BPM 밖 명령). 실패(E36)하면 수동 작성으로 간다 — 원 계산·회신·기록은 그대로다.

러너는 `mock`(결정론, 기본)과 `fail`(E36 재현)뿐이다 — SC02와 같은 사정(LLM 러너는 SC01 계약용)이다.
"""

from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal
from typing import Any

PROMPT_VERSION = "sc03-review-v1"
KINDS = {"AG30": "통합 손익 설명", "AG31": "회의 질의·후보 요약 · 과제 초안"}


class AgentFailure(Exception):
    pass


def _won(value: str | None) -> str:
    return "미산정" if value is None else f"{int(Decimal(value)):,}원"


def build_input(doc: dict, kind: str) -> dict[str, Any]:
    """입력은 run·보고버전·확인 기록·질의·후보 설명으로 한정한다(구현명세 12장)."""
    runs = sorted(doc["runs"].values(), key=lambda r: r["seq"])
    run = next((r for r in reversed(runs) if r["result"]["passed"]), None)
    if run is None:
        raise AgentFailure("정합을 통과한 분석이 없다")
    year = run["result"]["periods"]["year"]
    payload: dict[str, Any] = {
        "kind": kind,
        "demo_run_id": doc["demo_run_id"],
        "run_id": run["run_id"],
        "report_versions": sorted(doc["reports"]),
        "numbers": {
            "target": year["target"],
            "f01": year["f01"],
            "volume_effect": year["volume_effect"],
            "cost_effect": year["cost_effect"],
            "event_effect": year["event_effect"],
            "combined": year["combined"],
            "existing_gap": year["existing_gap"],
            "total_gap": year["total_gap"],
            "next12_increase": run["result"]["purchase"]["next12_increase"],
            "next12_combined": run["result"]["periods"]["next12"].get("combined"),
        },
        "facts": [
            {"id": f["fact_id"], "category": f["category"], "statement": f["statement"]}
            for f in sorted(doc["facts"].values(), key=lambda f: f["seq"])
        ],
        "questions": [
            {"id": q["question_id"], "question": q["question"]}
            for q in sorted(doc["questions"].values(), key=lambda q: q["seq"])
        ],
    }
    if kind == "AG31":
        meeting = doc["meetings"].get("MT31") or {}
        payload["meeting_records"] = [
            {"id": r["record_id"], "type": r["record_type"], "content": r["content"]}
            for r in meeting.get("records", [])
            if r["record_type"] in ("QUESTION", "ANSWER", "EXPLANATION")
        ]
        payload["candidates"] = [
            {"id": c["candidate_id"], "candidate": c["candidate"], "constraints": c["constraints"]}
            for c in sorted(doc["candidates"].values(), key=lambda c: c["seq"])
        ]
    return payload


def input_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def _refs(payload: dict[str, Any]) -> set[str]:
    out = {payload["run_id"], *payload["report_versions"]}
    for key in ("facts", "questions", "meeting_records", "candidates"):
        out.update(x["id"] for x in payload.get(key, []))
    return out


def mock(payload: dict[str, Any]) -> dict[str, Any]:
    n = payload["numbers"]
    run = payload["run_id"]
    if payload["kind"] == "AG30":
        findings = [
            {
                "text": f"전체 목표 부족 {_won(n['total_gap'])} 중 사건 이전부터 있던 기존 부족은 "
                f"{_won(n['existing_gap'])}, 이번 두 사건의 추가 악화는 "
                f"{_won(n['event_effect'])}다.",
                "evidence_refs": [run],
            },
            {
                "text": f"물량 영향 {_won(n['volume_effect'])}(장면 1)과 승인 단가 영향 "
                f"{_won(n['cost_effect'])}(장면 2)은 F02 물량에 승인 단가를 적용해 "
                "중복 없이 더했다.",
                "evidence_refs": [run],
            },
            {
                "text": f"향후 12개월 구매 증가 {_won(n['next12_increase'])}는 손익 영향과 다른 "
                "지표다 — 재고·시차 없는 가정에서만 CM 감소와 대응한다.",
                "evidence_refs": [run],
            },
        ]
        summary = (
            f"통합 관리손익 {_won(n['combined'])}, Target 대비 부족 {_won(n['total_gap'])}. "
            "두 사건을 해소해도 기존 부족은 남는다."
        )
        questions = ["기존 부족의 세부 원인은 아직 근거가 없다 — 추가 분석이 필요한가"]
        draft = ""
    else:
        records = payload.get("meeting_records", [])
        cands = payload.get("candidates", [])
        findings = [
            {"text": f"{r['id']} {r['content']}", "evidence_refs": [r["id"]]} for r in records
        ]
        findings += [
            {
                "text": f"{c['id']} {c['candidate']} — 확인 필요: {c['constraints']}",
                "evidence_refs": [c["id"]],
            }
            for c in cands
        ]
        summary = (
            f"질의 {len(records)}건과 대응 후보 {len(cands)}개를 정리했다. "
            "포함·제외는 주재자 판단이다 "
            "— 외주 확대의 수익성 개선을 단정하지 않는다."
        )
        questions = [f"{q['id']} {q['question']}" for q in payload["questions"]]
        draft = (
            "분석 지시 초안 — 부분 공정 생산·외주 조정은 회피가능·잔존 고정비와 "
            "추가 외주·전환비를, "
            "구매조건·대체 공급처는 조건과 검증비용을, 물량 재배분은 실제 배분 가능성과 공헌이익을 "
            "같은 기준(F02+EXT28-v1, C02-APP01)으로 확인한다. "
            "기존 부족 원인은 신규 사건과 중복 없이 "
            "따로 분석한다. 효과액은 미산정으로 둔다."
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
        # 식별자(RUN-SC03-01·F02·EXT28-v1)의 숫자는 숫자가 아니다
        plain = re.sub(r"[A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9.]+)*", " ", t)
        for m in _NUM.findall(plain):
            v = abs(Decimal(m.replace(",", "")))
            if (v <= 31 and v == v.to_integral_value()) or v in (2027, 2028):
                continue  # 날짜·월·연도
            if v not in allowed:
                problems.append(f"입력에 없는 숫자: {m}")
    return problems


def run(payload: dict[str, Any], mode: str) -> dict[str, Any]:
    if mode == "fail":
        raise AgentFailure("시연 사례 E36 — 초안 생성 실패(수동 작성으로 전환)")
    return mock(payload)
