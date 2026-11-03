"""장면 4~7 기록 시험의 공통 고정물 — 장면 1~N을 같은 메모리 저장소 묶음으로 잇는다."""

from __future__ import annotations

import sqlite3

from app.sc01.process import Sc01Process
from app.sc01.store import SqliteSc01Store
from app.sc02.process import Sc02Process
from app.sc03.process import Sc03Process
from app.sc04.process import Sc04Process
from app.sc05.process import Sc05Process
from app.sc06.process import Sc06Process
from app.sc07.process import Sc07Process

PREFIXES = ("sc01", "sc02", "sc03", "sc04", "sc05", "sc06", "sc07")


def chain(scene: int):
    """장면 `scene`의 프로세스(앞 장면 프로세스를 품는다)."""
    s = [SqliteSc01Store(sqlite3.connect(":memory:", check_same_thread=False), p) for p in PREFIXES]
    p = Sc03Process(s[2], Sc02Process(s[1], Sc01Process(s[0], inline_agent=True)))
    for n, cls in ((4, Sc04Process), (5, Sc05Process), (6, Sc06Process), (7, Sc07Process)):
        if n > scene:
            break
        p = cls(s[n - 1], p)
    return p
