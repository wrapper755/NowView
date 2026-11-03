"use client";

import { useEffect, useState } from "react";

import { useUserName } from "@/components/sc01/bits";
import { CompanyExchangeCard } from "@/components/sc01/company-exchange";
import { Sc02Body, Sc02Header, StatusPills, WaitingList } from "@/components/sc02/bits";
import { CompanySiteNote } from "@/components/shared/company-site-note";
import { Commentary } from "@/components/shared/commentary";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatClock, formatRatio, modelLabel } from "@/lib/sc01/format";
import { sc02Api } from "@/lib/sc02/client";
import { REQUEST_STATUS_LABEL } from "@/lib/sc02/format";
import type { Sc02View } from "@/lib/sc02/types";

/**
 * U21 단가 인상 요청 접수 — 공급사·요청건·상태, 공문, 품목별 기존가·요청가·적용일, 부품-모델 연결, 검사 오류.
 * 요청가는 승인 원가가 아니다(U21-A). 인상률은 분석 run이 생긴 뒤에만 보인다 — 화면이 계산하지 않는다.
 */
export function Sc02RequestScreen() {
  return (
    <main className="viz-root mx-auto w-full max-w-7xl space-y-8 px-4 py-8 sm:px-6 lg:px-8">
      <Sc02Header id="U21" title="단가 인상 요청 접수" question="정식 요청의 사실과 범위가 맞는가?" />
      <Sc02Body>{(view) => <Request view={view} />}</Sc02Body>
    </main>
  );
}

type Part = { modelId: string; partId: string; supplierId: string; qtyPer: string };

function Request({ view }: { view: Sc02View }) {
  const name = useUserName();
  const [parts, setParts] = useState<Part[]>([]);
  useEffect(() => {
    void sc02Api.parts().then((r) => r.ok && setParts(r.data));
  }, []);
  const req = view.request;
  const reqRun = view.runs.find((r) => r.price_version_id === "PV-REQ01");
  return (
    <>
      <StatusPills view={view} />
      {req === null ? <ReceiveCard /> : null}
      <WaitingList view={view} nodes={["Verify_Request"]} />

      {req ? (
        <div className="grid gap-4 [&>*]:min-w-0 lg:grid-cols-[2fr_3fr]">
          <Card>
            <CardHeader>
              <CardTitle>요청 {req.request_id}</CardTitle>
              <CardDescription>
                {req.supplier_id} {req.supplier_name} · 수신 {formatClock(req.received_at)} · 품목 {req.items.length}건 ·{" "}
                {REQUEST_STATUS_LABEL[req.status] ?? req.status}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              <blockquote className="rounded-md border-l-2 bg-muted/40 px-3 py-2 text-[13px]">
                <span className="mb-1 block font-mono text-[11px] text-muted-foreground">{req.source_doc_id} 요청 공문</span>
                {req.source_text}
              </blockquote>
              {req.verified_at ? (
                <p className="text-xs text-muted-foreground">
                  원문 확인 {name(req.verified_by)} · {formatClock(req.verified_at)} — {req.opinion}
                </p>
              ) : req.opinion ? (
                <p className="text-xs">보완 요청 — {req.opinion}</p>
              ) : null}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>품목별 요청 내용</CardTitle>
              <CardDescription>KRW · VAT 제외 · 월초 적용. 공급사 요청 내용이다 — 회사의 수용 단가가 아니다.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="overflow-x-auto">
                <table className="w-full min-w-[34rem] text-sm">
                  <thead>
                    <tr className="border-b text-left text-xs text-muted-foreground">
                      <th scope="col" className="py-2 pr-3 font-medium">품목</th>
                      <th scope="col" className="py-2 pr-3 text-right font-medium">기존가</th>
                      <th scope="col" className="py-2 pr-3 text-right font-medium">요청가</th>
                      <th scope="col" className="py-2 pr-3 text-right font-medium">인상률</th>
                      <th scope="col" className="py-2 pr-3 font-medium">적용 희망일</th>
                      <th scope="col" className="py-2 font-medium">사유</th>
                    </tr>
                  </thead>
                  <tbody>
                    {req.items.map((it) => (
                      <tr key={it.part_id} className="border-b">
                        <th scope="row" className="py-2 pr-3 text-left font-mono font-normal">{it.part_id}</th>
                        <td className="py-2 pr-3 text-right tabular-nums">{Number(it.old_price).toLocaleString("ko-KR")}원</td>
                        <td className="py-2 pr-3 text-right tabular-nums">{Number(it.requested_price).toLocaleString("ko-KR")}원</td>
                        <td className="py-2 pr-3 text-right tabular-nums">
                          {reqRun ? formatRatio(reqRun.result.rate) : <span className="text-xs text-muted-foreground">분석 후</span>}
                        </td>
                        <td className="py-2 pr-3">{it.effective_date ?? <span className="font-medium">누락</span>}</td>
                        <td className="py-2 text-xs">{it.reason}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {req.errors.length > 0 ? (
                <ul role="alert" className="space-y-0.5 rounded-md border px-3 py-2 text-xs">
                  {req.errors.map((e) => (
                    <li key={e.field + e.message}>
                      <span className="font-mono">{e.field}</span> {e.message}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-xs text-muted-foreground">자동 검사 통과 — 필수값·공급사-품목 매핑·기존가 = C01 부품 단가.</p>
              )}
            </CardContent>
          </Card>
        </div>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>부품 · 모델 연결</CardTitle>
          <CardDescription>공통부품 P-COM01은 a·b모델에 각 1개 쓰인다. c~e는 쓰지 않는다(직접 단가 영향 0).</CardDescription>
        </CardHeader>
        <CardContent>
          <ul className="flex flex-wrap gap-2 text-sm">
            {parts.map((p) => (
              <li key={p.modelId} className="rounded-md border px-2.5 py-1">
                {modelLabel(p.modelId)} <span className="font-medium tabular-nums">{Number(p.qtyPer)}개</span>
              </li>
            ))}
          </ul>
          <Commentary block>
            <p className="mt-2 text-xs text-muted-foreground">
              기존 외주비(a 75,000원 · b 95,000원)에 이 부품 2,000원이 이미 들어 있다 — 원가 등록 때 그 부분만 바꾼다.
            </p>
          </Commentary>
        </CardContent>
      </Card>
      <CompanyExchangeCard log={view.companyLog ?? []} />
    </>
  );
}

/** 공문 수신 — 공급사 요청은 회사 사이트의 시연 조작이 회사 구매 수신함에 보내고, NowView 일꾼이 들인다(읽기 전용, role-split §5.5). */
function ReceiveCard() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>공문 수신</CardTitle>
        <CardDescription>SUP-01 가상 정밀부품이 회사 구매 수신함에 보낸 단가 인상 요청 공문(DOC-REQ01)을 들인다.</CardDescription>
      </CardHeader>
      <CardContent>
        <CompanySiteNote>
          요청(기본 · 적용일 누락 변형)은 회사 사이트의 시연 조작에서 보낸다 — 수신함에 들어오면 이 화면이 따라 바뀐다.
        </CompanySiteNote>
      </CardContent>
    </Card>
  );
}
