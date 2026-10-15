# AX-20261015-01 — 프로젝트 가이드 스킬 정리 검토 검증 (Claude)

작업: 사용자 요청으로 `enclu-scm-project-guide` SKILL.md에서 Supabase 시절 서술 제거, 현행 구성(로컬 PostgreSQL 16 단일 DB,
로컬 웹앱, 백업, PG 17·18 의도적 설치)·UPH 데이터 흐름·진단법을 코드 기준으로 재작성. Codex용 사본(`.agents/...`) 동기화,
CLAUDE.md·HANDOFF 관련 문구 정리. 지시서: 사용자 요청 + 감사 F4.

작성 전 코드로 확인한 것: `watchdog_agent.py`(헤더·`process_file`·upsert의 `detected_at` 갱신),
`app.py:637-700`(`uph_get_order_counts`의 norm_key·배송>송장 우선 정렬·invoice_shipped), `uph_download_macro.py`(오프셋 상수),
`hub/secrets.py`(DPAPI·환경변수 이름), 환경변수 이름 목록.

## Codex 검토(`review.md`) 판정
| # | 지적 | 판정 | 근거 | 조치 |
|---|---|---|---|---|
| 1 | 재확인을 "발주일" 기준으로 잘못 기재 | **타당** | `uph_download_macro.py:140-146` 날짜 유형(송장입력일 `trans_date`/배송일 `trans_date_pos`), `:836-841` 재확인도 두 기준 각각 추가 | "송장입력일·배송일 각각 -21~-1일"로 수정, 2026-09-16 배송일 레그 누락 사고 함께 기재 |
| 2 | watchdog이 "최신 파일만" 처리한다고 기재 | **타당** | `watchdog_agent.py:702-703` 미처리 파일 전부 수정시각순, `:745-750` 주석(2026-08-31 파일 2개로 바뀌며 최신만 처리 전제 깨짐), `:759` 순회 | "미처리 파일 전부를 오래된 순서로"로 수정, 회귀 경고 추가 |

수정 반복 1회. 두 사본 일치 확인(`diff -q`). 비밀정보·IP 없음 확인.

## 미검증
- 운영 DB·WMS 실측 대조 없음 (문서 작업)
- 기타 문서의 Supabase 언급(`docs/새_PC_설치_가이드.md`, `UPH 시스템/README.txt`, `watchdog_agent.py` 헤더 주석 등)은 이번 범위 밖
