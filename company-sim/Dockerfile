# 가상 자동차 부품사 회사 시스템 시뮬레이터 (FastAPI)
#
# 빌드 컨텍스트는 `company-sim/`이다 (docker-compose.yml의 context 참조). 엔진 이미지와 같은 틀이다.

FROM python:3.12-slim AS base

COPY --from=ghcr.io/astral-sh/uv:0.10.9 /uv /uvx /bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PATH="/app/.venv/bin:$PATH" \
    AUTOPARTS_SIM_DB=/app/data/sim-state.sqlite

COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project

COPY autoparts_sim ./autoparts_sim
# 회사 자료의 원천(엑셀 원천 시트·조직) — 런타임에 읽는다.
COPY seed ./seed

RUN useradd --create-home --uid 1001 sim && mkdir -p /app/data && chown -R sim:sim /app
USER sim

EXPOSE 8091

# 팩토리 — 키(AUTOPARTS_SIM_KEY)가 없으면 기동하지 않는다.
CMD ["uvicorn", "autoparts_sim.main:build_app", "--factory", "--host", "0.0.0.0", "--port", "8091"]
