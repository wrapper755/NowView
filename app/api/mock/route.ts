import { ok } from "@/lib/api/response";
import { MOCK_DATASETS } from "@/app/api/mock/datasets";

/**
 * GET /api/mock — 사용 가능한 Mock 데이터셋 목록.
 *
 * 개별 데이터셋마다 라우트 파일을 두는 대신 레지스트리 하나로 관리한다
 * (`[dataset]/route.ts`). 데이터셋이 늘어도 파일이 늘지 않는다.
 */
export function GET() {
  return ok({
    datasets: Object.entries(MOCK_DATASETS).map(([name, entry]) => ({
      name,
      description: entry.description,
      href: `/api/mock/${name}`,
    })),
  });
}
