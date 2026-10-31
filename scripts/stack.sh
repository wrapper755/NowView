#!/usr/bin/env bash
#
# 로컬 개발 프로세스 제어 — 웹(:3000) · 엔진(:8077) · 회사 시스템 시뮬레이터(:8091) · DB(docker).
#
# 왜 스크립트로 두는가. 수동으로 띄우고 죽이다가 두 번 망가뜨렸다:
#
#   1. **중복 기동.** 포트가 이미 잡혀 있는데 또 띄우니 새 프로세스가 죽고, 그 과정에서
#      기존 프로세스도 연결이 쌓인 채(Recv-Q) 먹통이 됐다. → `start`는 멱등이다.
#   2. **`pkill -f "uvicorn app.main:app"`가 자기 셸의 명령줄까지 매치**해 스스로를
#      죽였다(exit 143/144). → 종료는 **리스닝 포트로 PID를 찾는다.**
#
# 또 하나: 엔진을 `--reload` 없이 띄워 두고 코드를 고쳐 "왜 반영이 안 되나"를 두 번
# 헤맸다. → `start engine`은 기본이 `--reload`다.
#
# 사용법
#   scripts/stack.sh start   [all|web|engine|sim|db]
#   scripts/stack.sh stop    [all|web|engine|sim|db]
#   scripts/stack.sh restart [all|web|engine|sim|db]
#   scripts/stack.sh status
#   scripts/stack.sh logs    <web|engine|sim> [줄수]
#
# 대상을 생략하면 `all`이다(db는 제외 — 아래 참조).

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="$ROOT/.dev"
mkdir -p "$RUN_DIR"

WEB_PORT="${WEB_PORT:-3000}"
ENGINE_PORT="${ENGINE_PORT:-8077}"
SIM_PORT="${SIM_PORT:-8091}"

# 종료를 기다리는 한계. 넘으면 강제 종료한다.
STOP_TIMEOUT=15
# 기동을 기다리는 한계. Next 첫 컴파일이 느릴 수 있어 넉넉히 둔다.
START_TIMEOUT=90

# ----------------------------------------------------------------- 유틸

c_ok()   { printf '\033[32m%s\033[0m' "$1"; }
c_bad()  { printf '\033[31m%s\033[0m' "$1"; }
c_dim()  { printf '\033[2m%s\033[0m' "$1"; }

die() { printf '%s %s\n' "$(c_bad '✘')" "$*" >&2; exit 1; }

port_pid() {
  # 그 포트를 **리스닝하는** 프로세스. 패턴 매칭을 쓰지 않는 이유는 위 주석 참조.
  ss -lptnH "sport = :$1" 2>/dev/null | grep -oP 'pid=\K[0-9]+' | head -1
}

port_open()   { [ -n "$(port_pid "$1")" ]; }

# `wait_until 15 ! port_open 8077`처럼 쓸 수 없다 — `!`는 예약어라서 소스 텍스트에서만
# 부정으로 동작하고, 확장된 인자로 넘기면 `!`라는 **명령**을 찾는다. 그러면 대기가 절대
# 성공하지 않아 매번 KILL로 넘어가고, 포트가 이미 비었는데도 실패로 보고했다.
port_closed() { ! port_open "$1"; }

pidfile() { printf '%s/%s.pid' "$RUN_DIR" "$1"; }
logfile() { printf '%s/%s.log' "$RUN_DIR" "$1"; }

owned_pgid() {
  # 우리가 띄운 프로세스 **그룹** id.
  local file; file="$(pidfile "$1")"
  [ -f "$file" ] || return 1
  local pgid; pgid="$(cat "$file" 2>/dev/null)"
  [ -n "$pgid" ] && printf '%s' "$pgid"
}

pgid_of() { ps -o pgid= -p "$1" 2>/dev/null | tr -d ' '; }

we_own() {
  # we_own <이름> <리스닝 pid>
  #
  # **PID로 비교하면 안 된다.** `setsid`로 띄우면 기록되는 것은 래퍼(`uv run`)의 PID인데
  # 포트를 쥐는 것은 그 아래 uvicorn 워커다 — 두 값이 다르니 우리가 띄운 것도 "외부"로
  # 오판한다(실제로 그랬다). setsid가 만든 프로세스 그룹은 서브트리가 공유하므로
  # **그룹으로 비교한다.** `kill -- -$pgid`가 통하는 근거도 같다.
  local recorded; recorded="$(owned_pgid "$1")" || return 1
  [ -n "$recorded" ] && [ "$(pgid_of "$2")" = "$recorded" ]
}

wait_until() {
  # wait_until <초> <명령...> — 명령이 성공하면 0, 시간 초과면 1.
  local limit="$1"; shift
  local start; start=$(date +%s)
  until "$@" >/dev/null 2>&1; do
    [ $(( $(date +%s) - start )) -ge "$limit" ] && return 1
    sleep 1
  done
  return 0
}

health_ok() { curl -sf --max-time 2 "http://localhost:$ENGINE_PORT/health" >/dev/null 2>&1; }
sim_ok()    { curl -sf --max-time 2 "http://localhost:$SIM_PORT/health" >/dev/null 2>&1; }
web_ok()    { curl -sf --max-time 3 -o /dev/null "http://localhost:$WEB_PORT/" 2>/dev/null; }

# ----------------------------------------------------------------- 시작

start_proc() {
  # start_proc <이름> <포트> <준비확인함수> <명령...>
  local name="$1" port="$2" ready="$3"; shift 3

  if port_open "$port"; then
    local pid
    pid="$(port_pid "$port")"
    if we_own "$name" "$pid"; then
      printf '%s %-7s 이미 돌고 있다 (pid %s)\n' "$(c_ok '·')" "$name" "$pid"
    else
      # **다른 누군가가 그 포트를 쓰고 있다.** 여기서 또 띄우면 둘 다 망가진다 —
      # 실제로 그렇게 프로세스를 먹통으로 만들었다.
      printf '%s %-7s 포트 %s를 우리가 띄우지 않은 프로세스(pid %s)가 쓰고 있다 — 건드리지 않는다.\n' \
        "$(c_bad '!')" "$name" "$port" "$pid"
      printf '  %s\n' "$(c_dim "IDE 프리뷰나 다른 터미널일 수 있다. 정말 내리려면: scripts/stack.sh stop $name --force")"
      return 1
    fi
    return 0
  fi

  printf '%s %-7s 시작 …' "$(c_dim '·')" "$name"
  # setsid로 떼어 놓는다 — 이 셸이 끝나도 살아 있어야 한다.
  setsid nohup "$@" >"$(logfile "$name")" 2>&1 &
  local pid=$!
  echo "$pid" >"$(pidfile "$name")"

  if wait_until "$START_TIMEOUT" "$ready"; then
    printf '\r%s %-7s 시작됨 (pid %s, :%s)      \n' "$(c_ok '✔')" "$name" "$(port_pid "$port")" "$port"
  else
    printf '\r%s %-7s %s초 안에 응답하지 않았다 — 로그를 보라: scripts/stack.sh logs %s\n' \
      "$(c_bad '✘')" "$name" "$START_TIMEOUT" "$name"
    return 1
  fi
}

start_web() {
  start_proc web "$WEB_PORT" web_ok \
    env -C "$ROOT" npm run dev -- --port "$WEB_PORT"
}

start_engine() {
  # `--reload` 없이 띄우면 코드를 고쳐도 반영되지 않는다 — 두 번 헤맸다.
  # DATABASE_URL이 있으면 엔진이 Postgres + LISTEN/NOTIFY로 뜬다(engine/README.md).
  # `--timeout-graceful-shutdown`: 브라우저가 SSE로 붙어 있으면 uvicorn이 그 연결이 닫히기를
  # 기다리며 **reload가 끝나지 않는다** — 엔진이 응답 없이 멈춘 것처럼 보였고 TERM에도 안 죽었다.
  # 운영 유닛과 같은 이유다(CLAUDE.md 5.4).
  # `engine/.env.local`(gitignore)이 있으면 읽는다 — Center 키·회사 시스템 키처럼 리포에 넣지 않을 값.
  local env_file=()
  [[ -f $ROOT/engine/.env.local ]] && env_file=(--env-file .env.local)
  start_proc engine "$ENGINE_PORT" health_ok \
    env -C "$ROOT/engine" uv run uvicorn app.main:app \
      --port "$ENGINE_PORT" --reload --timeout-graceful-shutdown 3 --log-level warning \
      "${env_file[@]}"
}

start_sim() {
  # 가상 자동차 부품사의 회사 시스템(company-sim/) — 엔진이 회사 자료·원천을 여기서 읽는다
  # (docs/worker-interfaces.md). 키는 `company-sim/.env.local`(gitignore)의 AUTOPARTS_SIM_KEY —
  # 엔진 `engine/.env.local`의 COMPANY_AUTOPARTS_KEY와 같은 값이다. 없으면 기동하지 않는다.
  local env_file=()
  [[ -f $ROOT/company-sim/.env.local ]] && env_file=(--env-file .env.local)
  start_proc sim "$SIM_PORT" sim_ok \
    env -C "$ROOT/company-sim" uv run uvicorn autoparts_sim.main:build_app --factory \
      --port "$SIM_PORT" --reload --log-level warning "${env_file[@]}"
}

start_db() {
  command -v docker >/dev/null 2>&1 || die "docker가 없다"
  printf '%s %-7s 시작 …' "$(c_dim '·')" "db"
  (cd "$ROOT" && docker compose up -d postgres >/dev/null 2>&1) || die "postgres 컨테이너를 띄우지 못했다"
  if wait_until 60 db_ok; then
    printf '\r%s %-7s 준비됨 (:55432)        \n' "$(c_ok '✔')" "db"
  else
    printf '\r%s %-7s pg_isready가 응답하지 않는다\n' "$(c_bad '✘')" "db"
    return 1
  fi
}

db_ok() {
  (cd "$ROOT" && docker compose exec -T postgres pg_isready -U nowview -d nowview) >/dev/null 2>&1
}

# ----------------------------------------------------------------- 중지

stop_proc() {
  # stop_proc <이름> <포트> [--force]
  local name="$1" port="$2" force="${3:-}"

  if ! port_open "$port"; then
    printf '%s %-7s 돌고 있지 않다\n' "$(c_dim '·')" "$name"
    rm -f "$(pidfile "$name")"
    return 0
  fi

  local pid
  pid="$(port_pid "$port")"

  if ! we_own "$name" "$pid" && [ "$force" != "--force" ]; then
    # 우리가 띄운 것이 아니면 함부로 죽이지 않는다.
    printf '%s %-7s pid %s는 우리가 띄운 것이 아니다 — 내리지 않는다 (--force로 강제)\n' \
      "$(c_bad '!')" "$name" "$pid"
    return 1
  fi

  printf '%s %-7s 종료 …' "$(c_dim '·')" "$name"
  # 프로세스 **그룹째** 보낸다 — uvicorn --reload는 reloader와 워커가 따로 있고, Next도
  # 자식을 띄운다. 부모만 죽이면 포트를 쥔 자식이 남는다.
  local group; group="$(owned_pgid "$name" || pgid_of "$pid")"
  kill -TERM -- "-$group" 2>/dev/null || kill -TERM "$pid" 2>/dev/null

  if ! wait_until "$STOP_TIMEOUT" port_closed "$port"; then
    printf '\r%s %-7s TERM에 응답하지 않아 KILL한다\n' "$(c_bad '!')" "$name"
    kill -KILL -- "-$group" 2>/dev/null || kill -KILL "$pid" 2>/dev/null
    wait_until 10 port_closed "$port" || {
      printf '%s %-7s 아직 포트를 쥐고 있다\n' "$(c_bad '✘')" "$name"
      return 1
    }
  fi
  rm -f "$(pidfile "$name")"
  printf '\r%s %-7s 종료됨            \n' "$(c_ok '✔')" "$name"
}

stop_db() {
  (cd "$ROOT" && docker compose stop postgres >/dev/null 2>&1) \
    && printf '%s %-7s 종료됨\n' "$(c_ok '✔')" "db" \
    || printf '%s %-7s 컨테이너가 없다\n' "$(c_dim '·')" "db"
}

# ----------------------------------------------------------------- 상태

status_line() {
  # status_line <이름> <포트> <부가정보>
  local name="$1" port="$2" extra="${3:-}"
  if port_open "$port"; then
    local pid mark
    pid="$(port_pid "$port")"
    mark=$(we_own "$name" "$pid" && echo "이 스크립트" || echo "외부")
    printf '  %s %-7s :%-5s pid %-7s %s %s\n' "$(c_ok '●')" "$name" "$port" "$pid" "$(c_dim "$mark")" "$extra"
  else
    printf '  %s %-7s :%-5s %s\n' "$(c_bad '○')" "$name" "$port" "$(c_dim '내려가 있음')"
  fi
}

cmd_status() {
  printf '\n'
  local engine_extra=""
  if health_ok; then
    # f-string 안에서 따옴표를 이스케이프하면 셸을 거치며 깨진다 — %% 포맷으로 둔다.
    engine_extra="$(curl -s --max-time 3 "http://localhost:$ENGINE_PORT/health" | python3 -c '
import sys, json
d = json.load(sys.stdin)
n = d.get("notify", {})
print("storage=%s notify=%s listening=%s 구독자=%s" % (
    d["storage"]["kind"], n.get("kind"), n.get("listening"), d.get("eventSubscribers")))
' 2>/dev/null)"
  fi
  status_line web "$WEB_PORT"
  status_line engine "$ENGINE_PORT" "$(c_dim "$engine_extra")"
  status_line sim "$SIM_PORT"

  if db_ok; then
    printf '  %s %-7s :%-5s %s\n' "$(c_ok '●')" "db" "55432" "$(c_dim 'docker compose')"
  else
    printf '  %s %-7s :%-5s %s\n' "$(c_bad '○')" "db" "55432" "$(c_dim '내려가 있음')"
  fi
  printf '\n  %s\n\n' "$(c_dim "로그: scripts/stack.sh logs web|engine|sim")"
}

cmd_logs() {
  local name="${1:-}" lines="${2:-60}"
  case "$name" in
    web|engine|sim) ;;
    *) die "logs <web|engine|sim> [줄수]" ;;
  esac
  local file; file="$(logfile "$name")"
  [ -f "$file" ] || die "$name 로그가 없다 (이 스크립트로 띄운 적이 없다)"
  tail -n "$lines" "$file"
}

# ----------------------------------------------------------------- 진입점

targets_for() {
  case "${1:-all}" in
    all)    echo "sim engine web" ;;   # 회사 시스템 → 엔진 → 웹 — 앞의 것을 뒤의 것이 부른다
    web)    echo "web" ;;
    engine) echo "engine" ;;
    sim)    echo "sim" ;;
    db)     echo "db" ;;
    *)      die "대상은 all|web|engine|sim|db 중 하나다 (받은 값: $1)" ;;
  esac
}

cmd_start() {
  for t in $(targets_for "${1:-all}"); do
    case "$t" in
      web) start_web ;;
      engine) start_engine ;;
      sim) start_sim ;;
      db) start_db ;;
    esac
  done
}

cmd_stop() {
  local target="${1:-all}" force="${2:-}"
  # 시작과 반대 순서로 내린다 — 웹이 엔진을 부르는 중에 엔진이 사라지면 오류가 찍힌다.
  local list; list="$(targets_for "$target")"
  local reversed=""
  for t in $list; do reversed="$t $reversed"; done
  for t in $reversed; do
    case "$t" in
      web) stop_proc web "$WEB_PORT" "$force" ;;
      engine) stop_proc engine "$ENGINE_PORT" "$force" ;;
      sim) stop_proc sim "$SIM_PORT" "$force" ;;
      db) stop_db ;;
    esac
  done
}

main() {
  local action="${1:-status}"; shift || true
  case "$action" in
    start)   cmd_start "${1:-all}" ;;
    stop)    cmd_stop "${1:-all}" "${2:-}" ;;
    restart) cmd_stop "${1:-all}" "${2:-}"; cmd_start "${1:-all}" ;;
    status)  cmd_status ;;
    logs)    cmd_logs "${1:-}" "${2:-60}" ;;
    -h|--help|help)
      sed -n '3,30p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      ;;
    *) die "알 수 없는 명령: $action (start|stop|restart|status|logs)" ;;
  esac
}

main "$@"
