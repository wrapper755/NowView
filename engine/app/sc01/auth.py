"""
시스템 작업의 인증(N6) — 바깥 Chaeksas가 서비스 태스크에서 부르는 길에만 건다.

**NowView가 키를 짓고 들고 있다**(Chaeksas R6 답, ADR-0094 §7). Center는 관리자가 넣은 원문을
배포 대상에 나를 뿐이고 검증 API가 없다. 키는 둘이다:

* 운영 키(`NOWVIEW_SYSTEM_KEY`) — 서버 실행기·Bot UI가 받는다 → **Center 실행**
* 시험용 키(`NOWVIEW_SYSTEM_KEY_TEST`) — Studio만 받는다 → **Studio 시험 실행**

그래서 어느 키로 왔는지가 곧 실행 위치다. 템플릿 값(R5, 거절됨)과 달리 부르는 쪽이 지어낼 수
없다 — 데모 실행에 선언한 실행 위치(`bpm.executor`)를 이것으로 검사한다(`domain.link_external_run`).

**키가 하나도 없으면 받지 않는다(503).** 운영계는 인터넷에 열려 있다 — 환경 파일이 빠진 채
올라갔을 때 조용히 열리면 안 된다. 로컬·테스트에서 끄려면 `NOWVIEW_SYSTEM_AUTH=off`를 **명시한다**.
"""

from __future__ import annotations

import hmac
import os
from dataclasses import dataclass
from typing import Any

from app.sc01.domain import DomainError

#: 키 종류 → 그 키를 받는 실행 위치.
KEY_EXECUTOR = {"run": "center", "test": "studio"}


@dataclass(frozen=True)
class SystemAuth:
    run_key: str | None = None
    test_key: str | None = None
    off: bool = False

    @classmethod
    def from_env(cls) -> SystemAuth:
        return cls(
            run_key=os.getenv("NOWVIEW_SYSTEM_KEY") or None,
            test_key=os.getenv("NOWVIEW_SYSTEM_KEY_TEST") or None,
            off=os.getenv("NOWVIEW_SYSTEM_AUTH", "").lower() == "off",
        )

    @property
    def problem(self) -> str | None:
        """받을 수 없는 설정이면 그 사유."""
        if self.off:
            return None
        if not (self.run_key or self.test_key):
            return "시스템 작업 키가 설정되지 않았다 (NOWVIEW_SYSTEM_KEY·NOWVIEW_SYSTEM_KEY_TEST)"
        if self.run_key == self.test_key:
            # 같으면 어느 실행 위치에서 왔는지 가를 수 없다 — 시험용 키가 운영을 열게 된다.
            return "운영 키와 시험용 키가 같다 — 따로 지어야 실행 위치를 가린다"
        if not all(k.isascii() for k in (self.run_key, self.test_key) if k):
            return "시스템 작업 키에 ASCII 밖의 글자가 있다 (HTTP 헤더에 실을 수 없다)"
        return None

    def describe(self) -> dict[str, Any]:
        """`/health`용 — 값은 싣지 않는다. 「꺼 둔 채 운영」을 눈치챌 수 있어야 한다."""
        mode = "off" if self.off else ("unconfigured" if self.problem else "keys")
        return {"mode": mode, "run": bool(self.run_key), "test": bool(self.test_key)}

    def executor_of(self, authorization: str | None) -> str | None:
        """
        `Authorization` 헤더 → 그 키가 가리키는 실행 위치(`center`·`studio`). 꺼 두었으면 `None`
        (실행 위치를 검사하지 않는다). 헤더가 없거나 틀리면 401, 설정이 틀렸으면 503.
        """
        if self.off:
            return None
        if self.problem:
            raise DomainError(self.problem, 503)
        scheme, _, given = (authorization or "").partition(" ")
        if scheme.lower() != "bearer" or not given.strip():
            raise DomainError("시스템 작업에는 Authorization: Bearer 키가 필요하다", 401)
        raw = given.strip().encode("utf-8")
        # 둘 다 비교한다 — 앞에서 맞으면 멈추는 식이면 걸린 시간이 어느 키인지 흘린다.
        hits = {
            kind: hmac.compare_digest(raw, key.encode("ascii"))
            for kind, key in (("run", self.run_key), ("test", self.test_key))
            if key
        }
        for kind, hit in hits.items():
            if hit:
                return KEY_EXECUTOR[kind]
        raise DomainError("시스템 작업 키가 맞지 않는다", 401)
