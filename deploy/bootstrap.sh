#!/usr/bin/env bash
#
# 운영 서버 최초 준비 — Postgres 역할·DB와 /etc/nowview.env를 만든다.
# 원격에서 root로 돈다. scripts/deploy.sh --bootstrap이 불러 준다.
#
# **멱등이다.** 이미 있는 역할·DB는 건드리지 않고, /etc/nowview.env가 있으면
# 덮어쓰지 않는다 — 덮어쓰면 DB 비밀번호가 바뀌어 엔진이 붙지 못한다.
#
# 비밀번호는 이 서버에서 생성해 이 서버에만 남는다. 리포에 들어가지 않는다.
#
# 시스템 작업 키(N6, NOWVIEW_SYSTEM_KEY*)는 더 짓지 않는다 — Center가 NowView를 부르지 않고 엔진의
# C15 일꾼이 일감을 가져간다(engine/app/consumer.py). 예전 파일에 남은 두 줄은 읽는 곳이 없다.
set -euo pipefail

ENV_FILE=/etc/nowview.env
DB_NAME=nowview
DB_USER=nowview
WEB_PORT=${WEB_PORT:-3100}
ENGINE_PORT=${ENGINE_PORT:-8077}

if [[ -f $ENV_FILE ]]; then
  echo "이미 있다: $ENV_FILE — 그대로 둔다 (비밀번호를 바꾸면 엔진이 붙지 못한다)"
  exit 0
fi

# 포트가 이미 쓰이고 있으면 여기서 멈춘다. Chaeksa가 3000·8000을 쓰고 있어
# 겹치면 서비스가 조용히 재시작 루프에 빠진다.
for port in "$WEB_PORT" "$ENGINE_PORT"; do
  if ss -tln | grep -q ":${port} "; then
    echo "포트 ${port}가 이미 쓰이고 있다 — WEB_PORT/ENGINE_PORT를 바꿔서 다시 실행하라" >&2
    exit 1
  fi
done

DB_PASS=$(openssl rand -hex 24)

# 역할이 없을 때만 만든다. psql -tAc로 존재를 먼저 확인한다 —
# CREATE ROLE에는 IF NOT EXISTS가 없다.
if [[ -z $(su - postgres -c "psql -tAc \"select 1 from pg_roles where rolname='${DB_USER}'\"") ]]; then
  su - postgres -c "psql -q -c \"create role ${DB_USER} login password '${DB_PASS}'\""
  echo "역할 생성: ${DB_USER}"
else
  # 역할이 이미 있는데 env 파일이 없다 — 비밀번호를 알 수 없으므로 새로 정한다.
  su - postgres -c "psql -q -c \"alter role ${DB_USER} password '${DB_PASS}'\""
  echo "역할이 이미 있어 비밀번호만 다시 정했다: ${DB_USER}"
fi

if [[ -z $(su - postgres -c "psql -tAc \"select 1 from pg_database where datname='${DB_NAME}'\"") ]]; then
  su - postgres -c "createdb -O ${DB_USER} ${DB_NAME}"
  echo "DB 생성: ${DB_NAME}"
fi

# 엔진이 기동 시 스스로 테이블을 만든다(app/sc01/store.py의 CREATE TABLE IF NOT EXISTS).
# 그래서 스키마 마이그레이션 단계가 따로 없고, public에 만들 권한만 있으면 된다.
su - postgres -c "psql -q -d ${DB_NAME} -c \"grant all on schema public to ${DB_USER}\""

umask 077
{
  echo "# NowView 운영 환경 — deploy/bootstrap.sh가 만들었다. 리포에 넣지 않는다."
  echo "DATABASE_URL=postgresql://${DB_USER}:${DB_PASS}@localhost:5432/${DB_NAME}"
  echo "WEB_PORT=${WEB_PORT}"
  echo "ENGINE_PORT=${ENGINE_PORT}"
  # 웹(Next의 BFF)이 엔진을 부르는 주소. 엔진은 localhost에만 바인딩한다.
  echo "ENGINE_URL=http://127.0.0.1:${ENGINE_PORT}"
  # ollama는 이 서버에 이미 돌고 있다. NOWVIEW_AGENT_MODE=llm일 때만 쓴다(기본 mock, CLAUDE.md 4.5).
  echo "OLLAMA_URL=http://127.0.0.1:11434"
  echo "OLLAMA_MODEL=kimi-k3:cloud"
} > "$ENV_FILE"
chmod 600 "$ENV_FILE"

echo "작성: $ENV_FILE (0600, root만)"
