/**
 * SC05 데모 장면 — 화면구성·시연순서 v0.2 「시연순서」 D501~D518.
 *
 * 장면 1~4와 같다: 장면은 엔진 각본의 한 지점과 화면 하나를 가리킨다. 앞으로 가면 엔진이 실제로 실행하고, 뒤로 가면
 * 이력을 읽기만 한다. **각본은 엔진에 있다**(`engine/app/sc05/demo.py`) — 사례(X502 등)마다 단계가 다르므로 화면은
 * 엔진의 각본 목록에서 장면을 만든다. 여기에는 연출(화면·단계·설명)만 있다. 시점 전환(계획 준비 → 조건 확인 → 운영
 * 적용 → 초기 관측 → 월간 Rolling)은 단계마다 가상시계가 옮겨 간다 — 한 번의 클릭으로 몇 달의 성과가 생기지 않는다.
 */

import type { Sc05ScriptStep } from "@/lib/sc05/types";

export interface Sc05Scene {
  id: string;
  script: number;
  route: string;
  stage: string;
  title: string;
  narration: string;
}

/** 노드 → 화면(U501~U508). */
export const ROUTE_OF_NODE: Record<string, string> = {
  Draft_Plan: "/sc05/plan",
  Coordinate_Plan: "/sc05/plan",
  Confirm_Plan: "/sc05/plan",
  Verify_Plan: "/sc05/plan",
  Request_Change: "/sc05/plan",
  Coordinate_Change: "/sc05/plan",
  Confirm_Change: "/sc05/plan",
  Verify_Change: "/sc05/plan",
  Evidence_CON41: "/sc05/ready",
  Ready_CON41: "/sc05/ready",
  Confirm_CON41: "/sc05/ready",
  Register_SUP41: "/sc05/ready",
  Verify_SUP41: "/sc05/ready",
  Submit_REQ51: "/sc05/ready",
  Func_REQ51: "/sc05/ready",
  Budget_REQ51: "/sc05/ready",
  Submit_OP51: "/sc05/ready",
  Func_OP51: "/sc05/ready",
  Budget_OP51: "/sc05/ready",
  Start_Operation: "/sc05/ready",
  Receive_Change: "/sc05/changes",
  Share_Change: "/sc05/changes",
  Ack_Change: "/sc05/changes",
  Respond_Change: "/sc05/changes",
  Approve_Urgent: "/sc05/changes",
  Execute_Order: "/sc05/changes",
  Confirm_Observation: "/sc05/results",
  Confirm_OPL51: "/sc05/operating",
  Confirm_OPL52: "/sc05/operating",
  Confirm_OPL53: "/sc05/operating",
  Verify_OPL51: "/sc05/operating",
  Verify_OPL52: "/sc05/operating",
  Verify_OPL53: "/sc05/operating",
  Draft_Forecast: "/sc05/forecast",
  Confirm_FC_BUY: "/sc05/forecast",
  Confirm_FC_PROD: "/sc05/forecast",
  Confirm_FC_SALES: "/sc05/forecast",
  Submit_Forecast: "/sc05/forecast",
  Approve_Forecast: "/sc05/forecast",
  Publish_Forecast: "/sc05/forecast",
  Complete_Scene: "/sc05/handoff",
};

/** BPM 밖 단계(착수·Agent·검토·조회)는 단계 코드의 화면이다. */
const ROUTE_OF_CODE: Record<string, string> = {
  D501: "/sc05",
  D502: "/sc05/plan",
  D503: "/sc05/plan",
  D504: "/sc05/ready",
  D505: "/sc05/plan",
  D506: "/sc05/plan",
  D507: "/sc05/ready",
  D508: "/sc05/ready",
  D509: "/sc05/ready",
  D510: "/sc05/changes",
  D511: "/sc05/changes",
  D512: "/sc05/changes",
  D513: "/sc05/results",
  D514: "/sc05/operating",
  D515: "/sc05/forecast",
  D516: "/sc05/forecast",
  D517: "/sc05/forecast",
  D518: "/sc05/handoff",
};

/** 시연순서 시트의 「고객에게 전달할 메시지」를 바탕으로 — 단계 코드별. */
const NARRATION: Record<string, string> = {
  D501: "7/13. 개선안 검토·실행 승인 승인서(APR41-v1)와 세 과제의 책임 인수를 연다. 회의의 결정이 실행 책임으로 연결된다 — 인수는 조건 충족이 아니다. CON41·SUP41은 아직 미충족이다.",
  D502: "구매 담당이 Agent 초안(AG51)을 불러와 협조 담당과 비용을 채우고 일정을 고친다. Agent가 계획 구체화를 돕고 담당자가 판단한다 — 원 제안과 수정본이 따로 남는다.",
  D503: "생산 임원이 협조를 확인한다. 정례 협의만으로는 회의 이후 생산계획 변경을 구매가 늦게 안다 — 계획 수립 단계에서 부서 간 애로를 푼다.",
  D504: "구매 임원이 확정하고 경영관리 임원이 정합성을 확인한다. 계획 확정만으로 실행 준비가 끝나지 않는다 — CON41·SUP41·품의가 남아 착수 대기다.",
  D505: "준비 중에 부재·정례회의 이후 접수의 적용 애로가 드러났다. 대행·수시 확인 경로를 더하고 교육을 8/19로 옮긴다(AG52 비교). 기존 확정본은 그대로 유효하다.",
  D506: "생산 협조 → 구매 임원 변경 확정 → 경영관리 확인. 예산 6백만원·9월 효과 개시·9/30 기한은 그대로라 대표 재승인 없이 위임 범위 안에서 조정한다.",
  D507: "8/20. 공동 기준과 양 부서 준비 근거를 열고 권한별로 확인한다 — CON41은 구매 임원, SUP41은 경영관리 임원. 첨부만으로 조건이 끝나지 않는다.",
  D508: "대표 승인서를 근거로 품의를 올리고 현업 임원·예산 임원이 승인한다. 승인과 약정이 함께 남고, 일회성 한도와 운영지원비는 따로 본다. 모든 요건이 갖춰져도 9/1 전엔 착수하지 않는다.",
  D509: "9/1 09:00. 구매 임원이 요건을 다시 확인하고 운영 적용을 시작한다(START51). 준비 완료와 실제 적용은 다른 기록이다.",
  D510: "9/2. 고객 변경(CP51)을 접수하고 생산이 공유, 구매가 확인한다. 변동 없는 c·d·e 모델도 같은 원문에 보인다 — 공유 25분, 확인 45분.",
  D511: "재고 80 + 기발주 120으로 정상 대응한다. 정보 공유와 조정으로 불필요한 긴급구매를 줄인다 — 14시 발주, 15시 처리 기록.",
  D512: "9/10 별도 요청창(CP52): 가용 0, 필요 9/13, 정상조달 9/15. 긴급 운송 90만원 + 할증 30만원을 기안하고 구매 임원 전결로 승인한다 — 필요한 긴급 대응은 통제 아래 실행한다.",
  D513: "10/4. 9월 마감 뒤 초기 결과 — 구매 60건 중 긴급 5건(전망 4건보다 1건 많다), 추가비 6백만원, 비교 기준 대비 추정 순개선 8.2백만원. 연간 달성으로 단정하지 않는다.",
  D514: "담당 임원이 잔여 10~12월 가정만 고친다 — 10월 4건, 11·12월 3건은 대행·수시 공유 정착을 전제로 한 판단이지 9월 실적의 외삽이 아니다. 배경 과제 ACT41·43은 요약만.",
  D515: "10/5. 9월까지 마감 실적과 10~12월 전망을 합친다. 개선안 검토·실행 승인 승인효과 127.8백만원을 공식본에 다시 더하지 않는다 — 9월 −1.2백만원, 11~12월 +2.4백만원, 대사 차이 0.",
  D516: "구매·생산·영업 임원이 자기 부서 가정만 확인하고 경영관리 임원이 대표에게 올린다. 아직 검토안이다 — 공식 지표를 덮지 않는다.",
  D517: "10/6 10:00. 대표가 공식 전망 갱신을 승인한다(실행계획 재승인과 다르다). 10:05 게시 — 3,428.99백만원, Target 3,477.29백만원 유지, 남는 부족 48.30백만원.",
  D518: "후속 책임과 기한을 점검해 결정 실행·계획 갱신 인계를 마친다. 과제는 운영 추적 중이고 Risk는 OPEN이다 — 남는 미달 가능성을 관리하며 실행을 이어간다.",
};

const STAGE: Record<string, string> = {
  D501: "결정 실행 연결",
  D502: "상세 계획",
  D503: "상세 계획",
  D504: "상세 계획",
  D505: "계획 보완",
  D506: "계획 보완",
  D507: "조건·착수",
  D508: "조건·착수",
  D509: "조건·착수",
  D510: "초기 실행",
  D511: "초기 실행",
  D512: "초기 실행",
  D513: "초기 결과",
  D514: "월간 Rolling",
  D515: "월간 Rolling",
  D516: "월간 Rolling",
  D517: "월간 Rolling",
  D518: "후속 관리",
};

export const D500: Sc05Scene = {
  id: "d500",
  script: -1,
  route: "/sc05",
  stage: "결정 실행 연결",
  title: "D500 개선안 검토·실행 승인 완료 · 결정 실행·계획 갱신 미착수",
  narration:
    "7/13 10:00. 대표가 세 과제를 포괄 승인했고 담당 임원들이 책임을 인수했다. 아직 상세 계획·조건·품의·실행은 없다 — 시연은 계획 준비 → 조건 확인 → 운영 적용 → 초기 관측 → 월간 Rolling 순으로 시점을 옮긴다.",
};

/** 엔진 각본 → 장면. 사례가 바뀌면 단계가 다르다(X507은 반려 뒤 보완 검토안이 끼어든다). */
export function scenesFor(script: Sc05ScriptStep[]): Sc05Scene[] {
  return [
    D500,
    ...script.map((s) => ({
      id: `${s.code}-${s.index}`,
      script: s.index,
      route: (s.nodeId ? ROUTE_OF_NODE[s.nodeId] : ROUTE_OF_CODE[s.code]) ?? "/sc05",
      stage: STAGE[s.code] ?? "예외 경로",
      title: `${s.code} ${s.label}`,
      narration: s.code.startsWith("X") ? `${s.label} — 기본 시연과 다른 갈래다.` : (NARRATION[s.code] ?? s.label),
    })),
  ];
}
