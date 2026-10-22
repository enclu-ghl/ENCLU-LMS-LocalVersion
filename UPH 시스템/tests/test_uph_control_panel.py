# -*- coding: utf-8 -*-
"""UPH 제어판: 종료 기록·창 닫기 확인·접근 코드 분리 검증 (AX-20261022-01).

화면 없이 위젯을 가짜로 바꿔 판단 로직만 확인한다.
실행 (저장소 루트에서): py -m unittest discover -s "UPH 시스템/tests" -v
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import uph_control_panel as cp  # noqa: E402


class _TmpLog(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.log_path = os.path.join(self.tmp.name, "uph_panel_events.log")
        self.enterContext(mock.patch.object(cp, "PANEL_EVENT_LOG", self.log_path))

    def events(self):
        if not os.path.exists(self.log_path):
            return ""
        with open(self.log_path, encoding="utf-8") as f:
            return f.read()


def _panel(script="uph_download_macro.py", running=True):
    p = cp.ProcessPanel.__new__(cp.ProcessPanel)
    p.script_name = script
    p.stderr_path = os.devnull
    p.proc = mock.Mock(pid=4321, returncode=None)
    p.proc.poll.return_value = None if running else 1
    p.start_time = None
    p.stop_time = None
    for name in ("status_label", "start_btn", "stop_btn", "time_label", "info_label"):
        setattr(p, name, mock.Mock())
    p._append_log = mock.Mock()
    p._external_check_counter = 0
    p._check_external = mock.Mock()
    p._tail_log = mock.Mock()
    return p


class PanelEventLog(_TmpLog):
    def test_stop_button_is_recorded_with_reason_and_result(self):
        p = _panel()
        with mock.patch.object(cp.subprocess, "run", return_value=mock.Mock(returncode=0)):
            p.stop()
        log = self.events()
        self.assertIn("종료(종료 버튼): uph_download_macro.py (PID 4321)", log)
        self.assertIn("taskkill 성공", log)
        self.assertIn("종료 확인됨", log)

    def test_stop_when_not_running_records_nothing(self):
        p = _panel(running=False)
        p.stop()
        self.assertEqual(self.events(), "")

    def test_unexpected_exit_records_exit_code_and_last_stderr_line(self):
        p = _panel(running=False)
        p.proc.returncode = 1
        p._read_stderr_tail = mock.Mock(return_value="Traceback...\nRuntimeError: boom\n")
        p.tick()
        log = self.events()
        self.assertIn("예상치 못한 종료: uph_download_macro.py (PID 4321, 종료코드 1)", log)
        self.assertIn("RuntimeError: boom", log)

    def test_log_failure_does_not_raise(self):
        with mock.patch.object(cp, "PANEL_EVENT_LOG", os.path.join(self.tmp.name, "없는폴더", "x.log")):
            cp.log_panel_event("x")  # 예외 없이 지나가야 한다


class CloseConfirmation(_TmpLog):
    def make_app(self, running=True):
        app = cp.App.__new__(cp.App)
        app.root = mock.Mock()
        app.watchdog_panel = _panel("watchdog_agent.py", running)
        app.download_panel = _panel("uph_download_macro.py", running)
        app.watchdog_panel.stop = mock.Mock()
        app.download_panel.stop = mock.Mock()
        return app

    def test_cancel_keeps_both_processes(self):
        app = self.make_app()
        with mock.patch.object(cp.messagebox, "askyesno", return_value=False):
            app.on_close()
        app.watchdog_panel.stop.assert_not_called()
        app.download_panel.stop.assert_not_called()
        app.root.after.assert_not_called()
        self.assertIn("창 닫기 취소", self.events())

    def test_confirm_stops_both_with_reason(self):
        app = self.make_app()
        with mock.patch.object(cp.messagebox, "askyesno", return_value=True):
            app.on_close()
        app.watchdog_panel.stop.assert_called_once_with(reason="창 닫기")
        app.download_panel.stop.assert_called_once_with(reason="창 닫기")
        self.assertIn("창 닫기 — 두 프로세스 종료", self.events())

    def test_no_prompt_when_nothing_running(self):
        app = self.make_app(running=False)
        with mock.patch.object(cp.messagebox, "askyesno") as ask:
            app.on_close()
        ask.assert_not_called()
        app.root.after.assert_called_once()


class AccessCode(unittest.TestCase):
    def make_screen(self):
        s = cp.LoginScreen.__new__(cp.LoginScreen)
        s.on_success = mock.Mock()
        s.code_var = mock.Mock()
        s.error_label = mock.Mock()
        return s

    def test_no_hardcoded_code_in_source(self):
        # 코드 값 자체를 테스트에 적으면 그게 다시 공개 저장소에 올라가므로, '문자열 상수로 대입' 형태만 검사한다
        import re
        src = Path(cp.__file__).read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"^ACCESS_CODE\s*=\s*['\"]", src, re.M))
        self.assertFalse(hasattr(cp, "ACCESS_CODE"))

    def test_env_code_matches(self):
        s = self.make_screen()
        s.code_var.get.return_value = "secret-1"
        with mock.patch.dict(os.environ, {cp.ACCESS_CODE_ENV: "secret-1"}):
            s.check_code()
        s.on_success.assert_called_once()

    def test_wrong_code_rejected(self):
        s = self.make_screen()
        s.code_var.get.return_value = "nope"
        with mock.patch.dict(os.environ, {cp.ACCESS_CODE_ENV: "secret-1"}):
            s.check_code()
        s.on_success.assert_not_called()

    def test_korean_code_and_korean_input(self):
        # Codex 검토: 한글이 섞이면 compare_digest(str)가 TypeError
        for configured, typed, ok in (("엔클루-1", "엔클루-1", True), ("엔클루-1", "엔클루-2", False),
                                      ("secret-1", "가", False)):
            s = self.make_screen()
            s.code_var.get.return_value = typed
            with mock.patch.dict(os.environ, {cp.ACCESS_CODE_ENV: configured}):
                s.check_code()
            self.assertEqual(s.on_success.called, ok, (configured, typed))

    def test_unconfigured_never_opens_even_with_empty_input(self):
        s = self.make_screen()
        s.code_var.get.return_value = ""
        with tempfile.TemporaryDirectory() as d, \
             mock.patch.dict(os.environ, {}, clear=False), \
             mock.patch.object(cp, "BASE_DIR", d):
            os.environ.pop(cp.ACCESS_CODE_ENV, None)
            s.check_code()
        s.on_success.assert_not_called()
        self.assertIn("설정되지 않았습니다", s.error_label.config.call_args.kwargs["text"])

    def test_standalone_reads_dotenv_next_to_script(self):
        s = self.make_screen()
        s.code_var.get.return_value = "from-file"
        with tempfile.TemporaryDirectory() as d, mock.patch.object(cp, "BASE_DIR", d):
            with open(os.path.join(d, ".env"), "w", encoding="utf-8") as f:
                f.write("OTHER=1\nUPH_PANEL_ACCESS_CODE=from-file\n")
            with mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop(cp.ACCESS_CODE_ENV, None)
                s.check_code()
        s.on_success.assert_called_once()


if __name__ == "__main__":
    unittest.main()
