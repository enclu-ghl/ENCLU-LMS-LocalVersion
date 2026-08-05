"""
[1회성 디버그 스크립트]
다운로드관리자(BL30) 목록의 실제 컬럼 aria-describedby 키를 확인하기 위한 스크립트.

사용법:
1. 디버그 크롬이 이미 켜져 있고(9222 포트), 그 크롬에서 이지어드민
   다운로드관리자(BL30) 화면이 열려 있는 상태여야 합니다.
   (지금까지 스크린샷 찍으셨던 그 화면 그대로, 이미 목록에 행이 있으면 그걸로 충분합니다)
2. uph_download_macro.py 와 같은 폴더에 이 파일을 두고 실행:
     python debug_dump.py
3. 실행 결과가 화면에 바로 출력됩니다. 그 내용을 그대로 복사해서 전달해주세요.
"""

from selenium import webdriver
from uph_download_macro import debug_dump_row_columns

options = webdriver.ChromeOptions()
options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
driver = webdriver.Chrome(options=options)

print(f"연결된 창 제목: {driver.title}")
print("다운로드관리자 화면이 맞는지 확인 후 계속 진행합니다...\n")

debug_dump_row_columns(driver)

print("\n완료. 위 [DEBUG] 로 시작하는 줄들을 그대로 복사해서 전달해주세요.")