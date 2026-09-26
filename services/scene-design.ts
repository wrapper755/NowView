/**
 * 장면별 설계표 생성 (기획안 4.2).
 *
 * 기획안은 각 장면에 대해 **시작 조건 · 관련 프로세스 · KPI–KRI–Control · 입력 정보 ·
 * 사람/Agent/BPM의 역할 · 출력과 검증 기준**을 정의하라고 한다. 이 여섯 항목은 이미
 * 전부 구현 안에 있다 — 손으로 옮겨 적으면 구현이 바뀔 때 문서만 낡는다.
 *
 * 그래서 **문서를 손으로 쓰지 않고 데이터에서 생성한다.** 설계표는 Business 설계를 BPM·
 * Agent 구현으로 잇는 공통 명세이므로(기획안 4.2), 둘이 갈라지면 명세로서 쓸모가 없다.
 *
 * 다만 경영 판단 기준처럼 코드에 없는 내용은 여기서 만들어내지 않는다. 그 부분은
 * 생성물에 **미정의로 표시**해 사람이 채우도록 남긴다 — 없는 내용을 그럴듯하게 쓰는 것이
 * 이 프로젝트에서 가장 피하려는 실패다.
 */

import { managementFramework } from "@/lib/mock-data/framework";
import type { DemoScene } from "@/lib/demo-scenario";
import type { BpmNodeSpec, BpmProcessInstance } from "@/lib/types/bpm";
import type { DataSource } from "@/lib/types/agent";
import type { Scenario } from "@/lib/types/scenario";
import { MANAGEMENT_STAGE_LABEL } from "@/lib/types/cockpit";
import { CONTROL_KIND_LABEL, CONTROL_STATUS_LABEL } from "@/lib/types/framework";
import { DECISION_RATIONALE_MIN_LENGTH } from "@/lib/types/workspace";
import { chainForRisk } from "@/services/framework";

/** 코드에 근거가 없는 항목. 지어내지 않고 이렇게 표시한다. */
const UNDEFINED_MARK = "미정의 — 경영 판단 기준 작성 필요";

export interface SceneDesignRow {
  sceneNo: number;
  scene: string;
  narration: string;
  startCondition: string;
  process: string;
  frameworkChain: string;
  inputs: string;
  humanRole: string;
  agentRole: string;
  bpmRole: string;
  output: string;
  verification: string;
}

const KIND_LABEL: Record<BpmNodeSpec["kind"], string> = {
  start: "시작 이벤트",
  end: "종료 이벤트",
  "agent-task": "AI Agent 수행",
  "user-task": "사람 수행 (Human-in-the-Loop)",
  "service-task": "시스템 자동 수행",
  gateway: "배타 분기",
};

function formatSources(sources: DataSource[]): string {
  return sources
    .map((s) =>
      s.quality === "complete"
        ? s.name
        : `${s.name} (불완전: ${s.caveat ?? s.quality})`,
    )
    .join(" · ");
}

/**
 * 시작 조건 — 이 장면에 진입하는 조건.
 *
 * 프로세스의 **들어오는 엣지**에서 끌어낸다. 게이트웨이 분기는 엣지 라벨이 곧 조건이다.
 */
function startConditionOf(process: BpmProcessInstance, node: BpmNodeSpec): string {
  const incoming = process.edges.filter((e) => e.target === node.id);
  if (incoming.length === 0) {
    return `${process.kri.label} ${process.kri.value} — 임계 ${process.kri.threshold} 이탈 감지 시 자동 착수`;
  }
  return incoming
    .map((edge) => {
      const from = process.nodes.find((n) => n.id === edge.source);
      const label = from?.label ?? edge.source;
      return edge.label ? `${label} 완료 후 분기 조건 "${edge.label}"` : `${label} 완료`;
    })
    .join(" 또는 ");
}

function rolesOf(
  process: BpmProcessInstance,
  node: BpmNodeSpec,
): { human: string; agent: string; bpm: string } {
  switch (node.kind) {
    case "agent-task": {
      const agent = process.agents.find((a) => a.id === node.agentId);
      return {
        human: "산출물과 근거 검토. 승인 권한은 없다.",
        agent: agent ? `${agent.name} — ${agent.capability}` : (node.actor ?? "-"),
        bpm: "완료 시 다음 노드로 자동 전이. 미완료 산출물은 노출하지 않는다.",
      };
    }
    case "user-task":
      return {
        human: `${node.actor ?? "담당자"} — 대안 선택 및 승인. 사유 ${DECISION_RATIONALE_MIN_LENGTH}자 이상 필수.`,
        agent: "분석·대안 제시까지. 선택과 승인에는 관여하지 않는다.",
        bpm: "waiting 상태로 정지. 승인 이벤트가 있어야 전이한다.",
      };
    case "service-task":
      return {
        human: "결과 확인.",
        agent: "-",
        bpm: `${node.actor ?? "시스템"}이 자동 수행 후 전이.`,
      };
    case "gateway":
      return {
        human: "-",
        agent: "-",
        bpm: "조건 평가 후 한 경로만 선택. 선택되지 않은 경로는 skipped로 파생된다.",
      };
    default:
      return { human: "-", agent: "-", bpm: "프로세스 경계 이벤트." };
  }
}

/**
 * 입력 정보 — 이 장면이 무엇을 받아 일하는가.
 *
 * Agent 노드는 자기 실행 기록의 데이터 소스가 곧 입력이다. 사람·시스템 노드는 자기
 * 실행 기록이 없으므로 **선행 Agent 산출물**이 입력이 된다 — 경영진은 원천 데이터가
 * 아니라 Agent 보고서를 보고 판단하기 때문이다. 처음엔 이 경로를 빠뜨려 Management
 * Review의 입력이 "미정의"로 나왔다.
 */
function inputsOf(scenario: Scenario, node: BpmNodeSpec): string {
  const own = scenario.process.runs.find((r) => r.nodeId === node.id);
  if (own) return formatSources(own.sources);

  if (node.kind === "start") {
    return `${scenario.process.kri.label} 실측치 (임계 ${scenario.process.kri.threshold})`;
  }

  // 이 노드 앞에서 이미 완료된 Agent 산출물.
  const at = scenario.process.sequence.indexOf(node.id);
  const upstream = scenario.process.sequence
    .slice(0, at)
    .map((id) => scenario.process.runs.find((r) => r.nodeId === id))
    .filter((r) => r !== undefined);

  if (upstream.length === 0) return UNDEFINED_MARK;

  const parts = upstream.map((r) => {
    const agent = scenario.process.agents.find((a) => a.id === r.agentId);
    return `${agent?.name ?? r.agentId} 산출물 (신뢰도 ${r.confidence})`;
  });

  if (node.kind === "user-task") {
    parts.push(
      `Agent 보고서 ${scenario.reviewCase.report.length}절`,
      `대응 대안 ${scenario.reviewCase.alternatives.length}안 (효과·비용·위험·실행 조건)`,
    );
    if (scenario.reviewCase.escalations.length > 0) {
      parts.push(`Agent 미답 질문 ${scenario.reviewCase.escalations.length}건`);
    }
  }

  return parts.join(" · ");
}

/**
 * 검증 기준 — 이 장면의 산출이 맞다고 볼 근거.
 *
 * 코드에 있는 검증(불변식 assert, 신뢰도, 사유 필수)만 적고, 그 외에는 미정의로 남긴다.
 */
function verificationOf(
  process: BpmProcessInstance,
  node: BpmNodeSpec,
  scenario: Scenario,
): string {
  const run = process.runs.find((r) => r.nodeId === node.id);
  if (run) {
    const incomplete = run.sources.filter((s) => s.quality !== "complete").length;
    const escalations = run.escalations?.length ?? 0;
    return [
      `산출물 신뢰도 ${run.confidence}${run.confidenceNote ? ` (${run.confidenceNote})` : ""}`,
      `근거 소스 ${run.sources.length}건 중 불완전 ${incomplete}건`,
      escalations > 0
        ? `Agent 미답 질문 ${escalations}건 — 답을 받지 못한 채 진행 시의 가정을 명시함`
        : "Agent 미답 질문 없음",
    ].join(" · ");
  }

  switch (node.kind) {
    case "user-task":
      return `사유 ${DECISION_RATIONALE_MIN_LENGTH}자 이상 입력 시에만 승인 가능 (UI·API 양쪽에서 검증). 승인 시 결정 사유가 실행 과제에 함께 배포된다.`;
    case "gateway":
      return "선택된 경로 외 노드는 sequence에서 제외되어 skipped로 파생된다. 상태를 저장하지 않으므로 순서와 상태가 어긋날 수 없다.";
    case "service-task":
      return node.stage === "rolling-plan"
        ? "분기 합계 = 전사 Target·Forecast (assertQuartersBalance가 불일치 시 throw). 승인 과제는 미반영으로 잡혀 이중 계상되지 않는다."
        : UNDEFINED_MARK;
    case "start":
      return `KRI ${scenario.process.kri.label} 임계 ${scenario.process.kri.threshold} 이탈 여부로 판정.`;
    default:
      return UNDEFINED_MARK;
  }
}

export function sceneDesignRows(scenario: Scenario): SceneDesignRow[] {
  const chain = chainForRisk(managementFramework, scenario.riskId);

  return scenario.scenes.map((scene: DemoScene, index) => {
    const nodeId = scenario.process.sequence[scene.step];
    const node = scenario.process.nodes.find((n) => n.id === nodeId);
    if (!node) {
      throw new Error(`${scenario.id} 장면 ${index + 1}: 노드 ${nodeId}를 찾을 수 없다`);
    }

    const run = scenario.process.runs.find((r) => r.nodeId === node.id);
    const roles = rolesOf(scenario.process, node);

    return {
      sceneNo: index + 1,
      scene: scene.title,
      narration: scene.narration,
      startCondition: startConditionOf(scenario.process, node),
      process: `${MANAGEMENT_STAGE_LABEL[node.stage]} / ${node.label} (${KIND_LABEL[node.kind]})`,
      frameworkChain: chain
        ? [
            `Value Driver ${chain.driver.name}`,
            `KPI ${chain.kpi.label} ${chain.kpi.current}${chain.kpi.unit} (목표 ${chain.kpi.target}${chain.kpi.unit})`,
            `KRI ${chain.kri.label} ${chain.kri.current}${chain.kri.unit} (임계 ${chain.kri.threshold}${chain.kri.unit})`,
            `Control ${chain.controls
              .map(
                (c) =>
                  `${c.name}[${CONTROL_KIND_LABEL[c.kind]}/${CONTROL_STATUS_LABEL[c.status]}]`,
              )
              .join(", ")}`,
          ].join(" → ")
        : UNDEFINED_MARK,
      inputs: inputsOf(scenario, node),
      humanRole: roles.human,
      agentRole: roles.agent,
      bpmRole: roles.bpm,
      output: run?.output ?? node.outcome ?? UNDEFINED_MARK,
      verification: verificationOf(scenario.process, node, scenario),
    };
  });
}

/** 마크다운 셀 안전화 — 파이프와 줄바꿈이 표를 깨뜨린다. */
function cell(text: string): string {
  return text.replace(/\|/g, "\\|").replace(/\n+/g, " ");
}

export function sceneDesignMarkdown(scenarios: Scenario[]): string {
  const lines: string[] = [
    "# 장면별 설계표",
    "",
    "기획안 4.2가 요구하는 시나리오 설계 명세다. **이 문서는 구현에서 생성된다**",
    "(`services/scene-design.ts`) — 손으로 고치지 말고 데이터를 고친 뒤 다시 생성할 것.",
    "",
    "```bash",
    "curl -s http://localhost:3000/api/docs/scene-design > docs/scene-design.md",
    "```",
    "",
    `\`${UNDEFINED_MARK}\`로 표시된 칸은 코드에 근거가 없는 항목이다.`,
    "경영 판단 기준에 해당하므로 지어내지 않고 비워 두었다.",
    "",
  ];

  for (const scenario of scenarios) {
    lines.push(`## ${scenario.title}`, "");
    lines.push(`- 시나리오 id: \`${scenario.id}\``);
    lines.push(`- 연결 리스크: \`${scenario.riskId}\``);
    lines.push(`- 프로세스: \`${scenario.process.id}\``);
    lines.push("", `> ${scenario.summary}`, "");

    for (const row of sceneDesignRows(scenario)) {
      lines.push(`### 장면 ${row.sceneNo}. ${row.scene}`, "");
      lines.push(`> ${cell(row.narration)}`, "");
      lines.push("| 항목 | 내용 |", "|---|---|");
      lines.push(`| 시작 조건 | ${cell(row.startCondition)} |`);
      lines.push(`| 관련 프로세스 | ${cell(row.process)} |`);
      lines.push(`| KPI–KRI–Control | ${cell(row.frameworkChain)} |`);
      lines.push(`| 입력 정보 | ${cell(row.inputs)} |`);
      lines.push(`| 사람의 역할 | ${cell(row.humanRole)} |`);
      lines.push(`| Agent의 역할 | ${cell(row.agentRole)} |`);
      lines.push(`| BPM의 역할 | ${cell(row.bpmRole)} |`);
      lines.push(`| 출력 | ${cell(row.output)} |`);
      lines.push(`| 검증 기준 | ${cell(row.verification)} |`);
      lines.push("");
    }
  }

  return lines.join("\n");
}
