"""
SC01 Agent 검토 지원 — 구현명세 11장(AG-01~03).

**Agent는 숫자를 만들지 않는다.** 규칙 계산이 끝난 뒤(계산 SUCCEEDED) 그 결과를 인용해 변동
요약·근거·확인 질문·검토 제안 **초안**을 쓴다. 산식 계산, 위험 등급, 원천 확인, 전망 승인, 업무
인수는 Agent에 맡기지 않는다.

* **검증이 핵심이다**(AG-01 "검증"). 응답 형식, 근거 ID가 실제로 있는지, **본문의 숫자가 규칙
  결과와 맞는지**를 본다. 하나라도 어긋나면 실패로 처리하고 화면에 확정 설명으로 내지 않는다.
  그럴듯한 숫자 하나가 틀려도 눈으로는 안 잡힌다 — 이전 구현에서 temperature 0인데도 같은
  질문에 14.2와 14.5가 나왔다(CLAUDE.md 4.15).
* **실패해도 업무는 계속된다**(EX08). 규칙 계산과 사람의 검토는 Agent 없이 끝난다.
* 러너는 셋이다: `mock`(결정론 — 기본 시연·테스트), `llm`(ollama), `fail`(EX08 재현).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol

import httpx

PROMPT_VERSION = "sc01-review-v2"

#: 계약 — 필수 출력(AG-01 표).
REQUIRED = ("summary", "findings", "evidence_refs", "questions", "suggested_tasks", "limitations")
TASK_TYPES = {"PROD", "MAT", "FIN", "DQ"}


class AgentFailure(Exception):
    """Agent가 계약을 못 맞췄거나 응답하지 않았다. 지어낸 값으로 메우지 않는다."""


# ─────────────────────────── 입력 ───────────────────────────


def build_input(doc: dict, run_id: str, rules: dict[str, Decimal]) -> dict[str, Any]:
    """
    Agent 입력(AG-01 "입력"): run과 고정 버전, 바뀐 모델·월의 목표·직전·최신·CM, 계산 지표·위험,
    원천 근거, 기존 이슈, 검토할 업무 범위. **근거 목록(evidence_catalog)을 함께 준다** — Agent는
    여기 있는 ID만 인용할 수 있다.
    """
    run = doc["calc_runs"][run_id]
    source = doc["sources"][run["source_id"]]
    changed = [r for r in run["results"] if r["metrics"]["M01"]["value"] not in (None, "0")]
    flagged = [r for r in run["results"] if r["risk"] in ("ATTENTION", "CRITICAL")]
    focus = changed or flagged
    catalog = {run_id, run["source_id"], *run["versions"].values()}
    for r in run["results"]:
        for mid in r["metrics"]:
            catalog.add(metric_ref(run_id, r["model_id"], r["period"], mid))
    issues = [
        {
            "issue_id": i["issue_id"],
            "model_id": i["model_id"],
            "period": i["period"],
            "risk": i["risk"],
            "history": [h["risk"] for h in i["history"]],
        }
        for i in doc["issues"].values()
        if run_id in i["runs"]
    ]
    catalog.update(i["issue_id"] for i in issues)
    return {
        "run_id": run_id,
        "versions": run["versions"],
        "source": {
            "source_id": source["source_id"],
            "customer_plan_id": source["customer_plan_id"],
            "received_at": source["received_at"],
            # 원천에는 감소 사유가 없다 — Agent가 원인을 단정하면 안 되는 이유다(구현명세 11장).
            "reason_given": None,
        },
        "focus": [
            {
                "model_id": r["model_id"],
                "period": r["period"],
                "target": r["target"],
                "prior": r["prior"],
                "latest": r["latest"],
                "unit_cm": r["unit_cm"],
                "risk": r["risk"],
                "metrics": {k: m["value"] for k, m in r["metrics"].items()},
            }
            for r in focus
        ],
        "rules": {k: str(v) for k, v in rules.items()},
        "issues": issues,
        "task_scope": ["PROD", "MAT", "FIN"],
        # 지표 코드만 주면 초안이 "M01 700"처럼 코드로 말한다 — 읽는 사람은 경영진이다.
        "metric_names": {
            "KPI01": "공급물량 전망 달성률(비율)",
            "M01": "직전 대비 추가 감소물량(대분)",
            "KRI01": "직전 대비 감소율(비율)",
            "M03": "물량 변동 순손익 영향(원)",
            "KRI02": "예상 공헌이익 감소액(원)",
            "M02": "목표 대비 부족물량(대분)",
            "KRI03": "목표 대비 부족률(비율)",
        },
        "evidence_catalog": sorted(catalog),
    }


def metric_ref(run_id: str, model_id: str, period: str, metric_id: str) -> str:
    return f"{run_id}:{model_id}:{period[:7]}:{metric_id}"


def input_hash(payload: dict[str, Any]) -> str:
    body = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(body.encode()).hexdigest()


# ─────────────────────────── 검증 ───────────────────────────

#: 숫자를 뽑기 전에 지우는 식별자(RUN-F02-001, ISSUE-B07, SRC02, KRI01, R01-v1, A-b …).
_ID = re.compile(r"\b[A-Za-z]+(?:-[A-Za-z0-9]+)*\d[\w-]*|\b[A-Z]-[a-e]\b")
_NUM = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(%|만\s*원|만|억\s*원|억|원|대분)?")


def allowed_numbers(payload: dict[str, Any]) -> tuple[set[Decimal], set[Decimal]]:
    """
    본문에 나와도 되는 숫자: (일반 값, 퍼센트 값). 규칙 결과와 입력에 있는 값만 허용한다.

    **31 이하 정수는 날짜·월·건수로 보고 허용한다.** "7월 16일"을 막으면 설명 자체가 불가능하다 —
    이 구멍 때문에 31 이하의 지표 값(예: 부족률 12%)은 퍼센트 단위가 붙어야 검사된다.
    """
    plain: set[Decimal] = {Decimal(n) for n in range(0, 32)} | {Decimal(2027)}
    pct: set[Decimal] = set()
    for f in payload["focus"]:
        for key in ("target", "prior", "latest", "unit_cm"):
            if f[key] is not None:
                plain.add(Decimal(str(f[key])))
        for mid, value in f["metrics"].items():
            if value is None:
                continue
            v = Decimal(value)
            if mid in ("KPI01", "KRI01", "KRI03"):
                pct.add(v * 100)
                plain.add(v)  # 입력의 원래 비율값(0.07368421)을 그대로 인용한 것도 같은 값이다
            else:
                plain.add(abs(v))
    for value in payload["rules"].values():
        v = Decimal(value)
        if v < 1:
            pct.add(v * 100)  # 비율 임계값 3%·5%·10%
            plain.add(v)
        else:
            plain.add(v)  # 금액 임계값 500만·1,000만원
    return plain, pct


def _numbers(text: str) -> list[tuple[Decimal, str]]:
    cleaned = _ID.sub(" ", text)
    out = []
    for raw, unit in _NUM.findall(cleaned):
        v = Decimal(raw.replace(",", ""))
        unit = (unit or "").replace(" ", "")
        if unit.startswith("만"):
            v *= 10_000
        elif unit.startswith("억"):
            v *= 100_000_000
        out.append((v, "%" if unit == "%" else ""))
    return out


def validate(output: Any, payload: dict[str, Any]) -> list[str]:
    """계약 위반 목록. 비어 있어야 화면에 초안으로 낸다."""
    if not isinstance(output, dict):
        return ["응답이 JSON 객체가 아니다"]
    errors = [f"필수 항목 없음: {k}" for k in REQUIRED if k not in output]
    if errors:
        return errors
    if not isinstance(output["summary"], str) or not output["summary"].strip():
        errors.append("summary가 비어 있다")
    for key in ("findings", "evidence_refs", "questions", "limitations"):
        if not isinstance(output[key], list) or not all(isinstance(x, str) for x in output[key]):
            errors.append(f"{key}는 문자열 목록이어야 한다")
    if not errors and not output["findings"]:
        errors.append("findings가 비어 있다")
    tasks = output["suggested_tasks"]
    if not isinstance(tasks, list) or not all(
        isinstance(t, dict) and t.get("type") in TASK_TYPES and isinstance(t.get("reason"), str)
        for t in tasks
    ):
        errors.append(f"suggested_tasks는 {{type: {sorted(TASK_TYPES)}, reason}} 목록이어야 한다")
    if errors:
        return errors

    catalog = set(payload["evidence_catalog"])
    unknown = [r for r in output["evidence_refs"] if r not in catalog]
    if unknown:
        errors.append(f"없는 근거 ID: {', '.join(unknown[:5])}")

    plain, pct = allowed_numbers(payload)
    texts = [
        output["summary"],
        *output["findings"],
        *output["questions"],
        *output["limitations"],
        *(t["reason"] for t in tasks),
    ]
    for text in texts:
        for value, unit in _numbers(text):
            pool = pct if unit == "%" else plain
            # 퍼센트는 표시 반올림(7.37 · 7.4)을 허용한다. 금액·물량은 정확히 같아야 한다.
            if unit == "%":
                ok = any(abs(value - v) <= Decimal("0.05") for v in pool)
            else:
                ok = value in pool
            if not ok:
                errors.append(f'규칙 결과에 없는 숫자: {value}{unit} — "{text[:40]}"')
    return errors


# ─────────────────────────── 러너 ───────────────────────────


@dataclass
class Draft:
    output: dict[str, Any]
    provenance: str  # mock | llm:<model>
    model: str | None
    latency_ms: int


class Runner(Protocol):
    def run(self, payload: dict[str, Any]) -> Draft: ...


def _won(value: str) -> str:
    v = Decimal(value)
    return f"{int(v / 10_000):,}만원" if abs(v) >= 10_000 else f"{int(v):,}원"


RISK_KO = {"CRITICAL": "중요", "ATTENTION": "관심", "NORMAL": "기준 이내", None: "판정 보류"}


class MockRunner:
    """
    결정론 초안 — 기본 시연과 테스트용. 규칙 결과에서만 문장을 만든다(구현명세 11장 기대 설명).

    **이것도 Agent 계약을 그대로 통과해야 한다** — 검증을 건너뛰는 지름길이 없다.
    """

    def run(self, payload: dict[str, Any]) -> Draft:
        started = time.monotonic()
        rank = {"CRITICAL": 2, "ATTENTION": 1, "NORMAL": 0, None: -1}
        top = max(payload["focus"], key=lambda f: rank[f["risk"]]) if payload["focus"] else None
        run_id = payload["run_id"]
        if top is None:
            output = {
                "summary": "이번 계산에서 바뀐 모델·월이 없다.",
                "findings": ["직전 승인 전망과 최신 전망이 같다."],
                "evidence_refs": [run_id],
                "questions": [],
                "suggested_tasks": [],
                "limitations": ["물량 변화만 반영한 초기 공헌이익 영향이다."],
            }
        else:
            m = top["metrics"]
            month = int(top["period"][5:7])
            model = top["model_id"][-1]
            pct = lambda v: f"{Decimal(v) * 100:.2f}".rstrip("0").rstrip(".")  # noqa: E731
            output = {
                "summary": (
                    f"{month}월 {model}모델의 공급 전망이 직전 승인 전망 {top['prior']:,}대분에서 "
                    f"{top['latest']:,}대분으로 {int(Decimal(m['M01'])):,}대분 감소했다. "
                    f"목표 달성률은 {pct(m['KPI01'])}%이며, 기준 단위 공헌이익 "
                    f"{int(Decimal(top['unit_cm'])):,}원 적용 시 추가 공헌이익 감소는 "
                    f"{_won(m['KRI02'])}이다."
                ),
                "findings": [
                    f"직전 대비 감소율 {pct(m['KRI01'])}%, 감소액 {_won(m['KRI02'])}, "
                    f"목표 대비 부족률 {pct(m['KRI03'])}% — 위험 수준 {RISK_KO[top['risk']]}.",
                    f"목표 대비 부족물량은 {int(Decimal(m['M02'])):,}대분이고 이번 추가 감소는 "
                    f"{int(Decimal(m['M01'])):,}대분이다 — 둘을 구분해야 한다.",
                ],
                "evidence_refs": [
                    run_id,
                    payload["source"]["source_id"],
                    *(
                        metric_ref(run_id, top["model_id"], top["period"], k)
                        for k in ("KRI01", "KRI02", "KRI03")
                    ),
                    *(i["issue_id"] for i in payload["issues"] if i["model_id"] == top["model_id"]),
                ],
                "questions": [
                    "고객의 차종별 생산 조정 사유 확인 필요 — 이번 원천에 감소 사유가 없다.",
                    f"{month}월 이후에도 같은 폭의 감소가 이어지는지 고객 재확인이 필요한가?",
                ],
                "suggested_tasks": [
                    {"type": "PROD", "reason": "생산계획·라인 운영 영향 검토"},
                    {"type": "MAT", "reason": "소요자재·발주 조정 가능 여부 검토"},
                    *(
                        [{"type": "FIN", "reason": "단가·운영비용을 반영한 통합 손익 검토"}]
                        if top["risk"] == "CRITICAL"
                        else []
                    ),
                ],
                "limitations": [
                    "물량 변화만 반영한 초기 공헌이익 영향이다 — 단가·원가 변동은 "
                    "다음 업무에서 분석한다.",
                    "감소 원인은 원천에 없어 단정하지 않았다.",
                ],
            }
        return Draft(output, "mock", None, int((time.monotonic() - started) * 1000))


class FailingRunner:
    """EX08 — Agent 응답 실패. 규칙 계산과 수동 검토는 그대로 가능해야 한다."""

    def run(self, payload: dict[str, Any]) -> Draft:
        raise AgentFailure("Agent 응답 실패(EX08 시연) — 담당자가 직접 검토한다")


_SCHEMA_HINT = {
    "summary": "str",
    "findings": ["str"],
    "evidence_refs": ["str — evidence_catalog의 ID"],
    "questions": ["str"],
    "suggested_tasks": [{"type": "PROD|MAT|FIN|DQ", "reason": "str"}],
    "limitations": ["str"],
}


class OllamaRunner:
    """
    ollama `/api/chat`. **스키마를 프롬프트에 넣고 검증한다** — `kimi-k3:cloud`는 `format`
    스키마를 무시하고 마크다운 산문을 돌려준 적이 있다(CLAUDE.md 4.15).
    """

    def __init__(self, base_url: str, model: str, *, timeout_s: float = 120.0) -> None:
        self.base_url, self.model, self.timeout_s = base_url.rstrip("/"), model, timeout_s

    def run(self, payload: dict[str, Any]) -> Draft:
        prompt = (
            "너는 자동차 부품사 경영관리의 검토 지원 Agent다. "
            "아래 규칙 계산 결과를 **인용만** 해서 영업팀장이 읽을 검토 초안을 한국어로 써라.\n"
            "규칙: 숫자는 입력에 있는 값만 쓴다(새로 계산하지 않는다). 원천에 없는 원인·고객 발언·"
            "개선 효과를 사실처럼 쓰지 않는다 — 모르면 questions에 묻는다. evidence_refs는 "
            "evidence_catalog에 있는 ID만 쓴다. 위험 수준을 바꾸지 않는다.\n"
            "표기: 지표는 코드가 아니라 metric_names의 이름으로 쓰고, 비율은 백분율(예: 7.37%), "
            "금액은 만원 단위(예: 1,400만원), 물량은 대분으로 쓴다. "
            "CRITICAL은 중요, ATTENTION은 관심이다.\n"
            "출력은 JSON 객체 하나만: "
            + json.dumps(_SCHEMA_HINT, ensure_ascii=False)
            + "\n\n입력:\n"
            + json.dumps(payload, ensure_ascii=False)
        )
        started = time.monotonic()
        try:
            r = httpx.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": 0},
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=self.timeout_s,
            )
            r.raise_for_status()
            content = r.json()["message"]["content"]
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            raise AgentFailure(f"모델 호출 실패: {exc}") from exc
        found = re.search(r"\{.*\}", content, re.S)
        if not found:
            raise AgentFailure("응답에 JSON이 없다")
        try:
            output = json.loads(found.group(0))
        except json.JSONDecodeError as exc:
            raise AgentFailure(f"JSON 해석 실패: {exc}") from exc
        latency = int((time.monotonic() - started) * 1000)
        return Draft(output, f"llm:{self.model}", self.model, latency)


def runner_for(mode: str) -> Runner:
    if mode == "fail":
        return FailingRunner()
    if mode == "llm":
        return OllamaRunner(
            os.getenv("OLLAMA_URL", "http://localhost:11434"),
            os.getenv("OLLAMA_MODEL", "kimi-k3:cloud"),
        )
    return MockRunner()


def default_mode() -> str:
    """`NOWVIEW_AGENT_MODE` — mock(기본) | llm. 시연은 결정론이 기본이고 LLM은 켜는 쪽이 고른다."""
    mode = os.getenv("NOWVIEW_AGENT_MODE", "mock")
    return mode if mode in ("mock", "llm") else "mock"
