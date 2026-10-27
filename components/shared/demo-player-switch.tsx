"use client";

import { usePathname } from "next/navigation";

import { Sc01DemoPlayer } from "@/components/sc01/demo-player";
import { Sc02DemoPlayer } from "@/components/sc02/demo-player";
import { Sc02SessionSync } from "@/components/sc02/session-sync";
import { Sc03DemoPlayer } from "@/components/sc03/demo-player";
import { Sc03SessionSync } from "@/components/sc03/session-sync";
import { sceneOf } from "@/components/shared/scenario-nav";

/**
 * 하단 데모 플레이어 — 지금 장면의 것 하나만 둔다(둘 다 두면 본문 아래 자리가 겹친다, 4.12).
 * 장면 2·3 문서 수신(`Sc02SessionSync`·`Sc03SessionSync`)은 그 장면 화면에서만 돈다. 장면 1 수신은 레이아웃이 늘 둔다.
 */
export function DemoPlayerSwitch() {
  const scene = sceneOf(usePathname());
  return (
    <>
      <Sc02SessionSync />
      <Sc03SessionSync />
      {scene === 3 ? <Sc03DemoPlayer /> : scene === 2 ? <Sc02DemoPlayer /> : <Sc01DemoPlayer />}
    </>
  );
}
