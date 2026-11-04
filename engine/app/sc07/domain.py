"""
SC07 업무 규칙 — 관리모델 개선 IMP71의 적재(구현명세 2장)와 조회(6장).

장면 7은 장면 6 성과 검토에서 사람이 보정한 경험(AG62 → PO61-1103)을 Agent의 근거 연결·원인 후보
방식에
반영하고, 개선 버전(AGT71-v2)을 검증해 다음 운영 설정(CFG71)에 적용하는 장면이다(SC07-S01~S09).

* **장면 6 보고본에서 시작한다.** 데모 실행 id가 장면 1~6과 같고, 장면 6 확인 절차가 대표
  보고(RPT61-v1
  REPORTED)까지 끝나 있어야 한다. 장면 6 결과는 스냅샷이다(`doc["sc06"]`) — AG62 초안·사람
  보정·보고본·성과
  수치를 **바꾸지 않고**(CT705) 비교 화면에만 쓴다. 그 지문(`fingerprint`)으로 원본 보존(TC707)을
  본다.
* **v0.7 SC07 시트를 별도 네임스페이스로 적재한다.** 고유 키 중복·참조 누락·필수 버전 공란은 적재
  오류다
  (422 DATA_INVALID). IMP71 → 버전 묶음 → TS71-v1 → 검증 사례 → 확인 이력 → AP71의 연결을 검사한다.
* **확인·적용 기록은 일정이자 기대값이다**(`schedule` — CF71·CF72·설정 반영·설정 확인). 확인
  절차(BPM,
  `confirm.py`)가 그 글·시각으로 다시 남긴다 — 장면 6과 같다.
* **조회는 아무것도 적지 않는다**(AT712 — 보기 전환·새로고침으로 승인·배포·적용 이벤트가 생기지
  않는다).
  모든 조회 응답에 `dataset_version`·`improvement_id`·`version_bundle`·`as_of`를 싣는다.
"""

from __future__ import annotations

import re
import secrets
from datetime import datetime
from typing import Any

from app.sc01.domain import USERS, DomainError
from app.sc05 import domain as sc05_domain
from app.sc07 import calc
from app.sc07.seed import DATASET_VERSION, SEED_ID, Seed, kst

IMPROVEMENT_ID = "IMP71"
APPLICATION_ID = "AP71"
SOURCE_REPORT = "RPT61-v1"
SOURCE_AGENT = "AG62"
FOCUS_INPUT = "IN71"
FOCUS_CASE = "TC701"
CASES = {"BASE": "기본 시연"}

#: 데이터의 가상 계정 → NowView 사용자. 장면 5·6과 같은 대응에 장면 7의 새 역할 둘을 더했다(이름은
#: 역할명).
ACCOUNTS = {**sc05_domain.ACCOUNTS, "USR-OPS71": "u-ops", "USR-DEV71": "u-dev"}
#: IMP71을 볼 수 있는 사람 — 개선에 참여한 조직(경영관리·구매·운영·구현)과 대표·시연관리자. 그
#: 밖(영업·
#: 생산·자재·품질)은 403이다(구현명세 6장 ACCESS_DENIED). 화면의 역할 선택은 신뢰 경계가
#: 아니다(5.4).
READERS = frozenset(
    {
        *(ACCOUNTS[k] for k in ("USR-FIN", "USR-CFO", "USR-CEO", "USR-BUY", "USR-BUY2", "EX-BUY")),
        "u-ops",
        "u-dev",
        "u-fin-lead",
        "u-demo",
    }
)


class ReadError(DomainError):
    """조회 오류 — 화면이 갈라 보일 코드(ACCESS_DENIED·NOT_FOUND·VERSION_MISMATCH·DATA_INVALID)를
    싣는다."""

    def __init__(self, message: str, status: int, code: str) -> None:
        super().__init__(message, status)
        self.code = code


def who(account: str | None) -> dict[str, Any] | None:
    """데이터 계정(USR-FIN …) → 화면에 보일 이름. 계정이 아닌 글은 그대로 둔다."""
    if not account:
        return None
    uid = ACCOUNTS.get(account)
    user = USERS.get(uid or "", {})
    return {
        "account": account,
        "userId": uid,
        "name": user.get("name", account),
        "role": user.get("role"),
    }


def account_of(user_id: str) -> str:
    """NowView 사용자 → 데이터 계정(기록에 적는 이름). 마스터 밖의 이름은 그대로."""
    return next((a for a, u in ACCOUNTS.items() if u == user_id), user_id)


def _head(value: Any) -> str:
    """「USR-OPS71. 가상 설정 변경 기록」 → 「USR-OPS71」. 근거 칸의 첫 토큰."""
    return re.split(r"[.\s/]", str(value or "").strip(), maxsplit=1)[0]


# ─────────────────────────── 적재 (구현명세 2장) ───────────────────────────


def _unique(rows: list[dict[str, Any]], key: str, sheet: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        k = str(r.get(key) or "").strip()
        if not k:
            raise ReadError(f"{sheet}: 키({key})가 빈 행", 422, "DATA_INVALID")
        if k in out:
            raise ReadError(f"{sheet}: 고유 키 중복 — {k}", 422, "DATA_INVALID")
        out[k] = r
    return out


def _inputs(rows: dict[str, dict[str, Any]], evidence: dict[str, dict[str, Any]]) -> dict:
    out = {}
    for iid, r in rows.items():
        source = str(r["원자료 / 사례"] or "")
        change = re.match(r"(CH\d+-\d+)", source)
        valid = r["대행 유효"]
        out[iid] = {
            "input_id": iid,
            "case_label": source,
            "change_id": change.group(1) if change else None,
            # 실제 SC06 사건인가 — 합성 사례(IN73·IN74)는 성과 집계·사건 이력에 넣지 않는다(구현명세
            # 3장)
            "synthetic": source.startswith("독립 합성"),
            # 실제 사건에 검증용 가정을 더했다(IN75 — 적시 공급 조건)
            "supplemented": "합성 보완" in source,
            "shared_at": kst(r["공유 시각"]),
            "primary_confirmed_at": kst(r["주담당 확인"]),
            "deputy_confirmed_at": kst(r["대행 확인"]),
            "deputy_valid": None if valid in (None, "") else bool(int(valid)),
            "required_at": kst(r["요구 납기"]),
            "timely_supply_at": kst(r["적시 주문 공급일"]),
            "order_cutoff_at": kst(r["발주 마감"]),
            "evidence_status": r["증적 상태"],
            "evidence_refs": sorted(e for e, ev in evidence.items() if iid in ev["links"]),
        }
    return out


def _evidence(rows: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        eid: {
            "evidence_id": eid,
            "links": [x.strip() for x in str(r["연결"] or "").split("/") if x.strip()],
            "kind": r["종류"],
            "content": r["기록 / 내용"],
            "caution": r["주의"],
        }
        for eid, r in rows.items()
    }


def load_batch(seed: Seed, rows: dict[str, list[dict[str, Any]]] | None = None) -> dict[str, Any]:
    """
    SC07 원천 → 문서 조각. 고유 키·참조·필수 버전을 검사한다(구현명세 2장 「적재 규칙」). `rows`로
    시트를
    바꿔 넣으면 시험 fixture다(기본 시연 데이터에 섞지 않는다).
    """
    src = {**seed.sheets, **(rows or {})}
    improvement_rows = _unique(src["SC07개선"], "개선 ID", "SC07개선")
    rules = _unique(src["SC07기준"], "기준 ID", "SC07기준")
    versions = _unique(src["SC07버전"], "식별자", "SC07버전")
    evidence = _evidence(_unique(src["SC07근거"], "근거 ID", "SC07근거"))
    inputs = _inputs(_unique(src["SC07검증입력"], "입력 ID", "SC07검증입력"), evidence)
    cases_raw = _unique(src["SC07검증결과"], "검증 ID", "SC07검증결과")
    confirmations = _unique(src["SC07확인이력"], "확인 ID", "SC07확인이력")
    apply_rows = _unique(src["SC07적용"], "항목", "SC07적용")

    if IMPROVEMENT_ID not in improvement_rows:
        raise ReadError(f"SC07개선: {IMPROVEMENT_ID}가 없다", 422, "DATA_INVALID")

    def version(key: str) -> str:
        v = str((versions.get(key) or {}).get("버전 / 값") or "").strip()
        if not v:
            raise ReadError(f"SC07버전: {key}의 버전이 비었다", 422, "DATA_INVALID")
        return v

    bundle = {
        "improvement": version("IMP71"),
        "agent": version("AGT71"),
        "agent_previous": str(versions["AGT71"]["이전 / 연결"]),
        "measure": version("MB71"),
        "measure_previous": str(versions["MB71"]["이전 / 연결"]),
        "projection": version("PR71"),
        "projection_previous": str(versions["PR71"]["이전 / 연결"]),
        "verification_set": version("TS71"),
    }
    threshold = int(version("TH71"))
    proposed = re.search(r"\d{4}-\d{2}-\d{2}", str(versions["IMP71"]["설명"] or ""))

    def value(item: str) -> Any:
        row = apply_rows.get(item)
        if row is None:
            raise ReadError(f"SC07적용: {item} 항목이 없다", 422, "DATA_INVALID")
        return row["값"]

    def note(item: str) -> str:
        return str(apply_rows[item]["근거 / 해석"] or "")

    scope_note = note("적용 범위")
    plan = {
        "application_id": str(value("적용 ID")),
        "verification_set": note("적용 ID").split("/")[-1].strip(),
        "target_version": str(value("대상 버전")),
        "snapshot_version": str(value("설정 스냅샷 버전")),
        "snapshot_id": _head(note("설정 스냅샷 버전")),
        "scope": str(value("적용 범위")),
        "scope_detail": scope_note.split(".")[0].strip(),
        "scope_note": scope_note,
        "applied_at": kst(value("설정 반영 일시")),
        "applied_by": _head(note("설정 반영 일시")),
        "checked_at": kst(value("설정 확인 일시")),
        "checked_by": _head(note("설정 확인 일시")),
        "evidence_type": str(value("증적 유형")),
        "evidence_note": note("증적 유형"),
        "operation_run_id": value("운영 실행 ID") or None,
        "next_run_at": kst(value("차기 운영 예정")),
        "verdict": str(value("판정")),
        "follow_up_at": kst(value("사후 점검")),
        "follow_up_by": _head(note("사후 점검")),
        "follow_up_items": note("사후 점검").split(".", 1)[-1].strip(),
    }
    found = re.search(r"전\s*(v\d+)\s*→\s*후\s*(v\d+)", plan["evidence_note"])
    plan["previous_version"] = (
        f"{bundle['agent'].rsplit('-', 1)[0]}-{found.group(1)}"
        if found
        else bundle["agent_previous"]
    )

    cases = []
    for cid, r in cases_raw.items():
        ref = str(r["입력 / 증적"] or "").strip()
        if ref not in inputs and ref not in evidence and ref != plan["application_id"]:
            raise ReadError(f"SC07검증결과 {cid}: 참조 누락 — {ref}", 422, "DATA_INVALID")
        cases.append(
            {
                "check": cid,
                "title": r["검증 내용"],
                "input_ref": ref,
                "expected": r["기대값 (Agent 제외)"],
                # 데이터의 가상 결과·일치 여부 — 시연용 이력이다(판정에 쓰지 않는다)
                "simulated": r["가상 결과 / 비교값"],
                "simulated_status": r["일치 여부"],
                "mode": r["실행 모드"],
                "fixture": ref in inputs and inputs[ref]["synthetic"],
            }
        )
    schedule = {}
    for seq, (cid, r) in enumerate(confirmations.items()):
        if r["개선 ID"] != IMPROVEMENT_ID:
            raise ReadError(f"SC07확인이력 {cid}: 다른 개선({r['개선 ID']})", 422, "DATA_INVALID")
        if not str(r["대상 버전"] or "").strip():
            raise ReadError(f"SC07확인이력 {cid}: 대상 버전이 비었다", 422, "DATA_INVALID")
        schedule[cid] = {
            "record_id": cid,
            "seq": seq,
            "actor": r["확인자"],
            "version": r["대상 버전"],
            "state": r["상태"],
            "at": kst(r["확인 일시"]),
            "content": r["확인 내용"],
        }
    if plan["verification_set"] != bundle["verification_set"]:
        raise ReadError(
            f"SC07적용: 검증 세트 {plan['verification_set']}가 버전 묶음"
            f"({bundle['verification_set']})과 다르다",
            422,
            "DATA_INVALID",
        )
    improvement = {
        "improvement_id": IMPROVEMENT_ID,
        "proposed_on": proposed.group(0) if proposed else None,
        "source": str(versions["IMP71"]["이전 / 연결"]),
        "items": [
            {
                "item_id": iid,
                "target": r["대상"],
                "before": r["변경 전"],
                "after": r["변경 후"],
                "scope": r["연결 / 범위"],
            }
            for iid, r in improvement_rows.items()
        ],
        "rules": [
            {"rule_id": k, "content": r["내용"], "version": r["버전"], "guard": r["불변 / 조건"]}
            for k, r in rules.items()
        ],
        "versions": [
            {
                "id": k,
                "kind": r["종류"],
                "value": r["버전 / 값"],
                "previous": r["이전 / 연결"],
                "note": r["설명"],
            }
            for k, r in versions.items()
        ],
    }
    return {
        "seed_id": SEED_ID,
        "sha256": seed.sha256,
        "dataset_version": DATASET_VERSION,
        "improvement": improvement,
        "bundle": bundle,
        "threshold_min": threshold,
        "inputs": inputs,
        "evidence": evidence,
        "cases": cases,
        "schedule": schedule,
        "plan": plan,
    }


# ─────────────────────────── 장면 6 결합 ───────────────────────────


def sc06_fingerprint(sc06_doc: dict) -> str:
    """장면 6의 보존 대상 — 보고본·확인 기록·산정·Agent 초안·변경 근거·거래(TC707·CT705)."""
    keys = ("report", "report_records", "calculations", "agent_runs", "changes", "orders")
    return calc.fingerprint({k: sc06_doc.get(k) for k in keys})


def sc06_link(sc06_doc: dict) -> dict[str, Any]:
    """
    장면 6 결과 스냅샷 — 보고본·AG62 초안과 사람 보정·대표 사례의 변경 근거·거래·근거. 대표 보고까지
    끝나야
    한다(장면 7 시작 조건 — 「장면 6 성과 검토와 사람의 원인 보정 기록이 확보됨」).
    """
    report = sc06_doc["report"]
    if report["state"] != "REPORTED" or report["report_version"] != SOURCE_REPORT:
        raise DomainError(
            f"완료·성과 검토 보고본이 대표 보고까지 끝나지 않았다({report['report_version']} "
            f"{report['state']}) — 보고 뒤에 관리모델 개선을 연다",
            409,
        )
    agent = sc06_doc["agent_runs"][SOURCE_AGENT]
    change = sc06_doc["changes"]["CH61-1103"]
    order = sc06_doc["orders"][change["order_id"]]
    totals = sc06_doc["calculations"][report["calculation_version"]]["totals"]
    return {
        "report_version": report["report_version"],
        "report_state": report["state"],
        "calculation_version": report["calculation_version"],
        "expected_krw": totals["expected_krw"],
        "actual_krw": totals["actual_krw"],
        "agent": {
            k: agent[k]
            for k in (
                "run_id",
                "at",
                "input_scope",
                "task",
                "draft",
                "candidate_cause",
                "human",
                "reviewed_by",
                "reviewed_at",
                "links",
                "state",
                "mode",
            )
        },  # fmt: skip
        "change": {
            k: change[k]
            for k in (
                "change_id",
                "order_id",
                "shared_at",
                "confirmed_at",
                "required_at",
                "supply_at",
                "cause",
                "evidence_id",
            )
        },  # fmt: skip
        "order": {
            "order_id": order["order_id"],
            "cost_krw": (order["freight"] or 0) + (order["surcharge"] or 0),
            "approved_by": order["approver"],
        },
        "evidence": sc06_doc["evidence"].get(change["evidence_id"]),
        "fingerprint": sc06_fingerprint(sc06_doc),
    }


def new_improvement(seed: Seed, demo_run_id: str, sc06: dict[str, Any], *, created_at: datetime):
    """IMP71 문서 — 확인 전(검증·확인·설정이 아직 없다). 확인 절차가 `confirm.py`로 채운다."""
    batch = load_batch(seed)
    # 대표 사례(IN71)는 장면 6의 PO61-1103 주문과 같은 사건이다 — 주문 id·주문 비용을 잇는다(AG62
    # 입력과 같다)
    for case in batch["inputs"].values():
        if case["change_id"] == sc06["change"]["change_id"]:
            case["order_id"] = sc06["order"]["order_id"]
            case["order_cost"] = sc06["order"]["cost_krw"]
            case["evidence_refs"] = sorted(
                {*case["evidence_refs"], sc06["change"]["evidence_id"], sc06["change"]["change_id"]}
            )
        else:
            case.setdefault("order_id", None)
            case.setdefault("order_cost", None)
    doc = {
        "scene": "SC07",
        "demo_run_id": demo_run_id,
        # 문서를 새로 만들 때마다 다른 값 — Center 멱등 키에 넣는다(`process._center_key`).
        # 장면 문서는 회차 초기화·장면부터 다시 때 지우고 새로 만들어 초기화 회차가 늘
        # 0이라, 이것 없이는 거둔 옛 작업(취소됨)이 같은 키로 그대로 돌아와 새 실행이
        # 서지 않았다(로컬 실측 2026-11-04).
        "center_epoch": secrets.token_hex(4),
        "case_id": "BASE",
        "created_at": created_at.isoformat(),
        "clock": None,
        "step": "D700",
        "sc06": sc06,
        "batch": {
            "batch_id": f"BATCH71-{batch['sha256'][:8]}",
            "seed_id": batch["seed_id"],
            "sha256": batch["sha256"],
            "dataset_version": batch["dataset_version"],
            "counts": {
                "inputs": len(batch["inputs"]),
                "evidence": len(batch["evidence"]),
                "cases": len(batch["cases"]),
                "rules": len(batch["improvement"]["rules"]),
            },
        },
        **{
            k: batch[k]
            for k in (
                "improvement",
                "bundle",
                "threshold_min",
                "inputs",
                "evidence",
                "cases",
                "schedule",
                "plan",
            )
        },
        "verification": None,
        "confirmations": {},
        "setting": None,
        "follow_up": None,
        "record_history": [],
        "audit": [],
    }
    audit(doc, actor="u-demo", action="sc07_loaded", batch=doc["batch"]["batch_id"])
    return doc


def planned_state(doc: dict) -> dict[str, Any]:
    """
    데이터의 확인·적용 기록(일정)을 끝난 것으로 본 적용 상태 — 시험이 `SC07요약`의 판정과 대조한다.
    """
    plan = doc["plan"]
    confirmations = {
        r["actor"]: {"state": r["state"], "version": r["version"], "at": r["at"]}
        for r in doc["schedule"].values()
    }
    setting = {
        "active_version": plan["snapshot_version"],
        "scope": plan["scope"],
        "evidence_type": plan["evidence_type"],
        "applied_at": plan["applied_at"],
        "checked_at": plan["checked_at"],
        "check_result": "MATCH",
    }
    return calc.application_state(
        verification=run_verification(doc, preserved=True),
        confirmations=confirmations,
        setting=setting,
        target_version=plan["target_version"],
        scope=plan["scope"],
        as_of=plan["checked_at"],
    )


def run_verification(doc: dict, *, preserved: bool) -> list[dict[str, Any]]:
    """TS71-v1을 개선 버전 규칙으로 실행한다 — `calc.verify`."""
    b = doc["bundle"]
    return calc.verify(
        doc["cases"],
        doc["inputs"],
        agent_version=b["agent"],
        projection=b["projection"],
        target_version=doc["plan"]["target_version"],
        preserved=preserved,
        threshold_min=doc["threshold_min"],
        bundle=f"{b['agent']}/{b['measure']}/{b['projection']}",
    )


def audit(doc: dict, *, actor: str, action: str, **detail: Any) -> None:
    user = USERS.get(actor, {"name": actor, "role": "system"})
    doc["audit"].append(
        {
            "seq": len(doc["audit"]) + 1,
            "at": doc["clock"],
            "actor": actor,
            "actorName": user["name"],
            "action": action,
            "detail": detail,
        }
    )


# ─────────────────────────── 조회 (구현명세 6장) ───────────────────────────


def check_reader(actor: str | None) -> None:
    if not actor:
        raise ReadError("X-Demo-Actor 헤더가 필요하다", 403, "ACCESS_DENIED")
    if actor not in READERS:
        # 근거 본문·상세 사유를 오류에 싣지 않는다
        raise ReadError("이 개선건을 볼 권한이 없다", 403, "ACCESS_DENIED")


def check_improvement(improvement_id: str) -> None:
    if improvement_id != IMPROVEMENT_ID:
        raise ReadError(f"없는 개선건: {improvement_id}", 404, "NOT_FOUND")


def check_application(application_id: str) -> None:
    if application_id != APPLICATION_ID:
        raise ReadError(f"없는 적용: {application_id}", 404, "NOT_FOUND")


def check_dataset(doc: dict, dataset_version: str | None) -> None:
    """두 보기의 데이터 버전이 다르면 섞어 비교하지 않는다 — 다시 조회한다(구현명세 6장)."""
    if dataset_version is not None and dataset_version != doc["batch"]["dataset_version"]:
        raise ReadError(
            f"화면의 데이터 버전({dataset_version})이 응답 버전"
            f"({doc['batch']['dataset_version']})과 "
            "다르다 — 전체를 다시 조회한다",
            409,
            "VERSION_MISMATCH",
        )


def _context(doc: dict) -> dict[str, Any]:
    b = doc["bundle"]
    return {
        "dataset_version": doc["batch"]["dataset_version"],
        "improvement_id": IMPROVEMENT_ID,
        "version_bundle": {
            "agent": b["agent"],
            "measure": b["measure"],
            "projection": b["projection"],
            "verification_set": b["verification_set"],
        },
        "as_of": doc["clock"],
        # 데이터의 검증 이력은 시연용 가정이다 — 실제 Agent 시험·운영 실행을 증명하지 않는다
        "fictional": True,
    }


def _fact(text: str, *refs: str) -> dict[str, Any]:
    return {"text": text, "evidence_refs": [r for r in refs if r]}


def _hm(at: str | None) -> str:
    return "미확인" if at is None else datetime.fromisoformat(at).strftime("%m/%d %H:%M")


def agent_output(doc: dict, input_id: str) -> dict[str, Any]:
    """
    개선 Agent(AGT71-v2)가 낼 출력의 모양(구현명세 4장) — 후보·소요시간·마감 상태·근거 연결
    사실·누락·다음
    처리. **규칙 계산의 결과를 사실마다 근거 ID와 함께 쓴 것이다** — 실시간 Agent 호출이
    아니다(execution_mode).
    """
    case = doc["inputs"][input_id]
    a = calc.assess(case, threshold_min=doc["threshold_min"])
    ev = {e["kind"]: eid for eid, e in doc["evidence"].items() if input_id in e["links"]}
    deleg = next((eid for k, eid in ev.items() if "위임" in k), None)
    log = next((eid for k, eid in ev.items() if "확인 로그" in k), None)
    supply = next((eid for k, eid in ev.items() if "공급" in k), case.get("change_id"))
    facts = []
    if a["confirmed_by"] == "DEPUTY":
        facts.append(
            _fact(
                f"주담당 확인란은 비었으나 유효 대행의 실제 확인이 {_hm(a['confirmed_at'])}에 있다",
                deleg,
                log,
            )
        )
    elif a["confirmed_by"] == "PRIMARY":
        facts.append(_fact(f"주담당 확인 {_hm(a['confirmed_at'])}", case.get("change_id")))
    if a["elapsed_minutes"] is not None:
        facts.append(
            _fact(
                f"공유 {_hm(case['shared_at'])} → 확인 {_hm(a['confirmed_at'])} = "
                f"{a['elapsed_minutes']}분(기준 {doc['threshold_min']}분 "
                f"{'초과' if a['deadline_status'] == 'OVER' else '이내'})",
                log or case.get("change_id"),
            )
        )
    if a["cutoff_status"] != "UNKNOWN":
        facts.append(
            _fact(
                f"발주 마감 {_hm(case['order_cutoff_at'])} "
                f"{'경과' if a['cutoff_status'] == 'OVER' else '이전 확인'}",
                supply,
            )
        )
    if a["supply_status"] != "UNKNOWN":
        facts.append(
            _fact(
                f"요구 납기 {_hm(case['required_at'])} · 적시 주문 공급일 "
                f"{_hm(case['timely_supply_at'])} — 적시 주문에도 "
                f"{'납기 초과' if a['supply_status'] == 'OVER' else '납기 충족'}",
                supply,
            )
        )
    next_action = (
        "근거를 보완한 뒤 다시 본다 — " + ", ".join(m["label"] for m in a["missing_fields"])
        if a["candidate_cause"] == "NEED_EVIDENCE"
        else "후보를 담당자가 확인한다 — 최종 원인은 사람이 판단한다"
    )
    if a["internal_review"]:
        next_action += " · 확인시간 기준 내·발주 마감 초과 — 내부 영향 추가 검토"
    return {
        **a,
        "candidate_label": calc.CAUSE_LABELS.get(a["candidate_cause"] or "", "판단 유보"),
        "facts": facts,
        "evidence_refs": case["evidence_refs"],
        "next_action": next_action,
        "agent_version": doc["bundle"]["agent"],
        "projection_version": doc["bundle"]["projection"],
        "execution_mode": "RULE_RECALC",
    }


def improvement(doc: dict, *, actor: str | None, dataset_version: str | None = None) -> dict:
    """U701 상태 A — 개선 사유, 기존 검토(AG62 원본·제한 입력), 개선한 검토 방식(IN71), 기준·절차 각
    한 줄."""
    check_reader(actor)
    check_dataset(doc, dataset_version)
    s6 = doc["sc06"]
    items = {i["item_id"]: i for i in doc["improvement"]["items"]}
    focus = doc["inputs"][FOCUS_INPUT]
    before_payload = calc.project(focus, doc["bundle"]["projection_previous"])
    after_payload = calc.project(focus, doc["bundle"]["projection"], bundle=doc["bundle"]["agent"])
    return {
        **_context(doc),
        "execution_mode": "RULE_RECALC",
        "improvement": {
            **{k: doc["improvement"][k] for k in ("improvement_id", "proposed_on", "source")},
            "main": items.get(IMPROVEMENT_ID),
            "framework": items.get(f"{IMPROVEMENT_ID}-F"),
            "process": items.get(f"{IMPROVEMENT_ID}-P"),
            "application": items.get(f"{IMPROVEMENT_ID}-A"),
            "excluded": items.get(f"{IMPROVEMENT_ID}-N"),
            "rules": doc["improvement"]["rules"],
            "versions": doc["improvement"]["versions"],
        },
        "source": {
            "report_version": s6["report_version"],
            "report_state": s6["report_state"],
            "order": s6["order"],
            "change": s6["change"],
            "evidence_id": s6["change"]["evidence_id"],
        },
        # 03 기존 검토 이력 — 원본 읽기 전용. 사람 보정은 비교용이고 재검증 입력이 아니다(BR708)
        "before": {
            "agent": s6["agent"],
            "agent_version": doc["bundle"]["agent_previous"],
            "projection_version": doc["bundle"]["projection_previous"],
            "payload": before_payload,
            "evidence_id": "EV76",
        },
        # 04 개선한 검토 방식 — 같은 사례를 개선 규칙으로 본다
        "after": {
            **agent_output(doc, FOCUS_INPUT),
            "payload": after_payload,
        },
        "areas": {"before": "OK", "after": "OK", "rules": "OK"},
    }


def verification(doc: dict, *, actor: str | None, dataset_version: str | None = None) -> dict:
    """
    U701 상태 B 왼쪽 — TC701 상세와 TC702~708 요약. 확인 절차의 검증 실행(`confirm`)이 남긴 결과다 —
    아직
    실행 전이면 「미실행」이다(빈 결과를 통과로 표시하지 않는다, UI703).
    """
    check_reader(actor)
    check_dataset(doc, dataset_version)
    run = doc["verification"]
    rows = []
    for c in doc["cases"]:
        result = next((r for r in (run or {}).get("results", []) if r["check"] == c["check"]), None)
        rows.append(
            {
                "check": c["check"],
                "title": c["title"],
                "input_ref": c["input_ref"],
                "expected": c["expected"],
                "observed": result["observed"] if result else None,
                "status": result["status"] if result else "NOT_RUN",
                "simulated": c["simulated"],
                "simulated_status": c["simulated_status"],
                "simulated_mode": c["mode"],
                "fixture": c["fixture"],
                "evidence_refs": result["evidence_refs"] if result else [c["input_ref"]],
                "detail": None
                if result is None
                else {
                    k: result[k] for k in ("leaks", "projection", "target_version") if k in result
                },
                # 데이터의 검증 이력에는 실행 일시·실행 ID가 없다 — 지어내지 않는다(구현명세 2장)
                "simulated_run_id": None,
            }
        )
    passed = sum(1 for r in rows if r["status"] == "PASS")
    focus_input = doc["inputs"][FOCUS_INPUT]
    return {
        **_context(doc),
        "execution_mode": "RULE_RECALC" if run else None,
        "run": None
        if run is None
        else {
            k: run[k] for k in ("run_id", "executed_at", "executed_by", "agent_version", "passed")
        },
        "summary": {
            "total": len(rows),
            "passed": passed,
            "not_run": sum(1 for r in rows if r["status"] == "NOT_RUN"),
            "state": "NOT_RUN" if run is None else ("PASSED" if run["passed"] else "NEEDS_WORK"),
        },
        "representative": {
            "check": FOCUS_CASE,
            "input": {k: v for k, v in focus_input.items() if k != "case_label"},
            "output": agent_output(doc, FOCUS_INPUT) if run else None,
            "human": doc["sc06"]["agent"]["human"],
            "human_by": who(doc["sc06"]["agent"]["reviewed_by"]),
        },
        "cases": rows,
    }


def _confirmation_view(r: dict | None) -> dict | None:
    return None if r is None else {**r, "actor": who(r["actor"])}


def application(doc: dict, *, actor: str | None, dataset_version: str | None = None) -> dict:
    """U701 상태 B 오른쪽 — 적용 범위·버전·적용일·책임·증적·확인 이력·상태 조건·운영 실행·후속
    점검."""
    check_reader(actor)
    check_dataset(doc, dataset_version)
    plan = doc["plan"]
    setting = doc["setting"]
    state = application_state(doc)
    return {
        **_context(doc),
        "application_id": APPLICATION_ID,
        "scope": plan["scope"],
        "scope_detail": plan["scope_detail"],
        "target_version": plan["target_version"],
        "previous_version": plan["previous_version"],
        "snapshot": None
        if setting is None
        else {
            **setting,
            "applied_by": who(setting["applied_by"]),
            "checked_by": who(setting.get("checked_by")),
        },
        "confirmations": [
            _confirmation_view(doc["confirmations"].get(rid))
            or {
                "record_id": rid,
                "actor": who(r["actor"]),
                "version": None,
                "state": "PENDING",
                "at": None,
                "content": None,
            }
            for rid, r in doc["schedule"].items()
        ],
        "state": state,
        "execution": {
            "status": "NOT_CONFIRMED",
            "operation_run_id": None,
            # 차기 운영 예정은 실행 사실이 아니다
            "next_run_at": plan["next_run_at"],
        },
        "follow_up": doc["follow_up"]
        and {**doc["follow_up"], "owner": who(doc["follow_up"]["owner"])},
        "rollback": {
            "previous_version": plan["previous_version"],
            "note": "적용 실패 시 이전 버전으로 되돌린다 — 기본 시연에서는 재연하지 않는다(V708)",
        },
    }


def application_state(doc: dict) -> dict[str, Any]:
    plan = doc["plan"]
    run = doc["verification"]
    return calc.application_state(
        verification=None if run is None else run["results"],
        confirmations={
            r["actor"]: {"state": r["state"], "version": r["version"], "at": r["at"]}
            for r in doc["confirmations"].values()
        },
        setting=doc["setting"],
        target_version=plan["target_version"],
        scope=plan["scope"],
        as_of=doc["clock"],
    )


def evidence(doc: dict, evidence_id: str, *, actor: str | None) -> dict[str, Any]:
    """
    근거 하나 — SC07근거(EV71~78)와 장면 6 대표 사례의 근거(E61-1103). 화면 조회 권한과 Agent 조회
    권한은
    다르다 — 이 경로는 화면 조회다(근거 본문을 Agent 입력으로 넘기지 않는다, 구현명세 4장).
    """
    check_reader(actor)
    found = doc["evidence"].get(evidence_id)
    if found is not None:
        return {**_context(doc), "evidence": found, "source": "SC07근거", "status": "OK"}
    s6 = doc["sc06"]
    if s6.get("evidence") and s6["evidence"]["evidence_id"] == evidence_id:
        return {
            **_context(doc),
            "evidence": {**s6["evidence"], "written_by": who(s6["evidence"]["written_by"])},
            "source": "SC06근거",
            "status": "OK",
        }
    raise ReadError(f"없는 근거: {evidence_id}", 404, "NOT_FOUND")


__all__ = [
    "ACCOUNTS",
    "APPLICATION_ID",
    "IMPROVEMENT_ID",
    "ReadError",
    "application",
    "evidence",
    "improvement",
    "load_batch",
    "new_improvement",
    "verification",
]
