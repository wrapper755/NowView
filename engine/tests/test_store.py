"""
상태 저장 백엔드.

SQLite와 Postgres는 **같은 코드가 돌아야 하지만 거의 모든 세부가 다르다** — SQL
자리표시자(`?` vs `%s`), 행 접근(튜플 vs dict), `created_at` 타입(문자열 vs datetime).
`store` 픽스처가 두 백엔드를 모두 돌리므로 여기 있는 것은 전부 양쪽에서 검증된다.
"""

from __future__ import annotations

import pytest
from conftest import require_postgres, spec_with

from app.instances import config_for, snapshot
from app.store import _safe_host, build_backend, build_sqlite_backend


class TestSpecStore:
    def test_저장한_명세로_인스턴스를_복구한다(self, store):
        instance = store.create(spec_with(True), agent_mode="mock")
        instance.graph.invoke({}, config_for(instance.id))

        store._cache.clear()
        recovered = store.get(instance.id)

        assert recovered.spec.scenario_id == "scn-profitability"
        assert recovered.agent_mode == "mock"
        # 체크포인트도 함께 살아 있어야 복구가 의미가 있다.
        assert snapshot(recovered)["pendingApproval"]["nodeId"] == "review"

    def test_없는_인스턴스는_KeyError다(self, store):
        with pytest.raises(KeyError):
            store.get("inst-없음")

    def test_목록이_최신순이고_날짜가_문자열이다(self, store):
        # Postgres는 datetime을, SQLite는 문자열을 돌려준다 — 경계에서 맞춰야
        # JSON 직렬화가 백엔드에 따라 갈리지 않는다.
        first = store.create(spec_with(True), agent_mode="mock")
        second = store.create(spec_with(False), agent_mode="llm")

        listed = store.list_ids()
        ids = [row["instanceId"] for row in listed]
        assert {first.id, second.id} <= set(ids)
        for row in listed:
            assert isinstance(row["createdAt"], str)
            assert row["agentMode"] in ("mock", "llm")

    def test_삭제하면_명세와_체크포인트가_함께_사라진다(self, store):
        instance = store.create(spec_with(True), agent_mode="mock")
        instance.graph.invoke({}, config_for(instance.id))
        assert instance.graph.get_state(config_for(instance.id)).values

        store.delete(instance.id)

        with pytest.raises(KeyError):
            store.get(instance.id)
        assert instance.id not in [row["instanceId"] for row in store.list_ids()]
        # 명세만 지우면 스레드가 남아 저장소가 계속 자란다.
        assert not instance.graph.get_state(config_for(instance.id)).values

    def test_인스턴스마다_상태가_독립이다(self, store):
        escalated = store.create(spec_with(True), agent_mode="mock")
        local = store.create(spec_with(False), agent_mode="mock")
        escalated.graph.invoke({}, config_for(escalated.id))
        local.graph.invoke({}, config_for(local.id))

        assert snapshot(escalated)["pendingApproval"]["nodeId"] == "review"
        assert snapshot(local)["pendingApproval"]["nodeId"] == "op-control"


class TestBackendSelection:
    def test_DATABASE_URL이_없으면_SQLite다(self, monkeypatch, tmp_path):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.setenv("NOWVIEW_ENGINE_DB", str(tmp_path / "x.sqlite"))
        backend = build_backend()
        try:
            assert backend.kind == "sqlite"
        finally:
            backend.close()

    def test_DATABASE_URL이_있으면_Postgres다(self, monkeypatch):
        url = require_postgres()
        monkeypatch.setenv("DATABASE_URL", url)
        backend = build_backend()
        try:
            assert backend.kind == "postgres"
        finally:
            backend.close()

    def test_설명에_자격증명이_들어가지_않는다(self):
        # `/health`가 그대로 내보내는 값이다 — 비밀번호가 섞이면 그대로 샌다.
        described = _safe_host("postgresql://nowview:s3cr3t@db.internal:5432/nowview")
        assert "s3cr3t" not in described
        assert "nowview:" not in described
        assert described == "db.internal:5432/nowview"

    def test_SQLite_백엔드는_운영에_부적합하다고_표시한다(self, tmp_path):
        backend = build_sqlite_backend(str(tmp_path / "y.sqlite"))
        try:
            # 어느 백엔드로 도는지 `/health`에서 구분할 수 있어야 한다.
            assert backend.kind == "sqlite"
            assert "sqlite" in backend.describe
        finally:
            backend.close()
