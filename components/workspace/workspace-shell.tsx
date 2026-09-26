"use client";

import { useState } from "react";

import { AgentReportViewer } from "@/components/workspace/agent-report-viewer";
import { AlternativeComparison } from "@/components/workspace/alternative-comparison";
import { DecisionPanel } from "@/components/workspace/decision-panel";
import { SimulatorPanel } from "@/components/workspace/simulator-panel";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useDemoController } from "@/lib/store/demo-controller";
import type { ReviewCase } from "@/lib/types/workspace";

/**
 * 협업 스테이션의 클라이언트 경계.
 *
 * 선택 대안과 레버 값은 로컬 상태다 — 승인 전까지는 이 화면 안의 검토 과정일 뿐이다.
 * 승인된 결정만 전역 스토어로 올라가고, 그 순간 ② 트래커의 진행 지점도 함께 움직인다.
 */
export function WorkspaceShell({ reviewCase }: { reviewCase: ReviewCase }) {
  const decision = useDemoController((s) => s.decision);
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
