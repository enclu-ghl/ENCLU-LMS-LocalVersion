# AX-20261014-05 — F1 수정 검토 검증 (Claude)

작업: 감사 F1 (`_local_db/verify_migration.py` 불일치·조회 실패에도 종료코드 0) 수정.
지시서: 별도 `plan.md` 없음 — `reports/AX-20261014-04/audit.md` F1 항목(Codex 모의 재현 포함)을 지시서로 사용.

## 변경
- `verify_migration.py`: 모듈 최상위 실행을 `compare(src, dst) -> bool`과 `main()`으로 분리, `main()`이 `sys.exit(0 if 일치 else 1)`.
  stdout UTF-8 재설정·환경변수 읽기는 `main()` 안으로 이동(import만으로는 실행·DB 접속 안 함). 비교·출력 로직은 그대로.
- 신규 `_local_db/tests/test_verify_migration.py`: SQLite로 원본/대상 흉내(`pg_tables` 카탈로그 테이블 포함), 실제 DB 미사용.

## 실행한 테스트 (Claude, Windows `py` 3.14.6)
| 대상 | 결과 |
|---|---|
| 수정본 `py -m unittest discover -s _local_db/tests -v` | 5개 통과 (compare 일치/행수 불일치/대상 테이블 누락, main 종료코드 0/1) |
| 옛 동작 재현(마지막 줄을 `compare()`만 호출로 임시 변경) | `main` 종료코드 테스트 2개 실패 → 테스트가 F1을 실제로 잡음 확인 후 원복 |

## Codex 검토(`review.md`) 판정
| # | 내용 | 판정 | 근거 |
|---|---|---|---|
| 1 | `compare()`가 불일치·조회 실패 시 False | 타당 | `verify_migration.py` 조회 실패 2곳·행수 불일치에서 `all_ok=False`, 반환 |
| 2 | 종료코드 0/1 연결 | 타당 | 위 테스트 결과와 일치 |
| 3 | 비밀정보·운영 DB 쓰기 없음 | 타당 | 변경분은 SELECT만, 테스트는 임시 SQLite |
| 4 | 종료코드 0은 "행수 일치"만 의미 (내용 차이·상쇄 미검출) | 타당 — 기존 F2 | 이번 범위 밖. 감사 F2로 이미 등록됨 |
| 5 | 실제 PostgreSQL 연결·권한·접속 실패 미검증 | 타당 | Claude도 실제 DB로는 실행 안 함(Supabase 읽기 전용 동결, 불필요한 원격 접속 회피) |

수정 반복 0회.

## 미검증
- 실제 Supabase↔로컬 DB 대상 실행 (Supabase 해지 전 최종 검증 때 실행 예정)
- CI(Python 3.12)에서의 테스트 실행 — CI 워크플로에 테스트 단계 없음
