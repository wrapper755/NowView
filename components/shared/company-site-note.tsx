import { ExternalLink } from "lucide-react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

/**
 * 「이 일은 회사 사이트에서 한다」 한 줄(2026-11-03, `docs/role-split.md` §5.5). NowView 화면은 읽기 전용이다 — 결재 답·장면
 * 열기·착수·회의 기록·Agent 요청·시계·초기화는 회사 사이트(결재 화면·시연 조작)에서 하고, 그 결과가 여기 보인다.
 */
export function CompanySiteNote({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <p className={cn("flex items-start gap-1.5 text-xs text-muted-foreground", className)}>
      <ExternalLink aria-hidden className="mt-0.5 size-3 shrink-0" />
      <span>{children}</span>
    </p>
  );
}

/** 지금 기다리는 결재 하나 — 읽기 전용. 답은 회사 사이트의 결재 화면에서 한다. */
export interface WaitingItem {
  nodeId: string;
  title: string;
  /** 담당 — 역할이거나 사람 이름. */
  who: string | null;
  taskId?: string | null;
  due?: string | null;
  /** 직전 답이 기록에서 거절됐으면 그 사유. */
  rejected?: string | null;
}

/**
 * 지금 기다리는 결재 카드들 — 예전의 결재 폼 자리다. 무엇을 누가 기다리는지는 보이고, 답하는 칸은 없다. 없으면 아무것도 그리지 않는다.
 */
export function WaitingNotice({ items }: { items: WaitingItem[] }) {
  if (items.length === 0) return null;
  return (
    <>
      {items.map((w) => (
        <Card key={`${w.nodeId}:${w.taskId ?? ""}`}>
          <CardHeader>
            <CardTitle>기다리는 결재 — {w.title}</CardTitle>
            <CardDescription>
              담당 {w.who ?? "—"}
              {w.taskId ? (
                <>
                  {" "}
                  · <span className="font-mono">{w.taskId}</span>
                </>
              ) : null}
              {w.due ? <> · 기한 {w.due}</> : null}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            {w.rejected ? (
              <p role="alert" className="text-xs" style={{ color: "var(--viz-status-serious)" }}>
                직전 답이 거절됐다 — {w.rejected}
              </p>
            ) : null}
            <CompanySiteNote>답은 회사 사이트의 결재 화면에서 한다 — 기록이 들어오면 이 화면이 따라 바뀐다.</CompanySiteNote>
          </CardContent>
        </Card>
      ))}
    </>
  );
}

const EXECUTOR_LABEL: Record<string, string> = {
  center: "Center 서버 실행",
  studio: "Studio 시험 실행",
  embedded: "내장 BPM(시험용)",
};

/**
 * 어디서 BPM이 도는지 — 그리고 이 화면은 읽기 전용이라는 것. 결재 답·시연 조작은 회사 사이트가 하고, 연동이 막혔으면 사유를
 * 그대로 보인다(조용히 다른 길로 가지 않는다).
 */
export function ExecutorNote({
  executor,
  problem,
  demoRunId,
  externalRunId,
}: {
  executor: string | null | undefined;
  problem?: string | null;
  demoRunId: string;
  externalRunId?: string | null;
}) {
  return (
    <p className="flex flex-wrap items-center gap-x-2 gap-y-1 rounded-md border px-3 py-2 text-xs">
      <ExternalLink aria-hidden className="size-3.5" />
      <span>
        {executor ? (
          <>
            <span className="font-medium">{EXECUTOR_LABEL[executor] ?? executor}</span>이 BPM을 돈다 —{" "}
          </>
        ) : null}
        결재 답·시연 조작은 회사 사이트에서 한다. 이 화면은 결과를 보인다.
      </span>
      {problem ? (
        <span className="inline-flex basis-full items-center gap-1 font-medium" style={{ color: "var(--viz-status-serious)" }}>
          {problem}
        </span>
      ) : null}
      <span className="text-muted-foreground">
        데모 실행 <span className="font-mono">{demoRunId}</span>
        {externalRunId !== undefined ? (
          <>
            {" "}· 바깥 실행 {externalRunId ? <span className="font-mono">{externalRunId}</span> : "첫 작업 호출 전"}
          </>
        ) : null}
      </span>
    </p>
  );
}

/**
 * 이 데모 실행에 장면 문서가 아직 없다 — 예전의 「시작」 카드 자리다. 장면 열기는 회사 사이트의 시연 조작이고, 열리면 이 화면이
 * 저절로 문서를 받는다(장면 수신이 짧게 다시 묻는다).
 */
export function SceneNotOpened({ work, demoRunId, from }: { work: string; demoRunId: string | null; from?: string }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{work} — 아직 열리지 않았다</CardTitle>
        <CardDescription>
          {from ? <>{from}에서 이어진다. </> : null}
          {demoRunId ? (
            <>
              데모 실행 <span className="font-mono">{demoRunId}</span>
            </>
          ) : (
            "데모 실행이 아직 없다"
          )}
          .
        </CardDescription>
      </CardHeader>
      <CardContent>
        <CompanySiteNote>
          업무는 회사 사이트의 시연 조작에서 연다(앞 업무가 끝나 있어야 한다). 열리면 이 화면이 저절로 따라온다.
        </CompanySiteNote>
      </CardContent>
    </Card>
  );
}

/** 착수 전 — 예전의 「분석 시작」·「확인 착수」 단추 자리다. 착수는 회사 사이트의 시연 조작이 한다. */
export function StartPending({ title, who, children }: { title: string; who: string; children?: React.ReactNode }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>착수 대기 — {title}</CardTitle>
        <CardDescription>
          담당 {who}
          {children ? <> · {children}</> : null}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <CompanySiteNote>착수는 회사 사이트의 시연 조작에서 한다 — 착수되면 이 화면이 따라 바뀐다.</CompanySiteNote>
      </CardContent>
    </Card>
  );
}
