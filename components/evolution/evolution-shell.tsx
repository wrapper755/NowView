"use client";

import { useState } from "react";

import { KriTuningPanel } from "@/components/evolution/kri-tuning-panel";
import { ProposalList } from "@/components/evolution/proposal-list";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useDemoController } from "@/lib/store/demo-controller";
import { PROPOSAL_KIND_LABEL, type EvolutionLab, type ProposalStatus } from "@/lib/types/evolution";

/**
 * Evolution Lab의 클라이언트 경계.
 *
 * 채택/보류는 이 화면의 로컬 상태다 — 프레임워크 변경은 배포 절차를 타야 하므로
 * 여기서 전역 상태나 다른 화면을 바꾸지 않는다. 앞선 화면들(승인 → 과제 → Forecast)과
 * 달리 이 단계는 다음 루프부터 효력이 생긴다.
 */
export function EvolutionShell({ lab }: { lab: EvolutionLab }) {
  const [statusById, setStatusById] = useState<Record<string, ProposalStatus>>({});

  // 보고 있는 KRI도 시나리오가 지정하므로 스토어에서 읽는다.
  const activeKriId = useDemoController((s) => s.activeKriId);
  const setActiveKriId = useDemoController((s) => s.setActiveKri);

  const activeKri = lab.kris.find((k) => k.id === activeKriId) ?? lab.kris[0];
  const adoptedCount = Object.values(statusById).filter((s) => s === "adopted").length;

  return (
    <div className="space-y-4">
      <Card className="viz-root">
        <CardHeader>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <CardTitle className="text-base">KRI 감지 임계치 튜닝</CardTitle>
              <CardDescription>
                과거 데이터로 재현한 백테스트다. 임계치를 조이면 더 빨리 잡히지만 오탐도
                함께 늘어난다.
              </CardDescription>
            </div>

            {/* KRI가 둘뿐이라 탭 컴포넌트 대신 토글 버튼으로 둔다. */}
            <div
              role="tablist"
              aria-label="튜닝할 KRI"
              className="flex shrink-0 gap-1 rounded-lg border p-0.5"
            >
              {lab.kris.map((kri) => (
                <button
                  key={kri.id}
                  role="tab"
                  type="button"
                  aria-selected={kri.id === activeKriId}
                  onClick={() => setActiveKriId(kri.id)}
                  className={
                    kri.id === activeKriId
                      ? "rounded-md bg-muted px-2.5 py-1 text-xs font-medium text-foreground"
                      : "rounded-md px-2.5 py-1 text-xs text-muted-foreground hover:text-foreground"
                  }
                >
                  {kri.label}
                </button>
              ))}
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {/* 임계치가 스토어에 KRI별로 남으므로 리마운트로 초기화할 필요가 없다.
              탭을 오가도 각 KRI의 조정값이 유지된다. */}
          <KriTuningPanel kri={activeKri} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            개선 제안 {lab.proposals.length}건
            {adoptedCount > 0 ? (
              <span className="ml-2 text-xs font-normal text-muted-foreground">
                채택 {adoptedCount}건
              </span>
            ) : null}
          </CardTitle>
          <CardDescription>
            제안은 모두 이번 루프에서 실제로 드러난 공백에서 나왔다. 기대 효과와 부작용을
            함께 보고 판단한다.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ProposalList
            proposals={lab.proposals}
            statusById={statusById}
            onDecide={(id, status) => setStatusById((prev) => ({ ...prev, [id]: status }))}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">반영 이력</CardTitle>
          <CardDescription>
            이전 루프에서 채택되어 이미 적용된 항목과, 그 뒤 관측된 효과다.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ol className="space-y-0">
            {lab.applied.map((item) => (
              <li key={item.id} className="border-b py-3 first:pt-0 last:border-0 last:pb-0">
                <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                  <span className="text-[10px] text-muted-foreground tabular-nums">
                    {item.date}
                  </span>
                  <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
                    {PROPOSAL_KIND_LABEL[item.kind]}
                  </span>
                </div>
                <p className="mt-1 text-sm font-medium text-foreground">{item.summary}</p>
                <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">
                  {item.observedEffect}
                </p>
              </li>
            ))}
          </ol>
        </CardContent>
      </Card>
    </div>
  );
}
