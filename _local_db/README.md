# 로컬 PostgreSQL

- 호스트: localhost / 포트: 5432 / DB명: enclu_scm / 계정: enclu_app
- 연결 문자열 형태: postgresql://enclu_app:<.env 참조>@localhost:5432/enclu_scm
- 각 프로그램 .env의 DATABASE_URL_LOCAL 키에 실제 값 저장 (Task 6에서 전환 시 사용)
- 설치 버전: PostgreSQL 16.15 (Windows x86-64)
- 설치 경로: C:\Program Files\PostgreSQL\16
