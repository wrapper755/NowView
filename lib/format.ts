/** 표시 포맷 유틸. 모든 금액 입력은 **억원** 단위다. */

/** 1조 = 10,000억. */
const EOK_PER_JO = 10_000;

/**
 * 억원 금액을 한국 경영보고 관례로 표기한다.
 * 10,000억 이상은 조 단위로 끊는다: 10200 → "1조 200억", 9940 → "9,940억".
 */
export function formatEok(eok: number): string {
  const sign = eok < 0 ? "-" : "";
  const abs = Math.abs(eok);

  if (abs >= EOK_PER_JO) {
    const jo = Math.floor(abs / EOK_PER_JO);
    const rest = Math.round(abs % EOK_PER_JO);
    return rest === 0
      ? `${sign}${jo}조`
      : `${sign}${jo}조 ${rest.toLocaleString("ko-KR")}억`;
  }
  return `${sign}${Math.round(abs).toLocaleString("ko-KR")}억`;
}

/** 부호를 항상 붙인다. Gap·증감 표기용. 0은 부호 없이 "0억". */
export function formatEokSigned(eok: number): string {
  const rounded = Math.round(eok);
  if (rounded === 0) return "0억";
  return `${rounded > 0 ? "+" : ""}${formatEok(rounded)}`;
}

/** 소수 1자리 퍼센트. */
export function formatPercent(value: number, digits = 1): string {
  return `${value.toFixed(digits)}%`;
}

/** 퍼센트포인트 증감. 부호를 항상 붙인다. */
export function formatPpSigned(value: number, digits = 1): string {
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(digits)}%p`;
}

/** 축 눈금용 — 천 단위 구분만. */
export function formatAxisEok(eok: number): string {
  return Math.round(eok).toLocaleString("ko-KR");
}
