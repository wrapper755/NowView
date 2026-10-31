/**
 * 회사 등록부(화면 쪽) — 엔진 `engine/app/companies.py`의 사본이다. 회사 목록 화면과 정적 경로(`/c/{회사}`)를 빌드 때
 * 만들어야 해서 화면에도 둔다. 엔진 시험(`test_companies.py`)이 두 등록부의 회사·장면·토픽을 대조한다.
 *
 * NowView는 회사 사이트가 아니다 — Center에 올린 회사별 BPM 프로세스의 일감을 수행하는 **일꾼**이고, 그 위에서 회사별
 * 운영 현황을 보여 주는 **대시보드**다. 회사마다 장면(BPM 프로세스)을 하나씩 회사 이름으로 옮긴다 — 옮긴 장면은
 * `migrated`다(Center에 회사 이름의 패키지·토픽으로 다시 올렸다).
 */

export type CompanyScene = {
  no: 1 | 2 | 3 | 4 | 5 | 6;
  work: string;
  detail: string;
  topic: string;
  package: string;
};

export type Company = {
  id: string;
  name: string;
  description: string;
  scenes: CompanyScene[];
};

export const COMPANIES: Company[] = [
  {
    id: "autoparts",
    name: "가상 자동차 부품사",
    description: "매출 약 1조원 · 현대·기아 주요 고객 · A제품 울산공장 a~e 모델 — 2027년 시나리오 1",
    scenes: [
      { no: 1, work: "고객 생산계획 변경 대응", detail: "위험 감지 · 현업 통제 · 인계", topic: "autoparts-sc01", package: "autoparts.sc01" },
      { no: 2, work: "외주 단가 인상 검토", detail: "협상 · 순차 승인 · 원가 등록", topic: "nowview-sc02", package: "nowview.sc02" },
      { no: 3, work: "수익성 통합 분석", detail: "부서 확인 · 수시회의 · 분석과제", topic: "nowview-sc03", package: "nowview.sc03" },
      { no: 4, work: "개선안 검토·실행 승인", detail: "월간회의 · 대표 승인 · 책임 인수", topic: "nowview-sc04", package: "nowview.sc04" },
      { no: 5, work: "결정 실행·계획 갱신", detail: "실행계획 · 착수 · 공식 전망", topic: "nowview-sc05", package: "nowview.sc05" },
      { no: 6, work: "완료·성과 검토", detail: "Q4 실현 효과 · 보고", topic: "nowview-sc06", package: "nowview.sc06" },
    ],
  },
];

export function findCompany(id: string | undefined): Company | undefined {
  return COMPANIES.find((c) => c.id === id);
}

/** 회사 이름으로 옮겨 Center에 다시 올린 장면인가 — 예전 이름(`nowview-…`)이면 아니다. */
export function migrated(scene: CompanyScene): boolean {
  return !scene.topic.startsWith("nowview-");
}

/** 회사 안의 화면 경로 — 장면 화면은 `/sc01/…`처럼 회사를 빼고 적고, 실제 주소는 `/c/{회사}/sc01/…`다. */
export function companyPath(companyId: string, scenePath: string): string {
  return `/c/${companyId}${scenePath === "/" ? "" : scenePath}`;
}
