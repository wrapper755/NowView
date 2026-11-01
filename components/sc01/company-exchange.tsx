"use client";

import { ArrowDownLeft, ArrowUpRight, ExternalLink } from "lucide-react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useCompanies } from "@/lib/companies";
import { useCompanyId } from "@/lib/company-nav";
import { formatClock } from "@/lib/sc01/format";
import type { CompanyExchange } from "@/lib/sc01/types";
import { useSc01 } from "@/lib/store/sc01";

/**
 * 회사 시스템과 오간 것 — NowView가 회사 기간계에서 받은 것(기준 자료·고객계획)과 적은 것(원천 확인 결과).
 * BPM(Center) ↔ NowView ↔ 회사가 이어지는 모습이 화면에서 보이지 않았다(2026-11-01). 회사 사이트 주소가
 * 설정돼 있으면 그 문서를 회사 사이트에서 연다 — 회사 세계 id가 데모 실행 id다. 고객계획(`DOC-…`)은 문서 화면,
 * 장면 2의 단가 인상 요청·원가 버전은 그 회차 화면으로 연다(회사 사이트에 문서 화면이 없다).
 */
export function CompanyExchangeCard({ log }: { log: CompanyExchange[] }) {
  const demoRunId = useSc01((s) => s.demoRunId);
  const companyId = useCompanyId();
  const { companies } = useCompanies();
  const company = companies?.find((c) => c.id === companyId);
  const site = company?.siteUrl ?? null;
  const world = site && demoRunId ? `${site}/legacy/worlds/${encodeURIComponent(demoRunId)}` : null;

  return (
    <Card>
      <CardHeader>
        <CardTitle>회사 시스템과 오간 것</CardTitle>
        <CardDescription>
          {company?.name ?? "회사"} 기간계에서 받은 것과 적은 것 — 원천과 확정 기록의 주인은 회사다.
          {world && (
            <>
              {" "}
              <a href={world} target="_blank" rel="noreferrer" className="inline-flex items-center gap-0.5 underline">
                회사 사이트에서 보기
                <ExternalLink aria-hidden className="size-3" />
              </a>
            </>
          )}
        </CardDescription>
      </CardHeader>
      <CardContent>
        {log.length === 0 ? (
          <p className="text-sm text-muted-foreground">기록이 없다 — 이 기록을 남기기 전에 만든 데모 실행이다. 초기화하면 생긴다.</p>
        ) : (
          <ol className="space-y-2">
            {log.map((e) => {
              const out = e.direction === "out";
              const Icon = out ? ArrowUpRight : ArrowDownLeft;
              return (
                <li key={e.seq} className="flex items-start gap-2 text-sm">
                  <span className="w-20 shrink-0 tabular-nums text-muted-foreground">{formatClock(e.at)}</span>
                  <span
                    className={`inline-flex shrink-0 items-center gap-0.5 rounded px-1.5 py-0.5 text-xs font-medium ${
                      out ? "bg-brand-soft text-brand" : "bg-muted text-muted-foreground"
                    }`}
                  >
                    <Icon aria-hidden className="size-3" />
                    {out ? "회사에 적음" : "회사에서 받음"}
                  </span>
                  <span className="min-w-0 flex-1">
                    {e.what}
                    {e.by && <span className="text-muted-foreground"> · {e.by}</span>}
                    {e.doc_id && (
                      <>
                        {" "}
                        {world ? (
                          <a
                            href={e.doc_id.startsWith("DOC-") ? `${world}/docs/${encodeURIComponent(e.doc_id)}` : world}
                            target="_blank"
                            rel="noreferrer"
                            className="font-mono text-xs underline"
                          >
                            {e.doc_id}
                          </a>
                        ) : (
                          <span className="font-mono text-xs text-muted-foreground">{e.doc_id}</span>
                        )}
                      </>
                    )}
                  </span>
                </li>
              );
            })}
          </ol>
        )}
      </CardContent>
    </Card>
  );
}
