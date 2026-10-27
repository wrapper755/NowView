"use client";

import { CheckCircle2, CircleDashed } from "lucide-react";

import { RiskTag, useUserName } from "@/components/sc01/bits";
import { BridgeTable } from "@/components/sc02/analysis-parts";
import { AgentCard } from "@/components/sc02/analysis-screen";
import { Sc02Body, Sc02Header, StatusPills, WaitingForms, Won } from "@/components/sc02/bits";
import { Commentary } from "@/components/shared/commentary";
import { Disclosure } from "@/components/shared/disclosure";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatClock, modelLabel } from "@/lib/sc01/format";
import { HANDOFF_STATUS_LABEL, KIND_LABEL } from "@/lib/sc02/format";
import type { Sc02View } from "@/lib/sc02/types";

const CONDITION_LABEL: Record<string, string> = {
  approved: "필요 승인 완료",
  cost_registered: "C02 원가 등록",
  run_matches_approval: "승인 조건 = 분석 run = 원가",
  sc01_run_valid: "고객 생산계획 변경 대응 run 유효(F02 검토 중)",
  evidence_complete: "원천·보고·협상·기안·승인 근거",
  no_renegotiation: "추가 협상지시 없음",
};

/**
 * U27 통합 영향 · 장면 3 인계 — 기준손익 → 물량효과 → 추가 원가효과 → 통합손익. **한 안만 고른다**(HAND-03):
 * 승인안이 있으면 그것, 없으면 최신 안을 **잠정**으로 보인다. 물량·원가 사건은 각각의 id로 상위 검토건에 걸린다.
 */
export function Sc02HandoffScreen() {
  return (
    <main className="viz-root mx-auto w-full max-w-7xl space-y-8 px-4 py-8 sm:px-6 lg:px-8">
      <Sc02Header id="U27" title="통합 영향 · 수익성 통합 분석 인계" question="물량 감소와 단가 인상의 영향을 중복 없이 연결해 넘겼는가?" />
      <Sc02Body>{(view) => <Handoff view={view} />}</Sc02Body>
    </main>
  );
}

function Handoff({ view }: { view: Sc02View }) {
  const name = useUserName();
  const run = view.runs.find((r) => r.run_id === view.selectedRunId);
  const h = view.handoff;
  const year = run?.result.periods.find((p) => p.kind === "year");
  return (
    <>
      <StatusPills view={view} />
      <WaitingForms
        view={view}
        nodes={["Request_Handoff", "Accept_Handoff"]}
        initial={{ Request_Handoff: { 경영관리담당자: "u-fin" } }}
        expect={h ? { bundle: h.bundle_hash } : undefined}
        labels={{ Request_Handoff: "인계 요청", Accept_Handoff: "인수" }}
      />

      <Card>
        <CardHeader>
          <CardTitle>수익성 검토건 {view.review.review_id}</CardTitle>
          <CardDescription>울산 A제품 수익성 통합검토 — 두 사건을 각각 유지한다(원가 사건으로 물량 이슈를 덮지 않는다).</CardDescription>
        </CardHeader>
        <CardContent>
          <ul className="grid gap-2 sm:grid-cols-2">
            {view.review.links.map((l) => (
              <li key={l.issue_id} className="rounded-md border px-3 py-2 text-sm">
                <p className="flex flex-wrap items-center gap-2">
                  <span className="font-mono">{l.issue_id}</span>
                  <span className="text-xs text-muted-foreground">{l.issue_type === "VOLUME" ? "고객 생산계획 변경 대응 물량" : "외주 단가 인상 검토 원가"}</span>
                  <RiskTag risk={l.issue_type === "VOLUME" ? view.sc01.issue.risk : (view.issue?.risk ?? null)} />
                </p>
                <p className="text-xs text-muted-foreground">
                  최신 근거 <span className="font-mono">{l.latest_run_id}</span> · 위험 열림
                </p>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>

      {run ? (
        <Card>
          <CardHeader>
            <CardTitle>
              통합 영향 — {KIND_LABEL[run.kind]} {run.result.new_price ? `${Number(run.result.new_price).toLocaleString("ko-KR")}원` : ""}
            </CardTitle>
            <CardDescription>
              {view.selectedProvisional ? "잠정 — 승인 전 자료다. 최종 인계가 아니다" : "승인안 기준"} ·{" "}
              <span className="font-mono">{run.run_id}</span> + <span className="font-mono">{view.sc01.run_id}</span> · 금액은 원,
              공장관리손익(전사 영업이익 아님)
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {year?.computable ? (
              <p className="text-sm">
                2027년: 기준 <Won value={year.profit_f01} /> → 물량 <Won value={year.volume_effect} signed /> → 단가{" "}
                <Won value={year.cost_effect} signed /> = 통합 <span className="font-semibold"><Won value={year.profit_combined} /></span>
                . Target 대비 부족 <Won value={year.target_gap} />
                <span className="block text-xs text-muted-foreground">
                  부족액 전체가 두 사건 때문이 아니다 — 두 사건 합계는 <Won value={year.total_change} />이다.
                </span>
              </p>
            ) : null}
            <BridgeTable periods={run.result.periods} kinds={["quarter", "remaining", "year", "next12"]} />
            <Commentary block>
              <p className="text-xs text-muted-foreground">
                고객 생산계획 변경 대응의 2027 물량효과 −1,400만원은 2027 영역에서만 그대로 쓴다. 12개월 값은 월별로 다시 모은 결과이고, 2028 물량은
                내부가정(F01 × 97%)이며 2028 Target이 없어 12개월 Target 차이는 미산출이다.
              </p>
            </Commentary>
            <Disclosure summary="2027 Q3 모델별 공헌이익 (고정비 배부 없음)">
              <ul className="space-y-0.5 text-xs">
                {run.result.q3_models.map((m) => (
                  <li key={m.model_id}>
                    {modelLabel(m.model_id)} F01 <Won value={m.cm_f01 ?? null} /> · 물량 <Won value={m.volume_effect ?? null} signed /> · 단가{" "}
                    <Won value={m.cost_effect ?? null} signed /> → <Won value={m.cm_combined ?? null} />
                  </li>
                ))}
              </ul>
            </Disclosure>
          </CardContent>
        </Card>
      ) : (
        <p className="text-sm text-muted-foreground">아직 분석이 없다.</p>
      )}

      <div className="grid gap-4 [&>*]:min-w-0 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>인계 조건</CardTitle>
            <CardDescription>하나라도 없으면 인계·인수할 수 없다 — 엔진이 다시 확인한다.</CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="space-y-1 text-sm">
              {Object.entries(view.handoffCheck.conditions).map(([k, ok]) => (
                <li key={k} className="flex items-center gap-2">
                  {ok ? (
                    <CheckCircle2 aria-hidden className="size-3.5" style={{ color: "var(--viz-status-good)" }} />
                  ) : (
                    <CircleDashed aria-hidden className="size-3.5 text-muted-foreground" />
                  )}
                  {CONDITION_LABEL[k] ?? k}
                  <span className="text-xs text-muted-foreground">{ok ? "충족" : "미충족"}</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>인계 {h ? `${h.handoff_id} r${h.revision}` : ""}</CardTitle>
            <CardDescription>{h ? HANDOFF_STATUS_LABEL[h.status] : "인계 요청 전"}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-1 text-sm">
            {h ? (
              <>
                <p>
                  요청 {name(h.requested_by)} · {formatClock(h.requested_at)} → 담당 {name(h.assignee)} · 기한 {formatClock(h.due_at)}
                </p>
                <p className="text-xs text-muted-foreground">
                  자료 <span className="font-mono">{h.bundle_id}</span> · 해시 <span className="font-mono">{h.bundle_hash}</span> · {h.note}
                </p>
                {h.accepted_at ? (
                  <p>
                    인수 {name(h.accepted_by)} · {formatClock(h.accepted_at)} — {h.opinion}
                    <span className="block text-xs font-medium">
                      외주 단가 인상 검토 인계 완료, 수익성 통합 분석 손익 검토 대기 (분석 기한 {formatClock(h.sc03_due_at)}) — 위험은 열려 있고 F02는 검토 중이다.
                    </span>
                  </p>
                ) : null}
              </>
            ) : (
              <p className="text-muted-foreground">승인·원가 등록 뒤 구매담당이 인계를 요청한다.</p>
            )}
            {view.review.bundles.some((b) => b.provisional) ? (
              <p className="text-xs">
                잠정 자료 {view.review.bundles.filter((b) => b.provisional).length}건 연결 — 최종 인계 조건에서 제외된다.
              </p>
            ) : null}
          </CardContent>
        </Card>
      </div>

      <AgentCard outputs={view.agentOutputs.filter((o) => o.kind === "AG24")} />

      <Card>
        <CardHeader>
          <CardTitle>감사 이력</CardTitle>
          <CardDescription>최근 5건 — 전체는 펼친다.</CardDescription>
        </CardHeader>
        <CardContent>
          <AuditList view={view} limit={5} />
          {view.audit.length > 5 ? (
            <Disclosure summary={`전체 ${view.audit.length}건`} className="mt-2">
              <AuditList view={view} />
            </Disclosure>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>다음 업무</CardTitle>
          <CardDescription>수익성 통합 분석 통합 손익 검토 — 설계표·데이터가 나온 뒤 만든다. 이야기만 있다.</CardDescription>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          경영관리 담당이 고객 생산계획 변경 대응 물량 감소와 외주 단가 인상 검토 원가 상승을 합산·검증하고 목표 차이를 분석한다. 대안의 숫자는 아직 없다 — 지어내지 않는다.
        </CardContent>
      </Card>
    </>
  );
}

function AuditList({ view, limit }: { view: Sc02View; limit?: number }) {
  const name = useUserName();
  const rows = limit ? view.audit.slice(-limit).reverse() : [...view.audit].reverse();
  return (
    <ul className="space-y-0.5 text-xs">
      {rows.map((a) => (
        <li key={a.seq}>
          <span className="tabular-nums text-muted-foreground">{formatClock(a.at)}</span> {name(a.actor)} ·{" "}
          <span className="font-mono">{a.action}</span>
        </li>
      ))}
    </ul>
  );
}
