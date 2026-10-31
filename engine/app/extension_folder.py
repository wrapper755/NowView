"""
Center 확장 폴더에 둘 파일을 짓는다(Chaeksas ADR-0121 — 기본 확장과 승인 없는 일꾼).

배포는 이 파일들을 Center의 확장 폴더(`CHK_CENTER__EXTENSIONS_DIR`, compose는
`deploy/extensions/`)에 복사하고 Center를 다시 띄운다. Center는 뜰 때 읽어 들인다 — 콘솔 등록·
요청 코드 승인이 없다.

* `<id>.extension.json` — 리포 `chaeksas/`의 확장 정의 그대로(기본 확장 `external`과 옮기기 전
  장면의 `nowview-sc02`~`sc06`). 서명은 Center가 한다.
* `nowview.consumer.json` — 승인 없는 일꾼(C15 `FolderConsumer`): 이름·토픽·토큰 해시. 토픽은
  NowView 설정(엔진 DB)의 일꾼 토픽이고, 토큰은 엔진 환경의 `NOWVIEW_CONSUMER_TOKEN`이다.
  **원문은 쓰지 않는다** — Center는 해시만 안다.

```bash
cd engine && uv run --env-file .env.local python -m app.extension_folder <확장 폴더>
cd engine && uv run python -m app.extension_folder --new-token   # 새 토큰 원문 하나를 찍는다
```
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import shutil
import sys
from pathlib import Path

from .config import ConfigStore
from .consumer import extensions_dir
from .store import build_backend

#: 일꾼 파일 이름(= Center가 아는 일꾼 자리 `folder:nowview`).
CONSUMER_FILE = "nowview.consumer.json"
CONSUMER_NAME = "NowView 엔진"


def new_token() -> str:
    """C7 키 모양을 따른 원문 — Center는 모양을 보지 않고 해시만 맞춘다."""
    return "chk_ctr_" + secrets.token_urlsafe(30)[:40]


def consumer_file(token: str, topics: list[str]) -> dict:
    return {
        "name": CONSUMER_NAME,
        "topics": topics,
        "token_sha256": hashlib.sha256(token.encode("utf-8")).hexdigest(),
    }


def write_folder(target: Path, token: str, topics: list[str], source: Path) -> list[Path]:
    """확장 정의를 복사하고 일꾼 파일을 짓는다. 쓴 파일 목록."""
    target.mkdir(parents=True, exist_ok=True)
    written = []
    for definition in sorted(source.glob("*.extension.json")):
        shutil.copyfile(definition, target / definition.name)
        written.append(target / definition.name)
    body = json.dumps(consumer_file(token, topics), ensure_ascii=False, indent=2) + "\n"
    (target / CONSUMER_FILE).write_text(body, encoding="utf-8")
    written.append(target / CONSUMER_FILE)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Center 확장 폴더 파일을 짓는다 (ADR-0121)")
    parser.add_argument("target", nargs="?", help="Center 확장 폴더")
    parser.add_argument("--new-token", action="store_true", help="새 일꾼 토큰 원문을 찍고 끝낸다")
    args = parser.parse_args(argv)
    if args.new_token:
        print(new_token())
        return 0
    if not args.target:
        parser.error("확장 폴더를 적는다")
    token = os.getenv("NOWVIEW_CONSUMER_TOKEN") or ""
    if not token:
        print(
            "NOWVIEW_CONSUMER_TOKEN이 없다 — `--new-token`으로 지어 엔진 환경에 두고 다시 한다",
            file=sys.stderr,
        )
        return 2
    config, _ = ConfigStore(build_backend()).load()
    for path in write_folder(Path(args.target), token, list(config.topics), extensions_dir()):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
