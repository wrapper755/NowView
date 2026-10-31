"""
회사 등록부(`app/companies.py`) — NowView가 운영 현황을 보여 주는 회사와, 그 회사의
BPM 프로세스가 Center에 올라간 이름(패키지·일꾼 토픽).

* **화면 사본과 같다** — `lib/companies.ts`는 빌드 때 정적 경로를 만들려고 둔 사본이다.
* **회사 이름으로 옮긴 장면은 그림·확장 정의·프로세스가 같은 이름을 말한다** — 패키지 id =
  BPMN 프로세스 id, 토픽 = 서비스 호출의 `app_id` = 확장 정의 id = `chk:process.extensions`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from chaeksas.contracts.bpmn_ext import read_process
from fastapi.testclient import TestClient

from app.companies import COMPANIES, build_router
from app.sc01.process import APP_ID as SC01_APP_ID
from app.sc01.process import INTAKE_PATH
from app.sc01.process import PROCESS_PATH as SC01_PATH

ROOT = Path(__file__).resolve().parents[2]
DRAWINGS = {1: [SC01_PATH, INTAKE_PATH]}


def _ts_registry() -> list[tuple[str, int, str, str]]:
    text = (ROOT / "lib" / "companies.ts").read_text("utf-8")
    company_ids = re.findall(r'^\s{4}id: "([a-z0-9-]+)"', text, re.M)
    scenes = re.findall(
        r'no: (\d), work: "[^"]+", detail: "[^"]+", topic: "([^"]+)", package: "([^"]+)"', text
    )
    assert len(company_ids) == 1, "회사가 늘면 이 대조를 회사별로 나눈다"
    return [(company_ids[0], int(no), topic, package) for no, topic, package in scenes]


def test_screen_registry_matches_the_engine() -> None:
    engine = [(c.id, s.no, s.topic, s.package) for c in COMPANIES for s in c.scenes]
    assert _ts_registry() == engine


def test_topics_are_unique_across_companies() -> None:
    topics = [s.topic for c in COMPANIES for s in c.scenes]
    assert len(topics) == len(set(topics))


@pytest.mark.parametrize(
    "scene",
    [s for c in COMPANIES for s in c.scenes if s.migrated],
    ids=lambda s: s.topic,
)
def test_migrated_scene_speaks_one_name(scene) -> None:
    """옮긴 장면: 확장 정의 id = 토픽, 그림의 프로세스 id = 패키지, 서비스 호출·확장 선언 = 토픽."""
    raw = json.loads((ROOT / "chaeksas" / f"{scene.topic}.extension.json").read_text("utf-8"))
    assert raw["id"] == scene.topic
    main, *others = DRAWINGS[scene.no]
    assert read_process(main.read_bytes()).id == scene.package
    for path in [main, *others]:
        process = read_process(path.read_bytes())
        assert [e.id for e in process.info.extensions] == [scene.topic], path.name
        for node in process.of_kind("serviceTask"):
            assert node.prop("serviceCall").app_id == scene.topic, (path.name, node.id)
    if scene.no == 1:
        assert SC01_APP_ID == scene.topic


class _Worker:
    def describe(self):
        return {
            "state": "off",
            "topics": [],
            "requestCode": None,
            "problem": None,
            "lastFetch": None,
        }

    def recent_tasks(self):
        return []


class _Center:
    class config:  # noqa: N801 — CenterClient.config 모양
        @staticmethod
        def describe():
            return {"url": None, "integration": False, "relay": False}


class _Poller:
    running = False


def test_companies_and_worker_routes() -> None:
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(build_router(_Worker(), _Center(), _Poller()))
    client = TestClient(app)
    body = client.get("/companies").json()
    assert body[0]["id"] == "autoparts"
    assert body[0]["scenes"][0] == {
        "no": 1,
        "work": "고객 생산계획 변경 대응",
        "topic": "autoparts-sc01",
        "package": "autoparts.sc01",
        "migrated": True,
    }
    assert [s["migrated"] for s in body[0]["scenes"]][1:] == [False] * 5
    worker = client.get("/worker").json()
    assert worker["consumer"]["state"] == "off" and worker["center"]["polling"] is False
