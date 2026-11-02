"""
SC07 시드 — `seed/SYN-SC07-v0.7.xlsx`(SC01~SC07 통합가상데이터 v0.7).

**v0.7은 앞선 92개 시트를 그대로 두고 SC07 시트 11개만 더했다**(시험이 v0.6과 대조한다 — 구현명세
2장
「v0.7의 앞선 92개 시트는 수정하지 않는다」).

**장면 7 시트는 세 종류다**(구현명세 2장 표).

* **원천 — 적재해서 계산한다.** `SC07개선`(IMP71과 하위 F·P·A·N), `SC07기준`(BR701~709),
  `SC07버전`(버전 묶음·확인 지연 기준 120분·새 역할), `SC07검증입력`(IN71~75 원시 필드),
  `SC07근거`(EV71~78),
  `SC07확인이력`(CF71·CF72 — 확인 절차의 일정이자 기대값), `SC07적용`(AP71·CFG71 — 세로 항목을 객체
  하나로).
* **기대값 — 계산 입력으로 쓰지 않는다.** `SC07판단`(입력별 시간·지연·후보), `SC07검증결과`의
  기대값·가상 결과·
  일치 여부, `SC07요약`. 시험이 계산 결과와 대조한다. 기대값(D열)은 평가 전용이다 — Agent 입력에
  넣지
  않는다(BR708·TC706).
* `SC07화면계약`은 화면 규칙의 설명이다(읽지 않는다).

헤더는 한글이다(장면 6까지는 영문 헤더 행이 있었다). 엑셀 시각은 KST 벽시계 값이다 — 장면 3
`kst()`를
그대로 쓴다(구현명세 2장 「Excel 일련번호를 UTC로 해석한 뒤 9시간을 더하지 않는다」).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from app.sc03.seed import _sheet, kst

SEED_PATH = Path(__file__).resolve().parents[2] / "seed" / "SYN-SC07-v0.7.xlsx"
SEED_ID = "SYN-SC07-v0.7"
DATASET_VERSION = "v0.7"
#: 시트 이름 → 헤더 첫 칸
SHEETS = {
    "SC07요약": "항목",
    "SC07개선": "개선 ID",
    "SC07기준": "기준 ID",
    "SC07버전": "식별자",
    "SC07검증입력": "입력 ID",
    "SC07근거": "근거 ID",
    "SC07판단": "입력 ID",
    "SC07검증결과": "검증 ID",
    "SC07확인이력": "확인 ID",
    "SC07적용": "항목",
}

__all__ = ["DATASET_VERSION", "SEED_ID", "SEED_PATH", "Seed", "kst", "load_seed"]


@dataclass(frozen=True)
class Seed:
    #: 장면 7 시트 이름 → 행 목록(헤더 → 값). 원값 그대로다 — 시각은 `kst()`로 읽는다.
    sheets: dict[str, list[dict[str, Any]]]
    #: 파일 판의 해시 — 적재 묶음에 남긴다
    sha256: str

    def rows(self, sheet: str) -> list[dict[str, Any]]:
        return self.sheets[sheet]

    def by_id(self, sheet: str) -> dict[str, dict[str, Any]]:
        key = SHEETS[sheet]
        return {str(r[key]): r for r in self.sheets[sheet]}


@cache
def load_seed(path: Path = SEED_PATH) -> Seed:
    """기대값 시트는 수식 칸의 캐시 값을 읽는다(`data_only`) — 엔진은 그것을 입력으로 쓰지
    않는다."""
    wb = load_workbook(path, data_only=True, read_only=True)
    sheets = {name: _sheet(wb[name], first) for name, first in SHEETS.items()}
    wb.close()
    return Seed(sheets=sheets, sha256=hashlib.sha256(path.read_bytes()).hexdigest())
