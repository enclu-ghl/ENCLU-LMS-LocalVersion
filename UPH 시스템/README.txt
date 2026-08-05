====================================================
ENCLU UPH 실시간 현황판 - 자동화 시스템 설치 안내
====================================================

[폴더 구성]
이 폴더 안에 아래 파일들이 전부 있어야 합니다:
  - watchdog_agent.py       (WMS 파일 감시 -> DB 반영)
  - uph_download_macro.py   (이지어드민 자동 다운로드, 상시 반복)
  - uph_control_panel.py    (위 둘을 켜고 끄는 GUI 제어판)
  - .env                    (DB 접속정보, 감시폴더 경로)
  - agent_requirements.txt  (필요한 파이썬 패키지 목록)
  - UPH_제어판_실행.bat      (제어판 실행용)
  - Download the Uph file  (폴더, 다운로드 받은 xls 파일이 쌓이는 곳 - 없으면 새로 만들어주세요)

[최초 설정 1회]

1. python.exe 경로 확인
   명령 프롬프트(cmd)에서:
       where python
   를 입력해서 나오는 실제 경로를 확인하세요.
   만약 "C:\Users\enclu\AppData\Local\Python\bin\python.exe" 가 아니라면,
   아래 두 파일 안의 경로를 실제 경로로 바꿔주세요:
     - UPH_제어판_실행.bat
     - uph_control_panel.py (PYTHON_EXE 변수)

2. 필요한 패키지 설치
   명령 프롬프트에서 이 폴더로 이동한 뒤:
       pip install -r agent_requirements.txt --break-system-packages
   (Windows 파이썬이면 --break-system-packages 없이도 됩니다)

3. .env 파일 확인
   - DATABASE_URL: Supabase 접속 정보 (이미 채워져 있음)
   - UPH_WATCH_FOLDER: 다운로드 파일이 쌓이는 폴더의 "정확한 전체경로"로 맞춰주세요.
     지금은 "Download the Uph file" 폴더를 가리키도록 되어 있습니다.

4. 디버그 크롬의 다운로드 폴더 설정
   디버그용 크롬(--remote-debugging-port=9222 로 켠 것)에서:
     chrome://settings/downloads
   -> 다운로드 위치를 .env의 UPH_WATCH_FOLDER와 "완전히 동일한 경로"로 지정
   -> "다운로드 전 저장 위치 확인" 옵션 끄기

[매일 사용법]

1. 디버그 크롬 실행:
     chrome.exe --remote-debugging-port=9222 --user-data-dir="C:\chrome-debug-profile"
   -> 이지어드민 로그인 (보안코드 입력)

2. UPH_제어판_실행.bat 더블클릭
   -> 제어판 창이 뜸 (콘솔창도 같이 뜰 수 있는데, 무시하고 최소화해두면 됩니다)

3. 제어판에서:
   - "watchdog 에이전트" 칸 -> ▶ 시작
   - "다운로드 매크로" 칸 -> ▶ 시작
   두 개 다 눌러주면, 로그가 실시간으로 흐르면서 자동으로 계속 돌아갑니다.

4. 최초 1회는 다운로드 매크로가 자동으로 "기준선 설정 모드"(상태=송장만)로
   한 번 돌고, 그 다음부터는 자동으로 평소 모드(송장+배송)로 반복됩니다.
   (baseline_done.flag 파일이 이 폴더에 자동 생성됨 - 지우면 기준선부터 다시 잡음)

5. 하루 일과 끝나면 제어판 창을 닫으면 두 프로세스 다 같이 종료됩니다.

[문제가 생기면]
- uph_agent.log          : watchdog 에이전트 로그
- uph_download_macro.log : 다운로드 매크로 로그
이 두 파일을 열어서 최근 내용을 확인해보세요.
