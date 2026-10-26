/**
 * SC02 데모 장면 — 화면구성·시연순서 v0.2 「기본시연」 D00~D12.
 *
 * SC01과 같다(`lib/sc01/scenes.ts`): 장면은 엔진 각본의 한 지점과 화면 하나를 가리킨다. 앞으로 가면
 * 엔진이 실제로 실행하고, 뒤로 가면 이력을 읽기만 한다. **각본은 엔진에 있다**(`engine/app/sc02/demo.py`) —
 * 시연 사례(X01 등)마다 단계가 다르므로 화면은 엔진의 각본 목록에서 장면을 만든다. 여기에는 연출만 있다.
 */

import type { ScriptStep } from "@/lib/sc01/types";

export interface Sc02Scene {
  id: string;
  script: number;
  route: string;
  stage: string;
  title: string;
  narration: string;
}

/** 노드 → 화면. 요청 접수(`null`)는 U21이다. */
export const ROUTE_OF_NODE: Record<string, string> = {
  "": "/sc02/request",
  Verify_Request: "/sc02/request",
  Report_Lead: "/sc02/analysis",
  Confirm_Analysis: "/sc02/analysis",
  Record_Negotiation: "/sc02/negotiation",
  Confirm_Reanalysis: "/sc02/analysis",
  Draft_Proposal: "/sc02/proposal",
  Approve_Lead: "/sc02/approval",
  Approve_Exec: "/sc02/approval",
  Approve_CEO: "/sc02/approval",
  Register_Cost: "/sc02/cost",
  Request_Handoff: "/sc02/handoff",
  Accept_Handoff: "/sc02/handoff",
};

const STAGE: Record<string, string> = {
  "": "Risk 감지",
  Verify_Request: "Operation Control",
  Report_Lead: "Operation Control",
  Confirm_Analysis: "Risk 감지",
  Record_Negotiation: "Operation Control",
  Confirm_Reanalysis: "Risk 감지",
  Draft_Proposal: "Operation Control",
  Approve_Lead: "Operation Control",
  Approve_Exec: "Operation Control",
  Approve_CEO: "Operation Control",
  Register_Cost: "Operation Control",
  Request_Handoff: "Management Review 연결",
  Accept_Handoff: "Management Review 연결",
};

/** 고객에게 설명할 내용(기본시연 시트) — 노드별. 사례가 다른 답을 내면 각본의 라벨이 제목이 된다. */
const NARRATION: Record<string, string> = {
  "": "6/17 09:00 주요 외주업체가 공통부품 P-COM01 단가를 2,000원에서 2,200원(10%)으로 올려 달라는 공문을 보낸다. 장면 1의 물량 감소 검토가 진행 중인 때다.",
  Verify_Request:
    "구매담당이 공문 원문과 등록 내용(공급사·품목·기존가·요청가·7/1 적용·VAT 제외)을 대조한다. a·b모델에 각 1개 쓰이고 c~e는 쓰지 않는다. 요청가는 승인 원가가 아니다.",
  Report_Lead:
    "팀장에게 구두보고하고 사전 손익분석 후 1차 협상하기로 한다. 별도 전자승인 단계를 늘리지 않고 협의 결과만 기록한다.",
  Confirm_Analysis:
    "협상 전에 영향을 본다. 요청안은 향후 12개월 구매 증가 3,136만원으로 금액 위험 중요, 대표 승인 대상이다. 당해 잔여기간(7~12월)과 12개월은 따로 보이고 합산하지 않는다.",
  Record_Negotiation:
    "6/21 1차 협상 — 내부 제시 2,100원, 공급사 잠정 2,120원, 7/1 적용 유지. 잠정합의는 회사 승인이 아니다. 저장하면 재분석이 필요하다.",
  Confirm_Reanalysis:
    "같은 F02·C01 기준으로 다시 잰다. 협상안은 기존 대비 6% 인상, 12개월 증가 1,882만원 — 요청 대비 1,254만원 줄었지만 원가 부담은 남는다. 위험 해소가 아니다.",
  Draft_Proposal:
    "기안가 = 협상가 2,120원, 7/1 적용. 상신하면 PROP01-v1이 고정되고 그 버전의 분석 run(RUN-PROP01)이 붙는다. 예상 승인선은 대표 대상이다.",
  Approve_Lead: "구매팀장이 필요성·협상 결과·계산 근거와 기안 일치를 보고 승인한다. 다음은 임원이다.",
  Approve_Exec:
    "구매임원 승인 뒤 시스템이 대표 대상을 판정한다. 기준은 위험 등급이 아니라 금액 — 최종 기안의 12개월 증가(VAT 제외) ≥ 1천만원이다.",
  Approve_CEO: "대표이사가 같은 기안 버전을 승인한다. 승인되는 것은 단가안이다 — 공식 전망·Target은 바뀌지 않는다.",
  Register_Cost:
    "승인 조건을 대조해 원가 버전 C02-APP01을 등록한다. a 외주비 75,000→75,120원, b 95,000→95,120원, c~e 그대로. 7/1 전이라 적용 예정이고 C01은 보존한다.",
  Request_Handoff:
    "2027년 손익을 중복 없이 잇는다: 물량 영향 −1,400만원 + 단가 영향 −936만원 → 통합 32.99억, Target 대비 1.77억 부족. 물량·원가 사건을 각각 두고 MR-2706-01로 넘긴다.",
  Accept_Handoff:
    "경영관리담당이 범위·버전·근거를 확인하고 인수한다. 장면 2 인계 완료, 장면 3 손익 검토 대기 — 위험은 열려 있고 F02는 여전히 검토 중이다.",
};

export const D00: Sc02Scene = {
  id: "d00",
  script: -1,
  route: "/sc02",
  stage: "성과·전망 모니터링",
  title: "장면 1 결과 확인",
  narration:
    "6/17 아침. 장면 1에서 b모델 7월 700대분 감소를 확인했고 ISSUE-B07(중요)이 열려 있다. 검토 전망 F02는 승인 전이다. 물량 감소에 대응하는 중에 원가 상승 요청이 들어온다.",
};

/** 엔진 각본 → 장면. 사례가 바뀌면 단계가 다르다(X01은 D08에서 추가 협상지시로 끝난다). */
export function scenesFor(script: ScriptStep[]): Sc02Scene[] {
  return [
    D00,
    ...script.map((s) => {
      const node = s.nodeId ?? "";
      return {
        id: `${s.code}-${s.index}`,
        script: s.index,
        route: ROUTE_OF_NODE[node] ?? "/sc02",
        stage: STAGE[node] ?? "Operation Control",
        title: `${s.code} ${s.label}`,
        narration: s.code.startsWith("X") ? `${s.label} — 기본 시연과 다른 갈래다.` : (NARRATION[node] ?? s.label),
      };
    }),
  ];
}
