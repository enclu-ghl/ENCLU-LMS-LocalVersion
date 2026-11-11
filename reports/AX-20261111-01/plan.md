# AX-20261111-01 재고할당 동 판정을 고정 목록에서 "로케이션 첫 영문자"로 (긴급, Claude 작성)

> 사용자 요청(2026-11-11): 물류 개편으로 A동도 적치 구역이 되어 A동에서 자사 물건을 빼야 한다.
> "A~F동에 구애받지 않고 맨 앞 글자로 동을 나누고, 이동시킬 피킹존만 잘 작성하면 된다."
> 긴급 요청이라 Codex 지시서 없이 Claude가 바로 구현했다 — 이 문서는 검토용 요약이다.

## 원래 동작
- `alloc_dong_of()`: 로케이션 첫 글자가 `alloc_dong_code` 활성 행(C동·D동·F동)에 있을 때만 그 동, 아니면 `기타`.
- 그래서 A로 시작하는 적치 로케이션은 `기타`로 빠진다.

## 변경 (웹 저장소 `app.py`)
1. `alloc_dong_of()`: 첫 글자가 A~Z면 무조건 `{글자}동`, 비었거나 영문자가 아니면 `기타`.
2. `alloc_dong_sort_key()`: 표시 순서 가나다순, `기타` 맨 뒤.
3. `alloc_ensure_dong_codes(conn, dongs)`: 업로드 시 처음 보는 동을 `alloc_dong_code`에 `ON CONFLICT (code) DO NOTHING`으로 등록
   (alloc_row·alloc_dong_status → alloc_dong_code FK 통과용). sort_order = (글자 순번)×10. 기존 행(비활성 `기타` 포함)은 그대로.
   업로드 트랜잭션에서 alloc_dong_status INSERT 직전에 호출.
4. 업로드 미리보기: 고정 C/D/F 칸 → 파일에 실제 있는 동만 표시. 경고 문구에서 "C/D/F" 제거.
5. `ALLOC_DONG_LIST`(표 읽기, 위 두 곳에서만 사용) 삭제.

## 확인한 것
- ② 동별 수량 작성·③ 확정 화면은 원래부터 세션의 alloc_row/alloc_dong_status에 있는 동을 그대로 씀 → 변경 불필요.
- 운영 DB: alloc_dong_code PK(code), enclu_app INSERT 권한 있음, color CHECK는 NULL 허용.
- 피킹존 마스터에 A로 시작하는 피킹존이 487개 → 사용자가 피킹존 파일을 개편에 맞게 다시 올려야 함(코드 범위 밖).

## 검토 요청 포인트
- FK·동시 업로드(두 사람이 같은 새 동을 동시에 등록) 시 문제 여부
- 영문자 아닌 첫 글자·소문자·공백 처리
- 다른 곳에서 C/D/F 고정 가정이 남아 있는지
