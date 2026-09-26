"use client";

import { useMemo, useState } from "react";

import { EnginePanel } from "@/components/engine/engine-panel";
import { useEngineProcess } from "@/components/engine/use-engine-process";
import { AgentReportViewer } from "@/components/workspace/agent-report-viewer";
import { AlternativeComparison } from "@/components/workspace/alternative-comparison";
import { DecisionPanel } from "@/components/workspace/decision-panel";
import { SimulatorPanel } from "@/components/workspace/simulator-panel";
import { EscalationCard } from "@/components/shared/data-source";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import Link from "next/link";
import { ArrowUpRight } from "lucide-react";

import { formatEok } from "@/lib/format";
import {
  selectDecision,
  selectScenario,
  useDemoController,
} from "@/lib/store/demo-controller";
import type { ReviewDecision } from "@/lib/types/workspace";
import { engineDecisionToReview } from "@/services/engine-view";

/**
 * 협업 스테이션의 클라이언트 경계.
 *
 * 선택 대안과 레버 값은 로컬 상태다 — 승인 전까지는 이 화면 안의 검토 과정일 뿐이다.
 * 승인된 결정만 전역 스토어로 올라가고, 그 순간 ② 트래커의 진행 지점도 함께 움직인다.
 *
 * **엔진 모드에서는 승인이 실제로 워크플로를 재개한다.** Mock 경로의 `approve`는
 * 스토어에 기록하고 진행 지점을 옮기는 순수 상태 변경이지만, 엔진에서는 `interrupt`로
 * 멈춰 있는 실행에 `resume`을 보낸다 — 승인이 프로세스를 움직이는 경로가 처음 생긴다.
 */
export function WorkspaceShell() {
  const scenario = useDemoController(selectScenario);
  const reviewCase = scenario.reviewCase;
  const decision = useDemoController(selectDecision);
  const approve = useDemoController((s) => s.approve);
  const clearDecision = useDemoController((s) => s.clearDecision);
  const engine = useEngineProcess(scenario.id, scenario.process);
  const engineApproval = engine.snapshot?.pendingApproval ?? null;
  const engineDecision = engine.snapshot?.decision ?? null;

  // 승인 후에는 결정된 대안을 보여 준다. 그 전에는 Agent 권고안에서 출발한다.
  const [selectedId, setSelectedId] = useState(reviewCase.recommendedAlternativeId);
  const [leverValue, setLeverValue] = useState(
    () => reviewCase.alternatives.find((a) => a.id === reviewCase.recommendedAlternativeId)!.lever.base,
  );

  /**
   * 시나리오가 바뀌면 선택과 레버를 그 시나리오의 권고안으로 되돌린다.
   *
   * **이것이 없으면 다른 시나리오의 대안을 승인한다.** `useState`는 첫 렌더 값만
   * 쓰는데, 화면은 정적 프리렌더라 첫 렌더가 항상 기본 시나리오다. 스토어가 복원되며
   * 시나리오가 바뀌어도 `selectedId`는 옛 시나리오의 id로 남고, 새 시나리오의 대안
   * 목록에 그 id가 없으니 `alternatives[0]`으로 떨어진다 — 실제로 시나리오 3에서
   * 권고안(3안)이 아니라 1안이 승인됐다. 레버도 옛 시나리오의 기본값이 남는다.
   *
   * effect로 고치면 `react-hooks/set-state-in-effect`에 걸린다. 렌더 중 조정은
   * React가 문서화한 패턴이며, 즉시 다시 렌더되고 자식은 그려지지 않는다.
   */
  const [trackedScenarioId, setTrackedScenarioId] = useState(scenario.id);
  if (trackedScenarioId !== scenario.id) {
    const recommended = reviewCase.alternatives.find(
      (a) => a.id === reviewCase.recommendedAlternativeId,
    )!;
    setTrackedScenarioId(scenario.id);
    setSelectedId(recommended.id);
    setLeverValue(recommended.lever.base);
  }

  // 엔진 모드에서는 서버가 소유한 결정이 우선이다 — 스토어의 결정은 Mock 경로의 것이다.
  const activeId = engine.view
    ? (engineDecision?.alternativeId ?? selectedId)
    : (decision?.alternativeId ?? selectedId);
  const alternative =
    reviewCase.alternatives.find((a) => a.id === activeId) ?? reviewCase.alternatives[0];

  const activeLeverValue = engine.view
    ? (engineDecision?.leverValue ?? leverValue)
    : (decision?.leverValue ?? leverValue);

  // 엔진 모드의 잠금은 "결정이 기록되었는가"가 아니라 "지금 내 결재가 걸려 있는가"다.
  // 승인 지점이 아니면(아직 Agent가 돌고 있거나 이미 지나갔으면) 고를 것이 없다.
  const engineAwaitingDecision = engineApproval?.kind === "decision";
  const locked = engine.view ? !engineAwaitingDecision : decision !== null;

  // 변환은 ④ Rolling Plan과 같은 함수를 쓴다 — 각자 변환하면 이 화면의 금액과
  // 과제 목표액이 갈라질 수 있고, 그건 눈으로 잡히지 않는다.
  const engineReviewDecision = useMemo(
    () => engineDecisionToReview(reviewCase, engineDecision),
    [engineDecision, reviewCase],
  );

  /**
   * 승인. 모드에 따라 가는 곳이 다르다.
   *
   * Mock은 스토어에 기록하고 진행 지점을 옮기는 순수 상태 변경이다. 엔진은 멈춰 있는
   * 실행에 `resume`을 보내고, 사유가 짧으면 **거부가 아니라 같은 지점에 다시 멈춘
   * 상태**가 돌아온다 — 그 경우 입력한 내용을 지우지 않고 반려 사유만 덧붙인다.
   */
  async function handleApprove(next: ReviewDecision) {
    if (!engine.view || !engine.instanceId) {
      approve(next);
      return;
    }
    await engine.resume(engine.instanceId, {
      alternativeId: next.alternativeId,
      leverValue: next.leverValue,
      rationale: next.rationale,
    });
  }

  // 대안을 바꾸면 레버 범위·단위가 달라지므로 그 대안의 제안값에서 다시 시작한다.
  function handleSelect(id: string) {
    const next = reviewCase.alternatives.find((a) => a.id === id);
    if (!next) return;
    setSelectedId(id);
    setLeverValue(next.lever.base);
  }

  return (
    <div className="space-y-4">
      <header className="space-y-2">
        <div className="flex flex-wrap items-baseline gap-x-2.5 gap-y-1">
          <h1 className="text-xl font-semibold">Human-Agent Collaboration Station</h1>
          <span className="text-sm text-muted-foreground">{reviewCase.subject}</span>
        </div>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-xs text-muted-foreground">
          <span className="rounded bg-muted px-1.5 py-0.5 text-foreground">
            {scenario.shortTitle}
          </span>
          <span className="tabular-nums">
            전사 영업이익 Gap{" "}
            <span className="font-medium text-foreground">
              {formatEok(reviewCase.profitGap)}
            </span>
          </span>
          <span className="font-mono text-[10px]">{reviewCase.processId}</span>
          <Link
            href="/bpm-tracker"
            className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 font-medium text-foreground hover:bg-muted"
          >
            프로세스에서 이 단계 보기
            <ArrowUpRight aria-hidden className="size-3" />
          </Link>
        </div>
      </header>

      {/* ②와 같은 인스턴스를 본다 — 트래커에서 실행한 프로세스를 여기서 승인한다. */}
      <EnginePanel {...engine.panelProps} />

      {/* 미답 질문은 결정의 전제다. 보고서보다 먼저 보여야 "무엇을 모른 채 결정하는지"를 안다. */}
      {reviewCase.escalations.length > 0 ? (
        <Card className="viz-root">
          <CardHeader>
            <CardTitle className="text-base">
              Agent가 답하지 못한 질문 {reviewCase.escalations.length}건
            </CardTitle>
            <CardDescription>
              정보가 부족할 때 Agent는 추측하지 않고 사람에게 묻는다. 답을 받지 못한 채
              진행하면 아래 가정 위에서 결정하는 것이며, 그 가정이 틀리면 권고도 함께
              무너진다.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="space-y-2">
              {reviewCase.escalations.map((escalation) => (
                <EscalationCard key={escalation.id} escalation={escalation} />
              ))}
            </ul>
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Agent 분석 보고서</CardTitle>
          <CardDescription>
            Agent가 수집·분석한 내용과 그 근거다. 결론만이 아니라 무엇을 보고 그렇게
            말했는지 확인할 수 있어야 한다.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <AgentReportViewer report={reviewCase.report} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">대안 비교</CardTitle>
          <CardDescription>
            Agent 제안 기본값 기준이다. 열 머리를 눌러 검토할 대안을 고른다.
            {locked ? " 승인 후에는 변경할 수 없다." : null}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <AlternativeComparison
            alternatives={reviewCase.alternatives}
            recommendedId={reviewCase.recommendedAlternativeId}
            selectedId={activeId}
            onSelect={handleSelect}
            disabled={locked}
          />
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="viz-root lg:col-span-2">
          <CardHeader>
            <CardTitle className="text-base">
              시뮬레이터 — {alternative.tag} {alternative.name}
            </CardTitle>
            <CardDescription>
              가정을 바꿔 가며 손익·가동률·리스크를 다시 계산한다. 대안 하나로 Gap이 모두
              메워지지는 않는다.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <SimulatorPanel
              alternative={alternative}
              leverValue={activeLeverValue}
              onLeverChange={setLeverValue}
              profitGap={reviewCase.profitGap}
              disabled={locked}
            />
          </CardContent>
        </Card>

        <Card className="viz-root lg:col-span-1">
          <CardHeader>
            <CardTitle className="text-base">의사결정</CardTitle>
            <CardDescription>
              선택과 승인은 사람이 한다. Agent 권고는 참고일 뿐이다.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <DecisionPanel
              alternative={alternative}
              leverValue={activeLeverValue}
              profitGap={reviewCase.profitGap}
              decision={engine.view ? engineReviewDecision : decision}
              onApprove={handleApprove}
              onClear={clearDecision}
              pending={engine.pending}
              rejection={engineApproval?.error}
              notAwaiting={engine.view !== null && !engineAwaitingDecision && !engineDecision}
            />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
