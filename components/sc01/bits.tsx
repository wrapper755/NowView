"use client";

import Link from "next/link";
import {
  AlertTriangle,
  BellRing,
  CheckCircle2,
  CircleAlert,
  CircleDashed,
  ExternalLink,
  History,
  OctagonAlert,
  WifiOff,
  type LucideIcon,
} from "lucide-react";

import { Commentary } from "@/components/shared/commentary";
import { cn } from "@/lib/utils";
import { EXECUTOR_LABEL, formatClock, riskLabel, SCENE_LABEL } from "@/lib/sc01/format";
import type { Risk } from "@/lib/sc01/types";
import { selectView, useSc01 } from "@/lib/store/sc01";

/**
 * 위험 수준 표시 — **색 단독으로 말하지 않는다**(4.4). 아이콘 + 한글 라벨이 항상 함께 나간다.
 * 판정 보류(null)는 정상이 아니므로 별도 아이콘이다(CALC-03).
 */
const RISK_ICON: Record<Risk, LucideIcon> = {
  NORMAL: CheckCircle2,
  ATTENTION: CircleAlert,
  CRITICAL: OctagonAlert,
};
const RISK_COLOR: Record<Risk, string> = {
  NORMAL: "var(--viz-status-good)",
  ATTENTION: "var(--viz-status-warning)",
  CRITICAL: "var(--viz-status-critical)",
};

export function RiskTag({ risk, className }: { risk: Risk | null; className?: string }) {
  const Icon = risk ? RISK_ICON[risk] : CircleDashed;
  return (
    <span className={cn("inline-flex items-center gap-1.5 text-xs font-medium", className)}>
      <Icon
        aria-hidden
        className="size-3.5 shrink-0"
        style={{ color: risk ? RISK_COLOR[risk] : "var(--color-muted-foreground)" }}
      />
      {riskLabel(risk)}
    </span>
  );
}

/** 상태 칩 — 데이터·계산·업무·승인 상태는 서로 다른 칩으로 따로 보인다(설계서 1.9). */
export function StatePill({
  label,
  value,
  tone = "neutral",
}: {
  label: string;
  value: string;
  tone?: "neutral" | "good" | "warn";
}) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs">
      <span className="text-muted-foreground">{label}</span>
      <span
        className="font-medium"
        style={
          tone === "good"
            ? { color: "var(--viz-delta-good)" }
            : tone === "warn"
              ? { color: "var(--viz-status-serious)" }
              : undefined
        }
      >
        {value}
      </span>
    </span>
  );
}

/**
 * 화면 머리 — 조회 범위·기준 시점·장면 상태를 모든 화면에 같은 모양으로 둔다(설계서 2.3).
 * "가상 회사·시연 데이터"는 공통으로 표시한다.
 */
export function ScreenHeader({ id, title, question }: { id: string; title: string; question: string }) {
  const view = useSc01(selectView);
  return (
    // **한 줄 제목 + 한 줄 상태.** 화면 id·핵심 질문·범위 설명은 해설 모드에서만 보인다 —
    // 매 화면 머리에 네 줄이 쌓여 본문이 밀려 내려갔다.
    <header className="space-y-1.5">
      <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted-foreground">
        <span>{view ? formatClock(view.clock) : "—"}</span>
        <span aria-hidden>·</span>
        <span>장면 1 {view ? SCENE_LABEL[view.scene] : "—"}</span>
        <span className="rounded border px-1.5 py-0.5 text-[10px]">시연 데이터</span>
        <MyAlerts />
      </div>
      <Commentary block>
        <p className="text-xs text-muted-foreground">
          <span className="font-mono">{id}</span> · {question} · A제품 · 울산공장(ULS) · 가상 고객군
          CUS-HK · 2027년 · 가상시각은 KST
        </p>
      </Commentary>
      <StatusBanner />
      <ExecutorBanner />
    </header>
  );
}

/** 지금 역할에게 온 기한 초과 알림 수 — 누르면 업무 화면으로 간다. */
function MyAlerts() {
  const view = useSc01(selectView);
  const actor = useSc01((s) => s.actor);
  const count = (view?.alerts ?? []).filter((a) => a.to.includes(actor)).length;
  if (count === 0) return null;
  return (
    <Link
      href="/tasks"
      className="inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[10px] font-medium text-foreground"
    >
      <BellRing aria-hidden className="size-3" style={{ color: "var(--viz-status-critical)" }} />
      내 알림 {count}건
    </Link>
  );
}

/**
 * 바깥 실행(Studio·Center)에 묶인 데모 실행이면 알린다 — 결재를 어디서 답하는지, 그리고 Studio에
 * 넣을 입력(데모실행ID·원천ID)을 보인다. 표시하지 않으면 화면에서 답할 수 있다고 착각한다(N2).
 * Center는 대리 답 설정이 있으면 이 화면의 답이 Center 결재함으로 간다(N3) — 연동이 막혔으면 사유를
 * 그대로 보인다(조용히 다른 길로 가지 않는다). 원천 수신은 여전히 여기서 한다 — BPM 바깥의 일이다.
 */
function ExecutorBanner() {
  const view = useSc01(selectView);
  if (!view || view.executor === "embedded") return null;
  const source = view.sources.at(-1)?.source_id;
  const answerAt = view.executor === "studio" ? "Studio 시험 대화상자" : "Center 결재함";
  const problem = view.bpm?.center?.problem;
  return (
    <p className="flex flex-wrap items-center gap-x-2 gap-y-1 rounded-md border px-3 py-2 text-xs">
      <ExternalLink aria-hidden className="size-3.5" />
      <span>
        <span className="font-medium">{EXECUTOR_LABEL[view.executor]}</span>이 BPM을 돈다 —{" "}
        {view.answerHere
          ? "이 화면의 답은 Center 결재함에 대리 답으로 간다."
          : `결재는 ${answerAt}에서 답하세요. 이 화면은 결재를 받지 않는다.`}
      </span>
      {problem ? (
        <span className="inline-flex basis-full items-center gap-1 font-medium">
          <AlertTriangle aria-hidden className="size-3.5 shrink-0" style={{ color: "var(--viz-status-serious)" }} />
          {problem}
        </span>
      ) : null}
      <span className="text-muted-foreground">
        입력 데모실행ID <span className="font-mono">{view.demoRunId}</span>
        {source ? (
          <>
            {" "}· 원천ID <span className="font-mono">{source}</span>
          </>
        ) : null}{" "}
        · 바깥 실행{" "}
        {view.bpm?.externalRunId ? (
          <span className="font-mono">{view.bpm.externalRunId}</span>
        ) : (
          "첫 작업 호출 전"
        )}
      </span>
    </p>
  );
}

/** 연결이 끊겼거나 지난 시점을 보고 있으면 알린다 — 조용히 낡은 화면을 보여 주지 않는다. */
function StatusBanner() {
  const past = useSc01((s) => s.past);
  const connection = useSc01((s) => s.connection);
  const error = useSc01((s) => s.error);
  const setPast = useSc01((s) => s.setPast);

  if (past) {
    return (
      <p className="flex flex-wrap items-center gap-2 rounded-md border px-3 py-2 text-xs">
        <History aria-hidden className="size-3.5" />
        지난 시점({formatClock(past.view.clock)})을 보고 있다 — 이 화면에서는 조작할 수 없다.
        <button type="button" className="font-medium underline" onClick={() => setPast(null)}>
          현재로
        </button>
      </p>
    );
  }
  if (connection === "offline") {
    return (
      <p role="alert" className="flex items-center gap-2 rounded-md border px-3 py-2 text-xs">
        <WifiOff aria-hidden className="size-3.5" style={{ color: "var(--viz-status-serious)" }} />
        BPM 엔진에 닿지 않는다 — {error ?? "연결 실패"}. `npm run stack:start`로 엔진을 띄운다.
      </p>
    );
  }
  if (error) {
    return (
      <p role="alert" className="flex items-center gap-2 rounded-md border px-3 py-2 text-xs">
        <AlertTriangle aria-hidden className="size-3.5" style={{ color: "var(--viz-status-serious)" }} />
        {error}
      </p>
    );
  }
  return null;
}

/**
 * 사용자 id → "역할 이름". 기록에는 id가 남지만(감사 이력의 키) 화면은 사람을 보여 준다.
 * 시스템이 한 일은 "시스템"이다.
 */
export function useUserName(): (id: string | null | undefined) => string {
  const users = useSc01((s) => s.users);
  return (id) => {
    if (!id) return "—";
    if (id === "system") return "시스템";
    const u = users.find((x) => x.userId === id);
    return u ? `${u.role} ${u.name}` : id;
  };
}

/** 아직 데이터가 오지 않았을 때. */
export function Loading({ what = "데모 실행" }: { what?: string }) {
  return <p className="text-sm text-muted-foreground">{what}을(를) 불러오는 중…</p>;
}
