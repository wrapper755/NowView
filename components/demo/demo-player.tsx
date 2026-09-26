"use client";

import { useCallback, useEffect } from "react";
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
  const setPlaying = useDemoController((s) => s.setPlaying);
  const togglePlayer = useDemoController((s) => s.togglePlayer);
  const exitDemo = useDemoController((s) => s.exitDemo);

  const scene = demoScenario[sceneIndex];

  /** 장면 이동 = 스토어 상태 적용 + 화면 전환. 둘은 항상 같이 일어난다. */
  const jump = useCallback(
    (index: number) => {
      const target = demoScenario[Math.min(Math.max(index, 0), LAST_SCENE_INDEX)];
      goToScene(index);
      if (target.route !== pathname) router.push(target.route);
    },
    [demoScenario, LAST_SCENE_INDEX, goToScene, pathname, router],
  );

  // 자동 재생. setState는 타이머 콜백 안에서만 일어나므로 effect 본문에서 상태를 바꾸지 않는다.
  useEffect(() => {
    if (!isPlaying) return;
    const id = setInterval(() => {
      const current = selectSceneIndex(useDemoController.getState());
      if (current >= LAST_SCENE_INDEX) {
        setPlaying(false);
        return;
      }
      jump(current + 1);
    }, DEMO_SCENE_INTERVAL_MS);
    return () => clearInterval(id);
  }, [isPlaying, jump, setPlaying, LAST_SCENE_INDEX]);

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
