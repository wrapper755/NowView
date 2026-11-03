"use client";

import { useState } from "react";
import { FileSearch, Lock, RefreshCw } from "lucide-react";

import { Problem, personName } from "@/components/sc06/bits";
import { SceneNotOpened } from "@/components/shared/company-site-note";
import { Commentary } from "@/components/shared/commentary";
import { Button } from "@/components/ui/button";
import { formatClock } from "@/lib/sc01/format";
import { sc07Api } from "@/lib/sc07/client";
import type { EvidenceView, Person } from "@/lib/sc07/types";
import { useSc01 } from "@/lib/store/sc01";
import { type Load, useSc07 } from "@/lib/store/sc07";

export { Problem, StateTag } from "@/components/sc06/bits";

/**
 * 장면 7 화면 머리 — 제목 한 줄 + 문맥 한 줄(구현명세 1장 U701-01): 긴급구매 원인 검토 Agent · 개선건 · 조회 시점 · 기준 버전 ·
 * 가상 검증 이력. 화면 id·질문은 해설 모드에서만 보인다.
 */
export function Sc07Header({ id, title, question }: { id: string; title: string; question: string }) {
  const meta = useSc07((s) => s.meta);
  const b = meta?.versionBundle;
  return (
    <header className="space-y-1.5">
      <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted-foreground">
        <span>조회 {meta ? formatClock(meta.clock) : "—"}</span>
        <span aria-hidden>·</span>
        <span>긴급구매 원인 검토 Agent · {meta?.improvementId ?? "IMP71"}</span>
        <span aria-hidden>·</span>
        <span>
          Agent {b?.agent ?? "AGT71-v2"} · 기준 {b?.measure ?? "MB71-v2"} · 검증 세트 {b?.verification_set ?? "TS71-v1"}
        </span>
        <span className="rounded border px-1.5 py-0.5 text-[10px]">가상 검증 이력</span>
        <span className="rounded border px-1.5 py-0.5 text-[10px]">시연 데이터 {meta?.datasetVersion ?? "v0.7"}</span>
      </div>
      <Commentary block>
        <p className="text-xs text-muted-foreground">
          <span className="font-mono">{id}</span> · {question} · 보기 전환·근거 펼침은 승인·배포·적용을 만들지 않는다 · 검증 8건 통과는
          Agent 정확도 100%가 아니다 · 설정 반영 확인은 운영 실행·장기 효과의 확인이 아니다 · 120분 기준·지표·효과 산식은 그대로다
        </p>
      </Commentary>
    </header>
  );
}

/** 장면 7 본문 — 열리지 않았으면 「아직 열리지 않았다」(여는 것은 회사 사이트), 머리 조회 실패면 사유. */
export function Sc07Body({ children }: { children: React.ReactNode }) {
  const meta = useSc07((s) => s.meta);
  const missing = useSc07((s) => s.missing);
  const error = useSc07((s) => s.metaError);
  const demoRunId = useSc01((s) => s.demoRunId);
  if (error) return <Problem text={`관리모델 개선 문서를 받지 못했다 — ${error}`} />;
  if (missing || (!meta && !demoRunId)) return <OpenCard />;
  if (!meta) return <p className="text-sm text-muted-foreground">관리모델 개선 문서를 불러오는 중…</p>;
  return <>{children}</>;
}

/** 장면 7 문서가 아직 없다 — 여는 것은 회사 사이트의 시연 조작이다(예전의 「열기」 단추 자리). */
function OpenCard() {
  const demoRunId = useSc01((s) => s.demoRunId);
  return <SceneNotOpened work="관리모델 개선" demoRunId={demoRunId} from="완료·성과 검토의 대표 보고(RPT61-v1)" />;
}

/** 조회 하나의 상태 — 로딩·권한 없음·버전 불일치·없음·통신 실패를 갈라 보인다. 실패를 통과·완료로 보이지 않는다(UI709). */
export function LoadGate<T>({ load, what, children }: { load: Load<T>; what: string; children: (data: T) => React.ReactNode }) {
  if (load.state === "idle" || load.state === "loading") return <p className="text-sm text-muted-foreground">{what}을(를) 불러오는 중…</p>;
  if (load.state === "ok") return <>{children(load.data)}</>;
  if (load.code === "ACCESS_DENIED") return <AccessDenied />;
  return (
    <div className="space-y-2">
      <Problem text={`${what} 조회 실패(${load.status}${load.code ? ` ${load.code}` : ""}) — ${load.error}. 통과·완료로 대신하지 않는다.`} />
      <Button variant="outline" size="sm" onClick={() => window.location.reload()}>
        <RefreshCw aria-hidden className="size-3.5" />
        다시 조회
      </Button>
    </div>
  );
}

function AccessDenied() {
  const setActor = useSc01((s) => s.setActor);
  return (
    <div className="flex flex-wrap items-center gap-3 rounded-md border px-3 py-2 text-sm">
      <Lock aria-hidden className="size-4 text-muted-foreground" />
      <span>지금 역할은 이 개선건(IMP71)을 볼 수 없다. 개선에 참여한 경영관리·구매·운영·구현 담당과 대표만 본다.</span>
      <Button size="sm" variant="outline" onClick={() => setActor("u-fin")}>
        경영관리 담당으로 보기
      </Button>
    </div>
  );
}

/** 사람 이름 — 역할명을 이름으로 쓰는 계정(운영담당·구현담당)은 한 번만 쓴다. */
export function who(p: Person | null | undefined): string {
  if (p && p.role === p.name) return p.name;
  return personName(p);
}

const FIELD_LABEL: Record<string, string> = {
  kind: "종류",
  links: "연결",
  content: "기록",
  caution: "주의",
  target: "대상",
  body: "본문",
  written_at: "작성",
  checked_at: "확인",
};

/**
 * 근거 ID — 누르면 같은 자리에서 구조화된 근거를 편다(U701-12). 화면 조회이고 Agent 입력이 아니다. 권한이 없거나 못 찾으면 그
 * 상태를 보이고 근거 확보로 보지 않는다.
 */
export function EvidenceChip({ id }: { id: string }) {
  const demoRunId = useSc01((s) => s.demoRunId);
  const actor = useSc01((s) => s.actor);
  const [open, setOpen] = useState(false);
  const [load, setLoad] = useState<Load<EvidenceView>>({ state: "idle" });
  const known = /^(EV7\d|E61-)/.test(id);
  const toggle = async () => {
    const next = !open;
    setOpen(next);
    if (!next || !demoRunId || !known || load.state === "ok") return;
    setLoad({ state: "loading" });
    const r = await sc07Api.evidence(demoRunId, id, actor);
    setLoad(r.ok ? { state: "ok", data: r.data } : { state: "error", status: r.status, error: r.error, code: r.code });
  };
  if (!known) return <span className="inline-block rounded border px-1.5 py-0.5 font-mono text-[11px] text-muted-foreground">{id}</span>;
  return (
    <span className="inline-block align-top">
      <button
        type="button"
        onClick={() => void toggle()}
        aria-expanded={open}
        className="inline-flex items-center gap-1 rounded border px-1.5 py-0.5 font-mono text-[11px] hover:bg-muted"
      >
        <FileSearch aria-hidden className="size-3" />
        {id}
      </button>
      {open ? (
        <span className="mt-1.5 block max-w-prose rounded-md border bg-muted/40 px-3 py-2 text-xs leading-relaxed">
          {load.state === "ok" ? (
            <>
              <span className="block text-muted-foreground">{load.data.source} · 가상 근거</span>
              {Object.entries(load.data.evidence)
                .filter(([k, v]) => k in FIELD_LABEL && v !== null && v !== "")
                .map(([k, v]) => (
                  <span key={k} className="block">
                    <span className="text-muted-foreground">{FIELD_LABEL[k]}</span>{" "}
                    {Array.isArray(v) ? v.join(" · ") : typeof v === "object" ? personName(v as Person) : String(v)}
                  </span>
                ))}
            </>
          ) : load.state === "error" ? (
            <span className="block">
              {load.code === "ACCESS_DENIED" ? "이 근거를 볼 권한이 없다" : load.code === "NOT_FOUND" ? "근거를 찾지 못했다" : load.error} — 근거
              확보로 보지 않는다.
            </span>
          ) : (
            <span className="block text-muted-foreground">근거를 불러오는 중…</span>
          )}
        </span>
      ) : null}
    </span>
  );
}
