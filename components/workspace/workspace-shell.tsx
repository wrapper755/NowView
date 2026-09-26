"use client";

import { useState } from "react";

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

/**
 * 협업 스테이션의 클라이언트 경계.
 *
 * 선택 대안과 레버 값은 로컬 상태다 — 승인 전까지는 이 화면 안의 검토 과정일 뿐이다.
 * 승인된 결정만 전역 스토어로 올라가고, 그 순간 ② 트래커의 진행 지점도 함께 움직인다.
 */
export function WorkspaceShell() {
  const scenario = useDemoController(selectScenario);
  const reviewCase = scenario.reviewCase;
  const decision = useDemoController(selectDecision);
  const approve = useDemoController((s) => s.approve);
  const clearDecision = useDemoController((s) => s.clearDecision);

  // 승인 후에는 결정된 대안을 보여 준다. 그 전에는 Agent 권고안에서 출발한다.
  const [selectedId, setSelectedId] = useState(reviewCase.recommendedAlternativeId);
  const activeId = decision?.alternativeId ?? selectedId;
  const alternative =
    reviewCase.alternatives.find((a) => a.id === activeId) ?? reviewCase.alternatives[0];

  const [leverValue, setLeverValue] = useState(alternative.lever.base);
  const activeLeverValue = decision?.leverValue ?? leverValue;

  const locked = decision !== null;

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
              decision={decision}
              onApprove={approve}
              onClear={clearDecision}
            />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
