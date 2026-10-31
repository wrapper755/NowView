"""
NowView가 Center에 쓰는 키 셋을 짓고, Center 폴더에 둘 해시 파일을 쓴다
(Chaeksas ADR-0122 — 폴더로 들인다).

NowView는 Chaeksas와 함께 설치된다. 그래서 키도 설치가 짓는다 — Center를 띄운 뒤
콘솔에서 발급받아 손으로 옮겨 적지 않는다(2026-11-01 사용자 결정). 키는 셋이다:

* `worker` — C15 일꾼(일감 가져가기·끝내기, `app/consumer.py`).
* `integration` — 연동용(실행 기동·메시지·진행 읽기, `app/sc01/center.py`).
* `relay` — 대리 답용(결재 읽기·답).

**원문은 엔진만 안다** — 보관 파일(`engine/.consumer/keys.json`, gitignore, 0600)에
두고 엔진이 뜰 때 읽는다(`center_key`). 같은 이름의 환경 변수
(`WORKER_CONSUMER_TOKEN`·`CHAEKSAS_INTEGRATION_KEY`·`CHAEKSAS_RELAY_KEY`)가 있으면
그것이 이긴다. Center 폴더(`CHK_CENTER__CONSUMERS_DIR`)에는 **해시만** 간다:

* `worker.consumer.json` — C15 `FolderConsumer`: 이름·토픽(NowView 설정의 일꾼 토픽)·
  토큰 해시.
* `nowview-integration.key.json` · `nowview-relay.key.json` — 이름·키 종류·토큰 해시.

Center는 뜰 때 이 파일들을 읽어 키를 들인다 — 콘솔 발급·승인이 없다. 확장 정의는
여기 없다 — 일꾼이 뜰 때 `PUT /consumers/self/extension`으로 올린다.

```bash
cd engine && uv run python -m app.worker_file <Center 폴더>            # 없는 키만 짓는다
cd engine && uv run python -m app.worker_file <Center 폴더> --rotate   # 셋 다 새로
```

파일을 쓴 뒤 Center와 엔진을 다시 띄운다(Center는 뜰 때만 폴더를 읽는다).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
from pathlib import Path

from .config import ConfigStore
from .store import build_backend

#: 일꾼 이름 — 파일 이름이 Center의 일꾼 자리(`folder:worker`)다.
WORKER_NAME = "worker"
WORKER_FILE = f"{WORKER_NAME}.consumer.json"

#: 키 종류 → 그 원문을 덮는 환경 변수.
KEY_ENV = {
    "worker": "WORKER_CONSUMER_TOKEN",
    "integration": "CHAEKSAS_INTEGRATION_KEY",
    "relay": "CHAEKSAS_RELAY_KEY",
}
#: Center API 키 파일의 이름 머리 — `<머리>-<종류>.key.json`.
KEY_FILE_PREFIX = "nowview"

DEFAULT_DIR = Path(__file__).resolve().parents[1] / ".consumer"


def keys_path() -> Path:
    return Path(os.getenv("NOWVIEW_CONSUMER_DIR") or DEFAULT_DIR) / "keys.json"


def new_token() -> str:
    """Center API 키 모양(`chk_ctr_` + 40자) — Center는 해시만 맞춘다."""
    return "chk_ctr_" + secrets.token_urlsafe(48)[:40]


def _sha256(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def load_keys(path: Path | None = None) -> dict[str, str]:
    path = path or keys_path()
    try:
        raw = json.loads(path.read_text("utf-8"))
    except FileNotFoundError:
        return {}
    return {k: v for k, v in raw.items() if k in KEY_ENV and isinstance(v, str) and v}


def center_key(kind: str) -> str | None:
    """엔진이 쓰는 키 원문 — 환경 변수가 이기고, 없으면 보관 파일."""
    return os.getenv(KEY_ENV[kind]) or load_keys().get(kind) or None


def ensure_keys(path: Path | None = None, *, rotate: bool = False) -> dict[str, str]:
    """없는 키만 짓는다(`rotate`면 셋 다). 보관 파일은 주인만 읽는다."""
    path = path or keys_path()
    keys = {} if rotate else load_keys(path)
    for kind in KEY_ENV:
        keys.setdefault(kind, new_token())
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(keys, indent=2) + "\n", encoding="utf-8")
    tmp.chmod(0o600)
    tmp.replace(path)
    return keys


def worker_file(token: str, topics: list[str]) -> dict:
    return {"name": WORKER_NAME, "topics": topics, "token_sha256": _sha256(token)}


def key_file(kind: str, token: str) -> dict:
    name = f"{KEY_FILE_PREFIX}-{kind}"
    return {"name": name, "type": kind, "token_sha256": _sha256(token)}


def _write(path: Path, body: dict) -> Path:
    path.write_text(json.dumps(body, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def write_folder(target: Path, keys: dict[str, str], topics: list[str]) -> list[Path]:
    """Center 폴더에 해시 파일 셋을 쓴다 — 원문은 쓰지 않는다."""
    target.mkdir(parents=True, exist_ok=True)
    written = [_write(target / WORKER_FILE, worker_file(keys["worker"], topics))]
    for kind in ("integration", "relay"):
        path = target / f"{KEY_FILE_PREFIX}-{kind}.key.json"
        written.append(_write(path, key_file(kind, keys[kind])))
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="NowView의 Center 키를 짓고 폴더 파일을 쓴다")
    parser.add_argument("target", help="Center 폴더 (CHK_CENTER__CONSUMERS_DIR)")
    parser.add_argument("--rotate", action="store_true", help="키 셋을 모두 새로 짓는다")
    args = parser.parse_args(argv)
    keys = ensure_keys(rotate=args.rotate)
    # 환경 변수가 덮는 키는 그 값으로 해시를 쓴다 — 엔진이 실제로 쓰는 키와 같아야 한다
    keys = {kind: os.getenv(KEY_ENV[kind]) or value for kind, value in keys.items()}
    config, _ = ConfigStore(build_backend()).load()
    for path in write_folder(Path(args.target), keys, list(config.topics)):
        print(path)
    print("Center와 엔진을 다시 띄운다 — Center는 뜰 때만 폴더를 읽는다")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
