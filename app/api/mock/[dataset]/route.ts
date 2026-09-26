import { MOCK_DATASETS } from "@/app/api/mock/datasets";
import { notFound, ok } from "@/lib/api/response";

/**
 * GET /api/mock/[dataset] — Mock 데이터셋 하나.
 *
 * Next 16에서 동적 세그먼트 `params`는 Promise다. await 하지 않으면 런타임에 터진다.
 */
export async function GET(
  _request: Request,
  { params }: { params: Promise<{ dataset: string }> },
) {
  const { dataset } = await params;
  const entry = MOCK_DATASETS[dataset];

  if (!entry) {
    return notFound(`알 수 없는 데이터셋: ${dataset}`, {
      available: Object.keys(MOCK_DATASETS),
    });
  }

  return ok(entry.load());
}
