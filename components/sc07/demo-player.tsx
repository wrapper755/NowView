"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useCompanyRouter as useRouter, useScenePath as usePathname } from "@/lib/company-nav";
import { ChevronLeft, ChevronRight, ChevronUp, Pause, Play, PlayCircle, RotateCcw, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Narration } from "@/components/shared/narration";
import { cn } from "@/lib/utils";
import { sc07Api } from "@/lib/sc07/client";
import { SC07_CONFIRM_STEPS, SC07_PLAYER, playerIndexFor } from "@/lib/sc07/scenes";
import { useSc01 } from "@/lib/store/sc01";
import { useSc07 } from "@/lib/store/sc07";
import { preparationText } from "@/components/shared/preparation-note";
import type { Preparation } from "@/lib/preparation";

const LAST_CONFIRM = SC07_CONFIRM_STEPS.length - 1;

/**
 * SC07 데모 플레이어 — **확인·적용 절차 다섯 단계 + U701 두 동작**. 장면 1~6 플레이어와 모양이 같다.
 *
 * * **확인·적용 절차는 앞으로는 실행이다** — 그 단계까지 엔진 각본(`POST …/script/{i}`)으로 실제로 결재한다(담당 검사·대상 버전·
 *   설정 일치 그대로, Center면 대리 답). 지난 단계로는 돌아가지 않는다 — 확인·적용 이력에서 본다.
 * * **두 동작은 화면 상태만 바꾼다**(보기 A·B). 절차가 덜 끝났으면 먼저 설정 반영 확인까지 진행한다 — 두 동작은 적용이 확인된
 *   뒤를 보는 시점이다(구현명세 5장 「화면 기준시각은 마지막 설정 확인시각」).
 * * **초기화는 확인·적용 절차만 되돌린다** — 적재(개선·입력·근거)는 그대로다. 보기는 A로 돌아간다.
 *
 * 조회는 **경영관리 담당 시점**이다. 지금 역할이 이 개선건을 볼 수 없으면(403) 이동할 때 경영관리 담당으로 바꾼다.
 */
export function Sc07DemoPlayer() {
  const router = useRouter();
  const pathname = usePathname();
  const demoRunId = useSc01((s) => s.demoRunId);
  const missing = useSc07((s) => s.missing);
  const meta = useSc07((s) => s.meta);
  const hasDoc = meta !== null;
  const scriptIndex = meta?.scriptIndex ?? -1;
  const denied = useSc07((s) => s.improvement.state === "error" && s.improvement.code === "ACCESS_DENIED");
  const view = useSc07((s) => s.view);
  const isPlaying = useSc07((s) => s.isPlaying);
  const isExpanded = useSc07((s) => s.isPlayerExpanded);
  const { setPlaying, togglePlayer } = useSc07.getState();
  const [pending, setPending] = useState(false);
  const [running, setRunning] = useState<string | null>(null);
  const [prep, setPrep] = useState<Preparation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const last = SC07_PLAYER.length - 1;
  // 플레이어 밖(GNB·화면 버튼·화면 답)으로 움직여도 지금 화면·엔진 위치가 곧 단계다
  const sceneIndex = playerIndexFor(pathname, view, scriptIndex);
  const scene = SC07_PLAYER[sceneIndex];
  const seq = useRef(0);
  // 장면 경로(회사 접두어 없는 `/sc07/…`) — 자동 재생 타이머가 지금 화면을 읽는다(window.location은 `/c/{회사}`가 붙는다)
  const pathRef = useRef(pathname);
  useEffect(() => {
    pathRef.current = pathname;
  }, [pathname]);

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

  /** 엔진 각본을 `upto`까지 — 이미 지난 단계는 건너뛴다. 실패하면 사유를 보이고 멈춘다. */
  const runScript = useCallback(async (upto: number): Promise<boolean> => {
    const s = useSc07.getState().meta;
    if (!s) return true;
    const mine = ++seq.current;
    for (let i = s.scriptIndex + 1; i <= upto; i++) {
      setRunning(SC07_CONFIRM_STEPS[i].title);
      const r = await sc07Api.step(s.demoRunId, i);
      if (mine !== seq.current) return false;
      if (!r.ok) {
        setRunning(null);
        setError(`${SC07_CONFIRM_STEPS[i].title} — ${r.error}`);
        setPlaying(false);
        return false;
      }
      useSc07.getState().setMeta(r.data);
    }
    setRunning(null);
    return true;
  }, [setPlaying]);

  const jump = useCallback(
    async (index: number) => {
      const target = SC07_PLAYER[Math.min(Math.max(index, 0), last)];
      setError(null);
      if (target.kind === "confirm") {
        if (target.route !== pathname) router.push(target.route);
        await runScript(target.scriptIndex);
        return;
      }
      if (!(await runScript(LAST_CONFIRM))) return;
      const s = useSc07.getState();
      if (s.improvement.state === "error" && s.improvement.code === "ACCESS_DENIED") useSc01.getState().setActor("u-fin");
      s.setView(target.view);
      if (target.route !== pathRef.current) router.push(target.route);
    },
    [last, pathname, router, runScript],
  );

  const jumpRef = useRef(jump);
  useEffect(() => {
    jumpRef.current = jump;
  }, [jump]);

  // 자동 재생 — 단계가 반영된 뒤 7초 머문다(장면 1~5와 같다). 결재가 도는 동안은 기다린다.
  useEffect(() => {
    if (!isPlaying || running) return;
    const timer = setTimeout(() => {
      const m = useSc07.getState().meta;
      const current = playerIndexFor(pathRef.current, useSc07.getState().view, m?.scriptIndex ?? -1);
      if (current >= last) {
        setPlaying(false);
        return;
      }
      void jumpRef.current(current + 1);
    }, 7_000);
    return () => clearTimeout(timer);
  }, [isPlaying, sceneIndex, last, setPlaying, running]);

  const open = async () => {
    setPending(true);
    setError(null);
    const r = await sc07Api.open(demoRunId, "center", setPrep);
    setPending(false);
    setPrep(null);
    if (!r.ok) {
      setError(r.error);
      return;
    }
    if (r.data.demoRunId !== demoRunId) useSc01.getState().setDemoRunId(r.data.demoRunId);
    useSc07.getState().setMeta(r.data);
    router.push("/sc07/confirm");
  };

  /** 확인·적용 절차만 처음으로 — 적재(개선·입력·근거)는 그대로다. 보기도 A로. */
  const reset = async () => {
    if (!meta) return;
    seq.current++;
    setPlaying(false);
    setPending(true);
    setError(null);
    const r = await sc07Api.reset(meta.demoRunId);
    setPending(false);
    if (!r.ok) {
      setError(`초기화 — ${r.error}`);
      return;
    }
    useSc07.getState().setMeta(r.data);
    useSc07.getState().resetView();
    if (pathname !== "/sc07/confirm") router.push("/sc07/confirm");
  };

  if (!isExpanded) {
    return (
      <aside ref={barRef} aria-label="관리모델 개선 데모 플레이어" data-demo-player="collapsed"
        className="fixed inset-x-0 bottom-0 z-50 lg:left-56 flex justify-center border-t-2 border-t-brand bg-demo-surface/95 py-2 backdrop-blur xl:inset-x-auto xl:right-4 xl:bottom-4 xl:rounded-full xl:border xl:py-1 xl:shadow-sm">
        <button type="button" onClick={togglePlayer} className="inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-medium hover:bg-muted" aria-expanded={false}>
          <PlayCircle aria-hidden className="size-3.5" />
          SC07 시연
          <span className="text-muted-foreground tabular-nums">
            {sceneIndex + 1}/{SC07_PLAYER.length}
          </span>
          <ChevronUp aria-hidden className="size-3.5 text-muted-foreground" />
        </button>
      </aside>
    );
  }

  return (
    <aside ref={barRef} aria-label="관리모델 개선 데모 플레이어" data-demo-player="expanded"
      className="fixed inset-x-0 bottom-0 z-50 lg:left-56 border-t-2 border-t-brand bg-demo-surface/95 backdrop-blur xl:inset-x-auto xl:top-12 xl:bottom-0 xl:right-0 xl:w-80 xl:overflow-y-auto xl:border-t-0 xl:border-l xl:border-l-brand/40">
      <div className="mx-auto w-full max-w-7xl px-4 sm:px-6 lg:px-8 xl:flex xl:max-w-none xl:flex-col xl:px-4 xl:pt-4">
        <ol className="hidden gap-1 px-3.5 pb-1 sm:flex xl:order-last xl:flex-col xl:gap-0.5 xl:border-t xl:px-0 xl:pt-3 xl:pb-4">
          {SC07_PLAYER.map((s, i) => (
            <li key={s.kind === "view" ? s.id : s.code} style={{ flexGrow: s.seconds }} className="basis-0 xl:flex-none xl:basis-auto">
              <button
                type="button"
                onClick={() => void jump(i)}
                title={s.kind === "view" ? `${s.title} · ${s.seconds}초` : `${s.code} ${s.title}`}
                aria-label={`단계 ${i + 1}: ${s.title}`}
                aria-current={i === sceneIndex ? "step" : undefined}
                disabled={!hasDoc || running !== null}
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
                단계 {sceneIndex + 1} / {SC07_PLAYER.length}
              </span>
              <span className="rounded bg-brand-soft px-1.5 py-0.5 text-[10px] text-brand">
                {scene.kind === "view" ? `조회 ${scene.seconds}초` : `확인·적용 ${scene.code}`}
              </span>
              <span className="text-sm font-semibold text-foreground xl:w-full xl:text-base xl:leading-snug">{scene.title}</span>
            </div>
            <Narration
              text={
                missing
                  ? "이 데모 실행에는 관리모델 개선이 없다 — 「관리모델 개선 열기」를 누르면 완료·성과 검토를 대표 보고까지 진행한 뒤 개선건(IMP71)을 적재하고 확인·적용 절차를 기다린다."
                  : denied
                    ? "지금 역할은 이 개선건을 볼 수 없다 — 단계 이동이 경영관리 담당 시점으로 바꾼다."
                    : scene.narration
              }
            />
            {pending ? (
              <p className="text-[11px] text-muted-foreground">
                {prep ? preparationText(prep) : "엔진에 반영하는 중…"}
              </p>
            ) : null}
            {running ? <p className="text-[11px] text-muted-foreground">결재 진행 중 — {running}…</p> : null}
            {error ? (
              <p role="alert" className="text-[11px]" style={{ color: "var(--viz-status-serious)" }}>
                {error}
              </p>
            ) : null}
          </div>

          <div className="flex max-w-full flex-wrap items-center gap-1.5 sm:shrink-0 xl:w-full xl:shrink">
            {missing ? (
              <Button size="sm" className="h-7 text-[11px]" onClick={() => void open()} disabled={pending}>
                <PlayCircle aria-hidden className="size-3" />
                관리모델 개선 열기
              </Button>
            ) : null}
            <Button variant="outline" size="sm" className="h-7 text-[11px]" onClick={() => void reset()} disabled={!hasDoc || pending || running !== null} title="확인·적용 절차만 처음으로 — 적재(개선·입력·근거)는 그대로다">
              <RotateCcw aria-hidden className="size-3" />
              <span className="sr-only sm:not-sr-only">초기화</span>
            </Button>
            <Button variant="outline" size="icon" className="size-7" onClick={() => void jump(sceneIndex - 1)} disabled={sceneIndex === 0 || !hasDoc || running !== null} aria-label="이전 단계">
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
            <Button variant="outline" size="icon" className="size-7" onClick={() => void jump(sceneIndex + 1)} disabled={!hasDoc || sceneIndex >= last || running !== null} aria-label="다음 단계">
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
