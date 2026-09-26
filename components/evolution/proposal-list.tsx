"use client";

import { ArrowRight, Check, CircleDashed, PauseCircle, type LucideIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";
import {
  PROPOSAL_KIND_LABEL,
  PROPOSAL_STATUS_LABEL,
  type EvolutionProposal,
  type ProposalStatus,
} from "@/lib/types/evolution";

const STATUS_ICON: Record<ProposalStatus, LucideIcon> = {
  proposed: CircleDashed,
  adopted: Check,
  deferred: PauseCircle,
};

const STATUS_COLOR: Record<ProposalStatus, string> = {
  proposed: "var(--color-muted-foreground)",
  adopted: "var(--viz-status-good)",
  deferred: "var(--viz-status-warning)",
};

/**
 * 개선 제안 목록.
 *
 * 제안마다 before → after와 **부작용**을 나란히 둔다. 기대 효과만 적힌 제안은 검토가
 * 아니라 홍보다 — 임계치를 조이면 오탐이 늘고, 분해 축을 늘리면 주 원인이 흐려진다.
 *
 * 채택 여부는 이 화면의 로컬 상태다. 실제 반영은 프레임워크 배포 절차를 타야 하므로
 * 여기서 전역 상태를 바꾸지 않는다.
 */
export function ProposalList({
  proposals,
  statusById,
  onDecide,
}: {
  proposals: EvolutionProposal[];
  statusById: Record<string, ProposalStatus>;
  onDecide: (id: string, status: ProposalStatus) => void;
}) {
  return (
    <ul className="space-y-3">
      {proposals.map((proposal) => {
        const status = statusById[proposal.id] ?? "proposed";
        const Icon = STATUS_ICON[status];
        const decided = status !== "proposed";

        return (
          <li
            key={proposal.id}
            className={cn("rounded-lg border p-3.5", decided && "bg-muted/30")}
          >
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
              <span className="inline-flex items-center gap-1.5 text-xs font-medium text-foreground">
                <Icon
                  aria-hidden
                  className="size-3.5 shrink-0"
                  style={{ color: STATUS_COLOR[status] }}
                />
                {PROPOSAL_STATUS_LABEL[status]}
              </span>
              <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
                {PROPOSAL_KIND_LABEL[proposal.kind]}
              </span>
            </div>

            <h4 className="mt-1.5 text-sm font-semibold text-foreground">{proposal.title}</h4>
            <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
              {proposal.rationale}
            </p>

            <div className="mt-2.5 flex flex-wrap items-center gap-2 text-[11px]">
              <span className="rounded border px-1.5 py-1 text-muted-foreground line-through decoration-muted-foreground/40">
                {proposal.before}
              </span>
              <ArrowRight aria-hidden className="size-3 shrink-0 text-muted-foreground" />
              <span className="rounded border px-1.5 py-1 font-medium text-foreground">
                {proposal.after}
              </span>
            </div>

            <Separator className="my-3" />

            <dl className="space-y-1.5 text-[11px]">
              <div className="flex gap-2">
                <dt className="w-16 shrink-0 text-muted-foreground">기대 효과</dt>
                <dd className="min-w-0 leading-relaxed text-foreground">
                  {proposal.expectedEffect}
                </dd>
              </div>
              <div className="flex gap-2">
                <dt className="w-16 shrink-0 text-muted-foreground">부작용</dt>
                <dd className="min-w-0 leading-relaxed text-foreground">{proposal.tradeoff}</dd>
              </div>
              <div className="flex gap-2">
                <dt className="w-16 shrink-0 text-muted-foreground">담당</dt>
                <dd className="min-w-0 text-muted-foreground">{proposal.owner}</dd>
              </div>
            </dl>

            <div className="mt-3 flex flex-wrap items-center gap-1.5">
              {decided ? (
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 text-[11px]"
                  onClick={() => onDecide(proposal.id, "proposed")}
                >
                  결정 취소
                </Button>
              ) : (
                <>
                  <Button
                    size="sm"
                    className="h-7 text-[11px]"
                    onClick={() => onDecide(proposal.id, "adopted")}
                  >
                    <Check aria-hidden className="size-3" />
                    채택
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    className="h-7 text-[11px]"
                    onClick={() => onDecide(proposal.id, "deferred")}
                  >
                    <PauseCircle aria-hidden className="size-3" />
                    보류
                  </Button>
                </>
              )}
            </div>
          </li>
        );
      })}
    </ul>
  );
}
