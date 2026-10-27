/**
 * SC04 데모 장면 — 화면구성·시연순서 v0.2 「기본시연」 D401~D413.
 *
 * 장면 1~3과 같다: 장면은 엔진 각본의 한 지점과 화면 하나를 가리킨다. 앞으로 가면 엔진이 실제로 실행하고,
 * 뒤로 가면 이력을 읽기만 한다. **각본은 엔진에 있다**(`engine/app/sc04/demo.py`) — 사례(E401 등)마다 단계가
 * 다르므로 화면은 엔진의 각본 목록에서 장면을 만든다. 여기에는 연출(화면·단계·설명)만 있다.
 */

import type { Sc04ScriptStep } from "@/lib/sc04/types";

export interface Sc04Scene {
  id: string;
  script: number;
  route: string;
  stage: string;
  title: string;
  narration: string;
}

/** 노드 → 화면(U401~U408). */
export const ROUTE_OF_NODE: Record<string, string> = {
  Submit_AT31: "/sc04",
  Confirm_AT31: "/sc04",
  Submit_AT32: "/sc04",
  Confirm_AT32: "/sc04",
  Submit_AT33: "/sc04",
  Confirm_AT33: "/sc04",
  Submit_AT34: "/sc04",
  Confirm_AT34: "/sc04",
  Verify_Effects: "/sc04/verify",
  Correct_Effects: "/sc04/verify",
  Recommend: "/sc04/recommend",
  Freeze_Report: "/sc04/report",
  Report_Meeting: "/sc04/report",
  Draft_Decision: "/sc04/meeting",
  Confirm_Decision: "/sc04/meeting",
  Decide: "/sc04/approval",
  Draft_Approval: "/sc04/approval",
  Finalize_Approval: "/sc04/approval",
  Register_Actions: "/sc04/actions",
  Accept_ACT41: "/sc04/actions",
  Accept_ACT42: "/sc04/actions",
  Accept_ACT43: "/sc04/actions",
  Accept_SUP41: "/sc04/actions",
  Accept_Overall: "/sc04/actions",
  Revise_ACT41: "/sc04/actions",
  Revise_ACT42: "/sc04/actions",
  Revise_ACT43: "/sc04/actions",
  Revise_SUP41: "/sc04/actions",
  Complete_Scene: "/sc04/handoff",
};

/** 각본 종류 → 화면(BPM 밖 단계). 조회 단계는 단계 코드로 고른다. */
const ROUTE_OF_KIND: Record<string, string> = {
  start: "/sc04",
  record: "/sc04/meeting",
  agent: "/sc04/meeting",
  clock: "/sc04/handoff",
};
const ROUTE_OF_VIEW: Record<string, string> = { D403: "/sc04/verify", D411: "/sc04/approval" };

/** 기본시연 시트의 「시연 메시지」 — 단계 코드별. */
const NARRATION: Record<string, string> = {
  D401: "경영관리 담당이 수익성 통합 분석 인계(HANDOFF31)에서 AT31~AT34를 열고 결과 제출 현황을 본다. 수익성 통합 분석의 분석 지시가 이번 의사결정의 입력으로 이어진다.",
  D402: "부서 책임자가 결과를 내고 담당 임원이 확인한다. AT33 물량 배분은 미수행이 아니라 검토 후 제외다 — 고객 물량을 임의 조정하는 비현실적 대안을 실행안에서 뺀다. AT34는 기존 부족 원인이다.",
  D403: "외주 조정의 비용 상세를 연다. 기존 감가상각비는 기준 손익에 그대로 남는다 — 외주 확대만으로 고정비를 절감하지 않는다. 보고 금액보다 실제 줄일 수 있는 비용을 검증한다.",
  D404: "구매조건 할인과 대체 공급업체 가격차가 같은 품목(P-MAT02)에 겹친다 — 10~12월 1,800,000원을 한 번만 반영한다. 낙관적 효과 합산을 줄인다.",
  D405: "3개 후보를 비교해 담당 임원들이 우선 실행안을 제안한다. 대표에게 선택을 떠넘기지 않는다 — 우선순위는 효과액 순이 아니라 착수 순서다(구매조건이 1순위).",
  D406: "7/12 월간회의. 대응 전 부족 1억 7,730만원, 예상 개선효과 1억 3,720만원, 남는 부족 4,010만원 — 목표 미달 가능성을 숨기지 않고 개선 범위와 추가 과제를 설명한다.",
  D407: "대표가 효과와 실행 가능성을 질문으로 점검한다 — 긴급구매를 줄이면 납기는 지킬 수 있는가, 구매부서만 노력하면 되는가.",
  D408: "구매·생산 임원의 답변으로 부서별 보고에 드러나지 않은 공동 과제(생산 변경정보 공유)가 확인된다. 생산 탓으로 단정하지 않는다.",
  D409: "공동 기준 마련(CON41·SUP41)을 지시하고 효과 시작을 9월로 조정한다. 원 보고본은 그대로 두고 판단본 DEC41-v2로 재계산 — 1억 2,780만원, 남는 부족 4,950만원.",
  D410: "대표가 최종 판단본으로 결정한다 — 부분 공정·대체 공급업체 승인, 긴급구매 개선은 조건부 승인. 권한과 책임을 주되 한도와 조건을 명확히 한다. 남는 부족은 추가 발굴(DIR41)로.",
  D411: "승인서와 회의록을 함께 확정한다 — 총괄 18백만원, 과제 8·6·4백만원, 계획 제출 7/16, 과제별 완료기한. 한도 안 전용은 경영관리 임원, 총괄 초과는 대표 별도 승인 — 반복 결재를 줄이고 예외는 통제한다.",
  D412: "승인과제를 등록하고 책임자가 차례로 인수한다. 전체 책임·개별 책임·추가 지시 인수가 따로 보이고, 전원 인수 전에는 종료할 수 없다.",
  D413: "모든 인수 뒤 개선안 검토·실행 승인 완료. 결정 실행·계획 갱신 상세 계획 대기 — CON41 미충족·위험 미해소는 그대로다. 실행 준비를 마쳤고 성과는 후속 실행에서 확인한다.",
};

const STAGE: Record<string, string> = {
  D401: "Management Review",
  D402: "Management Review",
  D403: "Management Review",
  D404: "Management Review",
  D405: "Management Review",
  D406: "Management Review",
  D407: "Management Review",
  D408: "Management Review",
  D409: "Management Review",
  D410: "Management Action 승인",
  D411: "Management Action 승인",
  D412: "Management Action",
  D413: "결정 실행·계획 갱신 연결",
};

export const D400: Sc04Scene = {
  id: "d400",
  script: -1,
  route: "/sc04",
  stage: "Management Review 연결",
  title: "D400 수익성 통합 분석 완료 · 개선안 검토·실행 승인 미착수",
  narration:
    "7/1 08:59. 수익성 통합 분석 수시회의에서 지정한 분석과제 AT31~AT34가 인수됐다. 7/6 제출, 7/8 취합, 7/12 대표 주재 월간회의가 예정돼 있다. 아직 결과·보고·승인은 없다 — 시연은 시간 이동으로 여러 날을 압축한다.",
};

/** 엔진 각본 → 장면. 사례가 바뀌면 단계가 다르다(E405는 반려·보완·재인수가 끼어든다). */
export function scenesFor(script: Sc04ScriptStep[]): Sc04Scene[] {
  return [
    D400,
    ...script.map((s) => ({
      id: `${s.code}-${s.index}`,
      script: s.index,
      route:
        (s.nodeId ? ROUTE_OF_NODE[s.nodeId] : s.kind === "view" ? ROUTE_OF_VIEW[s.code] : ROUTE_OF_KIND[s.kind]) ??
        "/sc04",
      stage: STAGE[s.code] ?? "예외 경로",
      title: `${s.code} ${s.label}`,
      narration: s.code.startsWith("E") ? `${s.label} — 기본 시연과 다른 갈래다.` : (NARRATION[s.code] ?? s.label),
    })),
  ];
}
