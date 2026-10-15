감사 F2 수정 (reports/AX-20261014-04/audit.md F2 참고).
대상: _local_db/verify_migration.py (F1에서 compare()/main()으로 분리됨, 테스트 _local_db/tests/test_verify_migration.py 5개).
문제: 원본(Supabase) public 테이블 목록 기준으로 행수만 비교 — 대상(로컬)에만 있는 테이블은 보고되지 않고, 행수가 같아도 컬럼 구성 차이·내용 차이는 못 잡음.
용도: Supabase·Cloud 앱 해지(되돌릴 수 없음) 전 최종 검증. 단, 현재 운영 DB는 로컬이며 Supabase는 읽기 전용 동결 상태라 로컬이 Supabase보다 행이 많은 것이 정상인 테이블(order_status_log 등 전환 후 계속 쌓이는 테이블)도 있다.
제약:
1. Supabase는 저사양(t4g.nano, 과거 대용량 쿼리로 다운된 사고 있음) — 원본에 전체 테이블 해시·대량 스캔 같은 무거운 쿼리 금지. information_schema 조회, COUNT(*), 인덱스 있는 컬럼의 MIN/MAX 정도로 제한.
2. 기존 출력·종료코드 의미(전체 일치 0 / 불일치·조회 실패 1)와 테스트 유지, 확장 시 테스트 추가.
3. 전환 이후 로컬에서 계속 늘어나는 테이블을 "불일치"로 처리할지 "정보"로 처리할지 판단 근거와 함께 제안 (예: 로컬 >= 원본이고 원본 범위의 행이 모두 있는지 PK MIN/MAX로 확인).
요구: 대상 전용 테이블 보고, 컬럼 구성(이름·타입) 비교, 행수 비교 규칙 개선. 실제 DB 접속 없이 테스트(SQLite 또는 모의).
