"use client";

import { useEffect } from "react";

import { useDemoController } from "@/lib/store/demo-controller";

/**
 * 저장된 데모 상태를 mount 이후에 복원한다.
 *
 * 스토어는 `skipHydration: true`라 자동 복원하지 않는다 — 화면이 정적 프리렌더라서
 * 서버 HTML은 항상 기본 상태인데, persist가 모듈 로드 시점에 복원해 버리면 첫 렌더가
 * 서버와 달라져 하이드레이션이 깨진다.
 *
 * 그래서 첫 페인트는 기본 상태로 나가고 직후에 저장된 상태로 바뀐다. 아주 짧게 깜빡이지만
 * 하이드레이션 오류를 감수하는 것보다 낫다.
 */
export function StoreHydrator() {
  useEffect(() => {
    void useDemoController.persist.rehydrate();
  }, []);

  return null;
}
