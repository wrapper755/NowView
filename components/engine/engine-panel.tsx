"use client";

/**
 * 엔진 모드 제어 — 인스턴스를 만들고, 상태를 보여주고, 실패를 드러낸다.
 *
 * **Mock이 기본이고 엔진은 옮겨 타는 것이다.** 엔진을 켜지 않은 사람에게는 화면이
 * 이전과 똑같아야 한다. 데모 플레이어는 두 모드 모두에서 동작한다 — 엔진 모드에서는
 * 장면이 선언한 지점으로 인스턴스를 옮긴다(`use-engine-playback`).
 *
 * 그래서 이 패널은 **지금 무엇을 보고 있는지**를 가장 먼저 말한다. 산출물이 Mock인지
 * 실제 LLM 호출인지 구분되지 않으면 데모의 주장을 검증할 수 없다(기획안 2.3).
 */

import { AlertTriangle, History, Loader2, Play, RefreshCw, Square } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { EngineError } from "@/components/engine/use-engine-instance";
import type { AgentMode, EngineSnapshot } from "@/services/engine-client";
import { cn } from "@/lib/utils";

const STATUS_LABEL: Record<EngineSnapshot["status"], string> = {
  created: "생성됨",
  running: "실행 중",
  waiting: "사람 대기",
  done: "종료",
};

const MODE_LABEL: Record<AgentMode, string> = {
  mock: "Mock 산출물",
  llm: "LLM 실호출",
};

export function EnginePanel({
  snapshot,
  loading,
  pending,
  error,
  agentMode,
  onAgentModeChange,
  onStart,
  onStop,
  onRefresh,
  historical = false,
  onLive,
}: {
  snapshot: EngineSnapshot | null;
  loading: boolean;
  pending: boolean;
  error: EngineError | null;
  agentMode: AgentMode;
  onAgentModeChange: (mode: AgentMode) => void;
  onStart: () => void;
  onStop: () => void;
  onRefresh: () => void;
  /** 데모가 과거 시점을 보여주는 중인가. */
  historical?: boolean;
  onLive?: () => void;
}) {
  const engaged = snapshot !== null;

  return (
    <div className="rounded-lg border">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2 p-3">
        <span
          className={cn(
            "rounded px-1.5 py-0.5 text-xs font-medium",
            engaged ? "text-foreground" : "bg-muted text-muted-foreground",
          )}
          style={engaged ? { backgroundColor: "var(--viz-status-good)", color: "#fff" } : undefined}
        >
          {engaged ? "엔진 모드" : "Mock 모드"}
        </span>

        <p className="min-w-0 flex-1 text-xs text-muted-foreground">
          {engaged ? (
            <>
              LangGraph 인스턴스가 상태를 소유한다. 진행 지점은 실행의 결과이고, 지난
              지점은 체크포인트로 되짚어 볼 수 있다.
            </>
          ) : (
            <>
              화면이 Mock 데이터를 직접 읽고 있다. 데모 플레이어는 두 모드 모두에서 동작한다.
            </>
          )}
        </p>

        {!engaged ? (
          <>
            {/* 기존 인스턴스의 모드는 바꿀 수 없다 — 산출물 출처가 섞이면
                어느 것이 실제 호출인지 알 수 없다. 그래서 시작 전에만 고른다. */}
            <div className="flex items-center gap-1 rounded-md border p-0.5">
              {(["mock", "llm"] as AgentMode[]).map((mode) => (
                <button
                  key={mode}
                  type="button"
                  onClick={() => onAgentModeChange(mode)}
                  className={cn(
                    "rounded px-2 py-1 text-xs transition-colors",
                    agentMode === mode
                      ? "bg-foreground text-background"
                      : "text-muted-foreground hover:bg-muted",
                  )}
                >
                  {MODE_LABEL[mode]}
                </button>
              ))}
            </div>
            <Button size="sm" onClick={onStart} disabled={pending}>
              {pending ? (
                <Loader2 aria-hidden className="size-3.5 animate-spin" />
              ) : (
                <Play aria-hidden className="size-3.5" />
              )}
              엔진으로 실행
            </Button>
          </>
        ) : (
          <>
            <span className="text-xs tabular-nums text-muted-foreground">
              {STATUS_LABEL[snapshot.status]}
              <span className="mx-1.5 text-muted-foreground/50">·</span>
              {MODE_LABEL[snapshot.agentMode]}
              <span className="mx-1.5 text-muted-foreground/50">·</span>
              <span className="font-mono text-[10px]">{snapshot.instanceId}</span>
            </span>
            <Button size="sm" variant="outline" onClick={onRefresh} disabled={loading || pending}>
              <RefreshCw aria-hidden className={cn("size-3.5", loading && "animate-spin")} />
              새로고침
            </Button>
            <Button size="sm" variant="outline" onClick={onStop} disabled={pending}>
              <Square aria-hidden className="size-3.5" />
              Mock으로 돌아가기
            </Button>
          </>
        )}
      </div>

      {historical ? (
        // 과거 시점인데 그 사실을 표시하지 않으면 지금 승인할 수 있다고 착각한다.
        <div
          className="flex flex-wrap items-center gap-2 border-t px-3 py-2"
          style={{ borderTopColor: "var(--viz-status-warning)" }}
        >
          <History
            aria-hidden
            className="size-3.5 shrink-0"
            style={{ color: "var(--viz-status-warning)" }}
          />
          <p className="min-w-0 flex-1 text-xs text-foreground">
            지난 시점을 되짚어 보는 중이다 — 인스턴스의 실제 진행은 이보다 앞서 있고,
            여기서는 승인할 수 없다.
          </p>
          {onLive ? (
            <Button size="sm" variant="outline" onClick={onLive}>
              현재로
            </Button>
          ) : null}
        </div>
      ) : null}

      {pending && agentMode === "llm" && !engaged ? (
        // LLM 모드는 Agent 노드마다 10초 이상 걸린다. 아무 표시가 없으면 멈춘 것처럼 보인다.
        <p className="border-t px-3 py-2 text-xs text-muted-foreground">
          Agent를 실제로 호출하는 중이다. 노드마다 10초 이상 걸리며 계약 위반 시 재시도한다 —
          1분 가까이 걸릴 수 있다.
        </p>
      ) : null}

      {error ? <EngineErrorBanner error={error} /> : null}

      {snapshot?.specWarnings?.length ? (
        <div className="border-t px-3 py-2">
          <p className="text-xs font-medium text-foreground">프로세스 명세의 문제</p>
          <ul className="mt-1 space-y-0.5">
            {snapshot.specWarnings.map((warning) => (
              <li key={warning} className="text-xs text-muted-foreground">
                · {warning}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

/**
 * 실패를 조용히 삼키지 않는다.
 *
 * 엔진이 꺼져 있는 것은 고장이 아니므로 앱을 망가진 것처럼 보이게 하지 않는다 —
 * 무엇이 왜 안 됐는지 말하고, 화면의 나머지는 Mock으로 계속 동작한다.
 */
export function EngineErrorBanner({ error }: { error: EngineError }) {
  const unreachable = error.status === 503;
  return (
    <div
      className="flex items-start gap-2.5 border-t p-3"
      role="alert"
      style={{ borderTopColor: "var(--viz-status-serious)" }}
    >
      <AlertTriangle
        aria-hidden
        className="mt-0.5 size-4 shrink-0"
        style={{ color: "var(--viz-status-serious)" }}
      />
      <div className="min-w-0 space-y-0.5">
        <p className="text-sm font-medium text-foreground">{error.message}</p>
        {unreachable ? (
          <p className="text-xs text-muted-foreground">
            엔진은 선택 사항이다 — 켜지 않아도 화면은 Mock으로 전부 동작한다. 띄우려면
            저장소 루트에서 <code className="font-mono">docker compose up</code>.
          </p>
        ) : null}
        {error.detail ? (
          <p className="break-words text-xs text-muted-foreground">{error.detail}</p>
        ) : null}
      </div>
    </div>
  );
}
