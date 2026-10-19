# NowView BPM 엔진 (FastAPI + Chaeksas BPM)
#
# 빌드 컨텍스트는 `engine/`이다 (docker-compose.yml의 context 참조).

FROM python:3.12-slim AS base

# uv를 공식 이미지에서 가져온다 — 설치 스크립트를 curl로 받는 것보다 재현성이 높다.
# 버전은 로컬(`uv --version`)과 맞춘다. 어긋나면 잠금 해석이 달라질 수 있다.
COPY --from=ghcr.io/astral-sh/uv:0.10.9 /uv /uvx /bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PATH="/app/.venv/bin:$PATH"

# 의존성을 먼저 깔아 레이어 캐시를 살린다 — 앱 코드만 바뀌면 재설치하지 않는다.
# --frozen: uv.lock을 그대로 쓰고 갱신하지 않는다. 어긋나면 실패한다.
# --no-dev: ruff·pytest는 이미지에 넣지 않는다.
# git: chaeksas-core가 git 의존성이다(커밋 고정, pyproject.toml). slim에는 git이 없다.
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app
# SC01 — BPMN(업무 흐름의 원천)과 엑셀 시드. 둘 다 런타임에 읽는다.
COPY processes ./processes
COPY seed ./seed

# root로 돌리지 않는다.
RUN useradd --create-home --uid 1001 engine && chown -R engine:engine /app
USER engine

EXPOSE 8077

# 컨테이너에서는 --reload를 쓰지 않는다 (코드가 이미지에 고정되어 있다).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8077"]
