/** 장면 2 노드 → 화면. 요청 접수(`""`)는 U21이다. 업무 현황이 지금 기다리는 결재를 그 화면으로 잇는다. */
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
