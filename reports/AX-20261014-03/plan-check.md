# AX-20261014-03 지시서 검증 (Claude)

대상: `reports/AX-20261014-03/plan.md` — AX 문서(AX_RULES·HANDOFF·DECISIONS)에 설치·연결 시험·합성 샘플·Hermes 전체 흐름 상태를 구분해 기록

## 증거 출처 구분

| 항목 | 내용 | 출처 | 이번 Claude 세션 재실행 |
|---|---|---|---|
| WSL | WSL2, Ubuntu 26.04.1 LTS | Codex 오케스트레이터 독립 확인(사용자 요청에 명시) | 안 함 (이 세션에 셸 도구 없음) |
| Hermes | `v0.22.0+102.g5f6d683` (WSL Ubuntu) | 위와 같음 | 안 함 |
| 연결 시험 | Hermes → Claude → Codex 표식 세션 `20261014_154228_bd9f0f` 성공 | 위와 같음 | 안 함 |
| 합성 샘플 | 저장소 밖 로컬 샘플 `~/.claude/project/ax-sample-02` — Ubuntu `python3 -B -m unittest -v` → Ran 26 tests, OK, exit 0. CLI 리포트 raw 7 / dedup 6 / 그룹 5 / 완료율 50% | 샘플 폴더의 `plan-check.md`·`implementation.md`·`report.md`를 직접 읽어 대조 (아래) | 테스트 재실행 안 함 |
| Hermes 읽기 전용 검증 | 세션 `20261014_162927_98ac5b` — `report.md` 집계·완료율 공식 일치 확인 | 샘플 `implementation.md` 5절, `plan-check.md` 4절 | — |
| 지시 스크립트 | `ax\codex-plan.ps1 AX-20261014-03` exit 0, `plan.md` 생성 | 사용자 요청 + 이 `plan.md` 존재 | — |
| 지시서 작성자(Codex, 읽기 전용 샌드박스)의 WSL 확인 | `E_ACCESSDENIED` 거부 (`plan.md:14`) | `plan.md` | — |

샘플 문서 대조 결과:
- `implementation.md` 2.1절: `python3 -B -m unittest -v` → `Ran 26 tests in 0.011s`, `OK`, exit 0.
- `implementation.md` 2.2절 / `report.md`: `--start 2026-10-14 --end 2026-10-14 --synthetic` 실행 exit 0, 원본 7건 / 중복 제거 6건 / `(date, shipment_id)` 그룹 5건 / shipped 2 · printed 1 · cancelled 1 · held 1 / 완료율 = shipped/(shipped+printed+held) = 2/4 = 50%. 수치 서로 일치.
- `implementation.md` 1·5절, `plan-check.md` 4절: 구현은 **Codex가 Claude를 통해 직접 진행**, Hermes는 구현을 진행하지 않고 읽기 전용 검증만 수행. → Hermes 전체 흐름(지시→구현→검토 순차 진행)은 **미검증**.
- 범위: 합성 데이터 한정. 운영 데이터·DB 연동 없음.

지시서 작성 Codex의 WSL 확인 거부는 **읽기 전용 샌드박스 제약**이며, 설치 여부에 대한 반증이 아니다. 설치 사실은 별도로 오케스트레이터가 확인한 것으로 구분해 기록한다.

## 판정

| # | 지시서 내용 | 판정 | 근거·조치 |
|---|---|---|---|
| 1 | 완료 조건: WSL·Hermes 버전·26개 테스트를 증거와 연결 (`plan.md:9`) | **수용** | 위 증거 표대로 출처를 붙여 기록 |
| 2 | 연결 시험 ≠ 전체 오케스트레이션, 전체 흐름 미검증 (`plan.md:10`) | **수용** | 샘플 문서의 주체 구분과 일치 |
| 3 | "Claude의 파일별 사전 승인" (`plan.md:11`), "변경안을 파일별로 제시하고 승인된 파일만 수정" (`plan.md:45`) | **수정** | 과잉 요구. 파일별 승인이 필요했던 것은 보호 경로(`~/.claude` 아래 샘플) 쓰기 확인창 때문이었다. 승인된 작업 범위 안의 일반 프로젝트 파일 수정은 파일마다 새 승인을 받지 않는다. 단, 보호 경로·전역 설정·작업 범위 밖 파일은 별도 승인. `AX_RULES` 6장에 이 구분을 반영 |
| 4 | `AX_RULES:60` "로컬 파일 수정은 바로 진행"과의 충돌 해소 (`plan.md:24`) | **수정 후 수용** | 충돌을 "파일별 승인"으로 푸는 대신, "승인된 작업 범위 안에서 바로 진행"으로 범위를 명확히 함 |
| 5 | Hermes: 승인된 호출 순차 진행, 권한·도구·쓰기 확대 불가 (`plan.md:12`, `:49`) | **수용** | `AX_RULES` 역할표의 "Hermes (보류) / 알림 / 읽기 전용 DB role"을 교체. "알림"은 외부 발송 금지(6장)와 충돌하므로 삭제, DB 접근은 별도 승인 전까지 없음 |
| 6 | Codex 읽기 전용, 수정 반복 최대 2회 유지 (`plan.md:47`, `:50`) | **수용** | 기존 규칙 그대로 유지 |
| 7 | 이번 작업 commit/push·DB 접근·외부 발송 금지 (`plan.md:51`) | **수용** | 기존 commit/push 사용자 확인 규칙은 그대로 둠 |
| 8 | HANDOFF 항목 분리 (`plan.md:52-58`) | **수용** | 설치 / 연결 시험 / 합성 샘플 / 전체 흐름(미검증) / 첫 실제 업무 과제(미완료) 분리 |
| 9 | 지시 스크립트 실행 여부를 증거로 판단 (`plan.md:26`) | **수용** | AX-03 `plan.md`가 실제 생성됨(exit 0) → 체크. 단 지시서 작성 Codex의 WSL 확인 거부는 별도 기록 |
| 10 | DECISIONS 상단에 후속 결정, 설치 기록에 버전 추가, 기존 이력 보존 (`plan.md:29-31`, `:59`) | **수용** | 기존 2026-10-14 결정은 삭제하지 않고 Hermes 항목에 후속 결정 연결 |
| 11 | 검증 명령 `wsl ...` 재실행 (`plan.md:66-69`) | **수정** | 이 세션에는 셸 도구가 없어 실행하지 않음. 오케스트레이터 확인 결과를 출처와 함께 기록 |
| 12 | 문서 수정 후 `git diff --check` 등 (`plan.md:79-84`) | **수정** | 같은 이유로 실행하지 못함. 수동 대조로 대체 — 미실행으로 보고 |
| 13 | 샘플 실제 경로를 문서에 만들지 않음 (`plan.md:39`) | **수정** | 경로는 이제 확인됨. 공개 저장소이므로 사용자 절대경로 대신 `~/.claude/project/ax-sample-02`(저장소 밖 로컬 샘플)로 표기 |
| 14 | 스크립트·전역 설정·AGENTS.md 수정 안 함 (`plan.md:92`) | **수용** | 수정 대상은 세 문서와 이 파일뿐 |

## 지시서 질문에 대한 답 (`plan.md:98-101`)
1. WSL·Hermes 버전: Codex 오케스트레이터가 독립 확인(사용자 전달). 저장소 안 로그 파일은 없음.
2. 샘플: `~/.claude/project/ax-sample-02`, `python3 -B -m unittest -v` (WSL Ubuntu), 근거는 샘플의 `implementation.md` 2절.
3. 연결 시험 경로: Hermes → Claude → Codex 표식 세션(`20261014_154228_bd9f0f`). 샘플 구현은 Hermes 경유가 아님(Codex → Claude 직접). Hermes는 읽기 전용 검증(`20261014_162927_98ac5b`)만.
4. 승인 범위: `docs/AX_RULES.md`, `docs/HANDOFF.md`, `docs/DECISIONS.md`, 이 `plan-check.md`. 다른 파일·설정·DB는 범위 밖.

## 한계
- 이 세션에서는 WSL·Hermes·unittest·git 명령을 직접 실행하지 않았다(셸 도구 없음). 설치·연결 사실은 오케스트레이터 확인, 샘플 결과는 샘플 문서 기록에 근거한다.
- Hermes 전체 흐름(지시→구현→검토를 Hermes가 순차 진행)은 미검증.
- cp949 터미널 한글 diff 전달(AX-01 미검증 항목)은 이번 작업과 무관, 여전히 미검증.
