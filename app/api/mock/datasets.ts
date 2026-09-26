/**
 * Mock 데이터셋 레지스트리.
 *
 * 화면들은 지금 이 API가 아니라 `lib/mock-data/*`를 직접 import한다(정적 프리렌더 유지).
 * 이 API는 **외부 소비자를 위한 경계**다 — FastAPI/LangGraph 서비스나 별도 클라이언트가
 * 같은 데이터를 읽어야 할 때 여기를 통한다. 실제 백엔드가 붙으면 이 레지스트리의
 * 값만 실 조회로 바꾸면 되고 응답 계약은 그대로다.
 */

import { bpmProcess } from "@/lib/mock-data/bpm-process";
import { deliveryProcess } from "@/lib/mock-data/bpm-process-delivery";
import { deliveryReviewCase } from "@/lib/mock-data/review-case-delivery";
import { managementFramework } from "@/lib/mock-data/framework";
import { scenarios } from "@/lib/mock-data/scenarios";
import { evolutionLab } from "@/lib/mock-data/evolution-lab";
import { nextAutomotive } from "@/lib/mock-data/next-automotive";
import { reviewCase } from "@/lib/mock-data/review-case";
import { rollingPlan } from "@/lib/mock-data/rolling-plan";

interface MockDataset {
  description: string;
  /** 지연 평가 — 목록 조회 시 전체 데이터를 직렬화하지 않기 위해. */
  load: () => unknown;
}

export const MOCK_DATASETS: Record<string, MockDataset> = {
  company: {
    description: "(주)넥스트오토모티브 전사 재무·운영 스냅샷 및 리스크 신호",
    load: () => nextAutomotive,
  },
  "bpm-process": {
    description: "가동률 이탈 대응 BPM 프로세스 인스턴스 (노드·엣지·Agent 실행 기록)",
    load: () => bpmProcess,
  },
  "review-case": {
    description: "Management Review 안건 — Agent 보고서와 대응 대안 3안",
    load: () => reviewCase,
  },
  "rolling-plan": {
    description: "FY2026 Rolling Plan — 분기 전망, 갱신 이력, 실행 과제",
    load: () => rollingPlan,
  },
  scenarios: {
    description: "시나리오 목록 — 안건별 프로세스·Review·데모 각본 묶음",
    load: () =>
      scenarios.map(({ id, title, shortTitle, summary, riskId }) => ({
        id,
        title,
        shortTitle,
        summary,
        riskId,
      })),
  },
  framework: {
    description: "Management Framework — Value Driver·KPI·KRI·Control 연결",
    load: () => managementFramework,
  },
  "bpm-process-delivery": {
    description: "시나리오 2 — 납기 준수 BPM 프로세스 인스턴스",
    load: () => deliveryProcess,
  },
  "review-case-delivery": {
    description: "시나리오 2 — 현업 통제 조치 선택 안건",
    load: () => deliveryReviewCase,
  },
  "evolution-lab": {
    description: "KRI 임계치 백테스트 및 프레임워크 개선 제안",
    load: () => evolutionLab,
  },
};

export type MockDatasetName = keyof typeof MOCK_DATASETS;
