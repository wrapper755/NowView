"""
Agent 산출물의 **계약 검증**.

CLAUDE.md 5.2가 예고한 전환이 여기다 — Mock일 때는 "산출물 문구에 +18억이 있다"를
확인할 수 있었지만 LLM은 비결정적이라 값을 비교할 수 없다. 실제로 temperature 0에서도
같은 질문에 14.2와 14.5가 나왔다. 그래서 검증 대상이 값이 아니라 **스키마·범위·
근거가 비어 있지 않은가**로 바뀐다.
"""

from __future__ import annotations

import json

import httpx
import pytest
from conftest import spec_with

from app.agents import (
    DEFAULT_MODEL,
    DEFAULT_OLLAMA_URL,
    AgentContractError,
    MockRunner,
    OllamaRunner,
    _format_duration,
    make_runner,
)


class TestMockRunner:
    def test_기록된_산출물을_그대로_돌려준다(self):
        spec = spec_with(True)
        run = MockRunner().run(
            spec=spec, node=spec.node("rca"), agent=None, required_flags=["crossFunctional"],
            state={},
        )
        assert run["provenance"] == "mock"
        assert run["flags"] == {"crossFunctional": True}
        assert run["confidence"] == "medium"
        assert run["confidenceNote"]

    def test_기록이_없으면_지어내지_않고_그_사실을_남긴다(self):
        spec = spec_with(True)
        spec.agent_outputs = []
        run = MockRunner().run(
            spec=spec, node=spec.node("rca"), agent=None, required_flags=[], state={},
        )
        assert run["provenance"] == "mock-missing"
        assert run["confidence"] == "low"
        assert run["confidenceNote"]


class TestContractValidation:
    """
    `OllamaRunner._validate`를 직접 시험한다 — 네트워크 없이 계약만 본다.

    검증된 사실: `kimi-k3:cloud`는 ollama의 `format` 스키마를 무시하고 마크다운
    산문을 돌려줄 수 있다. 그 경우를 반드시 걸러야 한다.
    """

    runner = OllamaRunner()

    def _validate(self, payload, required=("crossFunctional",)):
        raw = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
        # 12.5 같은 경계값은 피한다 — 파이썬은 짝수 반올림이라 12가 된다.
        return self.runner._validate((raw, 12.4), list(required))

    def _ok(self, **overrides):
        return {
            "output": "물량 감소가 갭의 68%를 설명한다.",
            "confidence": "high",
            "flags": {"crossFunctional": True},
            "escalations": [],
            **overrides,
        }

    def test_정상_응답을_통과시킨다(self):
        parsed = self._validate(self._ok())
        assert parsed["flags"] == {"crossFunctional": True}
        assert parsed["_duration"] == "0분 12초"

    def test_산문_응답을_거부한다(self):
        with pytest.raises(AgentContractError, match="산문"):
            self._validate("**갭: 5.9%p 미달**\n\n원인 2가지는 다음과 같습니다.")

    def test_코드블록은_벗겨_본다(self):
        # 붙이지 말라고 해도 붙여 오는 경우가 있다 — 그것만으로 실패시키지 않는다.
        wrapped = "```json\n" + json.dumps(self._ok(), ensure_ascii=False) + "\n```"
        assert self._validate(wrapped)["confidence"] == "high"

    def test_게이트웨이가_읽을_플래그가_없으면_거부한다(self):
        # 이게 없으면 분기를 못 한다 — 치명적이다.
        with pytest.raises(AgentContractError, match="판정 플래그 누락"):
            self._validate(self._ok(flags={}))

    def test_플래그가_불리언이_아니면_거부한다(self):
        with pytest.raises(AgentContractError, match="true/false"):
            self._validate(self._ok(flags={"crossFunctional": "yes"}))

    def test_요구하지_않은_플래그는_버린다(self):
        # 모델이 멋대로 판정을 덧붙이면 게이트웨이가 의도 없이 영향을 받는다.
        parsed = self._validate(self._ok(flags={"crossFunctional": True, "urgent": True}))
        assert parsed["flags"] == {"crossFunctional": True}

    def test_신뢰도_값이_범위_밖이면_거부한다(self):
        with pytest.raises(AgentContractError, match="허용 범위"):
            self._validate(self._ok(confidence="아주 높음"))

    def test_신뢰도가_high가_아니면_이유를_요구한다(self):
        # CLAUDE.md 4.12 — high가 아니면 이유를 적는다. 빈 채로 통과하면 규칙이 죽는다.
        with pytest.raises(AgentContractError, match="이유가 비어"):
            self._validate(self._ok(confidence="medium"))
        assert self._validate(
            self._ok(confidence="medium", confidenceNote="9월 수주 데이터에 결손이 있다.")
        )["confidence"] == "medium"

    def test_에스컬레이션에_가정이_빠지면_거부한다(self):
        # 답을 못 받고 진행할 때 어떤 가정 위에 서는지가 없으면 나중에 되짚을 수 없다.
        with pytest.raises(AgentContractError, match="ifUnanswered"):
            self._validate(self._ok(escalations=[
                {"question": "이관 물량 상한이 있나?", "reason": "고객 승인 필요",
                 "owner": "영업본부"}
            ]))

    def test_필수_키가_없으면_거부한다(self):
        with pytest.raises(AgentContractError, match="필수 키 누락"):
            self._validate({"output": "x", "confidence": "high", "flags": {}})


class TestDuration:
    @pytest.mark.parametrize(
        "seconds,expected",
        [(0, "0분 00초"), (9.4, "0분 09초"), (64, "1분 04초"), (671, "11분 11초")],
    )
    def test_TS가_읽는_형식으로_맞춘다(self, seconds, expected):
        # `parseDurationMinutes`가 못 읽으면 0이 아니라 throw한다 — 형식을 맞춰야 한다.
        assert _format_duration(seconds) == expected


class TestRunnerFactory:
    def test_모드에_따라_구현이_갈린다(self):
        assert make_runner("mock").mode == "mock"
        assert make_runner("llm").mode == "llm"

    def test_알_수_없는_모드는_거부한다(self):
        with pytest.raises(ValueError, match="mock | llm"):
            make_runner("gpt")


def _ollama_up() -> bool:
    try:
        return httpx.get(f"{DEFAULT_OLLAMA_URL}/api/version", timeout=3).status_code == 200
    except Exception:  # noqa: BLE001
        return False


@pytest.mark.llm
@pytest.mark.skipif(not _ollama_up(), reason="ollama가 떠 있지 않다")
class TestOllamaLive:
    """
    실제 호출. 기본 실행에서 제외된다(`pytest -m llm`으로 돈다).

    값을 확인하지 않는다 — 비결정적이다. **계약을 지키는지**만 본다.
    """

    def test_계약을_지키는_산출물을_만든다(self):
        spec = spec_with(True)
        runner = OllamaRunner(model=DEFAULT_MODEL)
        run = runner.run(
            spec=spec,
            node=spec.node("rca"),
            agent=spec.agents[1],
            required_flags=["crossFunctional"],
            state={"runs": [{"output": "가동률 82.1%, 3개월 연속 하락 확인."}]},
        )

        assert run["provenance"].startswith("llm:")
        assert run["output"].strip()
        assert run["confidence"] in ("high", "medium", "low")
        assert set(run["flags"]) == {"crossFunctional"}
        assert isinstance(run["flags"]["crossFunctional"], bool)
        # 근거 데이터는 모델이 만들지 않고 명세의 것을 쓴다.
        assert run["sources"] == spec.output_for("rca").sources
        if run["confidence"] != "high":
            assert run["confidenceNote"]
