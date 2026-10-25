# Chaeksas 작업 요청서 — NowView SC01을 Center·Studio에서 돌릴 때 필요한 것

- 보내는 쪽: NowView ([chaeksas-integration.md](../chaeksas-integration.md))
- 받는 쪽: Chaeksas (계약·엔진·Center·Studio)
- 작성: 2026-10-25 · 상태: **보내기 전**

이 문서는 Chaeksas 저장소에서 바로 일을 시작할 수 있게 쓴 요청서다. 결정은 Chaeksas가 한다.
`> 제안:`은 NowView의 권고이고, `> 미정:`은 Chaeksas가 정할 것이다. NowView는 Chaeksas를 두 가지 방식으로만 만난다.
하나는 **외부 확장**(`http-adapter`, `nowview-sc01`)이고, 다른 하나는 Center `/api/v1`이다(연동용 키·대리 답용 키).

## 1. 원하는 것

* NowView SC01 BPMN(`nowview.sc01`)을 Studio 시험 실행과 Center 서버 Bot에서 끝까지(인계까지) 돌린다.
  그동안 NowView 화면 전체가 그 실행을 따라간다.
* 사람 결재는 Center 결재함에 있다. 감독자와 현업은 콘솔(CON-04)과 NowView 화면 어디서든 답한다.
  NowView는 대리 답용 키로 답한다(ADR-0081).
* 고객계획 접수는 **가상 직원**이 맡는다(ADR-0079·0085). 접수 Bot이 원천을 검증하고, 감독자의 일괄 결재를 받은 건만
  SC01로 위임한다.
* 사람 결정의 업무 효과는 **결재 뒤의 서비스 태스크**가 NowView에 적는다. 답을 어디서 했든 같은 길이다.
  지금은 NowView 내장 실행기의 훅에만 있어서, Studio 실행에서 `compare`·`hand_off`가 409로 막혔다(실측).

## 2. 이미 있어서 그대로 쓰는 것

확인한 코드와 문서는 `main` `c127c6f` 기준이다.

| 필요 | Chaeksas에 있는 것 |
|---|---|
| SC01 기동 | `POST /jobs` (연동용 키, `inputs`) |
| 정정본(EX03) 전달 | `POST /messages` (상관 키로 기다리는 실행에) |
| 진행 읽기 | `GET /runs/{id}/events` (Center API 키는 `require_read`를 통과한다) |
| 역할별 결재함·대리 답 | `chk:approval.assignees` · `GET /approvals?assignee=` · 대리 답용 키 + `X-CHK-On-Behalf-Of` |
| 데모 실행 ↔ 실행 잇기 | 어댑터 템플릿 `{{run_id}}` |
| 가상 직원·일괄 기동 | `virtual_workers` 자원, B16, Call Activity 반복 + 위임(ADR-0082·0087) |

## 3. 요청

### R1. 결재에 답한 사람을 실행 변수로 — **필수**

**왜**: 결재 뒤 서비스 태스크가 NowView에 「누가 확인했나」를 적어야 한다. 원천 `verified_by`, 업무 완료자, 감사 이력이 그 값이다.
지금 `answer_variables`는 폼 칸만 변수로 만든다. `answered_by`는 C3 `human_answered`와 C6에만 있고, 그림에서는 읽을 수 없다.
폼에 「확인자」 칸을 두면 대신할 수는 있지만, 자칭한 이름이 두 개가 된다(Center가 담당자와 대조한 이름 하나, 폼에 적힌 이름 하나).

> 제안: `chk:approval`에 `answered_by_into: "<변수 이름>"`(선택)을 둔다. 엔진이 답을 넣을 때 `answered_by`를 그 변수에 적는다.
> `answered_via`도 같은 결로 적을 수 있으면 좋다. Studio 시험 실행에서는 케이스의 `approvals` 항목에 적은 이름을 쓰거나 Studio 사용자를 쓴다.

> 미정: 칸 이름, 그리고 확인(`manualTask`)에도 적을지.

### R2. 결재 답을 받기 전에 서비스 앱으로 검사 — 선택

**왜**: NowView 업무 규칙 중에는 폼으로 걸 수 없는 것이 있다. 예를 들어 「검증 오류가 남은 원천은 확인완료할 수 없다」,
「배정한 사람이 그 역할인가」 같은 것이다. 지금은 결재 뒤 기록 작업이 422를 내면 오류 경계로 받아 같은 결재로 되돌아가게 그린다.
그런데 이렇게 하면 그림이 결재마다 고리가 하나씩 늘고, 결재 기록에는 「닫힘」이 먼저 남는다.

> 제안: `chk:approval.check: {app_id, operation, input}`. 실행하는 쪽이 답을 엔진에 넣기 전에 그 작업을 부르고,
> 거절이면 결재를 열어 둔 채 답한 쪽에 사유를 돌려준다.

> 미정: 답은 Center → 하트비트 → 실행기로 내려가므로, 「답한 쪽에 사유를 돌려준다」를 어디서 할지. 어렵다면 **안 해도 된다.**
> NowView는 위의 되돌림 고리로 간다.

### R3. 실행·결재 변화를 바깥에 알리기 — 선택

**왜**: NowView 화면은 SSE로 즉시 바뀐다(CLAUDE.md 4.9). 바깥 실행을 따라가려면 지금은 Center의 `runs/{id}/events`와
`approvals`를 폴링해야 한다(2초 예정).

> 제안: 연동용 키로 거는 구독 하나. 예를 들면 `GET /runs/{id}/events?follow=1`(SSE)이나, 서명된 웹훅
> (`approval_created`·`approval_answered`·`run_state`) 같은 것이다.

> 미정: 어느 쪽이든 된다. 없으면 NowView는 폴링한다.

### R4. 외부 확장의 주소를 환경마다 — **필요**

**왜**: 외부 확장의 주소는 정의의 `base_url` 하나뿐이고, Center에서 바꿀 수 없다(CLAUDE.md 4.3에 적어 둔 것).
그래서 NowView는 같은 id(`nowview-sc01`)로 정의를 두 벌 두었다. 운영계 `0.1.0`과 로컬 `0.1.1-local`이고,
한 Center에는 하나만 올린다. 개발자 PC의 Studio에서 운영계를 부르거나, 그 반대가 되기 쉽다.
그런데 `contracts.extension.Service`의 설명은 「Center 리소스 등록(C7)의 `base_url`이 있으면 그것을」이라고 적고 있다.
**문서와 실제 동작 중 어느 쪽이 맞는지부터** 알려 달라.

> 제안: 서비스 앱처럼 Center 리소스 등록에서 `base_url`을 덮어쓸 수 있게 한다. 이때 `allowed_hosts`는 그 주소의 호스트로 함께 좁힌다.
> Studio도 시험 실행에 한해 로컬 덮어쓰기를 둔다.

### R5. 실행 위치를 어댑터 템플릿으로 — 작음

**왜**: NowView는 Studio 시험 실행에서는 화면을 읽기 전용으로 둔다(답은 Studio가 한다). 서버 실행에서는 대리 답을 연다.
그러려면 첫 작업 호출에서 실행 위치를 알아야 한다. 지금 템플릿 변수는 `run_id`·`node_id`·`idempotency_key`·`input.*`뿐이다.

> 제안: `{{run_location}}`(`server` | `pc` | `studio`) 또는 `{{executor}}`.

### R6. 외부 확장에 `auth`를 두면 받는 쪽은 키를 어떻게 아나 — 질문

NowView 시스템 작업 네 개는 지금 인증 없이 열려 있다. 운영계는 인터넷에 있다. 게다가 ADR-0091 이후로는
NowView 정의 두 벌이 **E3로 거절된다**(`requires_keys: run` + `auth` 없음, `main`에서 확인). NowView는 `auth: {type: bearer}`를
두려고 한다. 이때 실행하는 쪽(Studio·서버 실행기)은 Center가 발급한 키를 받는다(ADR-0092·0094).
**받는 쪽(NowView)은 그 키가 맞는지 무엇으로 확인하나?** 발급할 때 값을 NowView에 넣어 두는 것인지(NowView 운영자가
`/etc/nowview.env`에 넣는다), Center에 검증 API가 있는지 알려 달라.

### R7. 가상 직원의 감독자를 결재 담당자로 — 선택

ADR-0080의 「다시 볼 조건 ③」이 이 요청이다. 접수 Bot의 일괄 결재 담당자는 가상 직원의 `supervisors`와 같아야 한다.
지금은 그림에 이름을 다시 적는다(`["이도윤"]`). 가상 직원 자원을 바꾸면 그림과 어긋난다.

> 제안: 접수 Bot 실행에 감독자 목록을 변수로 실어 준다. 그러면 `assignees: "감독자"`로 쓸 수 있다.

## 4. NowView가 하는 것 (Chaeksas 일이 아님)

* 결재 뒤 기록 작업(`record_dq_review`·`record_sales_review`·`record_assignment`·`record_acceptance`)과 BPMN의 오류 경계 고리
* `assignees`를 사람 이름으로 정하고, `Confirm_Calc`를 확인 대신 결재로 바꾸기
* 연동용 키·대리 답용 키 클라이언트, 폴링 → SSE, 업무 화면의 대리 답
* 접수 Bot 그림(`nowview.sc01-intake`), 가상 직원 등록, 고객계획 화면의 가상 직원 카드
* 시스템 작업 인증(R6의 답에 따라)

## 5. 시험해 볼 장면 (Chaeksas 쪽 확인에 쓸 수 있게)

1. Center 서버 Bot `nowview.sc01`, 입력 `{데모실행ID, 원천ID}` → `Approve_DQ` 결재(담당자 이도윤) → 콘솔에서 확인완료 →
   기록 작업이 `answered_by = 이도윤`을 받는다(R1) → `compare` 200.
2. 같은 결재에 대리 답용 키로 `X-CHK-On-Behalf-Of: 박서진`(담당 아님)을 보내면 403 `not_assignee`다(이미 된다).
3. 접수 Bot: 메시지 하나로 원천 두 건 → 일괄 결재 승인 → SC01 자식 실행 두 개(`parent_run_id`).
   반려하면 자식은 0이다.
