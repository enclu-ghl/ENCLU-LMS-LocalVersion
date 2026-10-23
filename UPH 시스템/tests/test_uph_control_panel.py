# -*- coding: utf-8 -*-
"""UPH 제어판: 종료 기록·창 닫기 확인·접근 코드 분리 검증 (AX-20261022-01).

화면 없이 위젯을 가짜로 바꿔 판단 로직만 확인한다.
실행 (저장소 루트에서): py -m unittest discover -s "UPH 시스템/tests" -v
"""
import json
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


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class StallAlert(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.m = cp.StallMonitor(threshold_sec=600, clock=self.clock)

    def test_no_alert_before_threshold_then_once(self):
        started = self.clock.t
        self.clock.t += 599
        self.assertIsNone(self.m.observe(True, started, None))
        self.clock.t += 1
        self.assertEqual(self.m.observe(True, started, None), "alert")
        self.clock.t += 3600
        self.assertIsNone(self.m.observe(True, started, None))  # 같은 멈춤으로 계속 울리지 않는다

    def test_recovered_after_new_done_and_rearms(self):
        started = self.clock.t
        self.clock.t += 700
        self.assertEqual(self.m.observe(True, started, None), "alert")
        self.clock.t += 10
        self.assertEqual(self.m.observe(True, started, self.clock.t), "recovered")
        last_done = self.clock.t
        self.clock.t += 600
        self.assertEqual(self.m.observe(True, started, last_done), "alert")  # 다음 멈춤은 다시 알린다

    def test_recent_done_resets_reference(self):
        started = self.clock.t
        self.clock.t += 500
        last_done = self.clock.t
        self.clock.t += 500   # 시작 기준이면 1000초지만 마지막 완료 후 500초
        self.assertIsNone(self.m.observe(True, started, last_done))

    def test_not_running_never_alerts_and_resets(self):
        started = self.clock.t
        self.clock.t += 5000
        self.assertIsNone(self.m.observe(False, started, None))
        self.assertIsNone(self.m.observe(True, None, None))

    def test_threshold_env_floor_and_invalid(self):
        for raw, expected in (("35", 2100), ("3", 600), ("abc", 2100)):
            with mock.patch.dict(os.environ, {"UPH_ALERT_NO_DONE_MIN": raw}):
                self.assertEqual(cp._alert_threshold_sec(), expected, raw)


class StandaloneSettings(unittest.TestCase):
    def test_alert_settings_read_from_dotenv_when_env_missing(self):
        # Codex 2차 검토: 단독 실행에서도 .env의 알림 설정을 읽어야 한다 (환경변수가 우선)
        with tempfile.TemporaryDirectory() as d, mock.patch.object(cp, "BASE_DIR", d):
            with open(os.path.join(d, ".env"), "w", encoding="utf-8") as f:
                f.write("UPH_ALERT_NO_DONE_MIN=40\nUPH_ALERT_WEBHOOK_URL=https://example.invalid/hook\n")
            with mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop("UPH_ALERT_NO_DONE_MIN", None)
                os.environ.pop(cp.ALERT_WEBHOOK_ENV, None)
                self.assertEqual(cp._alert_threshold_sec(), 2400)
                opener = mock.MagicMock()
                self.assertTrue(cp.send_webhook("x", opener=opener))
            with mock.patch.dict(os.environ, {"UPH_ALERT_NO_DONE_MIN": "50"}):
                self.assertEqual(cp._alert_threshold_sec(), 3000)


class Webhook(unittest.TestCase):
    def test_no_url_or_non_https_does_not_send(self):
        opener = mock.Mock()
        # 실제 .env에 웹훅 주소가 있어도 영향받지 않게 빈 폴더를 기준으로 읽게 한다
        with tempfile.TemporaryDirectory() as empty_dir, \
                mock.patch.object(cp, "BASE_DIR", empty_dir), \
                mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(cp.ALERT_WEBHOOK_ENV, None)
            self.assertFalse(cp.send_webhook("x", opener=opener))
        self.assertFalse(cp.send_webhook("x", url="http://example.invalid/hook", opener=opener))
        opener.assert_not_called()

    def test_posts_json_text(self):
        opener = mock.MagicMock()
        self.assertTrue(cp.send_webhook("멈춤", url="https://example.invalid/hook", opener=opener))
        req = opener.call_args.args[0]
        self.assertEqual(req.get_method(), "POST")
        self.assertEqual(json.loads(req.data.decode("utf-8")), {"text": "멈춤"})

    def test_failure_returns_false(self):
        opener = mock.Mock(side_effect=OSError("down"))
        self.assertFalse(cp.send_webhook("x", url="https://example.invalid/hook", opener=opener))


class TailDoneDetection(_TmpLog):
    def make(self, content):
        p = _panel()
        p.log_path = os.path.join(self.tmp.name, "macro.log")
        with open(p.log_path, "w", encoding="utf-8") as f:
            f.write(content)
        p.log_pos, p.last_done_mono, p.done_watch_pos = 0, None, 0
        return p

    def test_done_line_updates_last_done(self):
        p = self.make("[x] 회차 시작\n")
        cp.ProcessPanel._tail_log(p)  # _panel()은 _tail_log를 가짜로 바꿔 두므로 원래 메서드를 직접 부른다
        self.assertIsNone(p.last_done_mono)
        with open(p.log_path, "a", encoding="utf-8") as f:
            f.write("[x] [DONE] 다운로드 매크로 정상 완료\n")
        cp.ProcessPanel._tail_log(p)
        self.assertIsNotNone(p.last_done_mono)

    def test_old_done_before_this_run_is_ignored(self):
        # Codex 검토: 누적 로그의 과거 [DONE]을 이번 실행의 완료로 오인하면 안 된다
        p = self.make("[10/19] [DONE] 다운로드 매크로 정상 완료\n[10/19] 90초 대기 후 다음 회차 진행...\n")
        p.done_watch_pos = os.path.getsize(p.log_path)   # start()가 하는 것과 같게
        cp.ProcessPanel._tail_log(p)
        self.assertIsNone(p.last_done_mono)
        p._append_log.assert_called()                    # 화면에는 과거 로그도 보여준다


class StallRestart(unittest.TestCase):
    def test_restart_between_ticks_rearms(self):
        # Codex 검토: 알림 후 다음 tick 전에 종료→재시작되면 새 실행의 멈춤도 다시 알려야 한다
        clock = Clock()
        m = cp.StallMonitor(threshold_sec=600, clock=clock)
        clock.t = 1600
        self.assertEqual(m.observe(True, 1000, None), "alert")
        clock.t = 10000
        self.assertEqual(m.observe(True, 1601, None), "alert")


class AppAlerts(_TmpLog):
    def make_app(self):
        app = cp.App.__new__(cp.App)
        app.root = mock.Mock()
        app.alert_label = mock.Mock()
        app.watchdog_panel = _panel("watchdog_agent.py")
        app.download_panel = _panel("uph_download_macro.py")
        for p in (app.watchdog_panel, app.download_panel):
            p.unexpected_exit = None
            p.started_mono = 0.0
            p.last_done_mono = None
        app.stall = mock.Mock()
        app.stall.observe.return_value = None
        app.stall.threshold = 2100
        return app

    def quiet(self):
        return mock.patch.multiple(cp, send_webhook=mock.DEFAULT),             mock.patch.object(cp.tk, "Toplevel"), mock.patch.object(cp.ttk, "Label"), mock.patch.object(cp.ttk, "Button")

    def run_checks(self, app, times=1):
        a, b, c, d = self.quiet()
        with a, b, c, d, mock.patch.object(cp.threading, "Thread"):
            for _ in range(times):
                app._check_alerts()

    def test_unexpected_exit_notifies_once(self):
        app = self.make_app()
        app.notify = mock.Mock()
        app.watchdog_panel.unexpected_exit = (1, "RuntimeError: boom")
        app._check_alerts()
        app._check_alerts()
        self.assertEqual(app.notify.call_count, 1)
        self.assertIn("watchdog_agent.py", app.notify.call_args.args[1])
        self.assertIn("RuntimeError: boom", app.notify.call_args.args[1])

    def test_stall_alert_and_recovery_messages(self):
        app = self.make_app()
        app.notify = mock.Mock()
        app.stall.observe.return_value = "alert"
        app._check_alerts()
        self.assertIn("35분", app.notify.call_args.args[1])
        app.stall.observe.return_value = "recovered"
        app._check_alerts()
        self.assertTrue(app.notify.call_args.kwargs.get("recovered"))

    def test_download_recovery_keeps_watchdog_exit_warning(self):
        # Codex 검토: 다운로드 회복이 아직 꺼져 있는 watchdog 경고를 지우면 안 된다
        app = self.make_app()
        app.watchdog_panel.proc.poll.return_value = 1        # watchdog 죽은 상태 유지
        app.watchdog_panel.unexpected_exit = (1, "boom")
        app.stall.observe.return_value = "alert"
        self.run_checks(app)
        app.stall.observe.return_value = "recovered"
        self.run_checks(app)
        label = app.alert_label.config.call_args.kwargs["text"]
        self.assertIn("watchdog_agent.py", label)
        self.assertNotIn("다운로드 매크로가 35분", label)

    def test_exit_warning_clears_when_process_running_again(self):
        app = self.make_app()
        app.watchdog_panel.proc.poll.return_value = 1
        app.watchdog_panel.unexpected_exit = (1, "boom")
        self.run_checks(app)
        app.watchdog_panel.proc.poll.return_value = None     # 사람이 다시 시작
        self.run_checks(app)
        self.assertEqual(app.alert_label.config.call_args.kwargs["text"], "")

    def test_restart_clears_previous_stall_warning(self):
        # Codex 2차 검토: 재시작 후 정상 완료해도 이전 멈춤 경고가 남으면 안 된다
        app = self.make_app()
        app.stall = cp.StallMonitor(threshold_sec=600, clock=lambda: 2000.0)
        app.download_panel.started_mono = 1000.0
        self.run_checks(app)
        self.assertIn("stall", app.active_alerts)
        app.download_panel.started_mono = 1990.0          # 다음 tick 전에 재시작
        app.download_panel.last_done_mono = 1995.0
        self.run_checks(app)
        self.assertNotIn("stall", app.active_alerts)
        self.assertEqual(app.alert_label.config.call_args.kwargs["text"], "")

    def test_notify_records_event_and_sends_webhook_in_background(self):
        app = cp.App.__new__(cp.App)
        app.root = mock.Mock()
        app.alert_label = mock.Mock()
        with mock.patch.object(cp, "send_webhook") as hook,              mock.patch.object(cp.threading, "Thread") as thread,              mock.patch.object(cp.tk, "Toplevel"), mock.patch.object(cp.ttk, "Label"),              mock.patch.object(cp.ttk, "Button"):
            app.notify("stall", "테스트 멈춤")
        self.assertIn("알림: 테스트 멈춤", self.events())
        thread.assert_called_once()
        self.assertIs(thread.call_args.kwargs["target"], hook)


if __name__ == "__main__":
    unittest.main()
