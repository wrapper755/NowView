import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    // dataviz 스킬에서 그대로 들여온 검증기. 스킬이 갱신될 때 병합할 수 있도록
    // 로직을 손대지 않으므로, 우리 규칙(미사용 헬퍼 경고)도 적용하지 않는다.
    "scripts/validate_palette.js",
  ]),
]);

export default eslintConfig;
