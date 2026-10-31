import Link from "next/link";
import { notFound } from "next/navigation";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { companyPath, findCompany, migrated } from "@/lib/companies";

/**
 * 회사 운영 현황 — 그 회사의 BPM 프로세스(업무)와 Center 등록 이름. 업무를 고르면 그 업무의 화면으로 간다. 업무별 진행 숫자는
 * 각 업무 화면이 엔진에서 받는다 — 여기에 같은 숫자를 다시 계산해 두지 않는다(4.3).
 */
export default async function CompanyPage({ params }: PageProps<"/c/[company]">) {
  const { company: id } = await params;
  const company = findCompany(id);
  if (!company) notFound();
  return (
    <main className="mx-auto w-full max-w-7xl space-y-4 px-4 py-6 sm:px-6 lg:px-8">
      <div>
        <h1 className="text-xl font-semibold">{company.name}</h1>
        <p className="text-sm text-muted-foreground">{company.description}</p>
      </div>
      <ol className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {company.scenes.map((s) => (
          <li key={s.no}>
            <Link href={companyPath(company.id, `/sc0${s.no}`)} className="block h-full">
              <Card className="h-full transition-colors hover:border-brand/60">
                <CardHeader>
                  <CardTitle>
                    {s.no}. {s.work}
                  </CardTitle>
                  <CardDescription>{s.detail}</CardDescription>
                </CardHeader>
                <CardContent className="space-y-1 text-xs">
                  <p>
                    <Badge variant={migrated(s) ? "default" : "outline"}>
                      {migrated(s) ? "회사 이름으로 등록" : "예전 이름 — 옮기기 전"}
                    </Badge>
                  </p>
                  <p className="font-mono text-muted-foreground">
                    패키지 {s.package} · 토픽 {s.topic}
                  </p>
                </CardContent>
              </Card>
            </Link>
          </li>
        ))}
      </ol>
    </main>
  );
}
