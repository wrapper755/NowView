"use client";

import { useUserName } from "@/components/sc01/bits";
import { Sc02Body, Sc02Header, StatusPills, WaitingForms } from "@/components/sc02/bits";
import { Commentary } from "@/components/shared/commentary";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatClock, modelLabel } from "@/lib/sc01/format";
import { APPROVAL_STATUS_LABEL, COST_STATUS_LABEL } from "@/lib/sc02/format";
import type { Sc02View } from "@/lib/sc02/types";

const won = (v: string) => `${Number(v).toLocaleString("ko-KR")}원`;

/**
 * U26 승인 조건 및 원가 적용 등록 — 최종 승인된 품목·단가·적용일·모델 범위만 등록한다. 승인과 다른 값을 직접
 * 등록하지 않는다(기안 변경 절차로). C01은 보존하고 **대상 부품 부분만** 바꾼다(COST-01).
 */
export function Sc02CostScreen() {
  return (
    <main className="viz-root mx-auto w-full max-w-7xl space-y-8 px-4 py-8 sm:px-6 lg:px-8">
      <Sc02Header id="U26" title="승인 조건 · 원가 적용 등록" question="승인된 조건이 그대로 새 원가 기준이 되었는가?" />
      <Sc02Body>{(view) => <Cost view={view} />}</Sc02Body>
    </main>
  );
}

function Cost({ view }: { view: Sc02View }) {
  const name = useUserName();
  const approved = view.proposals.find((p) => p.status === "APPROVED");
  const cv = view.costVersions.at(-1);
  return (
    <>
      <StatusPills view={view} />
      <WaitingForms view={view} nodes={["Register_Cost"]} labels={{ Register_Cost: "원가 버전 등록" }} />

      <Card>
        <CardHeader>
          <CardTitle>최종 승인 근거</CardTitle>
          <CardDescription>
            {approved
              ? `${approved.proposal_key} · ${formatClock(approved.approved_at)} · 최종 결재 ${approved.final_step === "EXEC" ? "구매임원(대표 비대상)" : "대표이사"}`
              : view.instruction
                ? "추가 협상지시 중 — 미승인. 원가를 등록할 수 없다"
                : `아직 승인 전 — ${APPROVAL_STATUS_LABEL[view.status.approval ?? ""] ?? "상신 전"}`}
          </CardDescription>
        </CardHeader>
        {approved ? (
          <CardContent className="text-sm">
            승인 단가 {won(approved.price)} · 적용일 {approved.effective_date} · 대상 a·b모델(P-COM01 각 1개)
          </CardContent>
        ) : null}
      </Card>

      {cv ? (
        <Card>
          <CardHeader>
            <CardTitle>원가 버전 {cv.cost_version_id}</CardTitle>
            <CardDescription>
              {COST_STATUS_LABEL[cv.status]} · {cv.effective_from}부터 · 부모 {cv.parent_cost_version}(보존) · 등록 {name(cv.registered_by)}{" "}
              {formatClock(cv.registered_at)}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[36rem] text-sm" aria-label="모델별 외주비 C01 대비 신규 원가">
                <thead>
                  <tr className="border-b text-left text-xs text-muted-foreground">
                    <th scope="col" className="py-2 pr-3 font-medium">모델</th>
                    <th scope="col" className="py-2 pr-3 text-right font-medium">소요량</th>
                    <th scope="col" className="py-2 pr-3 text-right font-medium">C01 외주비</th>
                    <th scope="col" className="py-2 pr-3 text-right font-medium">그중 공통부품</th>
                    <th scope="col" className="py-2 pr-3 text-right font-medium">승인 부품원가</th>
                    <th scope="col" className="py-2 text-right font-medium">신규 외주비</th>
                  </tr>
                </thead>
                <tbody>
                  {cv.models.map((m) => (
                    <tr key={m.model_id} className="border-b">
                      <th scope="row" className="py-2 pr-3 text-left font-normal">{modelLabel(m.model_id)}</th>
                      <td className="py-2 pr-3 text-right tabular-nums">{Number(m.qty_per)}</td>
                      <td className="py-2 pr-3 text-right tabular-nums">{won(m.outsource_before)}</td>
                      <td className="py-2 pr-3 text-right tabular-nums">{won(m.part_before)}</td>
                      <td className="py-2 pr-3 text-right tabular-nums">{won(m.part_after)}</td>
                      <td className="py-2 text-right font-medium tabular-nums">
                        {won(m.outsource_after)}
                        {m.outsource_after === m.outsource_before ? <span className="block text-[11px] font-normal text-muted-foreground">변동 없음</span> : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Commentary block>
              <p className="text-xs text-muted-foreground">
                적용일이 와도 사람 승인이나 전망 승인 이벤트가 아니다 — 상태만 「적용 중」으로 바뀐다. 공식 F02·Target은 그대로다.
              </p>
            </Commentary>
          </CardContent>
        </Card>
      ) : null}
    </>
  );
}
