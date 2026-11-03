#!/usr/bin/env bash
#
# 각본(입력 예시 값) 사본을 Company1에서 가져온다 — 각본의 원본은 Company1 리포의 `scenarios/`다(회사 사이트의
# 자동 모드·결재 예시 값이 쓴다, 2026-11-03 `docs/role-split.md` §5). NowView 엔진은 사본을 시험 전용 각본
# 실행기의 기본(BASE) 단계로 읽는다(`engine/app/scenarios.py`). 사본이 원본과 다르면 엔진 시험
# (`test_scenario_copies_match_company1`)이 알린다.
#
#   scripts/sync-scenarios.sh            # ../Company1 에서
#   COMPANY1_DIR=/path scripts/sync-scenarios.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="${COMPANY1_DIR:-$ROOT/../Company1}/scenarios"
[[ -d $SRC ]] || { echo "Company1 각본 폴더가 없다: $SRC (COMPANY1_DIR로 지정)" >&2; exit 1; }

changed=0
for json in "$SRC"/sc0*.json; do
  target="$ROOT/engine/scenarios/$(basename "$json")"
  if ! cmp -s "$json" "$target"; then
    cp "$json" "$target"
    echo "갱신: engine/scenarios/$(basename "$json")"
    changed=1
  fi
done
if [[ $changed == 1 ]]; then
  echo "각본이 바뀌었다 — 엔진 시험을 돌린다(끝난 문서를 데이터 시트와 대조한다)."
else
  echo "사본이 원본과 같다."
fi
