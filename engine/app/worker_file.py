"""
Center 일꾼 폴더에 둘 일꾼 파일을 짓는다(Chaeksas ADR-0121 — 일꾼은 폴더 파일로만 들어온다).

배포는 이 파일을 Center의 일꾼 폴더(`CHK_CENTER__CONSUMERS_DIR`, compose는 Chaeksas
`deploy/consumers/`)에 두고 Center를 다시 띄운다. Center는 뜰 때 읽어 이 일꾼을 처음부터
안다 — 요청 코드·콘솔 승인이 없다.

* `worker.consumer.json` — C15 `FolderConsumer`: 이름 `worker`·토픽·토큰 해시. 토픽은
  NowView 설정(엔진 DB)의 일꾼 토픽이고, 토큰은 엔진 환경의 `WORKER_CONSUMER_TOKEN`이다.
  **원문은 쓰지 않는다** — Center는 해시만 안다.
* 확장 정의는 이 파일에 없다 — 일꾼이 뜰 때 `PUT /consumers/self/extension`으로
  올린다(`app/consumer.py`).

```bash
cd engine && uv run python -m app.worker_file --new-token   # 새 토큰 원문을 찍는다
cd engine && uv run --env-file .env.local python -m app.worker_file <일꾼 폴더>
```
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import sys
from pathlib import Path

from .config import ConfigStore
from .store import build_backend

#: 일꾼 이름 — 파일 이름이 Center의 일꾼 자리(`folder:worker`)다.
WORKER_NAME = "worker"
WORKER_FILE = f"{WORKER_NAME}.consumer.json"


def new_token() -> str:
    """C7 키 모양을 따른 원문 — Center는 모양을 보지 않고 해시만 맞춘다."""
    return "chk_ctr_" + secrets.token_urlsafe(30)[:40]


def worker_file(token: str, topics: list[str]) -> dict:
    return {
        "name": WORKER_NAME,
        "topics": topics,
        "token_sha256": hashlib.sha256(token.encode("utf-8")).hexdigest(),
    }


def write_worker_file(target: Path, token: str, topics: list[str]) -> Path:
    target.mkdir(parents=True, exist_ok=True)
    path = target / WORKER_FILE
    body = json.dumps(worker_file(token, topics), ensure_ascii=False, indent=2) + "\n"
    path.write_text(body, encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Center 일꾼 파일을 짓는다 (ADR-0121)")
    parser.add_argument("target", nargs="?", help="Center 일꾼 폴더")
    parser.add_argument("--new-token", action="store_true", help="새 일꾼 토큰 원문을 찍고 끝낸다")
    args = parser.parse_args(argv)
    if args.new_token:
        print(new_token())
        return 0
    if not args.target:
        parser.error("일꾼 폴더를 적는다")
    token = os.getenv("WORKER_CONSUMER_TOKEN") or ""
    if not token:
        print(
            "WORKER_CONSUMER_TOKEN이 없다 — `--new-token`으로 지어 엔진 환경에 두고 다시 한다",
            file=sys.stderr,
        )
        return 2
    config, _ = ConfigStore(build_backend()).load()
    print(write_worker_file(Path(args.target), token, list(config.topics)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
