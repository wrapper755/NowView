"use client";

import { ChevronLeft, ChevronRight, RotateCcw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { selectStepIndex, useDemoController } from "@/lib/store/demo-controller";
import { MANAGEMENT_STAGE_LABEL } from "@/lib/types/cockpit";
import type { BpmProcessInstance } from "@/lib/types/bpm";
import { currentStage, maxStepIndex, progressPercent } from "@/services/bpm-engine";

/**
 * 프로세스 진행 지점 이동.
 *
 * 전역 플로팅 데모 플레이어(`components/demo/`)는 아직 없다. 같은 Zustand 스토어를 쓰므로
 * 나중에 플레이어가 붙어도 이 컨트롤과 상태가 어긋나지 않는다.
 */
export function StepControls({ process }: { process: BpmProcessInstance }) {
  const stepIndex = useDemoController(selectStepIndex);
  const next = useDemoController((s) => s.next);
  const prev = useDemoController((s) => s.prev);
  const reset = useDemoController((s) => s.reset);

  const max = maxStepIndex(process);
  const stage = currentStage(process, stepIndex);
  const percent = progressPercent(process, stepIndex);

  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div className="min-w-0 space-y-1.5">
        <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1 text-xs">
          <span className="text-muted-foreground tabular-nums">
            단계 {stepIndex + 1} / {max + 1}
          </span>
          {stage ? (
            <span className="rounded bg-muted px-1.5 py-0.5 font-medium text-foreground">
              {MANAGEMENT_STAGE_LABEL[stage]}
            </span>
          ) : null}
        </div>
        <div
          className="h-1 w-48 overflow-hidden rounded-full bg-muted"
          role="progressbar"
          aria-valuenow={Math.round(percent)}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label="프로세스 진행률"
        >
          <div
            className="h-full rounded-full"
            style={{ width: `${percent}%`, backgroundColor: "var(--viz-series-1)" }}
          />
        </div>
      </div>

      <div className="flex items-center gap-1.5">
        <Button variant="outline" size="sm" onClick={reset} disabled={stepIndex === 0}>
          <RotateCcw aria-hidden className="size-3.5" />
          처음으로
        </Button>
        <Button variant="outline" size="sm" onClick={prev} disabled={stepIndex === 0}>
          <ChevronLeft aria-hidden className="size-3.5" />
          이전
        </Button>
        <Button size="sm" onClick={next} disabled={stepIndex >= max}>
          다음
          <ChevronRight aria-hidden className="size-3.5" />
        </Button>
      </div>
    </div>
  );
}
