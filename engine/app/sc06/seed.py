"""
SC06 시드 — `seed/SYN-SC06-v0.6.xlsx`(SC01~SC06 통합가상데이터 v0.6).

**v0.6은 기존 71개 시트를 그대로 두고 SC06 시트 20개만 더했다**(시험이 v0.5와 대조한다 — 구현명세
7장 「원래 71개
시트의 역사 데이터는 수정하지 않는다」).

**장면 6 시트는 세 종류다**(구현명세 7·8장, SC06데이터계약).

* **원천 — 적재해서 계산한다.** `SC06설정`(검토 기준·시각·규칙), `SC06기준`(FC51 승인 기대의 불변
  스냅샷 — 장면 5
  FC51과 대사한다), `SC06실행실적`(ACT41·43 월 마감), `SC06운영비`(ACT42 월 운영지원),
  `SC06구매거래`(Q4 주문 180건),
  `SC06변경근거`(긴급 14건의 원인 근거),
  `SC06완료판단`·`SC06후속조치`·`SC06근거`·`SC06Agent`·`SC06보고`(사람 판단·
  확인 이력 — 이미 끝난 업무 기록이다).
* **과제 정보** — `SC06과제성과`의 과제명·완료일·근거·후속 글. 숫자 칸은 쓰지 않는다(계산한다).
* **기대값** — 요약·과제성과 숫자·원인집계·분기손익·월효과·운영지표·검증. 계산 입력으로 쓰지 않는다
  — 시험이
  계산 결과와 대조한다. `SC06예외`는 시험 fixture의 설명이다(기본 적재에 섞지 않는다).

엑셀 시각은 KST 벽시계 값이다 — 장면 3 `kst()`를 그대로 쓴다.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from app.sc03.seed import _sheet, kst

SEED_PATH = Path(__file__).resolve().parents[2] / "seed" / "SYN-SC06-v0.6.xlsx"
SEED_ID = "SYN-SC06-v0.6"
#: 시트 이름 → 헤더 첫 칸
SHEETS = {
    "SC06요약": "항목",
    "SC06과제성과": "task_id",
    "SC06원인집계": "원인코드",
    "SC06분기손익": "월",
    "SC06기준": "baseline_id",
    "SC06설정": "key",
    "SC06실행실적": "actual_id",
    "SC06운영비": "cost_id",
    "SC06구매거래": "order_id",
    "SC06변경근거": "change_id",
    "SC06월효과": "effect_id",
    "SC06운영지표": "metric_id",
    "SC06완료판단": "judgment_id",
    "SC06후속조치": "followup_id",
    "SC06근거": "evidence_id",
    "SC06Agent": "run_id",
    "SC06보고": "record_id",
    "SC06예외": "case_id",
    "SC06검증": "check_id",
}

__all__ = ["SEED_ID", "SEED_PATH", "Seed", "kst", "load_seed"]


@dataclass(frozen=True)
class Seed:
    #: 장면 6 시트 이름 → 행 목록(헤더 → 값). 원값 그대로다 — 시각은 `kst()`로 읽는다.
    sheets: dict[str, list[dict[str, Any]]]
    #: 파일 판의 해시 — 적재 묶음(import_batch)에 남긴다(구현명세 8장 1단계)
    sha256: str

    def rows(self, sheet: str) -> list[dict[str, Any]]:
        return self.sheets[sheet]

    def by_id(self, sheet: str) -> dict[str, dict[str, Any]]:
        key = SHEETS[sheet]
        return {str(r[key]): r for r in self.sheets[sheet]}

    def setting(self, key: str) -> Any:
        return self.by_id("SC06설정")[key]["value"]


@cache
def load_seed(path: Path = SEED_PATH) -> Seed:
    wb = load_workbook(path, data_only=True, read_only=True)
    sheets = {name: _sheet(wb[name], first) for name, first in SHEETS.items()}
    wb.close()
    return Seed(sheets=sheets, sha256=hashlib.sha256(path.read_bytes()).hexdigest())
