"use client";

/**
 * 탭이 보일 때만 도는 폴링.
 *
 * **숨겨진 탭을 계속 긁으면 안 된다.** 데모 중에는 탭을 여러 개 열어 두기 쉽고, 보이지도
 * 않는 화면 때문에 초당 요청이 늘면 LLM 모드의 엔진이 그만큼 느려진다. 이 프로젝트는
 * 숨겨진 패널에서 `document.hidden`이 true가 되는 것을 이미 겪었다(CLAUDE.md 함정 절).
 *
 * 다시 보이는 순간 **즉시 한 번 읽는다** — 숨어 있던 동안 바뀐 것을 그 자리에서 따라잡아야
 * 한다. 그러지 않으면 탭을 돌아왔을 때 다음 주기까지 낡은 값이 보인다.
 */

import { useEffect } from "react";

/** 무언가 실행 중일 때 — 값이 실제로 움직이는 구간이다. */
export const POLL_RUNNING_MS = 3_000;

/**
 * 멈춰 있을 때 — 사람 대기나 종료 상태.
 *
 * 0으로 두지 않는 이유: 변화가 **다른 탭이나 다른 사람**에게서 올 수 있다. 협업
 * 스테이션에서 승인하면 Rolling Plan의 과제가 달라지는데, 그 화면이 다시 읽지 않으면
 * 새로고침해야 반영된다.
 */
export const POLL_IDLE_MS = 15_000;

export function useVisiblePoll(run: () => void, intervalMs: number | null) {
  useEffect(() => {
    if (intervalMs === null) return;

    let timer: ReturnType<typeof setInterval> | null = null;

    const stop = () => {
      if (timer !== null) clearInterval(timer);
      timer = null;
    };
    const start = () => {
      stop();
      timer = setInterval(run, intervalMs);
    };

    const sync = () => {
      if (document.visibilityState === "visible") {
        // 숨어 있던 동안의 변화를 즉시 따라잡는다.
        run();
        start();
      } else {
        stop();
      }
    };

    sync();
    document.addEventListener("visibilitychange", sync);
    return () => {
      stop();
      document.removeEventListener("visibilitychange", sync);
    };
  }, [run, intervalMs]);
}
