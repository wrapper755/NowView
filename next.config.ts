import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /**
   * 컨테이너 이미지를 위해 `.next/standalone`에 필요한 것만 추려 낸다.
   * 이것이 없으면 이미지에 node_modules 전체(수백 MB)를 넣어야 한다.
   *
   * 로컬 개발에는 영향이 없다 — `next dev`도 `next start`도 그대로 동작하고,
   * standalone 산출물이 추가로 생길 뿐이다.
   */
  output: "standalone",
};

export default nextConfig;
