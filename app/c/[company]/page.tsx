import { CompanyDashboard } from "@/components/companies/company-list";
import { TopBar } from "@/components/shared/top-bar";

/**
 * 회사 대시보드 — 그 회사 업무의 BPM 진행·일꾼 일감·핵심 지표. 회사는 설정(엔진 DB)이라 빌드 때 모른다 — 서버에서 엔진을
 * 묻지 않고(엔진이 꺼져도 화면 틀은 뜬다, 4.3) 클라이언트가 읽는다. 업무 화면은 회사 사이트에 있다(`docs/role-split.md`).
 */
export default async function CompanyPage({ params, searchParams }: PageProps<"/c/[company]">) {
  const { company } = await params;
  // 사건 화면(회사 사이트)에서 돌아올 때 같은 회차를 연다(`?world=`)
  const { world } = await searchParams;
  return (
    <>
      <TopBar companyId={company} />
      <main className="mx-auto w-full max-w-7xl space-y-4 px-4 py-6 sm:px-6 lg:px-8">
        <CompanyDashboard companyId={company} initialWorld={typeof world === "string" ? world : null} />
      </main>
    </>
  );
}
