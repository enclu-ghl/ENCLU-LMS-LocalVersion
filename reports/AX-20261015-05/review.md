검토: Claude 대체 검토 (Codex 미검토) — devops-review 에이전트 (구현 대화와 분리된 컨텍스트)

대상: `_local_db/verify_migration.py`, `_local_db/tests/test_verify_migration.py` 미커밋 변경 (`git diff HEAD -- _local_db/`)
기준: AGENTS.md, reports/AX-20261015-05/plan.md, reports/AX-20261014-04/audit.md F1/F2

## 결론
지시서 완료 조건 구현, 테스트 12개 통과(기존 5 + 신규 7), 원본 쿼리 제한 준수. 다만 거짓 OK 경로 2개가 남아 해지 판단 전 지적 1·3 보강 권장.

## 실행한 것
- `py -B -m unittest discover -s _local_db/tests -v` → 12개 OK
- 임시 폴더에서 `_Dbs`로 SQLite 모의 데모, 원본 엔진 `before_cursor_execute`로 실행 SQL 기록. 실제 DB 접속·저장소 수정 없음.

## 지적
1. **[높음] `verify_migration.py:79-81` — 행수가 같으면 id 범위 확인을 안 해 실제 누락이 OK로 나옴**
   - 범위 확인은 `n_dst > n_src`일 때만 실행. 원본 k건 누락 + 로컬 신규 k건이면 행수가 같아져 OK. 계속 쌓이는 로그 테이블에서는 시간이 지나며 반드시 거치는 구간.
   - 재현(모의): 원본 id [0,1,2], 대상 [0,2,10] → True, `log 3 3 OK`.
   - 제안: 정수 id가 있으면 `n_dst >= n_src`에서 항상 범위 확인 + 테스트.
2. **[중간] `:46-53` — 범위 근사의 한계(로컬 신규 id가 원본 범위의 빈 번호에 들어가면 누락이 가려짐)가 출력에 안 보임**
   - 재현(모의): 원본 [0,5,10], 대상 [0,1,2,10] → id 5 누락인데 True·"증가". 문구 "원본 id 범위 행은 모두 있음"이 과도하게 단정적.
   - 제안: 문구를 "근사"로 낮추고 docstring 한계에 추가, 해지 전 체크리스트에 "로컬 시퀀스 ≥ 원본 MAX(id)" 확인 검토.
3. **[중간] 테스트 — 조회 실패 경로와 원본 쿼리 제한을 지키는 테스트 없음**
   - `except` 분기와 종료코드 1 경로 미검증(audit F1의 "조회 실패" 케이스). 원본에 무거운 쿼리를 넣어도 테스트가 통과.
   - 제안: 예외 주입 테스트, 원본 `before_cursor_execute` 기록으로 허용 패턴(pg_tables / information_schema.columns / COUNT(*) / MIN(id),MAX(id))만인지 확인.
4. **[낮음] `:71`, `:48` — 원본 쿼리에 statement_timeout 없음, MIN/MAX 인덱스 사용 보장 없음** — 쿼리 상한 설정, id PK 여부 수동 확인 절차 문서화 제안.
5. **[낮음] `:37-43` — 컬럼 비교는 data_type만**(길이·정밀도·NOT NULL·enum 이름 미비교), `information_schema.columns`는 권한 있는 컬럼만 보여 권한 문제 시 "컬럼 구성 다름"으로 오해 가능 — 문서에 한계로 남기면 충분.
6. **[낮음] `:92` — 조회 실패 메시지가 원본/로컬 구분 없음** (기존은 구분) — 단계 이름 표시 제안.
7. **[낮음] 범위 밖** — public 스키마만, 시퀀스·뷰·함수·트리거·RLS 미비교 → "전체 일치"여도 별도 확인 필요하다고 출력·문서에 안내 제안.

## 맞게 된 것
원본 전용 테이블 실패 / 대상 전용 정보 / 컬럼 다르면 실패 / 대상<원본 실패 / id 없는 증가 기본 정보·strict 실패 / 원본 빈 테이블 증가는 정보 / 종료코드 / 테이블명 인용·바인드 파라미터.

## 미검증
실제 PostgreSQL(Supabase·로컬) 실행, id 인덱스·PK 여부, 로컬 시퀀스 값과 원본 MAX(id) 관계, 운영 증가 테이블 목록과 id 타입.
