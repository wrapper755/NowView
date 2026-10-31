"use client";

import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

/** 엔진 `GET /admin/status` — 일꾼(C15)·Center 연동(N3)·회사 시스템의 지금 상태. 키·토큰 값은 없다. */
type AdminStatus = {
  consumer: {
    state: "off" | "enrolling" | "running";
    topics: string[];
    requestCode: string | null;
    problem: string | null;
    lastFetch: string | null;
  };
  recent: Array<{
    at: string;
    topic: string;
    operation: string;
    origin: string | null;
    runId: string | null;
    nodeId: string | null;
    demoRunId: string | null;
    outcome: string;
    reason: string | null;
  }>;
  center: { url: string | null; integration: boolean; relay: boolean; polling: boolean };
  companies: Record<string, { company: string; url: string | null; key: boolean; reachable: boolean }>;
  restartRequired: boolean;
};

const STATE_LABEL: Record<AdminStatus["consumer"]["state"], string> = {
  off: "꺼짐 — Center 주소가 없거나 NOWVIEW_CONSUMER=off",
  enrolling: "승인 대기",
  running: "일감을 가져가는 중",
};

const ORIGIN_LABEL: Record<string, string> = { run: "Center 서버 실행", test: "Studio 시험 실행" };

/** 5초마다 읽는다 — 관리자 화면에만 있다. */
function useAdminStatus(): { status: AdminStatus | null; error: string | null } {
  const [status, setStatus] = useState<AdminStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    const read = async () => {
      try {
        const response = await fetch("/api/admin/status", { cache: "no-store" });
        if (!alive) return;
        if (!response.ok) {
          setError(`상태를 읽지 못했다 (${response.status})`);
          return;
        }
        setStatus((await response.json()) as AdminStatus);
        setError(null);
      } catch (cause) {
        if (alive) setError(`엔진에 연결할 수 없다 — ${String(cause)}`);
      }
    };
    void read();
    const timer = setInterval(read, 5000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, []);
  return { status, error };
}

/** 관리자 화면의 상태 — 들이기(요청 코드)·토픽·Center 연동·회사 시스템·최근 일감. */
export function StatusPanel() {
  const { status, error } = useAdminStatus();
  if (error) return <p className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm">{error}</p>;
  if (!status) return <p className="text-sm text-muted-foreground">읽는 중…</p>;
  const { consumer, center, recent, companies } = status;
  return (
    <div className="grid gap-4">
      <Card>
        <CardHeader>
          <CardTitle>일꾼</CardTitle>
          <CardDescription>Center에 쌓인 서비스 태스크 일감을 가져가 회사 설정대로 수행한다.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3 text-sm">
          <p>
            상태 <span className="font-semibold">{STATE_LABEL[consumer.state]}</span>
            {consumer.lastFetch ? <span className="text-muted-foreground"> · 마지막 보고 {consumer.lastFetch}</span> : null}
          </p>
          {consumer.state === "enrolling" && consumer.requestCode ? (
            <p className="rounded-md border border-brand/40 bg-brand-soft/50 p-3">
              Center CON-07 「일꾼 승인 대기」에서 요청 코드{" "}
              <span className="font-mono text-base font-semibold tracking-wider">{consumer.requestCode}</span>를 승인하면 일감을
              가져가기 시작한다.
            </p>
          ) : null}
          {consumer.problem ? <p className="text-destructive">{consumer.problem}</p> : null}
          {status.restartRequired ? (
            <p className="rounded-md border border-amber-500/50 bg-amber-500/10 p-3">
              토픽 설정이 바뀌었다 — 엔진을 다시 띄워야 일꾼이 새 토픽으로 들이기를 한다(승인된 일꾼이면 Center 쪽 토픽도 바꾼다).
            </p>
          ) : null}
          <div>
            <p className="mb-1 text-xs text-muted-foreground">지금 맡은 토픽</p>
            <ul className="flex flex-wrap gap-1.5">
              {consumer.topics.map((t) => (
                <li key={t}>
                  <Badge variant="outline" className="font-mono">
                    {t}
                  </Badge>
                </li>
              ))}
            </ul>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>연결</CardTitle>
          <CardDescription>Center(기동·대리 답·진행 읽기)와 회사 시스템.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-1 text-sm">
          <p>
            Center <span className="font-mono">{center.url ?? "없음"}</span> · 연동용 키 {center.integration ? "있음" : "없음"} · 대리
            답용 키 {center.relay ? "있음" : "없음"} · 진행 폴링 {center.polling ? "도는 중" : "멈춤"}
          </p>
          {Object.entries(companies).map(([id, c]) => (
            <p key={id}>
              회사 시스템 <span className="font-mono">{id}</span> <span className="font-mono">{c.url ?? "주소 없음"}</span> · 키{" "}
              {c.key ? "있음" : "없음"} · {c.reachable ? "응답함" : "응답 없음"}
            </p>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>최근 일감</CardTitle>
          <CardDescription>엔진 메모리의 최근 50건 — 엔진이 다시 뜨면 빈다.</CardDescription>
        </CardHeader>
        <CardContent>
          {recent.length === 0 ? (
            <p className="text-sm text-muted-foreground">아직 가져간 일감이 없다.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="text-muted-foreground">
                  <tr>
                    <th className="py-1 pr-3 font-medium">시각</th>
                    <th className="py-1 pr-3 font-medium">토픽 · 작업</th>
                    <th className="py-1 pr-3 font-medium">실행</th>
                    <th className="py-1 pr-3 font-medium">데모 실행</th>
                    <th className="py-1 font-medium">결과</th>
                  </tr>
                </thead>
                <tbody>
                  {recent.map((r, i) => (
                    <tr key={`${r.at}-${i}`} className="border-t align-top">
                      <td className="py-1.5 pr-3 font-mono whitespace-nowrap">{r.at.slice(11, 19)}</td>
                      <td className="py-1.5 pr-3 font-mono">
                        {r.topic} · {r.operation}
                      </td>
                      <td className="py-1.5 pr-3">
                        {ORIGIN_LABEL[r.origin ?? ""] ?? r.origin}
                        <span className="block font-mono text-muted-foreground">{r.nodeId}</span>
                      </td>
                      <td className="py-1.5 pr-3 font-mono">{r.demoRunId}</td>
                      <td className="py-1.5">
                        <span className={r.outcome === "complete" ? "" : "font-semibold text-destructive"}>{r.outcome}</span>
                        {r.reason ? <span className="block text-muted-foreground">{r.reason}</span> : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
