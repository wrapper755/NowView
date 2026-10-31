"""
NowView 설정 — 회사 · 회사 시스템 연결 · BPM 프로세스 매핑 · 일꾼 토픽(`docs/worker-interfaces.md`
§0.1).

NowView는 BPM 패키지와 함께 배포되는 **고정 프로그램**이다. 무엇을 하는지(작업 목록·화면)는
코드이고, 어느 회사의 어느 BPM 프로세스를 맡는지는 **설정**이다. 설정은 엔진 DB에 두고 **관리자
모드에서만 고친다**(`/admin`) — 공개 화면·공개 API에는 내지 않는다. 비밀(회사 시스템 키·Center 키)은
설정에 두지 않고 환경 파일에만 둔다.

* **회사는 BPM 프로세스가 정한다.** 일꾼은 일감의 보낸 BPM 프로세스 id(`caller.bpm_process_id`)로
  `processes`를 찾아 그 회사·업무(장면)의 처리기로 간다. 매핑에 없는 BPM 프로세스의 일감은
  `not_found`로 거절한다.
* **처음 뜰 때 설정이 없으면 기본값을 적는다**(`default_config`) — 가상 자동차 부품사 하나. 회사
  시스템 주소의 기본은 환경의 `COMPANY_AUTOPARTS_URL`이다(옛 설정 호환).
* **토픽을 바꾸면 엔진을 다시 띄워야 한다** — 일꾼이 들이기 때 토픽을 Center에 알린다. 승인된 뒤의
  토픽 변경은 Center 쪽 승인도 다시 필요하다.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator

#: NowView가 아는 업무(장면) — 화면·처리기가 코드에 있는 것만 매핑할 수 있다.
SCENES = (1, 2, 3, 4, 5, 6)
#: NowView 고정 확장 — 판마다 하나(§0.1). 옮기기 전 장면은 예전 확장(`nowview-scN`)을 그대로 쓴다.
FIXED_TOPIC = "nowview"


class CompanyConfig(BaseModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9-]{1,31}$")
    name: str = Field(min_length=1, max_length=60)
    description: str = Field(default="", max_length=200)
    #: 회사 시스템 주소 — 키는 환경 `COMPANY_{ID}_KEY`에만 있다.
    system_url: str | None = None


class ProcessMapping(BaseModel):
    """Center의 BPM 프로세스 하나 → NowView의 회사·업무."""

    bpm_process_id: str = Field(min_length=1, max_length=120)
    company: str
    scene: int


class NowViewConfig(BaseModel):
    companies: list[CompanyConfig]
    processes: list[ProcessMapping]
    topics: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def _consistent(self) -> NowViewConfig:
        ids = [c.id for c in self.companies]
        if len(ids) != len(set(ids)):
            raise ValueError("회사 id가 겹친다")
        bpm = [p.bpm_process_id for p in self.processes]
        if len(bpm) != len(set(bpm)):
            raise ValueError("같은 BPM 프로세스를 두 번 매핑했다")
        for p in self.processes:
            if p.company not in ids:
                raise ValueError(f"없는 회사로 매핑했다: {p.bpm_process_id} → {p.company}")
            if p.scene not in SCENES:
                raise ValueError(f"NowView에 없는 업무다: {p.bpm_process_id} → {p.scene}")
        if len(self.topics) != len(set(self.topics)):
            raise ValueError("토픽이 겹친다")
        return self

    def company(self, company_id: str) -> CompanyConfig | None:
        return next((c for c in self.companies if c.id == company_id), None)

    def mapping(self, bpm_process_id: str | None) -> ProcessMapping | None:
        return next((p for p in self.processes if p.bpm_process_id == bpm_process_id), None)


def default_config() -> NowViewConfig:
    return NowViewConfig(
        companies=[
            CompanyConfig(
                id="autoparts",
                name="가상 자동차 부품사",
                description=(
                    "매출 약 1조원 · 현대·기아 주요 고객 · A제품 울산공장 a~e 모델 — "
                    "2027년 시나리오 1"
                ),
                system_url=os.getenv("COMPANY_AUTOPARTS_URL") or None,
            )
        ],
        processes=[
            ProcessMapping(bpm_process_id="autoparts.sc01", company="autoparts", scene=1),
            ProcessMapping(bpm_process_id="autoparts.sc01-intake", company="autoparts", scene=1),
            *(
                ProcessMapping(bpm_process_id=f"nowview.sc0{n}", company="autoparts", scene=n)
                for n in (2, 3, 4, 5, 6)
            ),
        ],
        topics=[FIXED_TOPIC, *(f"nowview-sc0{n}" for n in (2, 3, 4, 5, 6))],
    )


class ConfigStore:
    """설정 한 벌 — 엔진 백엔드(SQLite·Postgres)의 `nowview_config` 테이블 한 행."""

    def __init__(self, backend: Any) -> None:
        self.backend = backend
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection | None = None
        if backend.kind == "postgres":
            with backend.pool.connection() as conn:
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS nowview_config "
                    "(id TEXT PRIMARY KEY, body TEXT NOT NULL, updated_at TEXT NOT NULL)"
                )
        else:
            self._conn = sqlite3.connect(backend.sqlite_path, check_same_thread=False)
            with self._lock:
                self._conn.execute(
                    "CREATE TABLE IF NOT EXISTS nowview_config "
                    "(id TEXT PRIMARY KEY, body TEXT NOT NULL, updated_at TEXT NOT NULL)"
                )
                self._conn.commit()

    def _read(self) -> tuple[str, str] | None:
        if self._conn is None:
            with self.backend.pool.connection() as conn:
                row = conn.execute(
                    "SELECT body, updated_at FROM nowview_config WHERE id = 'main'"
                ).fetchone()
            return (row["body"], row["updated_at"]) if row else None
        with self._lock:
            row = self._conn.execute(
                "SELECT body, updated_at FROM nowview_config WHERE id = 'main'"
            ).fetchone()
        return (row[0], row[1]) if row else None

    def _write(self, body: str, at: str) -> None:
        sql = (
            "INSERT INTO nowview_config (id, body, updated_at) VALUES ('main', {p}, {p}) "
            "ON CONFLICT (id) DO UPDATE SET body = excluded.body, updated_at = excluded.updated_at"
        )
        if self._conn is None:
            with self.backend.pool.connection() as conn:
                conn.execute(sql.format(p="%s"), (body, at))
            return
        with self._lock:
            self._conn.execute(sql.format(p="?"), (body, at))
            self._conn.commit()

    def load(self) -> tuple[NowViewConfig, str | None]:
        """(설정, 마지막으로 고친 시각). 없으면 기본값을 적고 그것을 돌려준다."""
        found = self._read()
        if found is None:
            config = default_config()
            return config, self.save(config)
        return NowViewConfig.model_validate(json.loads(found[0])), found[1]

    def save(self, config: NowViewConfig) -> str:
        at = datetime.now(UTC).isoformat(timespec="seconds")
        self._write(json.dumps(config.model_dump(), ensure_ascii=False), at)
        return at
