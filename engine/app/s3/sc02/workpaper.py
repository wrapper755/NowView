"""
시나리오 3 장면 2의 첨부 Excel — 결산조정 계산근거(서식 FMT-S3-WP-v0.1 = 계산근거 견본 v0.1의
시트 구성).

결과 버전 하나에 파일 하나다. 원천 수치는 값으로, **계산은 수식으로** 둔다 — Excel에서 열면 다시
계산되고 각 금액에서 원천 행까지 따라갈 수 있다(구현명세 §3 「원천 수치, 계산식과 근거 참조를
보존」). 승인요약의 두 요청액은 상세 시트의 수식에 이어진다.

* 이번 판은 **모의 실행**이다 — 연계 PC의 Excel 대신 NowView 일꾼이 같은 시트·수식 구성으로
  파일을 짓는다(`실행정보` 시트와 실행 기록의 `execution_mode`). openpyxl은 수식의 계산값을 저장하지
  않으므로 여는 프로그램이 다시 계산한다.
* 사용월수만 값이다(계산 기능 산출 — 개시월 포함·처분월 제외). 금액은 모두 수식이다.
* 같은 결과·실행이면 같은 바이트다 — 재전송이 같은 파일이어야 한다(구현명세 §4 「같은 실행·파일을
  재전송」). 압축 항목의 시각과 문서 속성의 시각을 실행 시각으로 고정한다.
"""

from __future__ import annotations

import hashlib
import io
import re
import zipfile
from datetime import UTC, datetime
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

FORMAT_VERSION = "FMT-S3-WP-v0.1"
SHEETS = (
    "승인요약",
    "상각비비교",
    "유형자산주석",
    "충당금비교",
    "충당금주석",
    "자산별계산",
    "채권별계산",
    "개별평가",
    "손실률",
    "분기전이율",
    "참고원천",
    "원장대사",
    "실행정보",
)
CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
HEAD = Font(bold=True, color="FFFFFF")
HEAD_FILL = PatternFill("solid", fgColor="1F3A5F")
TITLE = Font(bold=True, size=13)
MIL = "#,##0.######"
RATE = "0.000000%"


def _num(text: str | None) -> float | int | None:
    if text is None:
        return None
    f = float(text)
    return int(f) if f == int(f) and "." not in text else f


def _sheet(wb: Workbook, name: str, title: str, note: str, header: list[str]):
    ws = wb.create_sheet(name)
    ws["A1"] = title
    ws["A1"].font = TITLE
    ws["A2"] = note
    ws["A2"].alignment = Alignment(wrap_text=False)
    for i, h in enumerate(header, start=1):
        c = ws.cell(row=4, column=i, value=h)
        c.font, c.fill = HEAD, HEAD_FILL
        ws.column_dimensions[get_column_letter(i)].width = max(12, len(h) * 2 + 2)
    ws.column_dimensions["A"].width = 26
    return ws


def _fmt(ws, cols: str, rows: range, fmt: str) -> None:
    for col in cols:
        for r in rows:
            ws[f"{col}{r}"].number_format = fmt


def build(
    result: dict[str, Any], run: dict[str, Any], rates_source: dict[str, Any], *, file_version: int
) -> dict[str, Any]:
    """
    결과 → 파일(바이트·이름·지문·시트 목록과 승인요약 칸의 위치). `rates_source`는 입력의
    전이율원천(원 단위 분기 잔액)이다.
    """
    dep, alw = result["depreciation"], result["allowance"]
    wb = Workbook()
    wb.remove(wb.active)
    sheets = {name: None for name in SHEETS}
    unit = "백만원"
    close = run["close_id"]
    head = (
        f"{close} · {result['period_end'][:4]}년말 / 전기 {result['comparative_end'][:4]}년"
        f" · 단위 {unit}"
    )

    # ── 참고원천(원) ──
    model = alw["model"]
    rates_src = rates_source
    quarters = rates_src["quarters"]
    ws = _sheet(
        wb,
        "참고원천",
        "참고원천",
        "2024년말 일반거래처 연령구간별 분기 잔액 · 단위 원 · 입력 전이율원천 그대로",
        ["연령", *quarters],
    )
    src_row = {}
    for i, row in enumerate(rates_src["rows"]):
        r = 5 + i
        src_row[row["aging"]] = r
        ws.cell(row=r, column=1, value=row["aging"])
        for j, q in enumerate(quarters):
            ws.cell(row=r, column=2 + j, value=row["balances"][q])
    sheets["참고원천"] = ws

    # ── 분기전이율 ──
    segs = [s["aging"] for s in model["segments"][:-1]]
    ws = _sheet(
        wb,
        "분기전이율",
        "분기전이율",
        "시작 분기 잔액 대비 다음 분기 한 단계 장기화된 잔액 · 상한 1 · 분모 0은 공란. "
        f"가중 관측 {model['window'][0]}~{model['window'][1]} 시작(아래 분자 행)",
        ["시작 구간", *quarters[:-1]],
    )
    order = [r["aging"] for r in rates_src["rows"]]
    first_window = quarters.index(model["window"][0])
    last_window = quarters.index(model["window"][1])
    num_row = {}
    for i, seg in enumerate(segs):
        r, rn = 5 + i, 12 + i
        s_row, n_row = src_row[seg], src_row[order[order.index(seg) + 1]]
        ws.cell(row=r, column=1, value=seg)
        ws.cell(row=rn, column=1, value=f"{seg} 가중 분자 min(시작, 다음)")
        num_row[seg] = rn
        for t in range(len(quarters) - 1):
            a = f"참고원천!{get_column_letter(2 + t)}{s_row}"
            b = f"참고원천!{get_column_letter(3 + t)}{n_row}"
            ws.cell(row=r, column=2 + t, value=f'=IF({a}=0,"",MIN(1,{b}/{a}))')
            if first_window <= t <= last_window:
                ws.cell(row=rn, column=2 + t, value=f"=MIN({a},{b})")
    ws.cell(row=11, column=1, value="가중 분자(최근 12개 관측)")
    _fmt(ws, [get_column_letter(c) for c in range(2, len(quarters) + 1)], range(5, 10), RATE)
    sheets["분기전이율"] = ws

    # ── 손실률 ──
    ws = _sheet(
        wb,
        "손실률",
        "손실률",
        "최종 설정률 = 잔액 가중 전이율의 누적곱 × LGD. 단순평균은 비교용. "
        "2024년 모형을 두 기간에 고정",
        [
            "연령",
            "단순 전이율",
            "가중 전이율",
            "누적 PD",
            "LGD",
            "최종 설정률",
            "24년 말 채권(원)",
            "원본 재현 충당금(원)",
        ],
    )
    loss_row = {}
    wf, wl = get_column_letter(2 + first_window), get_column_letter(2 + last_window)
    all_segs = [s["aging"] for s in model["segments"]]
    for i, seg in enumerate(all_segs):
        r = 5 + i
        loss_row[seg] = r
        ws.cell(row=r, column=1, value=seg)
        if seg in num_row:
            sr = src_row[seg]
            ws.cell(row=r, column=2, value=f"=AVERAGE(분기전이율!{wf}{5 + i}:{wl}{5 + i})")
            ws.cell(
                row=r,
                column=3,
                value=f"=SUM(분기전이율!{wf}{num_row[seg]}:{wl}{num_row[seg]})"
                f"/SUM(참고원천!{wf}{sr}:{wl}{sr})",
            )
            ws.cell(row=r, column=4, value=f"=C{r}*D{r + 1}")
            ws.cell(row=r, column=7, value=f"=참고원천!{get_column_letter(1 + len(quarters))}{sr}")
        else:  # 12개월 초과 — 원천 마지막 두 구간 합산, PD 100%
            ws.cell(row=r, column=4, value=1)
            last = get_column_letter(1 + len(quarters))
            ws.cell(
                row=r,
                column=7,
                value="=" + "+".join(f"참고원천!{last}{src_row[s]}" for s in order[len(segs) :]),
            )
        ws.cell(row=r, column=5, value=1)
        ws.cell(row=r, column=6, value=f"=D{r}*E{r}")
        ws.cell(row=r, column=8, value=f"=G{r}*F{r}")
    total = 5 + len(all_segs)
    ws.cell(row=total, column=1, value="합계")
    ws.cell(row=total, column=7, value=f"=SUM(G5:G{total - 1})")
    ws.cell(row=total, column=8, value=f"=ROUND(SUM(H5:H{total - 1}),0)")
    _fmt(ws, "BCDF", range(5, total), RATE)
    _fmt(ws, "GH", range(5, total + 1), "#,##0")
    sheets["손실률"] = ws

    # ── 개별평가 ──
    ws = _sheet(
        wb,
        "개별평가",
        "개별평가",
        "결산 담당자가 확인한 회수예상액(회계 평가 기록)으로 계산 · 집합평가와 분리 · 단위 백만원",
        ["거래처", "기준일", "채권잔액", "회수예상액", "개별 충당금", "판단 근거"],
    )
    ind_row = {}
    for i, ind in enumerate(sorted(alw["individual"], key=lambda x: (x["customer"], x["as_of"]))):
        r = 5 + i
        ind_row[(ind["customer"], ind["as_of"])] = r
        rounds = ind["plan_rounds"]
        basis = (
            f"{ind['plan_ref']} {len(rounds)}회 합계 {ind['plan_total']}"
            + (f" · 영업 {ind['sales_confirmation']}" if ind["sales_confirmation"] else "")
            + f" · 회계 {ind['accounting_confirmation']}"
            + (f" — {ind['basis']}" if ind["basis"] else "")
        )
        ws.append([ind["customer"], ind["as_of"], _num(ind["balance"]), _num(ind["recovery"])])
        ws.cell(row=r, column=5, value=f"=C{r}-D{r}")
        ws.cell(row=r, column=6, value=basis)
    sheets["개별평가"] = ws

    # ── 채권별계산 ──
    ws = _sheet(
        wb,
        "채권별계산",
        "채권별계산",
        "거래처·평가군·연령구간 행 · 집합은 손실률 시트의 설정률, 개별은 개별평가 행 · "
        "원 단위 반올림",
        [
            "거래처",
            "평가",
            "연령구간",
            "전기 채권",
            "당기 채권",
            "설정률",
            "전기 충당금",
            "당기 충당금",
            "변동",
            "당기 순위",
        ],
    )
    rank = {c["customer"]: c["rank"] for c in alw["customers"]}
    keys = []
    for period in ("prior", "current"):
        for row in alw["rows"][period]:
            k = (row["customer"], row["pool"], row["aging"])
            if k not in keys:
                keys.append(k)
    keys.sort(key=lambda k: (k[1] != "집합", k[0]))
    bal = {
        (p, (r["customer"], r["pool"], r["aging"])): r["balance"]
        for p in ("prior", "current")
        for r in alw["rows"][p]
    }
    recv_row = {}
    for i, k in enumerate(keys):
        r = 5 + i
        recv_row[k] = r
        ws.cell(row=r, column=1, value=k[0])
        ws.cell(row=r, column=2, value=k[1])
        ws.cell(row=r, column=3, value=k[2])
        ws.cell(row=r, column=4, value=_num(bal.get(("prior", k))) or 0)
        ws.cell(row=r, column=5, value=_num(bal.get(("current", k))) or 0)
        if k[1] == "집합":
            ws.cell(row=r, column=6, value=f"=손실률!F{loss_row[k[2]]}")
            ws.cell(row=r, column=7, value=f"=ROUND(D{r}*F{r},6)")
            ws.cell(row=r, column=8, value=f"=ROUND(E{r}*F{r},6)")
        else:
            p = ind_row.get((k[0], result["comparative_end"]))
            c = ind_row.get((k[0], result["period_end"]))
            ws.cell(row=r, column=7, value=f"=개별평가!E{p}" if p else 0)
            ws.cell(row=r, column=8, value=f"=개별평가!E{c}" if c else 0)
        ws.cell(row=r, column=9, value=f"=H{r}-G{r}")
        ws.cell(row=r, column=10, value=rank.get(k[0]))
    last_recv = 4 + len(keys)
    col_rows = [recv_row[k] for k in keys if k[1] == "집합"]
    ind_rows = [recv_row[k] for k in keys if k[1] == "개별"]
    _fmt(ws, "F", range(5, last_recv + 1), RATE)
    _fmt(ws, "DEGHI", range(5, last_recv + 1), MIL)
    sheets["채권별계산"] = ws

    def refsum(sheet: str, col: str, rows: list[int]) -> str:
        return "=" + ("+".join(f"{sheet}!{col}{r}" for r in rows) if rows else "0")

    # ── 원장대사 ──
    ledger = {x["label"]: x for x in alw["reconciliation"]}
    ws = _sheet(
        wb,
        "원장대사",
        "원장대사",
        "결산조정 전 장부금액과 계산·주석 비교 · 차이는 표시 반올림 전 원 단위",
        ["항목", "원장·기준액", "명세 또는 재계산", "차이(원)"],
    )
    ws.append(["감가상각비 기계상", _num(dep["summary"]["book"])])
    ws.append(["기초 충당금", _num(alw["note"]["opening"])])
    ws.append(["당기 제각 사용", _num(alw["note"]["written_off"])])
    ws.append(
        ["조정 전 충당금", _num(alw["summary"]["book"]), "=B6-B7", "=ROUND((C8-B8)*1000000,0)"]
    )
    ws.append(
        [
            "외상매출금 잔액",
            _num(ledger["외상매출금 잔액"]["book"]),
            f"=SUM(채권별계산!E5:E{last_recv})",
            "=ROUND((C9-B9)*1000000,0)",
        ]
    )
    sheets["원장대사"] = ws

    # ── 충당금비교 ──
    ws = _sheet(
        wb,
        "충당금비교",
        "충당금비교",
        "평가방법별 기말잔액 비교와 당기 충당금 상위 3개사 · 단위 백만원",
        ["방법 / 순위", "전기 충당금", "당기 충당금", "증감", "증감률", "당기 채권잔액"],
    )
    ws.append(["집합", refsum("채권별계산", "G", col_rows), refsum("채권별계산", "H", col_rows)])
    ws.append(["개별", refsum("채권별계산", "G", ind_rows), refsum("채권별계산", "H", ind_rows)])
    ws.append(["합계", "=B5+B6", "=C5+C6"])
    ws["F5"] = refsum("채권별계산", "E", col_rows)
    ws["F6"] = refsum("채권별계산", "E", ind_rows)
    ws["F7"] = "=F5+F6"
    for i, name in enumerate(alw["top3"]):
        r = 8 + i
        rows = [recv_row[k] for k in keys if k[0] == name]
        ws.cell(row=r, column=1, value=name)
        ws.cell(row=r, column=2, value=refsum("채권별계산", "G", rows))
        ws.cell(row=r, column=3, value=refsum("채권별계산", "H", rows))
        ws.cell(row=r, column=6, value=refsum("채권별계산", "E", rows))
    for r in range(5, 8 + len(alw["top3"])):
        ws.cell(row=r, column=4, value=f"=C{r}-B{r}")
        ws.cell(row=r, column=5, value=f'=IF(B{r}=0,"",D{r}/B{r})')
    _fmt(ws, "BCDF", range(5, 11), MIL)
    _fmt(ws, "E", range(5, 11), "0.0%")
    sheets["충당금비교"] = ws

    # ── 충당금주석 ──
    ws = _sheet(
        wb,
        "충당금주석",
        "충당금주석",
        "외상매출금 대손충당금 변동 · 전기말 대비 증감과 당기 추가 설정액은 제각 사용액만큼 다르다",
        ["항목", "기초", "설정", "환입", "제각 사용", "기말", "평가표 차이"],
    )
    ws.append(
        [
            "외상매출금",
            "=원장대사!B6",
            "=MAX(0,충당금비교!C7-원장대사!B8)",
            "=MAX(0,원장대사!B8-충당금비교!C7)",
            "=원장대사!B7",
            "=B5+C5-D5-E5",
            "=ROUND((F5-충당금비교!C7)*1000000,0)",
        ]
    )
    sheets["충당금주석"] = ws

    # ── 자산별계산 ──
    ws = _sheet(
        wb,
        "자산별계산",
        "자산별계산",
        "정액법·월할 · 사용개시월 포함·처분월 제외(사용월수는 계산 기능 산출) · "
        "상각 가능 잔액 한도",
        [
            "자산",
            "종류",
            "귀속",
            "기초 순액",
            "취득",
            "처분 순액",
            "손상",
            "취득원가",
            "잔존가",
            "내용연수",
            "사용개시일",
            "처분일",
            "사용월수",
            "연 상각액",
            "상각 가능 잔액",
            "당기 상각",
            "전기 상각",
            "기말 순액",
        ],
    )
    asset_row = {}
    for i, a in enumerate(dep["assets"]):
        r = 5 + i
        asset_row[a["asset_id"]] = r
        ws.append(
            [
                a["asset_id"],
                a["kind"],
                a["allocation"],
                _num(a["opening_net"]),
                _num(a["acquired"]),
                _num(a["disposed_net"]),
                _num(a["impairment"]),
                _num(a["cost"]),
                _num(a["residual"]),
                _num(a["life_years"]),
                a["in_service"],
                a["disposed_on"],
                a["months"],
                f"=(H{r}-I{r})/J{r}",
                f"=MAX(0,D{r}+E{r}-F{r}-G{r}-I{r})",
                f"=ROUND(MIN(N{r}*M{r}/12,O{r}),6)",
                _num(a["prior"]),
                f"=D{r}+E{r}-F{r}-G{r}-P{r}",
            ]
        )
    _fmt(ws, "DEFGHINOPQR", range(5, 5 + len(dep["assets"])), MIL)
    sheets["자산별계산"] = ws

    def assets_of(field: str, value: str) -> list[int]:
        return [asset_row[a["asset_id"]] for a in dep["assets"] if a[field] == value]

    # ── 상각비비교 ──
    ws = _sheet(
        wb,
        "상각비비교",
        "상각비비교",
        "자산 종류와 비용 귀속은 같은 상각비의 두 분류 · 단위 백만원",
        ["구분", "전기", "당기", "증감", "증감률"],
    )
    kinds = [g["group"] for g in dep["by_kind"][:-1]]
    for k in kinds:
        rows = assets_of("kind", k)
        ws.append([k, refsum("자산별계산", "Q", rows), refsum("자산별계산", "P", rows)])
    kind_total = 5 + len(kinds)
    ws.append(["자산 합계", f"=SUM(B5:B{kind_total - 1})", f"=SUM(C5:C{kind_total - 1})"])
    allocs = [g["group"] for g in dep["by_allocation"][:-1]]
    for k in allocs:
        rows = assets_of("allocation", k)
        ws.append([k, refsum("자산별계산", "Q", rows), refsum("자산별계산", "P", rows)])
    alloc_total = kind_total + 1 + len(allocs)
    ws.append(
        [
            "귀속 합계",
            f"=SUM(B{kind_total + 1}:B{alloc_total - 1})",
            f"=SUM(C{kind_total + 1}:C{alloc_total - 1})",
        ]
    )
    for r in range(5, alloc_total + 1):
        ws.cell(row=r, column=4, value=f"=C{r}-B{r}")
        ws.cell(row=r, column=5, value=f'=IF(B{r}=0,"",D{r}/B{r})')
    _fmt(ws, "BCD", range(5, alloc_total + 1), MIL)
    _fmt(ws, "E", range(5, alloc_total + 1), "0.0%")
    sheets["상각비비교"] = ws

    # ── 유형자산주석 ──
    ws = _sheet(
        wb,
        "유형자산주석",
        "유형자산주석",
        "유형자산 순장부금액 변동 · 처분액은 제거한 순장부금액 · 단위 백만원",
        ["유형", "기초", "취득", "처분", "손상", "상각", "기말"],
    )
    for k in kinds:
        rows = assets_of("kind", k)
        ws.append(
            [
                k,
                refsum("자산별계산", "D", rows),
                refsum("자산별계산", "E", rows),
                refsum("자산별계산", "F", rows),
                refsum("자산별계산", "G", rows),
                refsum("자산별계산", "P", rows),
            ]
        )
    note_total = 5 + len(kinds)
    ws.append(["합계", *[f"=SUM({c}5:{c}{note_total - 1})" for c in "BCDEF"]])
    for r in range(5, note_total + 1):
        ws.cell(row=r, column=7, value=f"=B{r}+C{r}-D{r}-E{r}-F{r}")
    sheets["유형자산주석"] = ws

    # 원장대사의 나머지 — 분류·주석 대사(시트가 생긴 뒤 칸을 안다)
    ws = sheets["원장대사"]
    ws.append(
        [
            "상각비 분류 대사",
            f"=상각비비교!C{kind_total}",
            f"=상각비비교!C{alloc_total}",
            "=ROUND((C10-B10)*1000000,0)",
        ]
    )
    ws.append(
        [
            "주석 상각 대사",
            f"=상각비비교!C{kind_total}",
            f"=유형자산주석!F{note_total}",
            "=ROUND((C11-B11)*1000000,0)",
        ]
    )
    ws.append(
        ["주석 충당금 대사", "=충당금비교!C7", "=충당금주석!F5", "=ROUND((C12-B12)*1000000,0)"]
    )
    _fmt(ws, "BC", range(5, 13), MIL)

    # ── 승인요약 ──
    ws = _sheet(
        wb,
        "승인요약",
        "승인요약",
        f"{head} · 결과 {run['result_version']} · 각 금액은 상세 시트 수식과 연결된다",
        ["조정항목", "전기", "당기", "증감", "장부액", "승인 요청액", "근거·주석"],
    )
    ws.append(
        [
            "감가상각비",
            f"=상각비비교!B{kind_total}",
            f"=상각비비교!C{kind_total}",
            "=C5-B5",
            "=원장대사!B5",
            "=C5-E5",
            "상각비비교 → 유형자산주석",
        ]
    )
    ws.append(
        [
            "대손충당금",
            "=충당금비교!B7",
            "=충당금비교!C7",
            "=C6-B6",
            "=원장대사!B8",
            "=C6-E6",
            "충당금비교 → 개별평가 → 충당금주석",
        ]
    )
    _fmt(ws, "BCDEF", range(5, 7), MIL)
    ws.column_dimensions["G"].width = 36
    sheets["승인요약"] = ws

    # ── 실행정보 ──
    ws = _sheet(
        wb,
        "실행정보",
        "실행정보",
        "이 파일을 만든 실행과 버전 — 화면 요약과 같은 결과 버전을 가리킨다",
        ["항목", "값"],
    )
    for k, v in (
        ("결산 건", close),
        ("실행 ID", run["run_id"]),
        ("결과 버전", run["result_version"]),
        ("파일 버전", file_version),
        ("입력 버전", run["input_version"]),
        ("계산 기능", result["rule_version"]),
        ("프롬프트", run["versions"]["prompt"]),
        ("출력 서식", FORMAT_VERSION),
        ("Agent", run["versions"]["agent"]),
        ("실행 방식", run["execution_mode"]),
        ("실행 방식 설명", run["execution_note"]),
        ("실행자", run["requested_by"]),
        ("요청 시각", run["requested_at"]),
    ):
        ws.append([k, v])
    ws.column_dimensions["B"].width = 80
    sheets["실행정보"] = ws

    wb._sheets = [sheets[n] for n in SHEETS]
    stamp = datetime.fromisoformat(run["requested_at"]).astimezone(UTC).replace(tzinfo=None)
    wb.properties.created = stamp
    wb.properties.modified = stamp
    wb.properties.creator = "NowView 결산 계산 기능(모의 실행)"
    raw = io.BytesIO()
    wb.save(raw)
    content = _fixed_zip(raw.getvalue(), stamp)
    return {
        "filename": f"{close}_결산조정_계산근거_v{file_version}.xlsx",
        "content_type": CONTENT_TYPE,
        "content": content,
        "sha256": hashlib.sha256(content).hexdigest(),
        "size": len(content),
        "sheets": list(SHEETS),
        "format_version": FORMAT_VERSION,
        #: 승인요약 칸 — 화면 요약과 대조할 위치
        "summary_cells": {
            "DEP": {"prior": "승인요약!B5", "current": "승인요약!C5", "request": "승인요약!F5"},
            "ALW": {"prior": "승인요약!B6", "current": "승인요약!C6", "request": "승인요약!F6"},
        },
        "trace": {
            "ALW": ["개별평가", "채권별계산", "충당금비교", "충당금주석", "승인요약"],
            "DEP": ["자산별계산", "상각비비교", "유형자산주석", "원장대사", "승인요약"],
        },
    }


def _fixed_zip(data: bytes, stamp: datetime) -> bytes:
    """
    압축 항목의 시각과 문서 속성의 수정 시각을 실행 시각으로 — 같은 결과는 같은 바이트. openpyxl은
    저장할 때 `modified`를 지금 시각으로 덮어쓴다.
    """
    src = zipfile.ZipFile(io.BytesIO(data))
    out = io.BytesIO()
    when = stamp.strftime("%Y-%m-%dT%H:%M:%SZ")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            body = src.read(info.filename)
            if info.filename == "docProps/core.xml":
                body = re.sub(
                    rb"(<dcterms:modified[^>]*>)[^<]*(</dcterms:modified>)",
                    rb"\g<1>" + when.encode() + rb"\g<2>",
                    body,
                )
            fixed = zipfile.ZipInfo(info.filename, date_time=stamp.timetuple()[:6])
            fixed.compress_type = zipfile.ZIP_DEFLATED
            fixed.external_attr = info.external_attr
            dst.writestr(fixed, body)
    return out.getvalue()


def opens(content: bytes) -> list[str]:
    """등록한 파일이 다시 열리는지 — 시트 이름 목록(열리지 않으면 예외)."""
    from openpyxl import load_workbook

    return load_workbook(io.BytesIO(content)).sheetnames


__all__ = ["CONTENT_TYPE", "FORMAT_VERSION", "SHEETS", "build", "opens"]
