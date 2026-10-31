import { CompanyOverview } from "@/components/companies/company-list";

/** 회사 운영 현황 — 그 회사가 쓰는 업무. 회사는 설정이라 클라이언트가 엔진의 공개 목록에서 확인한다(Q6). */
export default async function CompanyPage({ params }: PageProps<"/c/[company]">) {
  const { company } = await params;
  return (
    <main className="mx-auto w-full max-w-7xl space-y-4 px-4 py-6 sm:px-6 lg:px-8">
      <CompanyOverview companyId={company} />
    </main>
  );
}
