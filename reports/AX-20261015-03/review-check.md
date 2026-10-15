# AX-20261015-03 — exe SQLAlchemy 고정 검토 검증 (Claude)

지시서: 별도 `plan.md` 없음 — HANDOFF "위험" 항목(2026-10-15 Claude 발견)을 지시서로 사용.

## 변경
- 루트 `requirements.txt`: `sqlalchemy` → `sqlalchemy<2.1` (+ 이유 주석). 웹앱 저장소는 이미 고정.
- `hub/selftest.py` `pg_driver`: `URL.create("postgresql").get_dialect().driver`가 `psycopg2`가 아니면 실패.
  기존 점검은 psycopg2 import만 해서 2.1 번들을 못 잡았음. CI는 빌드한 exe로 `--selftest --ci`를 돌리고 실패 시
  빌드를 멈추므로(`.github/workflows/build.yml:111-117`), 앞으로 2.1이 번들되면 릴리스 전에 차단된다.
  커넥션 문자열 모양 문자열을 쓰지 않아 CI 비밀 유출 검사와 충돌 없음.

## 실행한 검증 (Claude)
| 환경 | 결과 |
|---|---|
| 현재 개발 Python (SQLAlchemy 2.0.51) | 기본 드라이버 psycopg2 → 점검 통과 |
| 임시 venv SQLAlchemy 2.1.4 + psycopg2-binary | 기본 드라이버 psycopg → 점검 실패(의도대로 잡음). 같은 환경에서 `create_engine("postgresql://…")`는 `No module named 'psycopg'` |
| `pip install --dry-run "sqlalchemy<2.1"` | SQLAlchemy 2.0.54 선택 |

## Codex 검토(`review.md`) 판정
| # | 내용 | 판정 |
|---|---|---|
| 1 | 결함 없음, 파일찢기·UPH가 URL을 그대로 `create_engine`에 전달 | 타당 (소스 확인과 일치) |
| 2 | 2.1 실패 분기 미검증 | Claude가 위 임시 venv로 검증함 |
| 3 | 릴리스하려면 `version.txt` 상향 필요 — 같은 태그면 릴리스 생략(`build.yml:137`) | 타당 — 릴리스 단계에서 처리(사용자 확인) |

## 미검증 / 남은 것
- v1.3.19 exe에 실제로 2.1이 들어갔는지 (CI 로그 미확인)
- PyInstaller exe 실제 빌드·자가진단, 직원 PC 접속 — `version.txt` 상향 + main 푸시(사용자 확인) 후 CI에서 확인
