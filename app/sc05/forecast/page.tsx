import type { Metadata } from "next";

import { Sc05ForecastScreen } from "@/components/sc05/forecast-screen";

export const metadata: Metadata = { title: "NowView — 장면 5 공식 Forecast" };

/** U507 Forecast 검토·승인. 데이터는 클라이언트에서 엔진(BFF)으로 받는다 — 페이지는 정적이다(4.3). */
export default function Page() {
  return <Sc05ForecastScreen />;
}
