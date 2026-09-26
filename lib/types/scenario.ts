/**
 * 경영 시나리오 하나 — 안건 단위의 묶음.
 *
 * 기획안 4.2는 첫 시나리오로 작동모델 전체를 연결·검증한 뒤 약 3개로 확장하고,
 * 후속 시나리오는 **"공통 Framework·Process·데이터·Agent의 재사용 가능성"**을 보고
 * 고르라고 한다. 그래서 시나리오가 소유하는 것과 전사가 소유하는 것을 나눈다:
 *
 * | 시나리오 소유 | BPM 프로세스 인스턴스, Review 안건, 데모 장면 |
 * | 전사 공유     | Framework(KPI·KRI·Control), Rolling Plan, Evolution Lab, 리스크 신호 |
 *
 * 전사 자산을 시나리오마다 복제하면 재사용이 아니라 복사가 된다 — Rolling Plan은 두
 * 시나리오의 승인 과제를 **함께** 받고, Framework는 두 안건의 KRI를 **같은 표**에 놓는다.
 */

import type { BpmProcessInstance } from "@/lib/types/bpm";
import type { DemoScene } from "@/lib/demo-scenario";
import type { ReviewCase, ReviewDecision } from "@/lib/types/workspace";

export interface Scenario {
  id: string;
  /** 화면 제목에 쓰는 정식 명칭. */
  title: string;
  /** 선택기·배지에 쓰는 짧은 이름. */
  shortTitle: string;
  /** 이 시나리오가 다루는 경영 문제. */
  summary: string;
  /** 연결된 Cockpit `RiskSignal.id`. */
  riskId: string;
  process: BpmProcessInstance;
  reviewCase: ReviewCase;
  /** 이 시나리오의 데모 각본. */
  scenes: DemoScene[];
  /** 데모가 자동으로 적용하는 결정. */
  demoDecision: ReviewDecision;
}
