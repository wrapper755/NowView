"""
SC05 시드 — `seed/SYN-SC05-v0.5.xlsx`(SC01~SC05 통합가상데이터 v0.5, 2026-10-24 검토 완료본).

**숫자 원천은 장면 2~4와 같은 시트다** — v0.5는 기존 45개 시트를 그대로 두고 SC05 시트 26개만
더했다(시험이
v0.4와 대조한다). 물량·원가·고정비는 `app/sc02/seed.load_seed`에 이 파일 경로를 줘서 읽는다.

**장면 5 시트는 세 종류다**(구현명세 11·12장, 데이터계약).

* **원천 — 업무 중에 읽는다.** `SC05설정`(규칙·가정), `SC05활동`(Agent 초안의 재료 — 사람이 고친다),
  `SC05고객계획`·`SC05변경공유`·`SC05구매표본`(고객 원문·변경 건·9월 구매 60건), `SC05예산원장`의
  배경 거래,
  `SC05근거`, `SC05Agent`(제안 문장), `SC05조건품의`의 배경 품의(REQ52·REQ53). 시각이 지나야 보인다
  —
  미래 행을 초기 화면에 내리지 않는다(구현명세 16장).
* **배경 이력** — `SC05이전공식`(FC50 — 9/6 승인된 가상 중간 공식본, 불변 스냅샷)·`SC05운영계획`의
  ACT41·43
  요약. 상세 시연이 없는 배경 과제는 근거와 함께 요약만 한다.
* **기본 시연 종료 시점의 기대값** —
  계획·월효과·모델손익·월손익·전망버전·변경대사·이벤트·인계·착수조건·
  초기지표·예산·검증. 계산 입력으로 쓰지 않는다 — 각본의 입력(사람이 칠 문장·시각)과 시험의
  기대값으로만 읽는다.

엑셀 시각은 KST 벽시계 값이다(+09:00, 가장 가까운 초) — UTC로 먼저 간주해 9시간 옮기지
않는다(구현명세 18장).
장면 3 `kst()`를 그대로 쓴다.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from app.sc02 import seed as sc02_seed
from app.sc02.seed import Seed as NumbersSeed
from app.sc03.seed import _sheet, kst

SEED_PATH = Path(__file__).resolve().parents[2] / "seed" / "SYN-SC05-v0.5.xlsx"
SEED_ID = "SYN-SC05-v0.5"
#: 시트 이름 → 헤더 첫 칸
SHEETS = {
    "SC05설정": "key",
    "SC05계획": "plan_id",
    "SC05활동": "activity_key",
    "SC05조건품의": "record_id",
    "SC05예산원장": "txn_id",
    "SC05예산": "과제",
    "SC05고객계획": "row_id",
    "SC05변경공유": "change_id",
    "SC05구매표본": "order_id",
    "SC05초기지표": "지표ID",
    "SC05월효과": "effect_id",
    "SC05모델손익": "row_id",
    "SC05월손익": "기간",
    "SC05이전공식": "version_id",
    "SC05전망버전": "version_id",
    "SC05변경대사": "원인",
    "SC05운영계획": "plan_id",
    "SC05근거": "evidence_id",
    "SC05Agent": "agent_run",
    "SC05이벤트": "event_id",
    "SC05인계": "id",
    "SC05착수조건": "checkpoint",
    "SC05예외": "case_id",
    "SC05검증": "check_id",
}

__all__ = ["SEED_ID", "SEED_PATH", "Seed", "kst", "load_seed"]


@dataclass(frozen=True)
class Seed:
    #: 숫자 — 장면 2~4와 같은 원천 시트(물량·원가·고정비·설정)
    numbers: NumbersSeed
    #: 장면 5 시트 이름 → 행 목록(헤더 → 값). 원값 그대로다 — 시각은 `kst()`로 읽는다.
    sheets: dict[str, list[dict[str, Any]]]

    def rows(self, sheet: str) -> list[dict[str, Any]]:
        return self.sheets[sheet]

    def by_id(self, sheet: str) -> dict[str, dict[str, Any]]:
        key = SHEETS[sheet]
        return {str(r[key]): r for r in self.sheets[sheet]}

    def setting(self, key: str) -> Any:
        return self.by_id("SC05설정")[key]["value"]


@cache
def load_seed(path: Path = SEED_PATH) -> Seed:
    wb = load_workbook(path, data_only=True, read_only=True)
    sheets = {name: _sheet(wb[name], first) for name, first in SHEETS.items()}
    wb.close()
    return Seed(numbers=sc02_seed.load_seed(path), sheets=sheets)
