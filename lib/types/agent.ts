/**
 * Agent가 쓰는 데이터의 품질과 판단의 불확실성.
 *
 * 기획안 2.1은 시나리오에 "데이터의 불완전성"을 포함하라고 하고, 3.6은 각 업무에
 * "정보 부족이나 판단 불확실성이 있을 때의 처리 방식"을 명시하라고 한다.
 *
 * **Agent가 늘 확신에 찬 결론만 내면 사람이 검증할 지점이 없어진다.** 근거 목록에
 * 소스 이름만 나열하는 것으로는 부족하다 — 그 소스가 완전한지, 추정인지, 언제 것인지가
 * 결론의 신뢰도를 좌우한다.
 */

/** 데이터 소스의 상태. */
export type DataQuality = "complete" | "partial" | "stale" | "estimated";

export const DATA_QUALITY_LABEL: Record<DataQuality, string> = {
  complete: "완전",
  partial: "일부 결손",
  stale: "최신성 부족",
  estimated: "추정치",
};

export interface DataSource {
  name: string;
  quality: DataQuality;
  /**
   * 무엇이 어떻게 불완전한지. `complete`가 아니면 반드시 적는다 —
   * "일부 결손"이라는 라벨만으로는 결론을 얼마나 믿어야 할지 알 수 없다.
   */
  caveat?: string;
}

/** Agent 산출물의 신뢰도. */
export type Confidence = "high" | "medium" | "low";

export const CONFIDENCE_LABEL: Record<Confidence, string> = {
  high: "높음",
  medium: "보통",
  low: "낮음",
};

/**
 * Agent가 스스로 답하지 못하고 사람에게 넘긴 판단.
 *
 * 정보가 부족할 때 Agent는 **추측하지 않고 질문한다.** 이것이 기획안 3.6의
 * "정보 부족이나 판단 불확실성이 있을 때의 처리 방식"이다. 답을 받지 못한 채 진행하면
 * 어떤 가정 위에 서 있는지를 `ifUnanswered`에 남긴다 — 그래야 나중에 결론이 틀렸을 때
 * 어디서 갈렸는지 되짚을 수 있다.
 */
export interface AgentEscalation {
  id: string;
  /** Agent가 사람에게 묻는 것. */
  question: string;
  /** 왜 Agent가 답할 수 없는가. */
  reason: string;
  /** 답해야 할 사람. */
  owner: string;
  /** 답을 받지 못한 채 진행할 때 Agent가 세우는 가정과 그 위험. */
  ifUnanswered: string;
}

/** 소스 목록에서 불완전한 것만. 화면 요약에 쓴다. */
export function incompleteSources(sources: DataSource[]): DataSource[] {
  return sources.filter((s) => s.quality !== "complete");
}
