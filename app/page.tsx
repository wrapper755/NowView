import { BrandHero } from "@/components/shared/brand-hero";
import { TopBar } from "@/components/shared/top-bar";
import { CompanyList } from "@/components/companies/company-list";

/**
 * 회사 목록 — NowView가 운영 현황을 보여 주는 회사들. 회사는 설정(엔진 DB, 관리자 모드)이고 화면은 공개 목록만 받는다 —
 * BPM 프로세스·토픽·일꾼 상태는 공개하지 않는다(`docs/worker-interfaces.md` §1).
 */
export default function CompaniesPage() {
  return (
    <>
      <TopBar />
      <BrandHero />
      <main className="mx-auto w-full max-w-5xl space-y-5 px-4 py-6 sm:px-6">
        <h2 className="text-xl font-semibold">회사</h2>
        <CompanyList />
      </main>
    </>
  );
}
