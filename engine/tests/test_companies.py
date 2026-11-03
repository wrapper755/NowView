"""
NowView 설정과 회사(`app/config.py` · `app/companies.py`, `docs/worker-interfaces.md` §1).

* **업무 목록은 코드다** — 화면 사본(`lib/companies.ts`의 `SCENES`)과 엔진(`SCENE_WORKS`)이 같다.
* **설정은 엔진 DB에 있다** — 처음에는 기본값(가상 자동차 부품사)을 적고, 고친 값이 남는다. 회사
  id·매핑의 회사·업무 번호·토픽 겹침을 검사한다.
* **등록은 공개하지 않는다** — 공개 목록은 이름·설명·업무 번호뿐이다. 관리 API는 키 없이 401, 키가
  서버에 없으면 503.
* **일꾼은 보낸 BPM 프로세스 id로 업무를 찾는다** — 매핑에 없으면 `not_found`.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.companies import SCENE_WORKS, Settings, build_router
from app.config import ConfigStore, NowViewConfig, default_config
from app.consumer import routed_by
from app.store import build_sqlite_backend

ROOT = Path(__file__).resolve().parents[2]
ADMIN_KEY = "admin-test-key"


def test_scene_catalog_matches_the_screen() -> None:
    text = (ROOT / "lib" / "companies.ts").read_text("utf-8")
    screen = {int(no): work for no, work in re.findall(r'\{ no: (\d), work: "([^"]+)"', text)}
    assert screen == SCENE_WORKS


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(ConfigStore(build_sqlite_backend(str(tmp_path / "engine.sqlite"))))


def test_config_defaults_then_persists(settings: Settings, tmp_path) -> None:
    assert settings.config == default_config()
    assert settings.scene_of("company1.sc01") == 1
    assert settings.scene_of("company1.sc04") == 4
    assert settings.scene_of("other.bpm") is None

    changed = settings.config.model_copy(deep=True)
    changed.companies[0].system_url = "http://sim:8091"
    settings.replace(changed)
    again = Settings(ConfigStore(build_sqlite_backend(str(tmp_path / "engine.sqlite"))))
    assert again.config.companies[0].system_url == "http://sim:8091"


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        (lambda d: d["processes"].append({**d["processes"][0]}), "두 번 매핑"),
        (lambda d: d["processes"][0].update(company="nope"), "없는 회사"),
        (lambda d: d["processes"][0].update(scene=9), "없는 업무"),
        (lambda d: d["companies"].append({**d["companies"][0]}), "회사 id가 겹친다"),
        (lambda d: d.update(topics=[]), "topics"),
    ],
)
def test_config_rejects_inconsistent_settings(change, reason) -> None:
    body = default_config().model_dump()
    change(body)
    with pytest.raises(ValueError, match=reason):
        NowViewConfig.model_validate(body)


class _Worker:
    def describe(self):
        return {
            "state": "running",
            "topics": ["external"],
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


class _System:
    configured = False

    def describe(self):
        return {"company": "company1", "url": None, "key": False}

    def reachable(self):
        return False


@pytest.fixture
def client(settings: Settings, monkeypatch) -> TestClient:
    monkeypatch.setenv("NOWVIEW_ADMIN_KEY", ADMIN_KEY)
    app = FastAPI()
    app.include_router(
        build_router(settings, _Worker(), _Center(), _Poller(), {"company1": _System()})
    )
    return TestClient(app)


def test_public_companies_show_no_registration(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("COMPANY_COMPANY1_SITE_URL", "http://site.example/")
    response = client.get("/companies")
    body = response.json()
    assert body == [
        {
            "id": "company1",
            "name": "가상 자동차 부품사",
            "description": body[0]["description"],
            "scenes": [1, 2, 3, 4, 5, 6, 7],
            # 회사 사이트는 공개 웹이다 — 회사 시스템 주소와 다르다
            "siteUrl": "http://site.example",
        }
    ]
    assert "external" not in response.text  # 토픽·BPM 프로세스 id가 없다
    assert client.get("/worker").status_code == 404


def test_admin_api_needs_the_key(client: TestClient, monkeypatch) -> None:
    assert client.get("/admin/status").status_code == 401
    assert client.get("/admin/status", headers={"x-admin-key": "wrong"}).status_code == 401
    ok = client.get("/admin/status", headers={"x-admin-key": ADMIN_KEY}).json()
    assert ok["consumer"]["state"] == "running" and ok["restartRequired"] is False
    monkeypatch.delenv("NOWVIEW_ADMIN_KEY")
    assert client.get("/admin/config", headers={"x-admin-key": ADMIN_KEY}).status_code == 503


def test_admin_edits_config(client: TestClient, settings: Settings) -> None:
    headers = {"x-admin-key": ADMIN_KEY}
    view = client.get("/admin/config", headers=headers).json()
    assert view["extension"]["id"] == "external"
    assert "assess_supply_risk" in view["extension"]["operations"]
    config = view["config"]
    config["processes"].append(
        {"bpm_process_id": "company1.sc01-v2", "company": "company1", "scene": 1}
    )
    saved = client.put("/admin/config", json=config, headers=headers).json()
    assert saved["restartRequired"] is False
    assert settings.scene_of("company1.sc01-v2") == 1  # 일꾼 매핑에 바로 쓰인다

    config["topics"] = ["external", "nowview-sc02"]
    assert client.put("/admin/config", json=config, headers=headers).json()["restartRequired"]

    config["processes"].append({"bpm_process_id": "x", "company": "nope", "scene": 1})
    bad = client.put("/admin/config", json=config, headers=headers)
    assert bad.status_code == 422
    assert "없는 회사" in " ".join(bad.json()["detail"]["reasons"])
    config["processes"].pop()
    config["companies"].append({"id": "other", "name": "다른 회사"})
    assert client.put("/admin/config", json=config, headers=headers).status_code == 422


def test_worker_routes_by_the_sending_bpm_process(settings: Settings) -> None:
    from chaeksas.contracts.service_app import OpRequest
    from chaeksas.service_kit.app import OpError

    scenes = {n: f"scene-{n}" for n in range(1, 8)}
    resolve = routed_by(settings.scene_of, scenes)

    def request(bpm: str) -> OpRequest:
        return OpRequest.model_validate(
            {
                "schema": 1,
                "mode": "deterministic",
                "run_id": "run_x",
                "node_id": "n",
                "node_instance": 1,
                "attempt": 1,
                "caller": {"type": "server_runner", "bpm_process_id": bpm},
            }
        )

    assert resolve(request("company1.sc01")) == "scene-1"
    assert resolve(request("company1.sc05")) == "scene-5"
    with pytest.raises(OpError) as missing:
        resolve(request("someone.else"))
    assert missing.value.code == "not_found" and "관리자" in missing.value.message


def test_bpmn_copies_match_company1() -> None:
    """
    엔진의 BPMN은 사본이다 — 원본은 Company1 리포의 `bpm/`(가상 자동차 부품사의 업무 정의). 옆에
    Company1 리포가 있으면(`COMPANY1_DIR`, 기본 `../Company1`) 사본이 원본과 같은지 본다. 다르면
    `scripts/sync-bpm.sh`로 가져온다.
    """
    import os

    source = Path(os.getenv("COMPANY1_DIR") or ROOT.parent / "Company1") / "bpm" / "company1"
    if not source.is_dir():
        pytest.skip(f"Company1 BPM 원본이 없다: {source}")
    drawings = sorted(source.glob("*/process/*.bpmn"))
    assert drawings, source
    for original in drawings:
        copy = ROOT / "engine" / "processes" / original.name
        assert copy.read_bytes() == original.read_bytes(), f"{copy.name} — scripts/sync-bpm.sh"


def test_scenario_copies_match_company1() -> None:
    """
    엔진의 각본은 사본이다 — 원본은 Company1 리포의 `scenarios/`(회사 사이트의 자동 모드·결재 예시
    값, role-split §5). 옆에 Company1 리포가 있으면 사본이 원본과 같은지 본다. 다르면
    `scripts/sync-scenarios.sh`로 가져온다.
    """
    import os

    source = Path(os.getenv("COMPANY1_DIR") or ROOT.parent / "Company1") / "scenarios"
    if not source.is_dir():
        pytest.skip(f"Company1 각본 원본이 없다: {source}")
    originals = sorted(source.glob("sc0*.json"))
    assert len(originals) == 7, source
    for original in originals:
        copy = ROOT / "engine" / "scenarios" / original.name
        assert copy.read_bytes() == original.read_bytes(), (
            f"{copy.name} — scripts/sync-scenarios.sh"
        )


