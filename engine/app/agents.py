"""
Agent 노드의 실행 주체.

두 구현이 같은 인터페이스를 만족한다:

* `MockRunner` — `lib/mock-data`의 산출물을 그대로 돌려준다. 결정론적이라 테스트와
  데모가 이것을 쓴다.
* `OllamaRunner` — 실제 LLM을 부른다.

**검증된 제약: `kimi-k3:cloud`는 ollama의 `format` 스키마 제약을 타지 않는다.**
스키마만 주면 JSON이 아닌 마크다운 산문이 돌아온다. 그래서 스키마를 **프롬프트에**
넣고, 받은 것을 검증하고, 실패하면 재시도한다. `format`도 함께 보내지만 그것에
기대지 않는다.

**계약을 못 맞추면 지어내지 않고 실패한다.** 조용히 그럴듯한 값으로 메우면
Agent가 고장난 것을 아무도 모른 채 화면에 숫자가 나간다 — 이 프로젝트에서 가장
피하려는 종류의 거짓말이다(CLAUDE.md 4.12).
"""

from __future__ import annotations

import json
import logging
from typing import Any, Protocol

import httpx

from .spec import AgentSpec, NodeSpec, ProcessSpec

log = logging.getLogger(__name__)

DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_MODEL = "kimi-k3:cloud"


class AgentContractError(RuntimeError):
    """LLM이 정해진 산출물 계약을 맞추지 못했다."""


class AgentRunner(Protocol):
    mode: str

    def run(
        self,
        *,
        spec: ProcessSpec,
        node: NodeSpec,
        agent: AgentSpec | None,
        required_flags: list[str],
        state: dict[str, Any],
    ) -> dict[str, Any]:
        """
        산출물을 돌려준다. 반환 dict는 TS의 `AgentRun` 모양 + `flags`다.
        """
        ...


class MockRunner:
    """명세에 실려 온 산출물을 그대로 돌려준다."""

    mode = "mock"

    def run(
        self,
        *,
        spec: ProcessSpec,
        node: NodeSpec,
        agent: AgentSpec | None,
        required_flags: list[str],
        state: dict[str, Any],
    ) -> dict[str, Any]:
        recorded = spec.output_for(node.id)
        if recorded is None:
            # Mock에 기록이 없는 Agent 노드. 산출물을 지어내지 않고 그 사실을 남긴다.
            return {
                "agentId": agent.id if agent else node.agent_id or node.id,
                "nodeId": node.id,
                "output": "Mock 산출물이 정의되지 않은 노드다.",
                "sources": [],
                "duration": "0분 00초",
                "confidence": "low",
                "confidenceNote": "Mock 데이터에 이 노드의 산출물이 없다.",
                "escalations": [],
                "flags": {},
                "provenance": "mock-missing",
            }
        return {
            "agentId": recorded.agent_id,
            "nodeId": recorded.node_id,
            "output": recorded.output,
            "sources": recorded.sources,
            "duration": recorded.duration,
            "confidence": recorded.confidence,
            "confidenceNote": recorded.confidence_note,
            "escalations": recorded.escalations,
            "flags": recorded.flags,
            "provenance": "mock",
        }


#: LLM에게 요구하는 산출물 계약. 프롬프트에 그대로 박아 넣는다.
OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "output": {"type": "string", "description": "산출물 요약 한두 문장. 한국어."},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "confidenceNote": {
            "type": "string",
            "description": "confidence가 high가 아니면 그 이유. high면 빈 문자열.",
        },
        "flags": {
            "type": "object",
            "description": "요구된 판정 플래그. 값은 true/false.",
            "additionalProperties": {"type": "boolean"},
        },
        "escalations": {
            "type": "array",
            "description": "스스로 답할 수 없어 사람에게 넘기는 질문. 없으면 빈 배열.",
            "items": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "reason": {"type": "string"},
                    "owner": {"type": "string"},
                    "ifUnanswered": {"type": "string"},
                },
                "required": ["question", "reason", "owner", "ifUnanswered"],
            },
        },
    },
    "required": ["output", "confidence", "flags", "escalations"],
}


class OllamaRunner:
    """
    ollama로 실제 LLM을 부른다.

    `sources`는 LLM이 만들지 않고 명세의 것을 그대로 쓴다 — 근거 데이터의 출처와
    품질을 모델이 지어내면 검증 자체가 무의미해진다(CLAUDE.md 4.12).
    """

    mode = "llm"

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_OLLAMA_URL,
        model: str = DEFAULT_MODEL,
        timeout: float = 180.0,
        max_attempts: int = 3,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.max_attempts = max_attempts

    def run(
        self,
        *,
        spec: ProcessSpec,
        node: NodeSpec,
        agent: AgentSpec | None,
        required_flags: list[str],
        state: dict[str, Any],
    ) -> dict[str, Any]:
        recorded = spec.output_for(node.id)
        sources = recorded.sources if recorded else []
        messages = [
            {"role": "system", "content": self._system_prompt(required_flags)},
            {"role": "user", "content": self._user_prompt(spec, node, agent, sources, state)},
        ]

        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                raw = self._chat(messages)
                parsed = self._validate(raw, required_flags)
            except (AgentContractError, json.JSONDecodeError) as exc:
                last_error = exc
                log.warning("Agent 계약 위반 (%s, 시도 %d/%d): %s",
                            node.id, attempt, self.max_attempts, exc)
                # 무엇이 틀렸는지 알려주고 다시 묻는다. 같은 프롬프트를 반복하면
                # 같은 실패를 반복한다.
                messages = messages[:2] + [
                    {"role": "user", "content": f"이전 응답이 계약을 위반했다: {exc}. "
                                                "스키마를 정확히 따르는 JSON만 다시 출력하라."}
                ]
                continue

            return {
                "agentId": agent.id if agent else node.agent_id or node.id,
                "nodeId": node.id,
                "output": parsed["output"],
                "sources": sources,
                "duration": parsed["_duration"],
                "confidence": parsed["confidence"],
                "confidenceNote": parsed.get("confidenceNote") or None,
                "escalations": parsed["escalations"],
                "flags": parsed["flags"],
                "provenance": f"llm:{self.model}",
            }

        raise AgentContractError(
            f"{node.id}: {self.max_attempts}회 시도 후에도 산출물 계약을 맞추지 못했다 "
            f"(모델 {self.model}). 마지막 오류: {last_error}"
        )

    # ------------------------------------------------------------------ 내부

    def _system_prompt(self, required_flags: list[str]) -> str:
        flag_note = (
            "다음 판정 플래그를 flags에 **반드시** 포함한다: " + ", ".join(required_flags)
            if required_flags
            else "요구된 판정 플래그가 없으므로 flags는 빈 객체로 둔다."
        )
        return (
            "당신은 자동차 부품 제조사의 경영 분석 Agent다.\n"
            "아래 JSON 스키마를 정확히 따르는 JSON 객체 **하나만** 출력한다.\n"
            "키 이름을 번역하거나 바꾸지 않는다. 코드블록·머리말·설명을 붙이지 않는다.\n"
            f"{flag_note}\n"
            "근거 데이터에 없는 수치를 단정하지 않는다. 확신이 없으면 confidence를 낮추고 "
            "이유를 confidenceNote에 적는다. 스스로 답할 수 없는 판단은 추측하지 말고 "
            "escalations에 질문으로 남긴다.\n\n"
            "스키마:\n" + json.dumps(OUTPUT_SCHEMA, ensure_ascii=False, indent=2)
        )

    def _user_prompt(
        self,
        spec: ProcessSpec,
        node: NodeSpec,
        agent: AgentSpec | None,
        sources: list[dict],
        state: dict[str, Any],
    ) -> str:
        parts = [
            f"안건: {spec.subject}",
            f"감지 지표: {spec.kri.get('label')} = {spec.kri.get('value')} "
            f"(임계치 {spec.kri.get('threshold')})",
            f"수행 단계: {node.label}",
        ]
        if agent:
            parts.append(f"당신의 역할: {agent.name} — {agent.role} ({agent.capability})")
        if sources:
            lines = []
            for s in sources:
                quality = s.get("quality", "complete")
                caveat = f" — 유의: {s['caveat']}" if s.get("caveat") else ""
                # TS `DataSource`의 필드는 `name`이다.
                lines.append(f"  · {s.get('name', s)} [품질: {quality}]{caveat}")
            parts.append("참조 가능한 데이터:\n" + "\n".join(lines))
        prior = state.get("runs") or []
        if prior:
            parts.append(
                "선행 Agent 산출물:\n"
                + "\n".join(f"  · {r.get('output', '')}" for r in prior[-3:])
            )
        return "\n".join(parts)

    def _chat(self, messages: list[dict[str, str]]) -> tuple[str, float]:
        body = {
            "model": self.model,
            "stream": False,
            "messages": messages,
            "options": {"temperature": 0},
            # cloud 모델에서는 무시되는 것을 확인했지만, 로컬 모델에서는 유효하므로
            # 계속 보낸다. 이것에 **기대지는** 않는다.
            "format": OUTPUT_SCHEMA,
        }
        with httpx.Client(timeout=self.timeout) as client:
            res = client.post(f"{self.base_url}/api/chat", json=body)
            res.raise_for_status()
            payload = res.json()
        if "error" in payload:
            raise AgentContractError(f"ollama 오류: {payload['error']}")
        # ollama는 나노초로 준다. 화면 표기가 "N분 NN초"라 같은 형식으로 맞춘다.
        elapsed = payload.get("total_duration", 0) / 1e9
        return payload["message"]["content"], elapsed

    def _validate(self, raw: tuple[str, float], required_flags: list[str]) -> dict[str, Any]:
        content, elapsed = raw
        text = content.strip()
        # 코드블록을 붙이지 말라고 했지만 붙여 오는 경우가 있다. 벗겨 본 뒤 판단한다.
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()
        if not text.startswith("{"):
            raise AgentContractError("JSON 객체가 아니다 (산문 응답)")

        obj = json.loads(text)
        for key in ("output", "confidence", "flags", "escalations"):
            if key not in obj:
                raise AgentContractError(f"필수 키 누락: {key}")
        if obj["confidence"] not in ("high", "medium", "low"):
            raise AgentContractError(f"confidence 값이 허용 범위 밖: {obj['confidence']!r}")
        if not isinstance(obj["flags"], dict):
            raise AgentContractError("flags가 객체가 아니다")
        missing = [f for f in required_flags if f not in obj["flags"]]
        if missing:
            # 게이트웨이가 읽을 플래그가 없으면 분기를 못 한다 — 치명적이다.
            raise AgentContractError(f"요구된 판정 플래그 누락: {', '.join(missing)}")
        if not all(isinstance(v, bool) for v in obj["flags"].values()):
            raise AgentContractError("flags 값이 true/false가 아니다")
        if not isinstance(obj["escalations"], list):
            raise AgentContractError("escalations가 배열이 아니다")
        for esc in obj["escalations"]:
            for key in ("question", "reason", "owner", "ifUnanswered"):
                if key not in esc:
                    raise AgentContractError(f"escalation에 {key}가 없다")
        if obj["confidence"] != "high" and not (obj.get("confidenceNote") or "").strip():
            raise AgentContractError("confidence가 high가 아닌데 이유가 비어 있다")

        obj["_duration"] = _format_duration(elapsed)
        obj["flags"] = {k: v for k, v in obj["flags"].items() if k in required_flags}
        return obj


def _format_duration(seconds: float) -> str:
    """`lib/format` 및 `parseDurationMinutes`가 읽는 형식으로 맞춘다."""
    total = max(0, int(round(seconds)))
    return f"{total // 60}분 {total % 60:02d}초"


def make_runner(mode: str, *, model: str | None = None, base_url: str | None = None) -> AgentRunner:
    if mode == "mock":
        return MockRunner()
    if mode == "llm":
        kwargs: dict[str, Any] = {}
        if model:
            kwargs["model"] = model
        if base_url:
            kwargs["base_url"] = base_url
        return OllamaRunner(**kwargs)
    raise ValueError(f"알 수 없는 Agent 모드: {mode!r} (mock | llm)")
