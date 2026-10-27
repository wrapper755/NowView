"""
SC05 Agent 지원 — AG51 계획 초안 · AG52 변경 비교 · AG53 조건 근거 점검 · AG54 고객 변경 요약 · AG55
초기 실적
집계 설명 · AG56 잔여 운영계획 제안 · AG57 전망 대사 설명 · AG58 후속 책임 점검(구현명세 16장).

**계산 결과와 근거 ID를 인용할 뿐이다.** 금액·승인·근거를 만들지 않고, 확정·확인·승인·착수를
대행하지 않는다
(업무 승인 권한이 없다). 장면 2~4와 같은 계약 검증을 쓴다 — 본문의 숫자가 입력에 있는 값인지, 근거
id가 입력의
목록에 있는지 본다. 통과하지 못한 응답은 초안으로 내지 않는다.

러너는 `mock`(고정 초안 재생 — 화면에 REPLAY로 보인다)과 `fail`(장애 — 수동 작성으로 간다,
T530)뿐이다. AG51·
AG52의 활동 제안은 시작할 때 둔 재생 초안(`doc["replay"]`)이다 — 사람이 협조·비용·일정을 고친다.
"""

from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal
from typing import Any

PROMPT_VERSION = "sc05-execution-v1"
KINDS = {
    "AG51": "승인 과제 → 활동·일정·협조 계획 초안",
    "AG52": "적용 애로와 계획 변경 비교",
    "AG53": "조건 근거·확인자 누락 점검",
    "AG54": "고객 변경 모델·납품 구간 요약",
    "AG55": "초기 실적·소요시간 집계 설명",
    "AG56": "지연 원인과 잔여 운영계획 제안",
    "AG57": "전망 대사와 변경 원인 설명",
    "AG58": "후속 책임·기한·근거 누락 점검",
}


class AgentFailure(Exception):
    pass


def _won(value: Any) -> str:
    return "미확인" if value is None else f"{int(Decimal(str(value))):,}원"


def build_input(doc: dict, kind: str) -> dict[str, Any]:
    """입력은 지금 시연 시각에 문서에 있는 자료로 한정한다 — 미래 기록을 Agent에 주지 않는다."""
    a = doc["sc04"]["actions"]["ACT42"]
    payload: dict[str, Any] = {
        "kind": kind,
        "demo_run_id": doc["demo_run_id"],
        "refs": [
            doc["sc04"]["approval"]["approval_id"],
            "ACT42",
            "CON41",
            "SUP41",
            *doc["evidence"],
        ],
        "approval": {
            "budget": str(a["budget"]),
            "completion_due": a["completion_due"],
            "effect_start": doc["sc04"]["assumptions"]["ACT42"]["start"],
            "condition_due": doc["sc04"]["directives"]["CON41"]["due_at"],
        },
    }
    plans = sorted(doc["plans"].values(), key=lambda p: p["seq"])
    payload["refs"] += [p["plan_id"] for p in plans]
    if kind == "AG51":
        payload["proposal"] = doc["replay"]["AG51"]
    elif kind == "AG52":
        base = doc["plans"].get(doc["plan_pointer"] or "")
        if base is None:
            raise AgentFailure("유효 계획이 없다 — 비교할 기준이 없다")
        payload["base"] = base["plan_id"]
        payload["proposal"] = doc["replay"]["AG52"]
    elif kind == "AG53":
        payload["conditions"] = {
            c: {
                "state": doc["conditions"][c]["state"],
                "evidence": [e["refs"] for e in doc["conditions"][c]["evidence"]],
            }
            for c in ("CON41", "SUP41")
        }
    elif kind == "AG54":
        plans_in = sorted(doc["customer_plans"].values(), key=lambda p: p["received_at"])
        if not plans_in:
            raise AgentFailure("접수한 고객 원문이 없다")
        cp = plans_in[-1]
        payload["refs"].append(cp["plan_ref"])
        payload["lines"] = [
            {
                "model_id": ln["model_id"],
                "changed": ln["changed"],
                "diffs": [
                    after - before for before, after in zip(ln["before"], ln["after"], strict=True)
                ],
                "month_diff": ln["month_diff"],
            }
            for ln in cp["lines"]
        ]
        payload["windows"] = cp["lines"][0]["windows"]
        payload["plan_ref"] = cp["plan_ref"]
    elif kind in ("AG55", "AG56"):
        from app.sc05.domain import observation

        obs = doc["observation"] or observation(doc)
        payload["observation"] = {
            k: obs[k]
            for k in (
                "orders",
                "qty",
                "urgent",
                "extra_cost",
                "baseline_cost",
                "support",
                "net",
                "late",
                "quality",
                "changes",
            )
        }
        payload["ack"] = obs["ack"]
        payload["share"] = obs["share"]
        payload["delayed_changes"] = [
            {"id": c["change_id"], "minutes": None}
            for c in sorted(doc["changes"].values(), key=lambda c: c["seq"])
            if any(
                al["target"] == c["change_id"] and al["kind"] == "ACK_DELAY" for al in doc["alerts"]
            )
        ]
        payload["refs"] += [c["change_id"] for c in doc["changes"].values()]
        payload["plan_after"] = doc["sc04"]["assumptions"]["ACT42"]["emergency_after"]
    elif kind == "AG57":
        from app.sc05.domain import compute_forecast

        if doc["official"] is None or doc["observation"] is None:
            raise AgentFailure("종전 공식본·마감 자료가 없다 — 대사할 기준이 없다")
        _effects, rows, recon, errors, _reported = compute_forecast(doc)
        if errors:
            raise AgentFailure("부서 운영계획 확인 전이다 — " + "; ".join(errors))
        annual = sum((Decimal(m["profit"]) for m in rows), Decimal(0))
        target = sum((Decimal(m["target"]) for m in rows), Decimal(0))
        payload["refs"] += ["작성 전 미리보기", doc["official"]]
        payload["run"] = {
            "run_id": "작성 전 미리보기",
            "annual": str(annual),
            "prior": recon["prior_total"],
            "delta": recon["delta"],
            "residual": recon["residual"],
            "rows": recon["rows"],
            "gap": str(target - annual),
        }
    elif kind == "AG58":
        official = doc["forecasts"].get(doc["official"] or "")
        if official is None or official["kind"] != "OFFICIAL" or official.get("background"):
            raise AgentFailure("게시된 새 공식본이 없다")
        run = doc["runs"][official["run_id"]]
        payload["refs"] += [official["forecast_id"], "DIR41", "ACT41", "ACT43"]
        payload["official"] = {
            "id": official["forecast_id"],
            "annual": official["annual"],
            "gap": run["gap"],
        }
    return payload


def input_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def mock(payload: dict[str, Any]) -> dict[str, Any]:
    kind = payload["kind"]
    ap = payload["approval"]
    out: dict[str, Any] = {"summary": "", "findings": [], "questions": [], "draft_text": ""}
    if kind == "AG51":
        out["summary"] = (
            f"승인 범위 — 예산 {_won(ap['budget'])}, 효과 개시 {ap['effect_start']}, 과제 기한 "
            f"{ap['completion_due'][:10]}. "
            "공동 기준·창구 지정·교육·조건 확인·운영 적용·초기 확인 활동 "
            f"{len(payload['proposal'])}개 초안"
        )
        out["findings"] = [
            {
                "text": "확인 필요: 각 활동의 협조 담당과 비용은 담당자가 채운다 — 초안에 없다",
                "evidence_refs": ["ACT42"],
            },
            {
                "text": f"CON41 기한 {ap['condition_due'][:10]} 전에 공동 기준을 마련해야 한다",
                "evidence_refs": ["CON41"],
            },
        ]
        out["activities"] = payload["proposal"]
    elif kind == "AG52":
        out["summary"] = (
            f"{payload['base']} 대비 — 부재 시 대행·수시 확인 경로와 교육 순서 보완 제안"
        )
        out["findings"] = [
            {
                "text": "확인 필요: 정례회의 이후 접수된 변경이 구매에 늦게 전달될 수 있다",
                "evidence_refs": [payload["base"]],
            },
            {
                "text": (
                    "예산·효과 개시·최종 기한은 유지하는 범위의 보완이다 — 대표 재승인 대상이 "
                    "아니다"
                ),
                "evidence_refs": ["ACT42"],
            },
        ]
        out["activities"] = payload["proposal"]
    elif kind == "AG53":
        out["summary"] = "CON41·SUP41 근거 연결 상태 — 임원의 실제 확인은 별도다"
        out["findings"] = [
            {
                "text": f"{cid} 상태 {c['state']} · 연결 근거 "
                f"{', '.join(sum(c['evidence'], [])) or '없음'}",
                "evidence_refs": [
                    cid,
                    *[r for r in sum(c["evidence"], []) if r in payload["refs"]],
                ],
            }
            for cid, c in payload["conditions"].items()
        ]
    elif kind == "AG54":
        changed = [ln for ln in payload["lines"] if ln["changed"]]
        out["summary"] = (
            f"{payload['plan_ref']} — 변경 모델 "
            f"{', '.join(ln['model_id'] for ln in changed) or '없음'}, "
            f"나머지 {len(payload['lines']) - len(changed)}개 모델 변동 없음. 월합계 변화 "
            f"{sum(ln['month_diff'] for ln in payload['lines'])}"
        )
        out["findings"] = [
            {
                "text": f"{ln['model_id']} 구간 변화 "
                + " · ".join(
                    f"{w} {d:+d}" for w, d in zip(payload["windows"], ln["diffs"], strict=True) if d
                ),
                "evidence_refs": [payload["plan_ref"]],
            }
            for ln in changed
        ]
        out["draft_text"] = "구매 확인 요청 — 원문과 수량을 생산 담당이 대조한 뒤 공유한다"
    elif kind == "AG55":
        o = payload["observation"]
        out["summary"] = (
            f"9월 구매 {o['orders']}건 중 긴급 {o['urgent']}건, 추가비 {_won(o['extra_cost'])}. "
            "비교 기준 "
            f"{_won(o['baseline_cost'])} 대비 추정 순개선 {_won(o['net'])} — 인과 확정치가 아니다"
        )
        out["findings"] = [
            {
                "text": f"구매 확인 지연 {payload['ack']['delayed']}건 — 변경 {o['changes']}건 "
                "기준",
                "evidence_refs": [d["id"] for d in payload["delayed_changes"]] or ["ACT42"],
            },
        ]
    elif kind == "AG56":
        o = payload["observation"]
        out["summary"] = (
            f"10월 긴급 {payload['plan_after']}건 관리 유지, 확인 지연 재발 점검 제안 — 9월 실적 "
            f"{o['urgent']}건에서 외삽하지 않는다"
        )
        out["findings"] = [
            {
                "text": "확인 필요: 11~12월 개선 가정은 담당 임원이 정한다",
                "evidence_refs": ["ACT42"],
            }
        ]
    elif kind == "AG57":
        r = payload["run"]
        out["summary"] = (
            f"{r['run_id']} 연간 {_won(r['annual'])} — 종전 공식 {_won(r['prior'])} 대비 "
            f"{_won(r['delta'])}, "
            f"설명 안 된 차이 {_won(r['residual'])}"
        )
        out["findings"] = [
            {
                "text": f"{row['month'][:7]} {row['cause']} {_won(row['amount'])}",
                "evidence_refs": [r["run_id"]],
            }
            for row in r["rows"]
        ]
    else:
        f = payload["official"]
        out["summary"] = (
            f"{f['id']} 게시 — 남는 목표 부족 {_won(f['gap'])}. 목표 미달 가능성 유지, 추가과제와 "
            "11~12월 가정 재점검"
        )
        out["findings"] = [
            {
                "text": "확인 필요: DIR41 추가과제 효과는 미산정 — 전망에 넣지 않는다",
                "evidence_refs": ["DIR41"],
            },
            {
                "text": "확인 필요: ACT41 품질·납기, ACT43 안정화 확인 담당과 기한",
                "evidence_refs": ["ACT41", "ACT43"],
            },
        ]
    return out


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
        elif isinstance(v, bool) or v is None:
            return
        elif isinstance(v, int | float | Decimal):
            out.update({Decimal(str(v)), abs(Decimal(str(v)))})
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
    refs = set(payload["refs"])
    allowed = _allowed(payload)
    texts = [output["summary"], output["draft_text"], *output["questions"]]
    for f in output["findings"]:
        texts.append(f["text"])
        problems += [f"없는 근거: {r}" for r in f.get("evidence_refs", []) if r not in refs]
    for t in texts:
        plain = re.sub(r"[A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9.]+)*", " ", t)
        plain = re.sub(r"\d{4}-\d{2}(?:-\d{2})?", " ", plain)  # 날짜
        plain = re.sub(r"\d{1,2}/\d{1,2}(?:~\d{1,2})?", " ", plain)  # 구간 이름
        for m in _NUM.findall(plain):
            v = abs(Decimal(m.replace(",", "")))
            if v <= 31 and v == v.to_integral_value():
                continue  # 날짜·월·건수
            if v not in allowed:
                problems.append(f"입력에 없는 숫자: {m}")
    return problems


def run(payload: dict[str, Any], mode: str) -> dict[str, Any]:
    if mode == "fail":
        raise AgentFailure(
            "Agent 생성 실패 — 수동 작성 또는 근거 조회로 진행한다(503 AGENT_UNAVAILABLE)"
        )
    return mock(payload)
