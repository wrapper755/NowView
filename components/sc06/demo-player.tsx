"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { ChevronLeft, ChevronRight, ChevronUp, Pause, Play, PlayCircle, RotateCcw, Undo2, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Narration } from "@/components/shared/narration";
import { cn } from "@/lib/utils";
import { sc06Api } from "@/lib/sc06/client";
import { SC06_SCENES, sceneFor } from "@/lib/sc06/scenes";
import { useSc01 } from "@/lib/store/sc01";
import { useSc06 } from "@/lib/store/sc06";
import { preparationText } from "@/components/shared/preparation-note";
import type { Preparation } from "@/lib/preparation";

/**
 * SC06 데모 플레이어 — 세 동작(210초). 장면 1~5 플레이어와 모양이 같지만 **엔진을 실행하지 않는다**: 장면 6은 이미 확인된
 * 보고본을 조회하는 시점이라 앞뒤 이동이 화면(어느 화면·상세 펼침)만 바꾼다. 초기화도 화면 상태만 되돌린다 — 확정본·
 * 근거·확인 이력은 엔진에 그대로다(구현명세 11장).
 *
 * 장면 6은 **경영관리 담당 시점**이다(화면구성 U601·U602). 지금 역할이 이 검토건을 볼 수 없으면(403) 이동할 때 경영관리
 * 담당으로 바꾼다 — 역할 선택은 신뢰 경계가 아니고(5.4) 엔진이 역할을 다시 검사한다.
 */
export function Sc06DemoPlayer() {
  const router = useRouter();
  const pathname = usePathname();
  const demoRunId = useSc01((s) => s.demoRunId);
  const missing = useSc06((s) => s.missing);
  const hasDoc = useSc06((s) => s.meta !== null);
  const denied = useSc06((s) => s.summary.state === "error" && s.summary.code === "ACCESS_DENIED");
  const detailOpen = useSc06((s) => s.detailOpen);
  const isPlaying = useSc06((s) => s.isPlaying);
  const isExpanded = useSc06((s) => s.isPlayerExpanded);
  const { setPlaying, togglePlayer } = useSc06.getState();
  const [pending, setPending] = useState(false);
  const [prep, setPrep] = useState<Preparation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const last = SC06_SCENES.length - 1;
  // 플레이어 밖(GNB·화면 버튼)으로 움직여도 지금 화면이 곧 장면이다
  const sceneIndex = sceneFor(pathname, detailOpen);
  const scene = SC06_SCENES[sceneIndex];

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

  const jump = useCallback(
    (index: number) => {
      const target = SC06_SCENES[Math.min(Math.max(index, 0), last)];
      const s = useSc06.getState();
      if (s.summary.state === "error" && s.summary.code === "ACCESS_DENIED") useSc01.getState().setActor("u-fin");
      if (target.detail) s.openDetail("ACT42");
      else s.closeDetail();
      setError(null);
      if (target.route !== pathname) router.push(target.route);
    },
    [last, pathname, router],
  );

  const jumpRef = useRef(jump);
  useEffect(() => {
    jumpRef.current = jump;
  }, [jump]);

  // 자동 재생 — 장면마다 시연순서의 시간(60·90·60초)을 다 머물지 않고 장면 1~5와 같은 7초씩 머문다
  useEffect(() => {
    if (!isPlaying) return;
    const timer = setTimeout(() => {
      const current = sceneFor(window.location.pathname, useSc06.getState().detailOpen);
      if (current >= last) {
        setPlaying(false);
        return;
      }
      jumpRef.current(current + 1);
    }, 7_000);
    return () => clearTimeout(timer);
  }, [isPlaying, sceneIndex, last, setPlaying]);

  const open = async () => {
    setPending(true);
    setError(null);
    const r = await sc06Api.open(demoRunId, "center", setPrep);
    setPending(false);
    setPrep(null);
    if (!r.ok) {
      setError(r.error);
      return;
    }
    if (r.data.demoRunId !== demoRunId) useSc01.getState().setDemoRunId(r.data.demoRunId);
    useSc06.getState().setMeta(r.data);
    jump(0);
  };

  /** 화면 상태만 처음으로 — 확정본·근거·확인 이력은 그대로다. */
  const reset = () => {
    useSc06.getState().resetView();
    if (pathname !== "/sc06") router.push("/sc06");
  };

  if (!isExpanded) {
    return (
      <aside ref={barRef} aria-label="완료·성과 검토 데모 플레이어" data-demo-player="collapsed"
        className="fixed inset-x-0 bottom-0 z-50 lg:left-56 flex justify-center border-t-2 border-t-brand bg-demo-surface/95 py-2 backdrop-blur xl:inset-x-auto xl:right-4 xl:bottom-4 xl:rounded-full xl:border xl:py-1 xl:shadow-sm">
        <button type="button" onClick={togglePlayer} className="inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-medium hover:bg-muted" aria-expanded={false}>
          <PlayCircle aria-hidden className="size-3.5" />
          SC06 시연
          <span className="text-muted-foreground tabular-nums">
            {sceneIndex + 1}/{SC06_SCENES.length}
          </span>
          <ChevronUp aria-hidden className="size-3.5 text-muted-foreground" />
        </button>
      </aside>
    );
  }

  return (
    <aside ref={barRef} aria-label="완료·성과 검토 데모 플레이어" data-demo-player="expanded"
      className="fixed inset-x-0 bottom-0 z-50 lg:left-56 border-t-2 border-t-brand bg-demo-surface/95 backdrop-blur xl:inset-x-auto xl:top-12 xl:bottom-0 xl:right-0 xl:w-80 xl:overflow-y-auto xl:border-t-0 xl:border-l xl:border-l-brand/40">
      <div className="mx-auto w-full max-w-7xl px-4 sm:px-6 lg:px-8 xl:flex xl:max-w-none xl:flex-col xl:px-4 xl:pt-4">
        <ol className="hidden gap-1 px-3.5 pb-1 sm:flex xl:order-last xl:flex-col xl:gap-0.5 xl:border-t xl:px-0 xl:pt-3 xl:pb-4">
          {SC06_SCENES.map((s, i) => (
            <li key={s.id} style={{ flexGrow: s.seconds }} className="basis-0 xl:flex-none xl:basis-auto">
              <button
                type="button"
                onClick={() => jump(i)}
                title={`${s.title} · ${s.seconds}초`}
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
                단계 {sceneIndex + 1} / {SC06_SCENES.length}
              </span>
              <span className="rounded bg-brand-soft px-1.5 py-0.5 text-[10px] text-brand">{scene.seconds}초</span>
              <span className="text-sm font-semibold text-foreground xl:w-full xl:text-base xl:leading-snug">{scene.title}</span>
            </div>
            <Narration
              text={
                missing
                  ? "이 데모 실행에는 완료·성과 검토가 없다 — 「완료·성과 검토 열기」를 누르면 결정 실행·계획 갱신을 완료(HANDOFF51)까지 진행한 뒤 Q4 검토 자료와 보고본을 적재한다."
                  : denied
                    ? "지금 역할은 이 검토건을 볼 수 없다 — 단계 이동이 경영관리 담당 시점으로 바꾼다."
                    : scene.narration
              }
            />
            {pending ? (
              <p className="text-[11px] text-muted-foreground">
                {prep ? preparationText(prep) : "결정 실행·계획 갱신을 끝내고 완료·성과 검토를 적재하는 중…"}
              </p>
            ) : null}
            {error ? (
              <p role="alert" className="text-[11px]" style={{ color: "var(--viz-status-serious)" }}>
                완료·성과 검토 열기 실패 — {error}
              </p>
            ) : null}
          </div>

          <div className="flex flex-wrap items-center gap-1.5 sm:shrink-0 sm:flex-nowrap xl:w-full xl:shrink xl:flex-wrap">
            {missing ? (
              <Button size="sm" className="h-7 text-[11px]" onClick={() => void open()} disabled={pending}>
                <PlayCircle aria-hidden className="size-3" />
                완료·성과 검토 열기
              </Button>
            ) : null}
            <Button variant="outline" size="sm" className="h-7 text-[11px]" onClick={() => jump(0)} disabled={sceneIndex === 0 || !hasDoc}>
              <Undo2 aria-hidden className="size-3" />
              <span className="sr-only sm:not-sr-only">처음으로</span>
            </Button>
            <Button variant="outline" size="sm" className="h-7 text-[11px]" onClick={reset} disabled={!hasDoc} title="화면 선택·펼침만 처음으로 — 확정본·근거·확인 이력은 그대로다">
              <RotateCcw aria-hidden className="size-3" />
              <span className="sr-only sm:not-sr-only">초기화</span>
            </Button>
            <Button variant="outline" size="icon" className="size-7" onClick={() => jump(sceneIndex - 1)} disabled={sceneIndex === 0 || !hasDoc} aria-label="이전 단계">
              <ChevronLeft aria-hidden className="size-3" />
            </Button>
            <Button size="sm" className="h-7 text-[11px]" onClick={() => setPlaying(!isPlaying)} disabled={!hasDoc || (sceneIndex >= last && !isPlaying)}>
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
            <Button variant="outline" size="icon" className="size-7" onClick={() => jump(sceneIndex + 1)} disabled={!hasDoc || sceneIndex >= last} aria-label="다음 단계">
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
