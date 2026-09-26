import { defineConfig } from "vitest/config";

/**
 * 테스트는 **순수 로직만** 다룬다 — 불변식, 상태 파생 규칙, 화면 간 수치 연동.
 * 렌더링 테스트를 두지 않으므로 jsdom도 React 플러그인도 필요 없고, 그만큼 빠르다.
 * 레이아웃·가독성처럼 계산으로 못 잡는 것은 브라우저에서 눈으로 본다.
 *
 * `.mts` 확장자인 이유: package.json에 `type: "module"`이 없어 `.ts` 설정은 CommonJS로
 * 읽히고 Vite가 경고한다. 앱 전체를 ESM으로 바꾸는 것보다 설정 파일만 바꾸는 쪽이 안전하다.
 */
export default defineConfig({
  // `@/` 경로 별칭을 tsconfig에서 그대로 읽는다 (vite-tsconfig-paths 플러그인 불필요).
  resolve: { tsconfigPaths: true },
  test: {
    environment: "node",
    include: ["tests/**/*.test.ts"],
  },
});
