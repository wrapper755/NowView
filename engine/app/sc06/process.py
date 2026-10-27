"""
SC06 실행 — 장면 5 인계(HANDOFF51)에서 이어 RV61 검토 문서를 적재하고, 화면은 그것을 **조회만**
한다.

**장면 6에는 이 장면이 돌리는 BPM 흐름이 없다.** 구현명세 11장이 「SC06은 이미 확인된 1/14 보고본을
조회하는 시점으로
시작한다. SC05처럼 단계별 결재를 재연할 필요가 없다」고 정했고, 13장은 BPM 몫을 「기존 확인 이력과
완료 판단·후속 상태
연결. 이 장면의 조회를 결재 트리거와 분리」로 둔다. 담당 임원 확인 → 경영관리 임원 종합 확인 →
보고본 확정 → 대표
보고는 끝난 업무 기록(SC06보고)으로 적재한다 — 장면 5의 배경 원천(`catch_up`)과 같은 성격이다.
그래서 외부 확장·
Center 패키지도 없다(조회가 Center를 부르지 않는다).

* **데모 실행 id가 장면 1~5와 같다.** 장면 5가 완료 전이면 장면 5 각본을 끝까지 실제로 실행한 뒤
  적재한다(장면 2~5와 같은
  원칙 — 지름길로 「완료됨」을 만들지 않는다). Studio 실행이면 409다 — Studio에서 장면 5를 끝낸 뒤
  연다.
* **초기화가 없다** — 구현명세 11장 「초기화는 브라우저 선택·펼침만 되돌린다. 확정본·근거·확인
  이력은 삭제하지
  않는다」. 화면의 초기화는 화면 상태만 되돌린다.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime

from app.sc01.domain import DomainError, executor_of
from app.sc01.store import Sc01Store
from app.sc05 import demo as sc05_demo
from app.sc05.process import Sc05Process
from app.sc06 import domain
from app.sc06.seed import Seed, load_seed

CENTER_WAIT_S = 10.0


class Sc06Process:
    def __init__(
        self,
        store: Sc01Store,
        sc05: Sc05Process,
        *,
        seed: Seed | None = None,
        publish=lambda _id: None,
        center_wait_s: float = CENTER_WAIT_S,
    ) -> None:
        self.store = store
        self.sc05 = sc05
        self.seed = seed or load_seed()
        self.publish = publish
        self.center_wait_s = center_wait_s

    def _finish_sc05(self, demo_run_id: str | None, executor: str) -> dict:
        """
        장면 5를 완료(HANDOFF51)까지 — 각본의 남은 단계를 실제로 실행한다(장면 5가 없으면 장면
        1부터).
        """
        found = None if demo_run_id is None else self.sc05.store.load(demo_run_id)
        doc = (
            self.sc05.create(sc01_demo_run_id=demo_run_id, executor=executor)
            if found is None
            else found[0]
        )
        rid = doc["demo_run_id"]
        if doc["handoff"] is not None:
            return doc
        if executor_of(doc) == "studio":
            raise DomainError(
                "장면 5가 Studio 시험 실행이다 — "
                "Studio에서 장면 5 완료까지 진행한 뒤 장면 6을 연다",
                409,
            )
        steps = sc05_demo.steps_for(doc["case_id"], self.sc05.seed)
        try:
            for i in range(doc.get("script_index", -1) + 1, len(steps)):
                doc = sc05_demo.run_step(self.sc05, rid, i)
                if executor_of(doc) == "center":
                    self.sc05.sync_center(rid)
        except DomainError as exc:
            raise DomainError(
                f"장면 5를 각본으로 완료까지 끝낼 수 없다 — {exc}. 장면 5를 초기화한 뒤 다시 한다",
                409,
            ) from exc
        deadline = time.monotonic() + self.center_wait_s
        doc = self.sc05.get(rid)
        while doc["handoff"] is None and time.monotonic() < deadline:
            time.sleep(min(0.5, self.center_wait_s))
            doc = self.sc05.get(rid)
        if doc["handoff"] is None:
            raise DomainError(
                "장면 5 각본을 다 돌렸지만 아직 완료가 기록되지 않았다 — "
                "바깥 실행이 완료 기록을 부를 때까지 "
                "기다린 뒤 다시 연다",
                409,
            )
        return doc

    def create(
        self,
        *,
        sc01_demo_run_id: str | None = None,
        case_id: str = "BASE",
        executor: str = "embedded",
    ) -> dict:
        """
        장면 6 적재. 이미 있으면 그대로 돌려준다 — 다시 적재하지 않는다(동일 키 중복 생성 없음,
        구현명세 8장 7단계).
        `executor`는 장면 1~5가 아직 없을 때 그 장면들을 어디서 돌릴지다 — 장면 6 자신은 BPM을 돌지
        않는다.
        """
        if case_id not in domain.CASES:
            raise DomainError(
                f"모르는 시연 사례: {case_id} — 장면 6 예외(X61-*)는 시험 fixture로만 적재한다", 422
            )
        if sc01_demo_run_id is not None:
            existing = self.store.load(sc01_demo_run_id)
            if existing is not None:
                return existing[0]
        sc05_doc = self._finish_sc05(sc01_demo_run_id, executor)
        rid = sc05_doc["demo_run_id"]
        doc = domain.new_review(self.seed, rid, sc05_doc, created_at=datetime.now(UTC))
        self.store.insert(rid, doc)
        self.publish(f"sc06:{rid}")
        return doc

    def get(self, demo_run_id: str) -> dict:
        found = self.store.load(demo_run_id)
        if found is None:
            raise domain.ReadError(
                f"장면 6이 열리지 않은 데모 실행: {demo_run_id}", 404, "NOT_FOUND"
            )
        return found[0]
