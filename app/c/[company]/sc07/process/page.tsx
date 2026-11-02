import type { Metadata } from "next";

import { Sc07ProcessScreen } from "@/components/sc07/process-screen";

export const metadata: Metadata = { title: "NowView — 관리모델 개선 BPM 흐름" };

/** 확인·적용 절차의 BPMN 캔버스. 페이지는 정적이다(4.3). */
export default function Page() {
  return <Sc07ProcessScreen />;
}
