#!/usr/bin/env bash
#
# 운영계 배포 — rsync로 소스를 올리고 서버에서 빌드한 뒤 systemd로 올린다.
#
#   scripts/deploy.sh              # 배포 (rsync → 빌드 → 재시작)
#   scripts/deploy.sh --bootstrap  # 최초 1회: Postgres 역할·DB·/etc/nowview.env까지
#   scripts/deploy.sh --status     # 원격 상태
#   scripts/deploy.sh --logs web|engine [줄수]
#
# **서버에서 빌드한다.** 로컬 `.next`를 올리지 않는다 — 산출물에 로컬 절대경로와
# 플랫폼 의존 바이너리가 섞여 있어 "로컬에서는 되는데 서버에서 죽는" 종류가 된다.
# Chaeksa의 `make web-build`도 서버에서 돈다.
set -euo pipefail

HOST=${NOWVIEW_HOST:-hetzner-server}
REMOTE=${NOWVIEW_REMOTE_DIR:-/root/Workspace/NowView}
LOCAL=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)

# 올리지 않는 것: 서버에서 다시 만드는 것(node_modules·.next·.venv)과
# 서버가 소유한 상태(engine의 sqlite, .env). .git도 올리지 않는다 —
# 배포본은 체크아웃이 아니라 산출물이다.
EXCLUDES=(
  --exclude=.git
  # 다른 세션의 worktree 사본 — 올리면 서버에 소스가 겹으로 쌓인다.
  --exclude=.claude/worktrees
  --exclude=node_modules
  --exclude=.next
  --exclude=engine/.venv
  --exclude='engine/*.sqlite'
  --exclude='engine/*.sqlite-*'
  # C15 일꾼 토큰(engine/app/consumer.py) — 서버가 Center 승인으로 받은 것이다. --delete가 지우면
  # 다시 들이기 승인을 받아야 한다.
  --exclude=engine/.consumer
  --exclude=.env
  --exclude='.env.*'
  --exclude=.dev
  --exclude=__pycache__
  --exclude=.pytest_cache
  --exclude=.ruff_cache
  --exclude=.mypy_cache
  --exclude=coverage
)

say() { printf '\n\033[1m== %s\033[0m\n' "$*"; }

remote() { ssh "$HOST" "$@"; }

case "${1:-deploy}" in
  --status)
    remote 'systemctl status nowview-engine nowview-web --no-pager -n 5' || true
    remote 'ss -tlnp | grep -E ":(3100|8077) " || echo "리스닝 없음"'
    exit 0
    ;;
  --logs)
    unit=${2:-web}
    lines=${3:-80}
    remote "journalctl -u nowview-${unit} -n ${lines} --no-pager"
    exit 0
    ;;
  --bootstrap) DO_BOOTSTRAP=1 ;;
  deploy) DO_BOOTSTRAP=0 ;;
  *) echo "알 수 없는 인자: $1" >&2; exit 2 ;;
esac

say "소스 전송 → ${HOST}:${REMOTE}"
remote "mkdir -p ${REMOTE}"
# --delete로 원격에만 남은 파일을 지운다. 지우지 않으면 삭제한 화면·데이터가
# 서버에 남아 라우트로 계속 잡힌다.
rsync -az --delete "${EXCLUDES[@]}" "${LOCAL}/" "${HOST}:${REMOTE}/"

if [[ $DO_BOOTSTRAP == 1 ]]; then
  say "최초 준비 (Postgres · /etc/nowview.env)"
  remote "bash ${REMOTE}/deploy/bootstrap.sh"
fi

say "엔진 의존성 (uv sync)"
# --locked: uv.lock이 pyproject.toml과 어긋나면 바로 실패한다(CI와 같은 이유).
remote "cd ${REMOTE}/engine && /root/.local/bin/uv sync --locked"

say "웹 의존성·빌드 (npm ci && npm run build)"
# npm ci는 락파일이 package.json과 어긋나면 바로 실패한다.
# build가 TypeScript 검사를 겸하므로 타입 오류도 여기서 잡힌다.
remote "cd ${REMOTE} && npm ci && npm run build"

say "systemd 유닛 설치"
remote "install -m 644 ${REMOTE}/deploy/nowview-engine.service ${REMOTE}/deploy/nowview-web.service /etc/systemd/system/"
remote "systemctl daemon-reload"
remote "systemctl enable nowview-engine nowview-web"

# 엔진 → 웹 순서로 올린다. 웹은 켜지자마자 엔진을 부른다.
say "재시작 (엔진 → 웹)"
remote "systemctl restart nowview-engine"
remote "systemctl restart nowview-web"

say "확인"
# 기동에 시간이 걸린다 — 엔진은 테이블 생성(CREATE TABLE IF NOT EXISTS)을, 웹은 Next 부팅을 한다.
remote 'for _ in $(seq 1 30); do
  curl -sf http://127.0.0.1:8077/health >/dev/null && break
  sleep 1
done
echo "engine /health:"; curl -s http://127.0.0.1:8077/health; echo
for _ in $(seq 1 30); do
  curl -sf -o /dev/null http://127.0.0.1:3100/ && break
  sleep 1
done
# 웹 → BFF → 엔진을 한 번에 지나는 경로로 본다. 예전 `/api/engine`은 LangGraph와 함께 지웠다 —
# 남겨 두었더니 배포가 성공해도 마지막 줄이 404 페이지 HTML을 찍었다.
echo "web → engine (/api/engine/sc01/process):"
curl -s http://127.0.0.1:3100/api/engine/sc01/process | head -c 120; echo
curl -s -o /dev/null -w "web / → %{http_code}\n" http://127.0.0.1:3100/'

# 외부 주소는 cloudflared 터널이 정한다(Cloudflare 대시보드의 라우트).
# 웹은 127.0.0.1에만 바인딩하므로 IP:포트로는 들어갈 수 없다.
say "완료 — ${NOWVIEW_PUBLIC_URL:-https://www.nowview.work}"
