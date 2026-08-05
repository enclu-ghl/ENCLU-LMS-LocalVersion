# Windows 종속성 보고서

각 항목을 "있음 / 없음 / 미확인"으로 판정하고, 있음인 경우 이식성(Linux 이전 가능성)에 미치는 영향을 표시.

| 항목 | 판정 | 근거 / 영향 |
|---|---|---|
| IIS / ASP.NET Framework | **없음** | 웹 대시보드는 Streamlit(Python)이며 Streamlit Cloud에서 구동 중. IIS 관련 흔적 없음 |
| MS Access / SQL Server LocalDB | **없음** | DB는 Supabase(Postgres)와 별도 원격 PostgreSQL만 사용 |
| Excel·Word·Outlook COM 자동화 | **없음** | 엑셀 처리는 `openpyxl`/`pandas`/`xlrd`로 파일 파싱만 함. `win32com` 등 COM 호출 흔적 없음 → Linux 이식에 우호적 |
| Windows 인증 / Active Directory | **없음** | 워크그룹 구성, 로컬 계정만 사용. 도메인 인증 미사용 |
| PowerShell / BAT 스크립트 | **있음 (경량)** | `.bat` 파일들은 단순히 python.exe 경로 호출용. 로직 자체는 Python에 있어 대체가 쉬움 |
| 레지스트리 설정 | **없음 (앱 로직 상)** | 설치설명서에 언급된 "앱 실행 별칭" 레지스트리는 설치 편의를 위한 것이며 애플리케이션 동작과 무관 |
| 네트워크 드라이브 문자 | **없음** | 매핑된 SMB 드라이브 0건 확인 |
| 프린터 / 바코드 / 시리얼·USB 장비 | **없음 (물리 장비 기준)** | 바코드 인식은 `pyzbar` + `streamlit-webrtc`로 **브라우저 웹캠 영상**을 처리하는 방식. 전용 스캐너/시리얼 장비 종속 없음 → Linux 이식에 우호적. 다만 `streamlit-webrtc`는 WebRTC(STUN/TURN, UDP 포트) 인프라가 필요 |
| GUI 로그인 / 원격 데스크톱 세션 | **있음 (핵심 종속성)** | 허브와 4개 하위 프로그램(박스추천, 매칭매크로, UPH제어판, 파일찢기)은 전부 Tkinter 데스크톱 GUI. 사람이 콘솔/RDP로 로그인한 상태에서만 실행 가능 |
| Chrome 사용자 프로필 / 브라우저 자동화 | **있음 (핵심 종속성)** | UPH 다운로드 매크로, 상품매칭 매크로 모두 Selenium으로 실제 Chrome을 원격디버깅 모드(`--remote-debugging-port=9222`)로 조작. 사람이 매일 수동으로 WMS에 보안코드 입력 후 로그인해야 파이프라인이 시작됨 |
| Windows 전용 프로그램/DLL | **미확인** | 코드베이스 전수 스캔은 하지 않았음. Tkinter/Selenium/Streamlit 스택 자체는 크로스플랫폼이나, 개별 패키지의 Windows 전용 의존성 유무는 실제 `pip install` 테스트로 재확인 필요 |
| WSL 또는 Docker Desktop 종속성 | **없음(사용 안 함으로 추정)** | `wsl.exe`만 설치돼 있고 Docker는 미설치. 이 프로젝트가 이를 사용한다는 증거 없음 |

## 결론

1. **웹 대시보드(app.py, Streamlit) 자체는 Windows 종속성이 거의 없다.** COM/레지스트리/네트워크드라이브/전용장비 의존이 없고, DB도 이미 클라우드(Supabase/원격 Postgres)라 Linux 서버로 옮기는 데 기술적 장애가 크지 않다.
2. **문제는 데스크톱 GUI 4종 + Selenium 브라우저 자동화다.** 이들은 "서버로 이전"이라는 개념 자체가 성립하기 어렵다 (사람이 화면을 보고 로그인/클릭해야 함). IDC 서버 마이그레이션의 범위를 "웹 대시보드 + 데이터 파이프라인"으로 한정할지, "GUI 도구까지 포함"할지 사용자 확인이 필요하다 (→ 10번 질문 참고).
3. 하드코딩된 절대경로(`C:\Users\...`)는 OS 선택과 무관하게 반드시 정리해야 한다.
