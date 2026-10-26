"use client";

import { usePathname } from "next/navigation";

import { Sc01DemoPlayer } from "@/components/sc01/demo-player";
import { Sc02DemoPlayer } from "@/components/sc02/demo-player";
import { Sc02SessionSync } from "@/components/sc02/session-sync";
import { isScene2 } from "@/components/shared/scenario-nav";

/**
 * 하단 데모 플레이어 — 지금 장면의 것 하나만 둔다(둘 다 두면 본문 아래 자리가 겹친다, 4.12).
 * 장면 2 문서 수신(`Sc02SessionSync`)은 장면 2 화면에서만 돈다. 장면 1 수신은 레이아웃이 늘 둔다.
 */
export function DemoPlayerSwitch() {
  const pathname = usePathname();
  return (
    <>
      <Sc02SessionSync />
      {isScene2(pathname) ? <Sc02DemoPlayer /> : <Sc01DemoPlayer />}
    </>
  );
}
