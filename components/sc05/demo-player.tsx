"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useCompanyRouter as useRouter, useScenePath as usePathname } from "@/lib/company-nav";
import { ChevronLeft, ChevronRight, ChevronUp, Clock, Pause, Play, PlayCircle, RotateCcw, Undo2, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Narration } from "@/components/shared/narration";
import { cn } from "@/lib/utils";
import { formatClock } from "@/lib/sc01/format";
import { historySeqFor, nextBusinessEvening } from "@/lib/sc01/scenes";
import { sc05Api, type Sc05Executor } from "@/lib/sc05/client";
import { scenesFor } from "@/lib/sc05/scenes";
import { useSc01 } from "@/lib/store/sc01";
import { useSc05 } from "@/lib/store/sc05";
import { preparationText } from "@/components/shared/preparation-note";
import type { Preparation } from "@/lib/preparation";

const DWELL_MS = 7_000;

/**
 * SC05 데모 플레이어 — 장면 4 플레이어와 같은 원칙(4.1·4.12).
 *
 * **앞으로는 실행, 뒤로는 읽기.** 장면은 엔진 각본(`GET /sc05/script?case_id=`)에서 만든다 — 사례마다 단계가
 * 다르다. **사례를 바꾸면 새 데모 실행이다**(BASE와 X 사례는 별도 실행 — 기본 결과와 섞지 않는다) — 초기화는 같은 사례로 D500.
 * 단계마다 가상시계가 그 시점으로 옮겨 가고, 그 사이의 배경 원천(다른 과제·주문·FC50)이 시각대로 들어온다.
 */
export function Sc05DemoPlayer() {
  const router = useRouter();
  const pathname = usePathname();
  const demoRunId = useSc01((s) => s.demoRunId);
  const script = useSc05((s) => s.script);
  const scenes = useMemo(() => scenesFor(script), [script]);
  const last = scenes.length - 1;
  const sceneIndex = useSc05((s) => Math.min(s.sceneIndex, last));
  const isPlaying = useSc05((s) => s.isPlaying);
  const isExpanded = useSc05((s) => s.isPlayerExpanded);
  const missing = useSc05((s) => s.missing);
  const hasDoc = useSc05((s) => s.live !== null);
  const caseId = useSc05((s) => s.live?.caseId ?? "BASE");
  const cases = useSc05((s) => s.cases);
  /**
   * 실행 위치 — Center(기본)·Studio. 화면은 내장을 고르지 않는다(2026-10-27). 지금 실행이 내장이면(이전에 만든
   * 시험용) Center를 고른 것으로 보인다 — 초기화하면 Center로 바뀐다.
   */
  const liveExecutor = useSc05((s) => s.live?.executor);
  const executor: Sc05Executor = liveExecutor === "studio" ? "studio" : "center";
  /** 각본이 돌지 않는 실행 — Studio, 그리고 대리 답용 키가 없는 Center. */
  const external = useSc05((s) => s.live !== null && !s.live.answerHere);
  const { setScene, setPlaying, togglePlayer } = useSc05.getState();
  const [pending, setPending] = useState(false);
  const [prep, setPrep] = useState<Preparation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const scene = scenes[sceneIndex];

  const barRef = useRef<HTMLElement>(null);
  useEffect(() => {
    const el = barRef.current;
    const root = document.documentElement;
    if (!el) return;
    const apply = () => root.style.setProperty("--demo-player-h", `${el.getBoundingClientRect().height}px`);
    apply();
    const observer = new ResizeObserver(apply);
    observer.observe(el);
    window.addEventListener("resize", apply, { passive: true });
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", apply);
      root.style.removeProperty("--demo-player-h");
    };
  }, [isExpanded]);

  const requestSeq = useRef(0);

  const jump = useCallback(
    async (index: number): Promise<"ok" | "failed"> => {
      if (!demoRunId || !hasDoc) return "failed";
      const clamped = Math.min(Math.max(index, 0), last);
      const target = scenes[clamped];
      const mine = ++requestSeq.current;
      setScene(clamped);
      setError(null);
      if (target.route !== pathname) router.push(target.route);
      const done = useSc05.getState().live?.scriptIndex ?? -1;
      setPending(true);
      try {
        if (target.script > done) {
          for (let i = done + 1; i <= target.script; i++) {
            const r = await sc05Api.step(demoRunId, i);
            if (mine !== requestSeq.current) return "ok";
            if (!r.ok) {
              setError(r.error);
              // 실패한 단계로 표시가 넘어가 있지 않게 — 엔진이 실제로 간 지점으로 되돌린다(화면 직접 진행 실측:
              // 실패 문구 옆에 「단계 4/62」가 보였다)
              const reached = useSc05.getState().live?.scriptIndex ?? -1;
              const at = scenes.findIndex((s) => s.script === reached);
              setScene(at < 0 ? 0 : at);
              return "failed";
            }
            useSc05.getState().setLive(r.data);
          }
          useSc05.getState().setPast(null);
        } else if (target.script === done) {
          useSc05.getState().setPast(null);
        } else {
          const h = await sc05Api.history(demoRunId);
          if (mine !== requestSeq.current) return "ok";
          const seq = h.ok ? historySeqFor(h.data, target.script) : null;
          if (seq === null) {
            setError("그 단계의 이력이 없다 — 초기화 후 다시 진행한다");
            return "failed";
          }
          const past = await sc05Api.at(demoRunId, seq);
          if (mine !== requestSeq.current) return "ok";
          if (!past.ok) {
            setError(past.error);
            return "failed";
          }
          useSc05.getState().setPast({ seq, view: past.data });
        }
        return "ok";
      } finally {
        if (mine === requestSeq.current) setPending(false);
      }
    },
    [demoRunId, hasDoc, last, pathname, router, scenes, setScene],
  );

  const jumpRef = useRef(jump);
  useEffect(() => {
    jumpRef.current = jump;
  }, [jump]);

  /**
   * 플레이어 위치가 엔진의 각본 지점(`scriptIndex`)을 따라간다 — 화면에서 직접 답해 앞으로 갔을 때(엔진이 화면의
   * 결정도 각본 지점으로 옮긴다, `process._follow_script`). 장면 3 플레이어와 같다 — 위치만 옮기고 라우팅은 하지
   * 않는다(4.1).
   */
  const liveScript = useSc05((s) => s.live?.scriptIndex ?? null);
  const liveRun = useSc05((s) => s.live?.demoRunId ?? null);
  const seenScript = useRef<{ run: string; index: number } | null>(null);
  useEffect(() => {
    if (liveRun === null || liveScript === null) return;
    const seen = seenScript.current;
    if (seen?.run === liveRun && liveScript <= seen.index) {
      seen.index = liveScript; // 초기화로 되돌아갔다 — 위치는 초기화 핸들러가 이미 정했다
      return;
    }
    const at = scenes.findIndex((s) => s.script === liveScript);
    if (at < 0) return; // 각본이 아직 오지 않았다 — 오면 다시 본다
    setScene(at);
    seenScript.current = { run: liveRun, index: liveScript };
  }, [liveRun, liveScript, scenes, setScene]);

  /**
   * 다음 각본 단계의 시각 — 손으로 진행할 때 시계를 그 단계 시각으로 옮긴다. 「다음 영업일 18:30」만 있으면 7/13 →
   * 8/19에 27번을 눌러야 했고, 8/20 아침에 들어오는 근거를 쓰려면 18:30(기한 18:00 뒤)까지 가야 했다(화면 직접 진행
   * 실측). 시각만 옮긴다 — 그 단계를 실행하지 않는다. 지금보다 늦은 첫 단계를 고른다.
   */
  const liveClock = useSc05((s) => s.live?.clock ?? null);
  const nextAt = useMemo(() => {
    if (liveClock === null || liveScript === null) return null;
    const now = Date.parse(liveClock);
    const step = script.find((s) => s.index > liveScript && Date.parse(s.at) > now);
    return step?.at ?? null;
  }, [liveClock, liveScript, script]);

  useEffect(() => {
    if (!isPlaying) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    const advance = async () => {
      if (cancelled) return;
      const current = useSc05.getState().sceneIndex;
      if (current >= scenesFor(useSc05.getState().script).length - 1) {
        setPlaying(false);
        return;
      }
      const result = await jumpRef.current(current + 1);
      if (cancelled) return;
      if (result === "failed") {
        setPlaying(false);
        return;
      }
      timer = setTimeout(() => void advance(), DWELL_MS);
    };
    timer = setTimeout(() => void advance(), DWELL_MS);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [isPlaying, setPlaying]);

  /** 같은 사례로 D500. 장면 4 기준·다른 실행은 그대로다. */
  const reset = async () => {
    if (!demoRunId) return;
    setPlaying(false);
    requestSeq.current++;
    setPending(true);
    const r = await sc05Api.reset(demoRunId, executor);
    setPending(false);
    if (!r.ok) {
      setError(r.error);
      return;
    }
    useSc05.getState().setLive(r.data);
    useSc05.getState().setPast(null);
    setScene(0);
    if (pathname !== "/sc05") router.push("/sc05");
  };

  /** 사례 바꾸기 = 새 데모 실행(장면 1~4를 완료까지 실제로 돌린 뒤 장면 5 D500). */
  const startCase = async (next: string) => {
    setPlaying(false);
    requestSeq.current++;
    setPending(true);
    setError(null);
    const fresh = next !== caseId || !hasDoc;
    const r = await sc05Api.create(fresh && hasDoc ? null : demoRunId, next, executor, setPrep);
    setPending(false);
    setPrep(null);
    if (!r.ok) {
      setError(r.error);
      return;
    }
    if (r.data.demoRunId !== demoRunId) useSc01.getState().setDemoRunId(r.data.demoRunId);
    useSc05.getState().setLive(r.data);
    useSc05.getState().setPast(null);
    setScene(0);
    if (pathname !== "/sc05") router.push("/sc05");
  };

  /** 실행 위치 바꾸기 = 이 데모 실행의 장면 5를 그 위치로 D500부터(장면 4 기준은 그대로). */
  const switchExecutor = async (next: Sc05Executor) => {
    if (!demoRunId || !hasDoc) return;
    setPlaying(false);
    requestSeq.current++;
    setPending(true);
    setError(null);
    const r = await sc05Api.reset(demoRunId, next);
    setPending(false);
    if (!r.ok) {
      setError(r.error);
      return;
    }
    useSc05.getState().setLive(r.data);
    useSc05.getState().setPast(null);
    setScene(0);
    if (pathname !== "/sc05") router.push("/sc05");
  };

  const moveClock = async (to?: string) => {
    const live = useSc05.getState().live;
    if (!demoRunId || !live) return;
    setPending(true);
    const r = await sc05Api.clock(demoRunId, to ?? nextBusinessEvening(live.clock));
    setPending(false);
    if (r.ok) {
      useSc05.getState().setLive(r.data);
      useSc05.getState().setPast(null);
    } else setError(r.error);
  };

  if (!isExpanded) {
    return (
      <aside ref={barRef} aria-label="결정 실행·계획 갱신 데모 플레이어" data-demo-player="collapsed"
        className="fixed inset-x-0 bottom-0 z-50 lg:left-56 flex justify-center border-t-2 border-t-brand bg-demo-surface/95 py-2 backdrop-blur xl:inset-x-auto xl:right-4 xl:bottom-4 xl:rounded-full xl:border xl:py-1 xl:shadow-sm">
        <button type="button" onClick={togglePlayer} className="inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-medium hover:bg-muted" aria-expanded={false}>
          <PlayCircle aria-hidden className="size-3.5" />
          SC05 시연
          <span className="text-muted-foreground tabular-nums">
            {sceneIndex + 1}/{scenes.length}
          </span>
          <ChevronUp aria-hidden className="size-3.5 text-muted-foreground" />
        </button>
      </aside>
    );
  }

  return (
    <aside ref={barRef} aria-label="결정 실행·계획 갱신 데모 플레이어" data-demo-player="expanded"
      className="fixed inset-x-0 bottom-0 z-50 lg:left-56 border-t-2 border-t-brand bg-demo-surface/95 backdrop-blur xl:inset-x-auto xl:top-12 xl:bottom-0 xl:right-0 xl:w-80 xl:overflow-y-auto xl:border-t-0 xl:border-l xl:border-l-brand/40">
      <div className="mx-auto w-full max-w-7xl px-4 sm:px-6 lg:px-8 xl:flex xl:max-w-none xl:flex-col xl:px-4 xl:pt-4">
        <ol className="hidden gap-1 px-3.5 pb-1 sm:flex xl:order-last xl:flex-col xl:gap-0.5 xl:border-t xl:px-0 xl:pt-3 xl:pb-4">
          {scenes.map((s, i) => (
            <li key={s.id} className="flex-1 xl:flex-none">
              <button
                type="button"
                onClick={() => void jump(i)}
                title={`${i + 1}. ${s.title}`}
                aria-label={`단계 ${i + 1}: ${s.title}`}
                aria-current={i === sceneIndex ? "step" : undefined}
                disabled={!hasDoc}
                className={cn("group w-full py-1.5 xl:rounded-md xl:px-2 xl:text-left xl:hover:bg-muted", i === sceneIndex && "xl:bg-brand-soft")}
              >
                <span
                  className={cn(
                    "block h-1 rounded-full transition-colors xl:hidden",
                    i === sceneIndex ? "bg-brand" : i < sceneIndex ? "bg-muted-foreground/50" : "bg-muted group-hover:bg-muted-foreground/30",
                  )}
                />
                <span className={cn("hidden text-xs leading-snug xl:block", i === sceneIndex ? "font-semibold text-brand" : i < sceneIndex ? "text-muted-foreground" : "text-foreground/80")}>
                  <span className="mr-1.5 tabular-nums text-muted-foreground">{i + 1}</span>
                  {s.title}
                </span>
              </button>
            </li>
          ))}
        </ol>

        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 pb-2.5">
          <div className="min-w-0 flex-1 basis-80 xl:rounded-lg xl:border xl:border-brand/25 xl:bg-card xl:p-3 xl:shadow-sm">
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
              <span className="text-[10px] text-muted-foreground tabular-nums">
                단계 {sceneIndex + 1} / {scenes.length}
              </span>
              <span className="rounded bg-brand-soft px-1.5 py-0.5 text-[10px] text-brand">{scene.stage}</span>
              <span className="text-sm font-semibold text-foreground xl:w-full xl:text-base xl:leading-snug">{scene.title}</span>
            </div>
            <Narration
              text={
                missing ? "이 데모 실행에는 결정 실행·계획 갱신이 없다 — 「결정 실행·계획 갱신 시작」을 누르면 개선안 검토·실행 승인을 완료(HANDOFF41)까지 진행한 뒤 시작한다." : scene.narration
              }
            />
            {pending ? (
              <p className="text-[11px] text-muted-foreground">{prep ? preparationText(prep) : "엔진에 단계를 반영하는 중…"}</p>
            ) : null}
            {error ? (
              <p role="alert" className="text-[11px]" style={{ color: "var(--viz-status-serious)" }}>
                단계 이동 실패 — {error}
              </p>
            ) : null}
          </div>

          <div className="flex flex-wrap items-center gap-1.5 sm:shrink-0 sm:flex-nowrap xl:w-full xl:shrink xl:flex-wrap">
            {missing ? (
              <Button size="sm" className="h-7 text-[11px]" onClick={() => void startCase(caseId)} disabled={pending}>
                <PlayCircle aria-hidden className="size-3" />
                결정 실행·계획 갱신 시작
              </Button>
            ) : null}
            <Button variant="outline" size="sm" className="h-7 text-[11px]" onClick={() => void jump(0)} disabled={sceneIndex === 0 || !hasDoc}>
              <Undo2 aria-hidden className="size-3" />
              <span className="sr-only sm:not-sr-only">처음으로</span>
            </Button>
            <Button variant="outline" size="sm" className="h-7 text-[11px]" onClick={() => void moveClock()} disabled={!hasDoc} title="가상시계를 다음 영업일 18:30으로 — 기한을 넘긴 업무에 알림이 생기고, 그 사이의 배경 원천이 들어온다. 승인·착수는 생기지 않는다">
              <Clock aria-hidden className="size-3" />
              <span className="sr-only sm:not-sr-only">다음 영업일 18:30</span>
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="h-7 text-[11px]"
              onClick={() => nextAt && void moveClock(nextAt)}
              disabled={!hasDoc || nextAt === null || pending}
              title="가상시계를 다음 시연 단계의 시각으로 — 손으로 진행할 때 쓴다. 그 단계를 실행하지 않고, 그 사이의 배경 원천만 들어온다"
            >
              <Clock aria-hidden className="size-3" />
              <span className="sr-only sm:not-sr-only">{nextAt ? `다음 단계 시각 ${formatClock(nextAt)}` : "다음 단계 시각"}</span>
            </Button>
            <select
              value={caseId}
              onChange={(e) => void startCase(e.target.value)}
              aria-label="시연 사례"
              title="사례를 바꾸면 새 데모 실행을 만든다(고객 생산계획 변경 대응부터) — 기본 시연 결과를 덮지 않는다"
              className="h-7 max-w-[8rem] rounded-md border bg-transparent px-1 text-[11px] sm:max-w-[11rem]"
            >
              {(cases.length ? cases : [{ caseId: "BASE", label: "기본 시연" }]).map((c) => (
                <option key={c.caseId} value={c.caseId}>
                  {c.label}
                </option>
              ))}
            </select>
            <select
              value={executor}
              onChange={(e) => void switchExecutor(e.target.value as Sc05Executor)}
              aria-label="실행 위치"
              title="BPM을 누가 돌 것인가 — 바꾸면 이 데모 실행의 결정 실행·계획 갱신을 D500부터 다시 시작한다"
              disabled={!hasDoc}
              className="hidden h-7 rounded-md border bg-transparent px-1 text-[11px] sm:block"
            >
              <option value="center">Center 서버 실행</option>
              <option value="studio">Studio 시험 실행</option>
            </select>
            <Button variant="outline" size="sm" className="h-7 text-[11px]" onClick={() => void reset()} disabled={!hasDoc} title="이 데모 실행의 결정 실행·계획 갱신만 D500으로 되돌린다">
              <RotateCcw aria-hidden className="size-3" />
              <span className="sr-only sm:not-sr-only">초기화</span>
            </Button>
            <Button variant="outline" size="icon" className="size-7" onClick={() => void jump(sceneIndex - 1)} disabled={sceneIndex === 0 || !hasDoc} aria-label="이전 단계">
              <ChevronLeft aria-hidden className="size-3" />
            </Button>
            <Button
              size="sm"
              className="h-7 text-[11px]"
              onClick={() => setPlaying(!isPlaying)}
              disabled={!hasDoc || external || (sceneIndex >= last && !isPlaying)}
              title={external ? "이 실행 위치에서는 각본이 결재에 답할 수 없다 — 결재는 바깥에서 답한다" : undefined}
            >
              {isPlaying ? (
                <>
                  <Pause aria-hidden className="size-3" />
                  일시정지
                </>
              ) : (
                <>
                  <Play aria-hidden className="size-3" />
                  자동 재생
                </>
              )}
            </Button>
            <Button variant="outline" size="icon" className="size-7" onClick={() => void jump(sceneIndex + 1)} disabled={!hasDoc || external || sceneIndex >= last} aria-label="다음 단계">
              <ChevronRight aria-hidden className="size-3" />
            </Button>
            <Button variant="ghost" size="icon" className="size-7" onClick={togglePlayer} aria-label="플레이어 접기">
              <X aria-hidden className="size-3.5" />
            </Button>
          </div>
        </div>
      </div>
    </aside>
  );
}
