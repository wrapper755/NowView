"use client";

import { UserRound } from "lucide-react";

import { useSc01 } from "@/lib/store/sc01";

/**
 * 시연용 역할 전환 — 설계서 2.3 "데모 역할 전환: 시연 환경에서만 제공, 전환한 역할과
 * 수행자를 기록". 고른 사용자가 `X-Demo-Actor`로 엔진에 가고 감사 이력에 남는다.
 *
 * **이것은 인증이 아니다.** 엔진은 "그 사용자가 그 업무의 역할·담당인가"만 검사한다(4.5).
 *
 * 좁은 화면에서는 폭을 묶는다 — 이름까지 다 보이게 두면 GNB의 화면 메뉴가 0px로 눌렸다(375px 실측).
 */
export function ActorSwitcher() {
  const actor = useSc01((s) => s.actor);
  const users = useSc01((s) => s.users);
  const setActor = useSc01((s) => s.setActor);

  return (
    <label className="inline-flex shrink-0 items-center gap-1 text-xs" title="시연 역할 전환">
      <UserRound aria-hidden className="hidden size-3.5 text-muted-foreground sm:block" />
      <span className="sr-only">시연 역할</span>
      {/* 좁을 때 5rem — 장면 칩 5를 더하자 화면 메뉴(최소 2.5rem)가 nav 밖으로 8px 넘쳤다(375px 실측). 역할 선택을
          8px 줄여 nav에 돌려줬다. 선택 상자라 이름이 잘려도 펼치면 전부 보인다. */}
      <select
        value={actor}
        onChange={(e) => setActor(e.target.value)}
        className="max-w-[5rem] rounded-md border bg-transparent px-1 py-1 text-xs sm:max-w-none sm:px-1.5"
      >
        {users.length === 0 ? <option value={actor}>{actor}</option> : null}
        {users
          .filter((u) => u.role !== "시연관리자")
          .map((u) => (
            <option key={u.userId} value={u.userId}>
              {u.role} · {u.name}
            </option>
          ))}
      </select>
    </label>
  );
}
