"use client";

import { useState } from "react";
import { CheckCircle2, RotateCcw, ShieldCheck } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { Textarea } from "@/components/ui/textarea";
import { formatEok, formatEokSigned } from "@/lib/format";
import {
  DECISION_RATIONALE_MIN_LENGTH,
  type Alternative,
  type ReviewDecision,
} from "@/lib/types/workspace";
import { simulateAlternative } from "@/services/agent-orchestrator";

/** 결정 시각 표시용. 클릭 시점에만 계산하므로 서버 렌더와 어긋날 일이 없다. */
function stampNow(): string {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/**
 * 의사결정 패널 — 이 화면의 책임 경계가 드러나는 곳.
 *
 * Agent가 아무리 좋은 권고를 내놔도 승인 버튼은 사유 없이는 눌리지 않는다.
 * 최종 판단의 책임이 사람에게 있다는 원칙(CLAUDE.md 1장)을 UI 제약으로 못 박은 것이다.
 */
export function DecisionPanel({
  alternative,
  leverValue,
  profitGap,
  decision,
  onApprove,
  onClear,
  pending = false,
  rejection,
  notAwaiting = false,
}: {
  alternative: Alternative;
  leverValue: number;
  profitGap: number;
  decision: ReviewDecision | null;
  onApprove: (decision: ReviewDecision) => void;
  onClear: () => void;
  /** 엔진에 재개 요청을 보내는 중. 두 번 눌리는 것을 막는다. */
  pending?: boolean;
  /**
   * 엔진이 승인 입력을 반려한 이유.
   *
   * **오류가 아니라 상태다** — 같은 지점에 다시 멈춘 것이므로 입력한 내용을 지우지 않고
   * 무엇이 틀렸는지만 덧붙인다. UI 검사(`canApprove`)를 통과해도 엔진이 거부할 수 있고
   * (버튼 비활성은 강제가 아니다), 그때 사람에게 보여 줄 문구가 필요하다.
   */
  rejection?: string;
  /** 엔진 모드인데 지금 이 단계가 승인 지점이 아니다. */
  notAwaiting?: boolean;
}) {
  const [rationale, setRationale] = useState("");
  const result = simulateAlternative(alternative, leverValue);
  const canApprove = rationale.trim().length >= DECISION_RATIONALE_MIN_LENGTH && !pending;

  if (decision) {
    return <DecisionRecord decision={decision} profitGap={profitGap} onClear={onClear} />;
  }

  if (notAwaiting) {
    // 실행 중인 그래프에서는 아무 때나 승인할 수 없다. 대기 지점이 아닌데 입력란을
    // 띄우면 "지금 결재할 수 있다"는 잘못된 인상을 준다.
    return (
      <p className="text-sm text-muted-foreground">
        지금은 승인 지점이 아니다. Agent가 수행 중이거나 이 단계를 이미 지났다 —
        프로세스가 승인 노드에 도달하면 여기서 결재할 수 있다.
      </p>
    );
  }

  return (
    <div className="space-y-4">
      <div className="space-y-1.5">
        <p className="text-xs text-muted-foreground">선택한 대안</p>
        <p className="text-sm font-semibold text-foreground">
          {alternative.tag} {alternative.name}
          <span className="ml-2 text-xs font-normal text-muted-foreground tabular-nums">
            {alternative.lever.label} {leverValue}
            {alternative.lever.unit} · 영업이익 {formatEokSigned(result.profitImpact)}
          </span>
        </p>
      </div>

      <Separator />

      <div className="space-y-2">
        <Label htmlFor="decision-rationale" className="text-xs">
          결정 사유
          <span className="ml-1 font-normal text-muted-foreground">
            (필수 · {DECISION_RATIONALE_MIN_LENGTH}자 이상)
          </span>
        </Label>
        <Textarea
          id="decision-rationale"
          value={rationale}
          onChange={(e) => setRationale(e.target.value)}
          rows={4}
          placeholder="이 대안을 선택한 근거와 감수하기로 한 리스크를 적는다."
          className="text-xs"
        />
        <p className="text-[11px] leading-relaxed text-muted-foreground">
          사유는 Management Action에 함께 배포되고 Rolling Plan 갱신 이력에 남는다.
          Agent 권고를 따르지 않은 경우 그 이유가 특히 중요하다.
        </p>
      </div>

      <Button
        className="w-full"
        disabled={!canApprove}
        onClick={() =>
          onApprove({
            alternativeId: alternative.id,
            leverValue,
            profitImpact: result.profitImpact,
            rationale: rationale.trim(),
            decidedAt: stampNow(),
          })
        }
      >
        <ShieldCheck aria-hidden className="size-4" />
        {pending ? "재개 요청 중…" : "승인하고 실행 과제로 배포"}
      </Button>

      {rejection ? (
        <p
          role="alert"
          className="rounded border p-2 text-[11px]"
          style={{ borderColor: "var(--viz-status-serious)" }}
        >
          엔진이 승인 입력을 반려했다 — {rejection}
        </p>
      ) : null}

      {!canApprove && !pending ? (
        <p className="text-center text-[11px] text-muted-foreground">
          사유를 입력해야 승인할 수 있다.
        </p>
      ) : null}
    </div>
  );
}

/** 승인 후 상태 — 결정 내용과 그 결과로 만들어질 실행 과제를 보여 준다. */
function DecisionRecord({
  decision,
  profitGap,
  onClear,
}: {
  decision: ReviewDecision;
  profitGap: number;
  onClear: () => void;
}) {
  const remainingGap = profitGap + decision.profitImpact;

  return (
    <div className="space-y-4">
      <div className="flex items-start gap-2">
        <CheckCircle2
          aria-hidden
          className="mt-0.5 size-4 shrink-0"
          style={{ color: "var(--viz-status-good)" }}
        />
        <div className="min-w-0">
          <p className="text-sm font-medium text-foreground">승인 완료</p>
          <p className="mt-0.5 text-[11px] text-muted-foreground tabular-nums">
            {decision.decidedAt} · BPM 프로세스가 Management Action 단계로 이동했다.
          </p>
        </div>
      </div>

      <Separator />

      <dl className="space-y-2 text-xs">
        <div className="flex gap-2">
          <dt className="w-20 shrink-0 text-muted-foreground">목표 회수액</dt>
          <dd className="font-medium text-foreground tabular-nums">
            {formatEokSigned(decision.profitImpact)}
          </dd>
        </div>
        <div className="flex gap-2">
          <dt className="w-20 shrink-0 text-muted-foreground">잔여 Gap</dt>
          <dd className="text-foreground tabular-nums">
            {formatEok(remainingGap)}
            <span className="ml-1.5 text-[11px] text-muted-foreground">
              (승인 전 {formatEok(profitGap)})
            </span>
          </dd>
        </div>
        <div className="flex gap-2">
          <dt className="w-20 shrink-0 text-muted-foreground">결정 사유</dt>
          <dd className="min-w-0 leading-relaxed text-foreground">{decision.rationale}</dd>
        </div>
      </dl>

      <p className="text-[11px] leading-relaxed text-muted-foreground">
        잔여 Gap은 여전히 남아 있다. Rolling Plan에서 이 효과를 반영한 Forecast와 남은 Gap을
        계속 관리한다 — 목표(Target)는 바꾸지 않는다.
      </p>

      <Button variant="outline" className="w-full" onClick={onClear}>
        <RotateCcw aria-hidden className="size-4" />
        데모 되돌리기
      </Button>
    </div>
  );
}
