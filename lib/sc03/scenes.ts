/**
 * SC03 데모 장면 — 화면구성·시연순서 v0.2 「기본시연」 D30~D41.
 *
 * 장면 1·2와 같다: 장면은 엔진 각본의 한 지점과 화면 하나를 가리킨다. 앞으로 가면 엔진이 실제로 실행하고,
 * 뒤로 가면 이력을 읽기만 한다. **각본은 엔진에 있다**(`engine/app/sc03/demo.py`) — 사례(E31 등)마다 단계가
 * 다르므로 화면은 엔진의 각본 목록에서 장면을 만든다. 여기에는 연출(화면·단계·설명)만 있다.
 */

import type { Sc03ScriptStep } from "@/lib/sc03/types";

export interface Sc03Scene {
  id: string;
  script: number;
  route: string;
  stage: string;
  title: string;
  narration: string;
}

/** 노드 → 화면(U31~U37). */
export const ROUTE_OF_NODE: Record<string, string> = {
  Save_Analysis: "/sc03/analysis",
  Fix_Calc: "/sc03/analysis",
  Request_Confirm: "/sc03/analysis",
  Confirm_Sales: "/sc03/confirm",
  Confirm_Buy: "/sc03/confirm",
  Confirm_Prod: "/sc03/confirm",
  Revise_Sales: "/sc03/confirm",
  Revise_Buy: "/sc03/confirm",
  Revise_Prod: "/sc03/confirm",
  Register_Gap: "/sc03/confirm",
  Judge_Questions: "/sc03/confirm",
  Freeze_Report: "/sc03/meeting",
  Distribute: "/sc03/meeting",
  Report_Meeting: "/sc03/meeting",
  Decide_Review: "/sc03/meeting",
  Confirm_Minutes: "/sc03/tasks",
  Assign_Tasks: "/sc03/tasks",
  Accept_AT31: "/sc03/tasks",
  Accept_AT32: "/sc03/tasks",
  Accept_AT33: "/sc03/tasks",
  Accept_AT34: "/sc03/tasks",
  Reassign_AT31: "/sc03/tasks",
  Reassign_AT32: "/sc03/tasks",
  Reassign_AT33: "/sc03/tasks",
  Reassign_AT34: "/sc03/tasks",
  Complete_Scene: "/sc03/handoff",
};

/** 각본 종류 → 화면(BPM 밖 단계). */
const ROUTE_OF_KIND: Record<string, string> = {
  start: "/sc03",
  view: "/sc03/analysis",
  record: "/sc03/meeting",
  agent: "/sc03/meeting",
  revision: "/sc03/meeting",
  clock: "/sc03/handoff",
};

/** 기본시연 시트의 「고객에게 설명할 내용」 — 단계 코드별. */
const NARRATION: Record<string, string> = {
  D31: "경영관리 담당이 장면 1 물량 감소(ISSUE-B07)와 장면 2 승인 단가(ISSUE-COST01)를 기존 검토건 MR-2706-01에 잇고 분석을 시작한다. 부서별 통제 결과를 공통 경영검토로 연결한다.",
  D32: "같은 기준(F02+EXT28-v1 · C02-APP01 · FC01/FC28-v1)으로 통합 계산한다. 기존 부족 1억 5,394만원과 이번 추가 악화 −2,336만원은 별개의 문제다 — 전체 부족 1억 7,730만원.",
  D33: "기간·모델·원가 근거까지 추적한다. b 7월 700대분 감소, 향후 12개월 Target은 미설정, c~e 모델도 함께 본다.",
  D34: "계산을 통합한 뒤 영업·구매·생산에 사실과 제약 확인을 요청한다. 회신기한 6/28 18시. 무응답은 동의가 아니다.",
  D35: "각 부서가 사실·가정·미확인을 나눠 회신한다. 생산은 회피가능 고정비를 미확인으로 남긴다 — 자료가 없는 대안 효과는 단정하지 않는다.",
  D36: "현 손익 계산의 오류와 대안 검증에 필요한 추가 자료를 구분한다. Q31·Q32를 비차단으로 처리하고 6/29 09시 REP31-v1을 확정·배포한다.",
  D37: "6/29 10시 경영관리 임원 주재 수시 경영검토회의. 확정본으로 보고하고 질의에 답한다 — 두 사건을 해소해도 기존 부족이 남는다.",
  D38: "지금은 무엇을 더 분석할지 정한다. 후보 6개 중 4개를 상세 분석에 포함, 전면 외주화·해외 신규 차종은 이번 분석에서 제외(사유 기록). 상세 비교는 대표 주재 월간회의다.",
  D39: "실제로 실행 가능한지 같은 기준으로 비교하도록 과제를 구조화한다 — AT31~AT34, 단일 책임·협조·7/6 제출기한·기준 버전.",
  D40: "지시 발행뿐 아니라 담당자 인수까지 잇는다. 3/4에서는 완료가 막히고 4/4가 되면 열린다.",
  D41: "분석 검토와 책임 배정이 끝났다. 장면 3 완료 — 위험은 열려 있고 공식 전망은 검토 중, Target은 그대로다. 대응안 상세 분석·선택은 7/12 MT41로 이어진다.",
};

const STAGE: Record<string, string> = {
  D31: "Management Review 연결",
  D32: "Management Review",
  D33: "Management Review",
  D34: "Management Review",
  D35: "Management Review",
  D36: "Management Review",
  D37: "Management Review",
  D38: "Management Review",
  D39: "Management Action 지시",
  D40: "Management Action 지시",
  D41: "장면 4 연결",
};

export const D30: Sc03Scene = {
  id: "d30",
  script: -1,
  route: "/sc03",
  stage: "Management Review 연결",
  title: "D30 장면 2 인수 완료 · 장면 3 미착수",
  narration:
    "6/24 10시. 장면 2에서 승인 단가 2,120원의 원가 등록과 경영관리 인수가 끝났다. 부서별 확인·승인은 됐지만 수익성 목표 부족과 두 사건의 위험은 남아 있다. 실제 업무는 여러 날 걸린다 — 시연은 시간 이동으로 압축한다.",
};

/** 엔진 각본 → 장면. 사례가 바뀌면 단계가 다르다(E31은 구매 이견·보완·재확인이 끼어든다). */
export function scenesFor(script: Sc03ScriptStep[]): Sc03Scene[] {
  return [
    D30,
    ...script.map((s) => ({
      id: `${s.code}-${s.index}`,
      script: s.index,
      route: (s.nodeId ? ROUTE_OF_NODE[s.nodeId] : ROUTE_OF_KIND[s.kind]) ?? "/sc03",
      stage: STAGE[s.code] ?? "예외 경로",
      title: `${s.code} ${s.label}`,
      narration: s.code.startsWith("E") ? `${s.label} — 기본 시연과 다른 갈래다.` : (NARRATION[s.code] ?? s.label),
    })),
  ];
}
