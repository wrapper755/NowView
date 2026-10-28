"""
SC01 기본 시연 각본 — S0 → EV01~EV07 (통합 가상 데이터 설계 「업무이력」 시트).

**단계 진행은 실제 상태 전환을 실행한다**(구현명세 2장). 각본은 "누가 언제 무엇을 했나"만
들고 있고, 실행은 사람이 버튼을 누른 것과 같은 경로(`Sc01Process.receive`·`act`)를 탄다 —
역할 검사·업무 규칙을 건너뛰는 지름길이 없다. 이미 끝난 단계를 다시 실행하면 아무것도 새로
만들지 않고 현재 문서를 돌려준다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.sc01 import domain
from app.sc01.domain import DomainError, parse_at
from app.sc01.process import Sc01Process


@dataclass(frozen=True)
class Step:
    code: str
    at: str  # KST 가상시각
    actor: str
    node_id: str | None  # None이면 원천 수신
    answer: dict[str, Any] = field(default_factory=dict)
    label: str = ""


BASE: list[Step] = [
    Step(
        "EV01",
        "2027-06-16T09:00:00+09:00",
        "u-sales",
        None,
        {"fixture_id": "CP02"},
        "새 고객계획 수신",
    ),
    Step(
        "EV02",
        "2027-06-16T10:00:00+09:00",
        "u-sales",
        "Approve_DQ",
        {
            "확인결과": "확인완료",
            "확인의견": "CP02 15행 — 당사 배정·월 전체 물량. b모델 7월만 9,500→8,800으로 바뀌었다.",
            "확인근거": "SRC02 원본 대조, 매핑표 A-a~A-e",
        },
        "원천 확인",
    ),
    Step("EV03", "2027-06-16T10:10:00+09:00", "u-sales", "Confirm_Calc", {}, "비교 계산"),
    Step(
        "EV04",
        "2027-06-16T11:00:00+09:00",
        "u-sales-lead",
        "Approve_Sales",
        {
            "영업의견": "고객이 확정한 7월 변경이다. 8월 이후 지속 여부는 고객 재확인이 필요하다.",
            "영업근거": "RUN-F02-001 b모델 7월 지표, CP02 수신본",
            "경영검토요청": False,
        },
        "영업 검토",
    ),
    Step(
        "EV04",
        "2027-06-16T11:00:00+09:00",
        "u-sales-lead",
        "Approve_Dispatch",
        {
            "생산담당자": "u-prod",
            "자재담당자": "u-mat",
            "배정사유": "b모델 7월 700대분 감소의 생산계획·소요자재·발주 영향 검토",
        },
        "현업 검토 배정",
    ),
    Step(
        "EV05",
        "2027-06-16T11:05:00+09:00",
        "u-sales-lead",
        "Approve_Review",
        {
            "경영관리담당자": "u-fin",
            "검토요청사유": "감소율·감소액·목표 부족률 모두 중요 — 통합 손익 검토 필요",
        },
        "Management Review 요청",
    ),
    Step(
        "EV06",
        "2027-06-16T11:30:00+09:00",
        "u-prod",
        "Accept_PROD",
        {"생산인수의견": "7월 b라인 일정 재검토 착수"},
        "생산 인수",
    ),
    Step(
        "EV06",
        "2027-06-16T11:30:00+09:00",
        "u-mat",
        "Accept_MAT",
        {"자재인수의견": "7월 b모델 외주부품 발주 조정 가능분 확인 착수"},
        "자재 인수",
    ),
    Step(
        "EV07",
        "2027-06-16T11:45:00+09:00",
        "u-fin",
        "Accept_FIN",
        {"경영관리인수의견": "단가·운영비용 반영 통합 손익분석 착수"},
        "경영관리 인수",
    ),
]


def run_step(process: Sc01Process, demo_run_id: str, index: int) -> dict:
    """각본의 `index`번째 단계를 실행한다. 이미 지나간 단계면 현재 문서를 돌려준다."""
    if not 0 <= index < len(BASE):
        raise DomainError(f"각본에 없는 단계: {index}", 404)
    doc = process.get(demo_run_id)
    if domain.executor_of(doc) == "studio":
        # Studio 시험 실행의 결재는 Studio 대화상자만 받는다. Center는 각본이 대리 답한다(N3).
        raise DomainError(
            "Studio 시험 실행의 데모 실행은 각본을 돌리지 않는다 — 결재는 Studio에서 답한다",
            409,
        )
    done = doc.get("script_index", -1)
    if index <= done:
        return doc
    if index != done + 1:
        raise DomainError(f"단계를 건너뛸 수 없다 — 다음은 {done + 1}번이다", 409)
    step = BASE[index]
    if parse_at(step.at) > parse_at(doc["clock"]):
        process.set_clock(demo_run_id, step.at, actor="u-demo", event_code=step.code)
    if step.node_id is None:
        return process.receive(
            demo_run_id,
            step.answer["fixture_id"],
            actor=step.actor,
            event_code=step.code,
            script_index=index,
        )
    if domain.executor_of(doc) == "center" and not (doc["bpm"] or {}).get("external_run_id"):
        # 접수 가상 직원을 거친 수신이면 SC01은 감독자 일괄 승인 뒤에야 기동된다(N5). 각본은
        # 장면 2 시작과 같이 감독자로 대리 승인한다 — 기다리는 일괄이 없으면 아무것도 하지 않는다.
        process.approve_intake_for_script(demo_run_id, opinion="각본 — 감독자 대리 승인")
    return process.act(
        demo_run_id,
        step.node_id,
        step.answer,
        actor=step.actor,
        event_code=step.code,
        script_index=index,
    )
