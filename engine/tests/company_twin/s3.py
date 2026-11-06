"""
시나리오 3(연말결산 — 결산조정) 회사 자료와 세계 기록 — 장면 1 「결산조정 업무 착수」.

NowView `docs/s3/common.md`(시나리오 3 공통 설계)·`docs/s3/sc01.md`. 자료는
`seed/S3-INPUT-v0.1.xlsx`(입력자료 명세 및 대표 사건 v0.1)의 **입력 시트 7개만** 읽는다 —
결산기준·자산대장·채권명세·전이율원천·원장·회수계획·확인기록(입력 허용목록). 설계안내·입력명세·
대표사건·검수기준은 설계·기대값 대조용이라 읽지 않는다(구현명세 §1 「7개 입력 시트만 허용한다」).

* `GET /company/s3/master` — 불변 회사 자료: 결산 건 S3-CLOSE-01(결산기간·비교기간·조정항목 둘의
  원업무·담당·결산 일정), 입력 시트별 소유 역할, 원천 7개 시트(정상 입력 IN-26-01의 내용), 시험
  변형 목록.
* 회차를 만들면 **선행 업무가 끝난 상태**다 — 자료 담당자가 입력 IN-26-01을 결산 건에 연결했고
  두 조정항목이 회계담당자에게 배정됐다(BPM v0.2 「선행 업무」, 업무설계표 「시작: 선행자료 등록·
  업무 배정」).
* `POST /worlds/{w}/sim/close-inputs {variants}` — (시연·시험) 자료 담당자가 입력을 다시 연결했다.
  원천 + 변형으로 새 입력 버전(IN-26-02 …)을 세계 시각에 등록한다. 변형이 없으면 정상 원천이다(보완
  완료). 지금 버전과 내용이 같으면 새 버전을 만들지 않는다(재등록 없음). 변형은 `VARIANTS`.
* `GET /worlds/{w}/close-inputs` · `…/inbox?after=` · `…/close-inputs/{version}`(시트 전부·단위·추출
  참조·변형·바뀐 시트).

금액은 백만원이다(전이율원천만 원). 엑셀의 부동소수 잡음(33.799690999999996)은 **백만원 소수
6자리(= 원 단위)**로 반올림해 싣는다 — 결산기준 「원 단위(백만원 소수 6자리) 반올림」.
판정(준비 완료·보완 필요)은 NowView 규칙 계산이 내고 시험이 대조한다.

이 파일은 NowView 엔진 시험의 기간계 쌍둥이(`engine/tests/company_twin/s3.py`)에 **그대로**
복사한다 — 자료 위치를 두 자리에서 찾는다(`_workbook`).
"""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel

KST = timezone(timedelta(hours=9))
SCENARIO = "s3"
NAME = "S3-INPUT-v0.1.xlsx"
DATASET = "S3-INPUT-v0.1"
CLOSE_ID = "S3-CLOSE-01"
FIRST_VERSION = "IN-26-01"
#: 시나리오 3 회차의 처음 시각 — 2026년 연말결산 착수일(가안: 2027-01-04 월 09:00). 자료 날짜는
#: 2026-12-31까지라 결산 업무는 그 뒤 첫 영업일에 시작한다.
S0_CLOCK = datetime(2027, 1, 4, 9, 0, tzinfo=KST).isoformat()

#: 입력 허용목록 — 이 순서로 싣는다
SHEETS = ("결산기준", "자산대장", "채권명세", "전이율원천", "원장", "회수계획", "확인기록")
#: 설계·기대값 대조용 — Agent·점검 입력이 아니다
EXCLUDED = ("설계안내", "입력명세", "대표사건", "검수기준")

#: 머리(4행) → 칸 이름. 결산기준은 항목·값, 전이율원천은 연령 + 분기 열이다.
COLUMNS: dict[str, dict[str, str]] = {
    "결산기준": {"항목": "item", "적용값·계산 방법": "value"},
    "자산대장": {
        "ID": "asset_id",
        "종류": "kind",
        "귀속": "allocation",
        "기초 순액": "opening_net",
        "당기취득": "acquired",
        "처분 순액": "disposed_net",
        "손상": "impairment",
        "취득원가": "cost",
        "잔존가": "residual",
        "연수": "life_years",
        "사용개시일": "in_service",
        "처분일": "disposed_on",
        "전기 상각": "prior_depreciation",
    },
    "채권명세": {
        "기준일": "as_of",
        "거래처": "customer",
        "평가단위": "pool",
        "연령": "aging",
        "채권 잔액": "balance",
        "계획 참조": "plan_ref",
    },
    "원장": {"기준일": "as_of", "항목": "account", "금액": "amount", "구분": "nature"},
    "회수계획": {
        "계획 ID": "plan_id",
        "거래처": "customer",
        "기준일": "as_of",
        "회차": "round",
        "예정일": "due",
        "예정액": "amount",
        "증빙 성격": "nature",
    },
    "확인기록": {
        "확인 ID": "confirmation_id",
        "거래처": "customer",
        "확인일": "confirmed_on",
        "근거 버전": "plan_ref",
        "확인자": "confirmed_by",
        "확인액": "amount",
        "확인 내용": "note",
    },
}

#: 시트 단위 — 결산기준 「전이율원천만 원, 그 외 금액 백만원」
UNITS = {s: ("원" if s == "전이율원천" else "백만원") for s in SHEETS}
UNITS["결산기준"] = None

#: 시트 소유 역할(업무설계표 자료점검 · 구현명세 §2 보완 요청)
SHEET_OWNERS = {
    "결산기준": "회계담당",
    "자산대장": "자산담당",
    "채권명세": "채권담당",
    "전이율원천": "회계담당",
    "원장": "회계담당",
    "회수계획": "영업담당",
    "확인기록": "회계담당",
}


def _workbook() -> Path:
    here = Path(__file__).resolve()
    for root in (here.parents[1], here.parents[2]):  # 기간계 `legacy/seed/` · 쌍둥이 `engine/seed/`
        if (root / "seed" / NAME).exists():
            return root / "seed" / NAME
    raise FileNotFoundError(f"시나리오 3 자료가 없다: {NAME}")


def _num(value: Any) -> Any:
    """숫자 칸 — 정수는 그대로, 실수는 백만원 소수 6자리(원 단위)로. 빈칸은 None(0이 아니다)."""
    if isinstance(value, bool) or value is None or value == "":
        return None if value in (None, "") else value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        r = round(value, 6)
        return int(r) if r == int(r) else r
    return value


def _text(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.date().isoformat()
    return None if value == "" else value


def _rows(ws: Any, columns: dict[str, str]) -> list[dict[str, Any]]:
    """4행이 머리, 5행부터 자료 — 첫 칸이 빈 행에서 멈춘다."""
    header = [c.value for c in ws[4]]
    out = []
    for row in ws.iter_rows(min_row=5, values_only=True):
        if row[0] is None:
            break
        rec = {}
        for name, value in zip(header, row, strict=False):
            if name in columns:
                key = columns[name]
                rec[key] = _num(value) if isinstance(value, (int, float)) else _text(value)
        out.append(rec)
    return out


def _rates(ws: Any) -> dict[str, Any]:
    """전이율원천 — 연령구간 × 분기 잔액(원). 분기 열 이름은 머리 그대로(2021.1Q …)."""
    header = [c.value for c in ws[4]]
    quarters = [str(h) for h in header[1:] if h is not None]
    rows = []
    for row in ws.iter_rows(min_row=5, values_only=True):
        if row[0] is None:
            break
        rows.append(
            {
                "aging": row[0],
                "balances": {q: _num(v) for q, v in zip(quarters, row[1:], strict=False)},
            }
        )
    return {"quarters": quarters, "rows": rows}


@lru_cache(maxsize=1)
def master() -> dict[str, Any]:
    from openpyxl import load_workbook

    wb = load_workbook(_workbook(), data_only=True)
    sheets = {s: _rows(wb[s], COLUMNS[s]) for s in SHEETS if s != "전이율원천"}
    sheets["전이율원천"] = _rates(wb["전이율원천"])
    return {
        "dataset_version": DATASET,
        "close": {
            "close_id": CLOSE_ID,
            "title": "2026년 연말결산",
            "period_end": "2026-12-31",
            "comparative_end": "2025-12-31",
            "unit": "백만원",
            "reviewer": {"role": "회계팀장", "name": "회계팀장", "user_id": "u-acct-lead"},
            "items": [
                {
                    "item_id": "DEP",
                    "work_id": "W-S3-DEP",
                    "name": "감가상각비",
                    "owner_role": "회계담당",
                    "owner_name": "회계담당",
                    "owner_id": "u-acct",
                    "sheets": ["결산기준", "자산대장", "원장"],
                    "follow_up": ["전표 반영", "유형자산 주석 취합"],
                },
                {
                    "item_id": "ALW",
                    "work_id": "W-S3-ALW",
                    "name": "외상매출금 대손충당금",
                    "owner_role": "회계담당",
                    "owner_name": "회계담당",
                    "owner_id": "u-acct",
                    "sheets": [
                        "결산기준",
                        "채권명세",
                        "전이율원천",
                        "원장",
                        "회수계획",
                        "확인기록",
                    ],
                    "follow_up": ["전표 반영", "충당금 주석 취합"],
                },
            ],
            # 결산 일정(가안 — 자료에 일정이 없다). 기한·잔여일은 이 일정에서 읽는다.
            "schedule": {
                "started": S0_CLOCK,
                "submit_due": datetime(2027, 1, 8, 18, 0, tzinfo=KST).isoformat(),
                "approve_due": datetime(2027, 1, 11, 18, 0, tzinfo=KST).isoformat(),
                "posting_due": datetime(2027, 1, 13, 18, 0, tzinfo=KST).isoformat(),
            },
        },
        "allowed_sheets": list(SHEETS),
        "excluded_sheets": list(EXCLUDED),
        "units": UNITS,
        "sheet_owners": SHEET_OWNERS,
        "sheets": sheets,
        "variants": {k: v["label"] for k, v in VARIANTS.items()},
    }


# ─────────────────────────── 시험 변형(구현명세 §3 인수시험 03~07) ───────────────────────────


def _asset(sheets: dict, asset_id: str) -> dict:
    return next(r for r in sheets["자산대장"] if r["asset_id"] == asset_id)


def _e2_start_missing(s: dict, refs: dict, units: dict) -> None:
    _asset(s, "E2")["in_service"] = None


def _conf_f_missing(s: dict, refs: dict, units: dict) -> None:
    s["확인기록"] = [r for r in s["확인기록"] if r["confirmation_id"] != "CONF-26-F"]


def _conf_prior_plan(s: dict, refs: dict, units: dict) -> None:
    next(r for r in s["확인기록"] if r["confirmation_id"] == "CONF-26-F")["plan_ref"] = "PLAN-A-25"


def _conf_amount_mismatch(s: dict, refs: dict, units: dict) -> None:
    next(r for r in s["확인기록"] if r["confirmation_id"] == "CONF-26-F")["amount"] = 65


def _plan_dup_round(s: dict, refs: dict, units: dict) -> None:
    dup = next(r for r in s["회수계획"] if r["plan_id"] == "PLAN-A-26" and r["round"] == 2)
    s["회수계획"].append(dict(dup))


def _ledger_1won(s: dict, refs: dict, units: dict) -> None:
    row = next(r for r in s["원장"] if r["account"] == "외상매출금")
    row["amount"] = round(row["amount"] + 0.000001, 6)


def _rate_unit_million(s: dict, refs: dict, units: dict) -> None:
    units["전이율원천"] = "백만원"
    for row in s["전이율원천"]["rows"]:
        row["balances"] = {
            q: None if v is None else round(v / 1_000_000, 6) for q, v in row["balances"].items()
        }


def _asset_replaced(s: dict, refs: dict, units: dict) -> None:
    """자산대장을 다시 추출했다 — 값은 같고 추출 참조만 새것이다(인수시험 07 「자산자료 교체」)."""
    refs["자산대장"] = "ERP-FA-20261231-R2"


VARIANTS: dict[str, dict[str, Any]] = {
    "E2-START-MISSING": {"label": "자산대장 E2 사용개시일 누락", "apply": _e2_start_missing},
    "CONF-F-MISSING": {"label": "회계 평가 기록 CONF-26-F 없음", "apply": _conf_f_missing},
    "CONF-PRIOR-PLAN": {
        "label": "CONF-26-F가 전기 계획 PLAN-A-25를 가리킴",
        "apply": _conf_prior_plan,
    },
    "CONF-AMOUNT-MISMATCH": {
        "label": "CONF-26-F 확인액 65 — 계획 합계와 불일치",
        "apply": _conf_amount_mismatch,
    },
    "PLAN-DUP-ROUND": {"label": "PLAN-A-26 회차 2 중복 입력", "apply": _plan_dup_round},
    "LEDGER-1WON": {"label": "원장 외상매출금 1원 차이", "apply": _ledger_1won},
    "RATE-UNIT-MILLION": {
        "label": "전이율원천을 백만원 단위로 추출",
        "apply": _rate_unit_million,
    },
    "ASSET-REPLACED": {
        "label": "자산대장 재추출(값 동일·추출 참조 변경)",
        "apply": _asset_replaced,
    },
}

#: 시트별 처음 추출 참조(가상 ERP 추출 id)
FIRST_REFS = {s: f"ERP-{i + 1:02d}-20261231-R1" for i, s in enumerate(SHEETS)}
FIRST_REFS["자산대장"] = "ERP-FA-20261231-R1"


def _digest(value: Any) -> str:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def build_version(
    version: str, seq: int, variants: list[str], registered_at: str, before: dict | None
) -> dict[str, Any]:
    """원천 + 변형 → 입력 버전 하나. 바뀐 시트는 앞 버전과 시트 지문으로 가린다."""
    unknown = [v for v in variants if v not in VARIANTS]
    if unknown:
        known = ", ".join(VARIANTS)
        raise HTTPException(404, f"모르는 변형: {', '.join(unknown)} (가능: {known})")
    sheets = copy.deepcopy(master()["sheets"])
    refs, units = dict(FIRST_REFS), dict(UNITS)
    for v in variants:
        VARIANTS[v]["apply"](sheets, refs, units)
    prints = {s: _digest([sheets[s], refs[s], units[s]]) for s in SHEETS}
    digest = _digest(prints)
    changed = [s for s in SHEETS if before is None or before["fingerprints"][s] != prints[s]]
    return {
        "version": version,
        "seq": seq,
        "close_id": CLOSE_ID,
        "period_end": "2026-12-31",
        "comparative_end": "2025-12-31",
        "registered_at": registered_at,
        "registered_by": "자료담당",
        "variants": list(variants),
        "units": units,
        "source_refs": refs,
        "fingerprints": prints,
        #: 내용 지문 — 「장면 1부터 다시」 뒤에는 같은 버전 id에 다른 내용이 올 수 있다(캐시 키)
        "digest": digest,
        "changed_sheets": changed,
        "sheets": sheets,
    }


def new_world() -> dict[str, Any]:
    """시나리오 3 세계의 변하는 기록 — 결산 건에 연결된 입력 버전(처음은 IN-26-01 하나)."""
    first = build_version(FIRST_VERSION, 1, [], S0_CLOCK, None)
    return {"close_input_seq": 1, "close_inputs": {FIRST_VERSION: first}}


def rewind(w: dict[str, Any], scene: int) -> None:
    """「장면 N부터 다시」 — 장면 1부터면 입력을 IN-26-01 하나로 되돌린다."""
    if w.get("scenario_id") != SCENARIO:
        return
    if scene <= 1:
        w.update(new_world())


def summary(w: dict[str, Any]) -> dict[str, Any]:
    """세계 요약에 더하는 칸 — NowView 일꾼이 입력 버전 번호를 보고 새 연결을 들인다."""
    if w.get("scenario_id") != SCENARIO:
        return {}
    return {"close_inputs": w.get("close_input_seq", 0)}


class InputsBody(BaseModel):
    variants: list[str] = []


def _summary(v: dict[str, Any]) -> dict[str, Any]:
    keys = ("version", "seq", "registered_at", "variants", "changed_sheets", "digest")
    return {k: v[k] for k in keys}


def _current(w: dict[str, Any]) -> dict[str, Any]:
    return max(w["close_inputs"].values(), key=lambda v: v["seq"])


def mount(
    app: FastAPI,
    *,
    store: Any,
    world: Callable[[str], dict[str, Any]],
    auth: Callable[..., None],
) -> None:
    """시나리오 3 경로를 기간계 앱에 붙인다(기간계와 쌍둥이가 같은 함수를 쓴다)."""

    def _s3(world_id: str) -> dict[str, Any]:
        w = world(world_id)
        if w.get("scenario_id") != SCENARIO:
            raise HTTPException(409, f"시나리오 3 회차가 아니다: {world_id}")
        return w

    @app.get("/company/s3/master", dependencies=[Depends(auth)])
    def s3_master() -> dict[str, Any]:
        return master()

    @app.post("/worlds/{world_id}/sim/close-inputs", status_code=201, dependencies=[Depends(auth)])
    def link_inputs(world_id: str, body: InputsBody) -> dict[str, Any]:
        """자료 담당자가 입력을 다시 연결했다 — 등록 시각은 세계 시각이다."""
        with store.lock():
            w = _s3(world_id)
            before = _current(w)
            seq = w["close_input_seq"] + 1
            found = build_version(f"IN-26-{seq:02d}", seq, body.variants, w["clock"], before)
            if found["fingerprints"] == before["fingerprints"]:
                return {**_summary(before), "created": False}
            w["close_input_seq"] = seq
            w["close_inputs"][found["version"]] = found
            store.put(w)
        return {**_summary(found), "created": True}

    @app.get("/worlds/{world_id}/close-inputs", dependencies=[Depends(auth)])
    def close_inputs(world_id: str) -> list[dict[str, Any]]:
        docs = sorted(_s3(world_id)["close_inputs"].values(), key=lambda v: v["seq"])
        return [_summary(v) for v in docs]

    @app.get("/worlds/{world_id}/close-inputs/inbox", dependencies=[Depends(auth)])
    def close_input_inbox(world_id: str, after: int = 0) -> list[dict[str, Any]]:
        docs = sorted(_s3(world_id)["close_inputs"].values(), key=lambda v: v["seq"])
        return [_summary(v) for v in docs if v["seq"] > after]

    @app.get("/worlds/{world_id}/close-inputs/{version}", dependencies=[Depends(auth)])
    def close_input(world_id: str, version: str) -> dict[str, Any]:
        found = _s3(world_id)["close_inputs"].get(version)
        if found is None:
            raise HTTPException(404, f"없는 입력 버전: {version}")
        return found
