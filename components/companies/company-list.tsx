"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { SCENES, useCompanies } from "@/lib/companies";
import { formatClock } from "@/lib/sc01/format";
import { useSc01 } from "@/lib/store/sc01";

/** 회사 목록 — 엔진 설정의 공개 목록(이름·설명·업무). 회사는 설정이라 빌드 때 모른다. */
export function CompanyList() {
  const { companies, error } = useCompanies();
  if (error) return <p className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm">{error}</p>;
  if (!companies) return <p className="text-sm text-muted-foreground">회사 목록을 읽는 중…</p>;
  if (companies.length === 0) return <p className="text-sm text-muted-foreground">등록된 회사가 없다.</p>;
  return (
    <ul className="grid gap-4 md:grid-cols-2">
      {companies.map((c) => (
        <li key={c.id}>
          <Link href={`/c/${c.id}`} className="block h-full">
            <Card className="h-full transition-colors hover:border-brand/60">
              <CardHeader>
                <CardTitle>{c.name}</CardTitle>
                <CardDescription>{c.description}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                <p className="text-muted-foreground">업무 {c.scenes.length}개</p>
                <ol className="flex flex-wrap gap-1.5">
                  {SCENES.filter((s) => c.scenes.includes(s.no)).map((s) => (
                    <li key={s.no}>
                      <Badge variant="outline">
                        {s.no}. {s.work}
                      </Badge>
                    </li>
                  ))}
                </ol>
              </CardContent>
            </Card>
          </Link>
        </li>
      ))}
    </ul>
  );
}

/**
 * 업무 하나의 지금 상태 — 장면마다 문서 모양이 달라 모든 장면 문서에 있는 칸(BPM 상태·가상시각)만 읽는다. 단계 코드(`step`)는
 * 각본 위치라 싣지 않는다 — 화면에서 직접 진행한 실행은 인계까지 가도 「S0」로 남았다.
 */
type WorkStatus =
  | { kind: "none" }
  | { kind: "error"; message: string }
  | { kind: "doc"; state: string | null; clock: string | null };

const STATE_LABEL: Record<string, string> = {
  running: "진행 중",
  done: "흐름 끝",
  failed: "멈춤",
  cancelled: "멈춤",
};

/**
 * 업무별 상태를 읽는다 — 엔진이 회사 업무마다 한 번에 준다(`GET /companies/{회사}/works`). 데모 실행 id는 장면 1~6이
 * 같다(4.16). 장면마다 문서를 읽으면 시작 전 업무가 404로 콘솔을 메웠다(2026-11-01). 장면 2~6은 이 화면이 구독하지
 * 않으므로 20초마다 다시 읽는다.
 */
function useWorkStatus(companyId: string, demoRunId: string | null): Record<number, WorkStatus> {
  const [status, setStatus] = useState<Record<number, WorkStatus>>({});
  useEffect(() => {
    if (!demoRunId) return;
    let alive = true;
    const failed = (message: string) =>
      Object.fromEntries(SCENES.map((s): [number, WorkStatus] => [s.no, { kind: "error", message }]));
    const read = async () => {
      let next: Record<number, WorkStatus>;
      try {
        const res = await fetch(
          `/api/engine/companies/${encodeURIComponent(companyId)}/works?demoRunId=${encodeURIComponent(demoRunId)}`,
          { cache: "no-store" },
        );
        if (res.ok) {
          const rows: { scene: number; state: string; clock: string | null }[] = await res.json();
          next = Object.fromEntries(
            rows.map((r): [number, WorkStatus] => [
              r.scene,
              r.state === "none" ? { kind: "none" } : { kind: "doc", state: r.state, clock: r.clock },
            ]),
          );
        } else {
          next = failed(`읽지 못함 (${res.status})`);
        }
      } catch {
        next = failed("엔진에 닿지 않음");
      }
      if (alive) setStatus(next);
    };
    void read();
    const timer = setInterval(read, 20_000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [companyId, demoRunId]);
  return status;
}

function WorkStatusLine({ status }: { status: WorkStatus | undefined }) {
  if (!status) return <p className="text-xs text-muted-foreground">상태를 읽는 중…</p>;
  if (status.kind === "error") return <p className="text-xs text-muted-foreground">{status.message}</p>;
  if (status.kind === "none") {
    return (
      <p className="flex items-center gap-2 text-xs text-muted-foreground">
        <Badge variant="outline">시작 전</Badge>
      </p>
    );
  }
  const label = (status.state && STATE_LABEL[status.state]) ?? "착수 전";
  return (
    <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
      <Badge variant={status.state === "running" ? "default" : "secondary"}>{label}</Badge>
      {status.clock && <span>가상시각 {formatClock(status.clock)}</span>}
    </p>
  );
}

/**
 * 회사 운영 현황 — 그 회사가 쓰는 업무마다 지금 상태(이 데모 실행에서). 업무 목록 자체는 왼쪽 사이드바에도 있으므로
 * 카드는 상태를 싣는다 — 같은 목록만 두 번 보이지 않게(2026-11-01). 없는 회사면 그렇게 말한다.
 */
export function CompanyOverview({ companyId }: { companyId: string }) {
  const { companies, error } = useCompanies();
  const demoRunId = useSc01((s) => s.demoRunId);
  const company = companies?.find((c) => c.id === companyId);
  const status = useWorkStatus(companyId, demoRunId);
  if (error) return <p className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm">{error}</p>;
  if (!companies) return <p className="text-sm text-muted-foreground">읽는 중…</p>;
  if (!company) {
    return (
      <p className="text-sm">
        없는 회사다: <span className="font-mono">{companyId}</span> —{" "}
        <Link href="/" className="underline">
          회사 목록
        </Link>
      </p>
    );
  }
  return (
    <>
      <div>
        <h1 className="text-xl font-semibold">{company.name}</h1>
        <p className="text-sm text-muted-foreground">{company.description}</p>
      </div>
      {/* 업무 카드 제목이 섹션 탭이 되면 같은 목록이 한 화면에 또 나온다 — 탭에서 뺀다(4.10). */}
      <ol data-index-skip className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {SCENES.filter((s) => company.scenes.includes(s.no)).map((s) => (
          <li key={s.no}>
            <Link href={`/c/${company.id}/sc0${s.no}`} className="block h-full">
              <Card className="h-full transition-colors hover:border-brand/60">
                <CardHeader>
                  <CardTitle>
                    {s.no}. {s.work}
                  </CardTitle>
                  <CardDescription>{s.detail}</CardDescription>
                </CardHeader>
                <CardContent>
                  <WorkStatusLine status={status[s.no]} />
                </CardContent>
              </Card>
            </Link>
          </li>
        ))}
      </ol>
      {demoRunId && (
        <p className="text-xs text-muted-foreground">
          데모 실행 <span className="font-mono">{demoRunId}</span> 기준 — 업무들이 같은 데모 실행을 잇는다.
        </p>
      )}
    </>
  );
}
