"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import {
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  Clock,
  Pause,
  Play,
  PlayCircle,
  RotateCcw,
  Undo2,
  X,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { sc01Api } from "@/lib/sc01/client";
import { historySeqFor, nextBusinessEvening, SC01_SCENES } from "@/lib/sc01/scenes";
import { useSc01 } from "@/lib/store/sc01";

/** 장면이 반영된 뒤 머무는 시간. */
const DWELL_MS = 7_000;
const LAST = SC01_SCENES.length - 1;

/**
 * SC01 데모 플레이어 — 하단 고정 바(4.12).
 *
 * **앞으로는 실행, 뒤로는 읽기.** 장면이 엔진 각본보다 앞이면 그 단계까지 엔진이 실제로
 * 실행한다(역할 검사·업무 규칙을 그대로 탄다). 이미 지나간 장면이면 그 시점의 이력을 읽어
 * 보여 주기만 한다 — 실행을 되돌리지 않는다(4.6과 같은 원칙). "초기화"만 데모 실행을 S0로 되돌린다.
 *
 * 장면 이동은 한 핸들러에서 상태 적용과 라우팅을 함께 한다 — 상태를 감시하는 effect로
 * 라우팅하면 GNB로 직접 이동할 때 플레이어가 되돌려 버린다(4.1).
 */
export function Sc01DemoPlayer() {
  const router = useRouter();
  const pathname = usePathname();
  const demoRunId = useSc01((s) => s.demoRunId);
  const sceneIndex = useSc01((s) => Math.min(s.sceneIndex, LAST));
  const isPlaying = useSc01((s) => s.isPlaying);
  const isExpanded = useSc01((s) => s.isPlayerExpanded);
  const setScene = useSc01((s) => s.setScene);
  const setPlaying = useSc01((s) => s.setPlaying);
  const togglePlayer = useSc01((s) => s.togglePlayer);
  const [pending, setPending] = useState(false);
  const liveCase = useSc01((s) => s.live?.caseId ?? "BASE");
  /** 초기화할 때 고를 시연 사례 — 기본 / EX08(Agent 응답 실패). 같은 각본을 다른 조건으로 돌린다. */
  const [caseChoice, setCaseChoice] = useState<string | null>(null);
  const caseId = caseChoice ?? liveCase;
  const [error, setError] = useState<string | null>(null);
  const scene = SC01_SCENES[sceneIndex];

  // 본문 아래 비워 둘 자리를 재서 CSS에 알린다 — 높이를 상수로 박지 않는다(4.12).
  const barRef = useRef<HTMLElement>(null);
  useEffect(() => {
    const el = barRef.current;
    const root = document.documentElement;
    if (!el) return;
    const apply = () => root.style.setProperty("--demo-player-h", `${el.getBoundingClientRect().height}px`);
    apply();
    const observer = new ResizeObserver(apply);
    observer.observe(el);
    // 숨겨진 탭에서는 ResizeObserver가 발화하지 않는다 — resize로도 잰다(4.12).
    window.addEventListener("resize", apply, { passive: true });
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", apply);
      root.style.removeProperty("--demo-player-h");
    };
  }, [isExpanded]);

  /** 최신 요청만 반영한다 — 겹친 요청이 늦게 도착해 화면이 뒤로 튀지 않게(4.6). */
  const requestSeq = useRef(0);

  const jump = useCallback(
    async (index: number): Promise<"ok" | "failed"> => {
      if (!demoRunId) return "failed";
      const clamped = Math.min(Math.max(index, 0), LAST);
      const target = SC01_SCENES[clamped];
      const mine = ++requestSeq.current;
      setScene(clamped);
      setError(null);
      if (target.route !== pathname) router.push(target.route);

      const store = useSc01.getState();
      const done = store.live?.scriptIndex ?? -1;
      setPending(true);
      try {
        if (target.script > done) {
          // 앞으로 — 남은 단계를 차례로 실제 실행한다.
          for (let i = done + 1; i <= target.script; i++) {
            const r = await sc01Api.step(demoRunId, i);
            if (mine !== requestSeq.current) return "ok";
            if (!r.ok) {
              setError(r.error);
              return "failed";
            }
            useSc01.getState().setLive(r.data);
          }
          useSc01.getState().setPast(null);
        } else if (target.script === done) {
          store.setPast(null);
        } else {
          // 뒤로 — 그 시점을 읽기만 한다.
          const h = await sc01Api.history(demoRunId);
          if (mine !== requestSeq.current) return "ok";
          const seq = h.ok ? historySeqFor(h.data, target.script) : null;
          if (seq === null) {
            setError("그 장면의 이력이 없다 — 초기화 후 다시 진행한다");
            return "failed";
          }
          const past = await sc01Api.at(demoRunId, seq);
          if (mine !== requestSeq.current) return "ok";
          if (!past.ok) {
            setError(past.error);
            return "failed";
          }
          useSc01.getState().setPast({ seq, view: past.data });
        }
        return "ok";
      } finally {
        if (mine === requestSeq.current) setPending(false);
      }
    },
    [demoRunId, pathname, router, setScene],
  );

  // 자동 재생 effect가 `jump`에 의존하면 화면이 바뀔 때마다 타이머가 다시 걸린다 — ref로 쓴다(4.6).
  const jumpRef = useRef(jump);
  useEffect(() => {
    jumpRef.current = jump;
  }, [jump]);

  // 자동 재생 — 고정 간격이 아니라 장면이 반영된 뒤에 머무름을 시작하는 자기 예약 루프다.
  useEffect(() => {
    if (!isPlaying) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    const advance = async () => {
      if (cancelled) return;
      const current = useSc01.getState().sceneIndex;
      if (current >= LAST) {
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

  const reset = async () => {
    if (!demoRunId) return;
    setPlaying(false);
    requestSeq.current++;
    setPending(true);
    const r = await sc01Api.reset(demoRunId, caseId);
    setPending(false);
    if (!r.ok) {
      setError(r.error);
      return;
    }
    useSc01.getState().setLive(r.data);
    useSc01.getState().setPast(null);
    setScene(0);
    if (pathname !== "/") router.push("/");
  };

  /** 가상시계 이동(시연관리자). 시각만 옮긴다 — 인수·승인은 실행하지 않는다. 기한을 넘기면 알림이 생긴다. */
  const moveClock = async () => {
    const live = useSc01.getState().live;
    if (!demoRunId || !live) return;
    setPending(true);
    const r = await sc01Api.clock(demoRunId, nextBusinessEvening(live.clock));
    setPending(false);
    if (r.ok) {
      useSc01.getState().setLive(r.data);
      useSc01.getState().setPast(null);
    } else {
      setError(r.error);
    }
  };

  if (!isExpanded) {
    return (
      <aside
        ref={barRef}
        aria-label="데모 시나리오 플레이어"
        className="fixed inset-x-0 bottom-0 z-50 flex justify-center border-t bg-background/95 py-2 backdrop-blur"
      >
        <button
          type="button"
          onClick={togglePlayer}
          className="inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-medium hover:bg-muted"
          aria-expanded={false}
        >
          <PlayCircle aria-hidden className="size-3.5" />
          SC01 시연
          <span className="text-muted-foreground tabular-nums">
            {sceneIndex + 1}/{SC01_SCENES.length}
          </span>
          <ChevronUp aria-hidden className="size-3.5 text-muted-foreground" />
        </button>
      </aside>
    );
  }

  return (
    <aside
      ref={barRef}
      aria-label="데모 시나리오 플레이어"
      className="fixed inset-x-0 bottom-0 z-50 border-t bg-background/95 backdrop-blur"
    >
      <div className="mx-auto w-full max-w-7xl px-4 sm:px-6 lg:px-8">
        {/* 좁은 화면에서는 스크러버를 감춘다(4.14). */}
        <ol className="hidden gap-1 px-3.5 pb-1 sm:flex">
          {SC01_SCENES.map((s, i) => (
            <li key={s.id} className="flex-1">
              <button
                type="button"
                onClick={() => void jump(i)}
                title={`${i + 1}. ${s.title}`}
                aria-label={`장면 ${i + 1}: ${s.title}`}
                aria-current={i === sceneIndex ? "step" : undefined}
                className="group w-full py-1.5"
              >
                <span
                  className={cn(
                    "block h-1 rounded-full transition-colors",
                    i === sceneIndex ? "bg-foreground" : i < sceneIndex ? "bg-muted-foreground/50" : "bg-muted group-hover:bg-muted-foreground/30",
                  )}
                />
              </button>
            </li>
          ))}
        </ol>

        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 pb-2.5">
          <div className="min-w-0 flex-1 basis-80">
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
              <span className="text-[10px] text-muted-foreground tabular-nums">
                장면 {sceneIndex + 1} / {SC01_SCENES.length}
              </span>
              <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">{scene.stage}</span>
              <span className="text-sm font-semibold text-foreground">{scene.title}</span>
            </div>
            <p className="line-clamp-1 text-xs leading-relaxed text-muted-foreground sm:line-clamp-2">{scene.narration}</p>
            {pending ? <p className="text-[11px] text-muted-foreground">엔진에 장면을 반영하는 중…</p> : null}
            {error ? (
              <p role="alert" className="text-[11px]" style={{ color: "var(--viz-status-serious)" }}>
                장면 이동 실패 — {error}
              </p>
            ) : null}
          </div>

          <div className="flex flex-wrap items-center gap-1.5 sm:shrink-0 sm:flex-nowrap">
            <Button variant="outline" size="sm" className="h-7 text-[11px]" onClick={() => void jump(0)} disabled={sceneIndex === 0}>
              <Undo2 aria-hidden className="size-3" />
              처음으로
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="h-7 text-[11px]"
              onClick={() => void moveClock()}
              title="가상시계를 다음 영업일 18:30으로 옮긴다 — 기한을 넘긴 업무에 알림이 생긴다(EX07)"
            >
              <Clock aria-hidden className="size-3" />
              다음 영업일 18:30
            </Button>
            <select
              value={caseId}
              onChange={(e) => setCaseChoice(e.target.value)}
              aria-label="초기화할 시연 사례"
              title="초기화할 때 적용할 시연 사례"
              className="h-7 rounded-md border bg-transparent px-1 text-[11px]"
            >
              <option value="BASE">기본 시연</option>
              <option value="EX08">EX08 Agent 실패</option>
            </select>
            <Button
              variant="outline"
              size="sm"
              className="h-7 text-[11px]"
              onClick={() => void reset()}
              title="이 데모 실행을 S0(사건 전)으로 되돌린다"
            >
              <RotateCcw aria-hidden className="size-3" />
              초기화
            </Button>
            <Button variant="outline" size="icon" className="size-7" onClick={() => void jump(sceneIndex - 1)} disabled={sceneIndex === 0} aria-label="이전 장면">
              <ChevronLeft aria-hidden className="size-3" />
            </Button>
            <Button size="sm" className="h-7 text-[11px]" onClick={() => setPlaying(!isPlaying)} disabled={sceneIndex >= LAST && !isPlaying}>
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
            <Button variant="outline" size="icon" className="size-7" onClick={() => void jump(sceneIndex + 1)} disabled={sceneIndex >= LAST} aria-label="다음 장면">
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
