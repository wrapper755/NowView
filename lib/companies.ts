"use client";

import { useEffect, useState } from "react";

/**
 * 회사와 업무(화면 쪽).
 *
 * NowView는 회사 사이트가 아니다 — Center에 올린 회사별 BPM 프로세스의 일감을 수행하는 **일꾼**이고, 그 위에서 회사별 운영
 * 현황을 보여 주는 **대시보드**다(`docs/worker-interfaces.md` §1). NowView는 고정 프로그램이라 **업무(장면)는 코드**이고
 * (`SCENES` — 엔진 `app/companies.py`의 `SCENE_WORKS`와 시험이 대조), **회사는 설정**이다(엔진 DB, 관리자 모드에서 고친다).
 * 화면은 공개 목록(`GET /api/engine/companies` — 이름·설명·업무 번호)만 받는다. BPM 프로세스 id·토픽·회사 시스템 주소는
 * 관리자 모드(`/admin`)에만 있다.
 */

/** 업무 번호 — 시나리오 1은 1~7, 시나리오 2 장면 N은 20 + N, 시나리오 3 장면 N은 30 + N(`docs/platform.md` §7). */
export type SceneNo = 1 | 2 | 3 | 4 | 5 | 6 | 7 | 21 | 22 | 23 | 24 | 31 | 32 | 33;

export const SCENES: Array<{ no: SceneNo; work: string; detail: string }> = [
  { no: 1, work: "고객 생산계획 변경 대응", detail: "위험 감지 · 현업 통제 · 인계" },
  { no: 2, work: "외주 단가 인상 검토", detail: "협상 · 순차 승인 · 원가 등록" },
  { no: 3, work: "수익성 통합 분석", detail: "부서 확인 · 수시회의 · 분석과제" },
  { no: 4, work: "개선안 검토·실행 승인", detail: "월간회의 · 대표 승인 · 책임 인수" },
  { no: 5, work: "결정 실행·계획 갱신", detail: "실행계획 · 착수 · 공식 전망" },
  { no: 6, work: "완료·성과 검토", detail: "Q4 실현 효과 · 보고" },
  { no: 7, work: "관리모델 개선·적용", detail: "Agent 개선 · 검증 · 운영 설정 반영" },
  { no: 21, work: "납기 위험 조기 감지", detail: "시나리오 2 · 공급 경보 · 영향 약정 · 사건 분석" },
  { no: 22, work: "정형통제 실행과 주문별 분기", detail: "시나리오 2 · 수행계획 · 생산계획 확인 · 주문별 재평가" },
  { no: 23, work: "잔여 납기 위험의 경영검토와 대응 합의", detail: "시나리오 2 · 기존 운송 문의 참조 · 팀장 재보고 · 임원 결정 · 과제 인수" },
  { no: 24, work: "실행 결과 확인과 관리기준 개선", detail: "시나리오 2 · 결정·실적 대조 · 당시 자료 재현 · 시험 · 다음 사건 적용" },
  { no: 31, work: "결산조정 업무 착수", detail: "시나리오 3 · 결산 체크리스트 · 입력자료 점검 · 분석 준비" },
  { no: 32, work: "결산조정 계산 및 담당자 검토", detail: "시나리오 3 · 분석 실행 · 계산근거 Excel 첨부 · 항목 검토 · 한 건 상신" },
  { no: 33, work: "팀장 보고 및 승인", detail: "시나리오 3 · 승인 요약 · 근거 조회 · 승인/보완 요청 · 전표 반영·주석 취합 인계" },
];

/** 공개 목록의 회사 하나 — `scenes`는 그 회사의 BPM 프로세스가 매핑된 업무 번호다. */
export type PublicCompany = {
  id: string;
  name: string;
  description: string;
  scenes: SceneNo[];
  /** 회사 사이트(공개 웹) 주소 — 없으면 회사 문서로 링크하지 않는다. */
  siteUrl?: string | null;
};

type CompaniesState = { companies: PublicCompany[] | null; error: string | null };

let cache: Promise<PublicCompany[]> | null = null;

function fetchCompanies(): Promise<PublicCompany[]> {
  // 한 화면에서 여러 조각이 묻는다(공통 줄·본문) — 요청 하나를 나눠 쓴다. 실패하면 다음에 다시 묻는다.
  cache ??= fetch("/api/engine/companies", { cache: "no-store" }).then(async (response) => {
    if (!response.ok) throw new Error(`엔진이 ${response.status}를 돌려줬다`);
    return (await response.json()) as PublicCompany[];
  });
  cache.catch(() => {
    cache = null;
  });
  return cache;
}

/** 공개 회사 목록 — 회사는 설정이라 빌드 때 모른다(정적 페이지가 클라이언트에서 받는다). */
export function useCompanies(): CompaniesState {
  const [state, setState] = useState<CompaniesState>({ companies: null, error: null });
  useEffect(() => {
    let alive = true;
    fetchCompanies().then(
      (companies) => alive && setState({ companies, error: null }),
      (cause: unknown) => alive && setState({ companies: null, error: `엔진에 연결할 수 없다 — ${String(cause)}` }),
    );
    return () => {
      alive = false;
    };
  }, []);
  return state;
}
