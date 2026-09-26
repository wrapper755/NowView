"use client";

import { useCallback, useEffect, useRef } from "react";
import { usePathname, useRouter } from "next/navigation";
import {
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  Pause,
  Play,
  PlayCircle,
  RotateCcw,
  X,
} from "lucide-react";

import { useEnginePlayback } from "@/components/engine/use-engine-playback";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { DEMO_SCENE_INTERVAL_MS, type DemoScene } from "@/lib/demo-scenario";
import { scenarios } from "@/lib/mock-data/scenarios";
import {
  selectScenario,
  selectSceneIndex,
  useDemoController,
} from "@/lib/store/demo-controller";
import { MANAGEMENT_STAGE_LABEL } from "@/lib/types/cockpit";

/**
 * 플로팅 데모 시나리오 플레이어.
 *
 * 다섯 화면을 6단계 루프 순서로 이어 준다. 장면을 옮길 때 스토어 상태(BPM 지점·승인)와
 * 화면 전환을 **한 핸들러 안에서 함께** 처리한다 — 상태 변화를 감시하는 effect로 라우팅하면
 * 사용자가 직접 이동했을 때 플레이어가 되돌려 버리는 싸움이 난다.
 *
 * **엔진 모드에서도 동작한다**(CLAUDE.md 4.18). 장면이 선언한 진행 지점을 엔진 인스턴스에
 * 반영한다 — 뒤로는 체크포인트를 읽고, 앞으로는 실제로 진행한다.
 *
 * **자동 재생은 고정 간격이 아니다.** 장면이 반영된 뒤에 머무름을 시작하므로 LLM 모드에서
 * 왕복이 수십 초여도 장면이 밀리지 않는다.
 */
export function DemoPlayer() {
  const router = useRouter();
  const pathname = usePathname();

  const scenario = useDemoController(selectScenario);
  const sceneIndex = useDemoController(selectSceneIndex);
  const activeScenarioId = useDemoController((s) => s.activeScenarioId);
  const setScenario = useDemoController((s) => s.setScenario);
  const demoScenario = scenario.scenes;
  const LAST_SCENE_INDEX = demoScenario.length - 1;
  const isPlaying = useDemoController((s) => s.isPlaying);
  const isExpanded = useDemoController((s) => s.isPlayerExpanded);
  const goToScene = useDemoController((s) => s.goToScene);
  const { applyScene, pending: enginePending, error: engineError } = useEnginePlayback();
  const setPlaying = useDemoController((s) => s.setPlaying);
  const togglePlayer = useDemoController((s) => s.togglePlayer);
  const exitDemo = useDemoController((s) => s.exitDemo);

  const scene = demoScenario[sceneIndex];

  /**
   * 장면 이동 = 스토어 상태 적용 + 화면 전환. 둘은 항상 같이 일어난다.
   *
   * **엔진 모드면 인스턴스도 그 장면으로 옮긴다.** 뒤로는 과거 체크포인트를 읽고
   * (인스턴스는 그대로), 앞으로는 실제로 진행하며 장면이 선언한 결정을 넣는다.
   * 엔진이 붙어 있지 않으면 `applyScene`이 아무것도 하지 않으므로 Mock 경로 그대로다.
   *
   * 스토어 상태를 **먼저** 적용한다 — 엔진 왕복(LLM 모드에서는 수십 초)을 기다리는
   * 동안 화면이 멈춰 있으면 플레이어가 고장난 것처럼 보인다.
   */
  const jump = useCallback(
    (index: number) => {
      const clamped = Math.min(Math.max(index, 0), LAST_SCENE_INDEX);
      const target = demoScenario[clamped];
      goToScene(index);
      if (target.route !== pathname) router.push(target.route);
      return applyScene(scenario, target);
    },
    [demoScenario, LAST_SCENE_INDEX, goToScene, pathname, router, applyScene, scenario],
  );

  /**
   * 최신 `jump`을 ref에 담아 둔다.
   *
   * **자동 재생 effect가 `jump`에 의존하면 안 된다.** `jump`은 `pathname`에 의존하는데,
   * 장면이 화면을 바꾸면 pathname이 바뀌어 effect가 재실행되고 머무름 타이머가 처음부터
   * 다시 걸린다 — LLM 왕복이 40초여도 7초 뒤에 다음 장면이 발사된다. 고치려던 바로
   * 그 문제다. ref는 렌더 중이 아니라 effect에서 갱신한다(`react-hooks/refs`).
   */
  const jumpRef = useRef(jump);
  useEffect(() => {
    jumpRef.current = jump;
  }, [jump]);

  /**
   * 자동 재생 — **고정 간격이 아니라 자기 예약 루프**다.
   *
   * `setInterval`로 7초마다 넘기면 Mock 모드에서는 맞지만 엔진 LLM 모드에서 깨진다.
   * 앞 장면의 왕복이 수십 초 걸리는데 타이머는 그것을 모르고 다음 장면을 발사하므로
   * 요청이 겹치고, 화면은 아직 반영되지 않은 장면의 내레이션을 읽는다.
   *
   * 그래서 **장면이 반영된 뒤에 머무름을 시작한다.** 한 장면에 머무는 시간은
   * "엔진 왕복 + `DEMO_SCENE_INTERVAL_MS`"가 되고, Mock 모드에서는 왕복이 0이라
   * 기존과 똑같이 7초다.
   *
   * setState는 전부 타이머·비동기 콜백 안에서 일어난다 — effect 본문에서 상태를 바꾸면
   * `react-hooks/set-state-in-effect`에 걸린다.
   */
  useEffect(() => {
    if (!isPlaying) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;

    const advance = async () => {
      if (cancelled) return;
      const current = selectSceneIndex(useDemoController.getState());
      if (current >= LAST_SCENE_INDEX) {
        setPlaying(false);
        return;
      }

      const result = await jumpRef.current(current + 1);
      if (cancelled) return;
      if (result === "failed") {
        // 엔진이 실패했는데 계속 넘어가면 화면과 인스턴스가 어긋난 채로 데모가 진행된다.
        // 멈추고 사유를 보여 주는 편이 낫다(내레이션 아래 배너).
        setPlaying(false);
        return;
      }
      timer = setTimeout(() => void advance(), DEMO_SCENE_INTERVAL_MS);
    };

    timer = setTimeout(() => void advance(), DEMO_SCENE_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
    // `jump`을 빼는 것이 핵심이다(위 ref 주석 참조).
  }, [isPlaying, setPlaying, LAST_SCENE_INDEX]);

  if (!isExpanded) {
    return (
      <button
        type="button"
        onClick={togglePlayer}
        className="fixed bottom-4 left-1/2 z-50 inline-flex -translate-x-1/2 items-center gap-2 rounded-full border bg-background/95 px-3.5 py-2 text-xs font-medium shadow-lg backdrop-blur hover:bg-muted"
        aria-expanded={false}
      >
        <PlayCircle aria-hidden className="size-3.5" />
        데모 시나리오
        <span className="text-muted-foreground tabular-nums">
          {sceneIndex + 1}/{demoScenario.length}
        </span>
        <ChevronUp aria-hidden className="size-3.5 text-muted-foreground" />
      </button>
    );
  }

  return (
    <aside
      aria-label="데모 시나리오 플레이어"
      className="fixed bottom-4 left-1/2 z-50 w-[min(44rem,calc(100vw-2rem))] -translate-x-1/2 rounded-xl border bg-background/95 shadow-lg backdrop-blur"
    >
      <div className="flex items-start gap-3 p-3.5">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className="text-[10px] text-muted-foreground tabular-nums">
              장면 {sceneIndex + 1} / {demoScenario.length}
            </span>
            <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
              {MANAGEMENT_STAGE_LABEL[scene.stage]}
            </span>
            <span className="text-sm font-semibold text-foreground">{scene.title}</span>
          </div>
          <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
            {scene.narration}
          </p>
          {/* 엔진 모드에서는 장면 이동이 서버 왕복이다. 진행·실패를 숨기면
              플레이어가 멈춘 것인지 실패한 것인지 알 수 없다. */}
          {enginePending ? (
            <p className="mt-1 text-[11px] text-muted-foreground">엔진에 장면을 반영하는 중…</p>
          ) : null}
          {engineError ? (
            <p
              role="alert"
              className="mt-1 text-[11px]"
              style={{ color: "var(--viz-status-serious)" }}
            >
              엔진 장면 이동 실패 — {engineError.message}
            </p>
          ) : null}
        </div>

        <div className="flex shrink-0 items-center gap-1">
          {/* 시나리오 전환. 각 시나리오는 자기 진행·결정을 따로 들고 있어 오가도 유지된다. */}
          <div
            role="tablist"
            aria-label="시나리오 선택"
            className="flex gap-0.5 rounded-lg border p-0.5"
          >
            {scenarios.map((s) => (
              <button
                key={s.id}
                role="tab"
                type="button"
                aria-selected={s.id === activeScenarioId}
                title={s.summary}
                onClick={() => {
                  setScenario(s.id);
                  const target = s.scenes[0];
                  if (target.route !== pathname) router.push(target.route);
                }}
                className={
                  s.id === activeScenarioId
                    ? "rounded-md bg-muted px-2 py-1 text-[11px] font-medium text-foreground"
                    : "rounded-md px-2 py-1 text-[11px] text-muted-foreground hover:text-foreground"
                }
              >
                {s.shortTitle}
              </button>
            ))}
          </div>
          <Button
            variant="ghost"
            size="icon"
            className="size-7"
            onClick={togglePlayer}
            aria-label="플레이어 접기"
          >
            <X aria-hidden className="size-3.5" />
          </Button>
        </div>
      </div>

      <SceneScrubber scenes={demoScenario} sceneIndex={sceneIndex} onJump={jump} />

      <div className="flex flex-wrap items-center justify-between gap-2 border-t p-2.5">
        <div className="flex items-center gap-1">
          <Button
            variant="outline"
            size="sm"
            className="h-7 text-[11px]"
            onClick={() => {
              setPlaying(false);
              exitDemo();
              if (demoScenario[0].route !== pathname) router.push(demoScenario[0].route);
            }}
            disabled={sceneIndex === 0 && !isPlaying}
          >
            <RotateCcw aria-hidden className="size-3" />
            처음으로
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="h-7 text-[11px]"
            onClick={() => jump(sceneIndex - 1)}
            disabled={sceneIndex === 0}
          >
            <ChevronLeft aria-hidden className="size-3" />
            이전
          </Button>
        </div>

        <div className="flex items-center gap-1">
          <Button
            size="sm"
            className="h-7 text-[11px]"
            onClick={() => setPlaying(!isPlaying)}
            disabled={sceneIndex >= LAST_SCENE_INDEX && !isPlaying}
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
          <Button
            variant="outline"
            size="sm"
            className="h-7 text-[11px]"
            onClick={() => jump(sceneIndex + 1)}
            disabled={sceneIndex >= LAST_SCENE_INDEX}
          >
            다음
            <ChevronRight aria-hidden className="size-3" />
          </Button>
        </div>
      </div>
    </aside>
  );
}

/** 장면 스크러버. 어느 장면으로든 바로 건너뛸 수 있다. */
function SceneScrubber({
  scenes,
  sceneIndex,
  onJump,
}: {
  scenes: DemoScene[];
  sceneIndex: number;
  onJump: (index: number) => void;
}) {
  return (
    <ol className="flex gap-1 px-3.5 pb-1">
      {scenes.map((s: DemoScene, index: number) => {
        const isCurrent = index === sceneIndex;
        const isPast = index < sceneIndex;
        return (
          <li key={s.id} className="flex-1">
            <button
              type="button"
              onClick={() => onJump(index)}
              title={`${index + 1}. ${s.title}`}
              aria-label={`장면 ${index + 1}: ${s.title}`}
              aria-current={isCurrent ? "step" : undefined}
              className="group w-full py-1.5"
            >
              <span
                className={cn(
                  "block h-1 rounded-full transition-colors",
                  isCurrent
                    ? "bg-foreground"
                    : isPast
                      ? "bg-muted-foreground/50"
                      : "bg-muted group-hover:bg-muted-foreground/30",
                )}
              />
            </button>
          </li>
        );
      })}
    </ol>
  );
}
