#!/usr/bin/env bash
#
# BPMN 사본을 autopart1에서 가져온다 — 업무 흐름(BPMN)의 원본은 autopart1 리포의 `bpm/`이다(가상 자동차 부품사가
# 자기 업무를 정의한다). NowView 엔진은 사본을 둔다: 내장 실행기 시험, BPM 흐름 화면의 토폴로지, 장면 3·5의 사전
# 검사가 그림을 읽는다. 사본이 원본과 다르면 엔진 시험(`test_bpmn_copies_match_autopart1`)이 알린다.
#
#   scripts/sync-bpm.sh            # ../autopart1 에서
#   AUTOPART1_DIR=/path scripts/sync-bpm.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="${AUTOPART1_DIR:-$ROOT/../autopart1}/bpm/autopart1"
[[ -d $SRC ]] || { echo "autopart1 BPM 폴더가 없다: $SRC (AUTOPART1_DIR로 지정)" >&2; exit 1; }

changed=0
for bpmn in "$SRC"/*/process/*.bpmn; do
  target="$ROOT/engine/processes/$(basename "$bpmn")"
  if ! cmp -s "$bpmn" "$target"; then
    cp "$bpmn" "$target"
    echo "갱신: engine/processes/$(basename "$bpmn")"
    changed=1
  fi
done
if [[ $changed == 1 ]]; then
  echo "그림이 바뀌었다 — 엔진 시험을 돌리고, 실패가 알려 주는 명령으로 tests/fixtures/sc0N-process.json을 다시 만든다."
else
  echo "사본이 원본과 같다."
fi
