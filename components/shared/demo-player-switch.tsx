"use client";

import { useScenePath as usePathname } from "@/lib/company-nav";

import { Sc01DemoPlayer } from "@/components/sc01/demo-player";
import { Sc02DemoPlayer } from "@/components/sc02/demo-player";
import { Sc02SessionSync } from "@/components/sc02/session-sync";
import { Sc03DemoPlayer } from "@/components/sc03/demo-player";
import { Sc03SessionSync } from "@/components/sc03/session-sync";
import { Sc04DemoPlayer } from "@/components/sc04/demo-player";
import { Sc04SessionSync } from "@/components/sc04/session-sync";
import { Sc05DemoPlayer } from "@/components/sc05/demo-player";
import { Sc05SessionSync } from "@/components/sc05/session-sync";
import { Sc06DemoPlayer } from "@/components/sc06/demo-player";
import { Sc06SessionSync } from "@/components/sc06/session-sync";
import { Sc07DemoPlayer } from "@/components/sc07/demo-player";
import { Sc07SessionSync } from "@/components/sc07/session-sync";
import { sceneOf } from "@/components/shared/scenario-nav";

/**
 * 하단 데모 플레이어 — 지금 장면의 것 하나만 둔다(둘 다 두면 본문 아래 자리가 겹친다, 4.12). 회사 첫 화면에는 없다.
 * 장면 2~7 문서 수신(`Sc02SessionSync`~`Sc07SessionSync`)은 그 장면 화면에서만 돈다. 장면 1 수신은 레이아웃이 늘 둔다.
 */
export function DemoPlayerSwitch() {
  const path = usePathname();
  const scene = sceneOf(path);
  return (
    <>
      <Sc02SessionSync />
      <Sc03SessionSync />
      <Sc04SessionSync />
      <Sc05SessionSync />
      <Sc06SessionSync />
      <Sc07SessionSync />
      {/* 회사 첫 화면은 어느 업무도 아니다 — 장면 1 플레이어를 띄우면 첫 화면이 장면 1처럼 보였다(2026-11-01). */}
      {path === "/" ? null : scene === 7 ? <Sc07DemoPlayer /> : scene === 6 ? <Sc06DemoPlayer /> : scene === 5 ? <Sc05DemoPlayer /> : scene === 4 ? <Sc04DemoPlayer /> : scene === 3 ? <Sc03DemoPlayer /> : scene === 2 ? <Sc02DemoPlayer /> : <Sc01DemoPlayer />}
    </>
  );
}
