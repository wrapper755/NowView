"""
경영 기록 — 회사 시스템(기간계)에 적는 판의 공통 몫(`docs/role-split.md` §3,
스키마 `docs/records/`).

장면마다 `app/sc0N/records.py`가 지금 문서의 기록 전부를 짓고(`records_of`), 여기서 바뀐 것만
새 판으로 고른다(`pending_writes`). 각 장면의 `_commit`(그리고 생성)이 **저장 직전에** 적는다 —
회사가 받지 못하면 그 조작은 저장되지 않는다(503). 문서의 `company_records`에 기록마다 (판, 본문
해시)를 둔다 — 문서가 저장되지 않으면 고친 판도 버려져 다음 조작이 같은 판을 다시 낸다(ref 멱등).

* **기간계의 기록 키는 kind/record_id다**(장면을 가리지 않는다). 장면 2~7에는 같은 업무 id가
  다시 나온다(TASK-VERIFY는 장면 2·4, MR-2706-01은 장면 2·3) — 그래서 장면 2~7의 record_id는
  장면 코드를 앞에 붙인다(`SC02:TASK-VERIFY`, `scoped`). 장면 1(파일럿)은 id가 겹치지 않아 그대로
  뒀다. 본문의 업무 id는 그대로다.
* **본문은 NowView 화면이 읽는 모양 그대로다**(2026-11-03 사용자 결정) — 장면 view의 같은 칸.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def record(kind: str, record_id: str, state: str | None, title: str, body: Any) -> dict:
    return {"kind": kind, "record_id": record_id, "state": state, "title": title, "body": body}


def scoped(scene: int, record_id: str) -> str:
    """장면 2~7의 기록 id — 장면 코드를 앞에 붙인다(기간계 키가 장면을 가리지 않는다)."""
    return f"SC{scene:02d}:{record_id}"


def items(
    scene: int, kind: str, rows: list[dict], id_key: str, state_key: str | None, title: Any
) -> list[dict]:
    """목록 칸 하나 → 기록 여럿. `title`은 글자 칸 이름이거나 행을 받는 함수다."""
    out = []
    for row in rows:
        state = None if state_key is None else row.get(state_key)
        label = title(row) if callable(title) else str(row.get(title) or row[id_key])
        state = None if state is None else str(state)
        out.append(record(kind, scoped(scene, str(row[id_key])), state, label, row))
    return out


def bpm_head(bpm: dict | None) -> dict | None:
    """화면 머리의 BPM 칸 — 실행 위치·바깥 실행 id·상태·지나온 노드(결재 대기·폼은 싣지 않는다)."""
    if bpm is None:
        return None
    return {k: bpm[k] for k in ("executor", "externalRunId", "state", "visited")}


def _digest(body: Any) -> str:
    text = json.dumps(body, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(text.encode()).hexdigest()


def pending_writes(doc: dict, scene: int, found: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    바뀐 기록을 새 판으로 — 회사에 보낼 봉투 목록. 문서의 `company_records`(판·해시)를 함께 고친다.
    ref = 데모실행:종류/id:v판 — 재시도는 회사가 다시 적지 않는다.
    """
    known = doc.setdefault("company_records", {})
    writes = []
    for r in found:
        key = f"{r['kind']}/{r['record_id']}"
        digest = _digest([r["state"], r["title"], r["body"]])
        prior = known.get(key)
        if prior is not None and prior["hash"] == digest:
            continue
        version = (prior["version"] if prior else 0) + 1
        known[key] = {"version": version, "hash": digest}
        writes.append(
            {
                **r,
                "version": version,
                "scene": scene,
                "at": doc["clock"],
                "by": None,
                "ref": f"{doc['demo_run_id']}:{key}:v{version}",
            }
        )
    return writes


def write(company: Any, doc: dict, scene: int, found: list[dict[str, Any]]) -> None:
    """바뀐 기록을 회사에 적는다 — 저장 직전에. 받지 못하면 예외(그 조작은 저장되지 않는다)."""
    # 저장한 문서가 JSON을 지나며 바뀌는 값(튜플·Decimal)이 해시를 흔들지 않게 한 번 정규화한다
    normalized = json.loads(json.dumps(found, ensure_ascii=False, default=str))
    writes = pending_writes(doc, scene, normalized)
    # 한 조작의 기록을 한 번에 — 판마다 보내면 회사가 판마다 세계 문서 전체를 다시 썼다(시험 실측
    # 판 하나 약 0.1초). 전부 적거나 하나도 적지 않는다.
    for start in range(0, len(writes), 500):
        company.write_records(doc["demo_run_id"], writes[start : start + 500])


def restart(company: Any, doc: dict, scene: int) -> None:
    """장면을 처음으로 — 회사의 그 장면 기록을 지우고 판을 처음부터(초기화·새로 열기)."""
    company.reset_records(doc["demo_run_id"], scene)
    doc["company_records"] = {}


__all__ = ["bpm_head", "items", "pending_writes", "record", "restart", "scoped", "write"]
