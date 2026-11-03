"""
경영 기록 계약 시험의 공통 몫 — 장면 2~7(`test_records_sc0N.py`).

* 기본 시연을 끝까지 돌리는 동안 회사에 적힌 **모든 판**(최신·지난 판)이 봉투·종류별 스키마
  (`docs/records/sc0N/`)를 통과하는지 본다 — 회사 사이트가 같은 스키마로 읽는다.
* **스키마는 손으로 쓰지 않고 기본 시연의 모든 판에서 뽑았다**(`infer`). 그래서 스키마가 보장하는
  것은 「기본 시연이 실제로 낸 모양」이다 — 필수 칸·값 종류·금액 문자열(DECIMAL)·시각 형식. 이
  시연 밖의 사례(X·E 사례)가 새 칸을 내도 막지 않고(`additionalProperties`), 있던 칸을 빼거나
  종류를 바꾸면 막는다. 다시 뽑으려면 `NOWVIEW_WRITE_RECORD_SCHEMAS=1` — 무엇이 바뀌었는지 diff로
  본다.
* 사이트 시험용 예시(`docs/records/sc0N/examples/base-end.json`)는
  `NOWVIEW_WRITE_RECORD_EXAMPLES=1`로 다시 만든다(장면 1과 같다).
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

DOCS = Path(__file__).resolve().parents[2] / "docs" / "records"
ENVELOPE = Draft202012Validator(json.loads((DOCS / "envelope.schema.json").read_text("utf-8")))
DECIMAL = r"^-?\d+(\.\d+)?(E-?\d+)?$"
DATETIME = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d(:\d\d(\.\d+)?)?([+-]\d\d:\d\d|Z)$")
_TYPES = {
    type(None): "null",
    bool: "boolean",
    int: "integer",
    float: "number",
    str: "string",
    list: "array",
    dict: "object",
}
#: 키가 이보다 많거나 식별자 모양이 아니면 「모양」이 아니라 「사전」(id·기간·모델 → 값)으로 본다
_MAP_KEYS = 24
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def every_version(company: Any, world: str, scene: int) -> list[dict]:
    out = []
    for r in company.records(world, scene=scene):
        full = company.record(world, r["kind"], r["record_id"])
        out.extend([full, *full["history"]])
    return out


def _infer(values: list[Any], depth: int = 0) -> dict[str, Any]:
    types = sorted({_TYPES[type(v)] for v in values})
    if depth > 8:
        return {}
    present = [v for v in values if v is not None]
    if not present:
        return {"type": "null"}
    kinds = {_TYPES[type(v)] for v in present}
    if kinds == {"integer", "number"}:
        kinds = {"number"}
        types = sorted(set(types) - {"integer"})
    if len(kinds) > 1:
        return {"type": types}
    kind = next(iter(kinds))
    schema: dict[str, Any] = {"type": types[0] if len(types) == 1 else types}
    if kind == "string":
        if all(re.match(DECIMAL, v) for v in present):
            schema["pattern"] = DECIMAL
        elif all(DATETIME.match(v) for v in present):
            schema["format"] = "date-time"
    elif kind == "array":
        inner = [x for v in present for x in v]
        if inner:
            schema["items"] = _infer(inner, depth + 1)
    elif kind == "object":
        keys: dict[str, list[Any]] = {}
        for v in present:
            for k, x in v.items():
                keys.setdefault(k, []).append(x)
        if len(keys) > _MAP_KEYS or not all(_IDENT.match(k) for k in keys):
            inner = [x for v in present for x in v.values()]
            schema["additionalProperties"] = _infer(inner, depth + 1) if inner else {}
        else:
            schema["required"] = sorted(k for k in keys if all(k in v for v in present))
            schema["properties"] = {k: _infer(xs, depth + 1) for k, xs in keys.items()}
            schema["additionalProperties"] = True
    return schema


def infer(scene: int, kind: str, bodies: list[dict], description: str) -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"sc{scene:02d}/{kind}.schema.json",
        "title": f"장면 {scene} {kind}",
        "description": description,
        **_infer(bodies),
    }


def check(scene: int, kinds: dict[str, str], versions: list[dict]) -> list[str]:
    """
    모든 판을 봉투·종류별 스키마로 검사한다. 스키마가 없는 종류·쓰이지 않은 스키마도 문제다.
    `NOWVIEW_WRITE_RECORD_SCHEMAS`가 켜져 있으면 이 판들로 스키마를 다시 뽑아 쓴다.
    """
    folder = DOCS / f"sc{scene:02d}"
    by_kind: dict[str, list[dict]] = {}
    for r in versions:
        by_kind.setdefault(r["kind"], []).append(r["body"])
    if os.getenv("NOWVIEW_WRITE_RECORD_SCHEMAS"):
        folder.mkdir(parents=True, exist_ok=True)
        for kind, bodies in by_kind.items():
            schema = infer(scene, kind, bodies, kinds.get(kind, ""))
            text = json.dumps(schema, ensure_ascii=False, indent=2) + "\n"
            (folder / f"{kind}.schema.json").write_text(text, "utf-8")
    found: list[str] = []
    schemas = {
        p.name.removesuffix(".schema.json"): Draft202012Validator(
            json.loads(p.read_text("utf-8")), format_checker=Draft202012Validator.FORMAT_CHECKER
        )
        for p in folder.glob("*.schema.json")
    }
    if set(schemas) != set(kinds):
        found.append(f"스키마 {sorted(schemas)} ≠ 종류 {sorted(kinds)}")
    if set(by_kind) != set(kinds):
        found.append(f"적힌 종류 {sorted(by_kind)} ≠ 종류 {sorted(kinds)}")
    for r in versions:
        head = {k: r[k] for k in ENVELOPE.schema["properties"]}
        found += [f"봉투: {e.message}" for e in ENVELOPE.iter_errors(head)]
        if r["scene"] != scene:
            found.append(f"{r['record_id']}: 장면 {r['scene']}")
        if not r["record_id"].startswith(f"SC{scene:02d}:"):
            found.append(f"{r['record_id']}: 장면 코드가 앞에 없다")
        schema = schemas.get(r["kind"])
        if schema is not None:
            for e in schema.iter_errors(r["body"]):
                found.append(f"{r['kind']}/{r['record_id']} {list(e.path)}: {e.message}")
    return found


def normalized(records: list[dict], world: str) -> list[dict]:
    text = json.dumps(records, ensure_ascii=False).replace(world, "demo-example")
    # 실제 시각(만든 시각·Agent 요청)은 예시마다 달라진다
    real = r'"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d+\+00:00)"'
    text = re.sub(real, '"2026-11-03T00:00:00+00:00"', text)
    text = re.sub(r"apr_run_[0-9a-z_]+?_(?=[A-Z])", "apr_run_example_", text)
    return json.loads(text)


def example(company: Any, world: str, scene: int) -> list[str]:
    """
    사이트 시험이 쓰는 예시(그 장면 기록의 최신 판)가 지금 엔진이 적는 것과 같은 목록·판인지.
    `NOWVIEW_WRITE_RECORD_EXAMPLES`가 켜져 있으면 다시 쓴다.
    """
    path = DOCS / f"sc{scene:02d}" / "examples" / "base-end.json"
    latest = [
        company.record(world, r["kind"], r["record_id"])
        for r in company.records(world, scene=scene)
    ]
    for r in latest:
        r.pop("history")
    now = normalized(latest, world)
    if os.getenv("NOWVIEW_WRITE_RECORD_EXAMPLES"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(now, ensure_ascii=False, indent=1) + "\n", "utf-8")
    if not path.exists():
        return [f"예시가 없다: {path}"]
    saved = json.loads(path.read_text("utf-8"))
    if [(r["kind"], r["record_id"], r["version"]) for r in saved] != [
        (r["kind"], r["record_id"], r["version"]) for r in now
    ]:
        return ["예시가 낡았다 — NOWVIEW_WRITE_RECORD_EXAMPLES=1로 다시 만든다"]
    return []
