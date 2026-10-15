# -*- coding: utf-8 -*-
"""UPH 다운로드 매크로 반복 실패 자동 새로고침 검증 (AX-20261015-07).

실제 브라우저·WMS 없이 가짜 driver와 가짜 시계로 PageRefresher 판단과 run_forever 연결을 확인한다.
실행 (저장소 루트에서): py -m unittest discover -s "UPH 시스템/tests" -v
"""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import uph_download_macro as m  # noqa: E402


class FakeDriver:
    def __init__(self, handles=("W",), current="W"):
        self.window_handles = list(handles)
        self.current_window_handle = current
        self.title = "확장주문검색2"
        self.refreshes = []  # 새로고침 때 선택돼 있던 창
        self.switch_to = mock.Mock()
        self.switch_to.window.side_effect = self._switch

    def _switch(self, h):
        self.current_window_handle = h

    def refresh(self):
        self.refreshes.append(self.current_window_handle)


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class RefresherTest(unittest.TestCase):
    def setUp(self):
        self.logs = []
        self.enterContext(mock.patch.object(m, "log", side_effect=self.logs.append))
        self.ready = self.enterContext(mock.patch.object(m.PageRefresher, "_wait_wms_ready", return_value=True))
        self.clock = Clock()
        self.r = m.PageRefresher(clock=self.clock)
        self.d = FakeDriver()

    def step(self):
        return self.r.maybe_refresh(self.d, "W")

    def test_no_refresh_while_succeeding(self):
        for _ in range(5):
            self.assertFalse(self.step())
            self.r.record_round(True)
            self.clock.t += 120
        self.assertEqual(self.d.refreshes, [])

    def test_failure_triggers_one_refresh_then_reset_on_success(self):
        self.r.record_round(False)
        self.assertTrue(self.step())
        self.assertFalse(self.step())  # 같은 실패로 두 번 하지 않음
        self.r.record_round(True)
        self.assertEqual(self.r.consecutive, 0)
        self.assertTrue(any("직후 회차 결과: 성공" in s for s in self.logs))

    def test_idle_threshold_899_vs_900(self):
        self.clock.t += m.REFRESH_AFTER_NO_SUCCESS_SEC - 1
        self.assertFalse(self.step())
        self.clock.t += 1
        self.assertTrue(self.step())
        self.assertTrue(any("성공 없음" in s for s in self.logs))

    def test_no_history_counts_from_start(self):
        r = m.PageRefresher(clock=self.clock)  # 생성 시각 = 시작 시각
        self.clock.t += m.REFRESH_AFTER_NO_SUCCESS_SEC
        self.assertTrue(r.maybe_refresh(self.d, "W"))

    def test_failure_and_idle_together_refresh_once(self):
        self.clock.t += m.REFRESH_AFTER_NO_SUCCESS_SEC + 10
        self.r.record_round(False)
        self.assertTrue(self.step())
        self.assertEqual(len(self.d.refreshes), 1)

    def test_stops_after_max_consecutive_and_logs_once(self):
        for _ in range(m.REFRESH_MAX_CONSECUTIVE):
            self.r.record_round(False)
            self.assertTrue(self.step())
        for _ in range(3):
            self.r.record_round(False)
            self.assertFalse(self.step())
        self.assertEqual(len(self.d.refreshes), m.REFRESH_MAX_CONSECUTIVE)
        self.assertEqual(sum("자동 새로고침을 멈춥니다" in s for s in self.logs), 1)
        self.r.record_round(True)  # 성공하면 다시 새로고침 가능
        self.r.record_round(False)
        self.assertTrue(self.step())

    def test_dead_session_does_not_schedule_refresh(self):
        self.r.record_dead_session()
        self.assertFalse(self.step())

    def test_refreshes_wms_tab_not_manager_window(self):
        d = FakeDriver(handles=("W", "MGR"), current="MGR")
        self.r.record_round(False)
        self.r.maybe_refresh(d, "W")
        self.assertEqual(d.refreshes, ["W"])

    def test_missing_wms_handle_skips_refresh(self):
        # Codex 지적 1: 원래 WMS 탭이 없으면 다른 창(다운로드관리자)을 새로고침하지 않는다
        d = FakeDriver(handles=("MGR",), current="MGR")
        self.r.record_round(False)
        self.assertFalse(self.r.maybe_refresh(d, "W"))
        self.assertEqual(d.refreshes, [])
        self.assertTrue(any("찾지 못해" in s for s in self.logs))

    def test_no_refresh_right_after_reconnect_even_if_idle(self):
        # Codex 지적 3: 장시간 세션 장애 후 재연결 직후 첫 회차엔 새로고침하지 않음 (그다음부터는 규칙대로)
        self.clock.t += m.REFRESH_AFTER_NO_SUCCESS_SEC + 1
        self.r.record_dead_session()
        self.assertFalse(self.step())
        self.assertTrue(self.step())

    def test_not_ready_logs_error(self):
        self.ready.return_value = False
        self.r.record_round(False)
        self.step()
        self.assertTrue(any(s.startswith("[ERR] 새로고침#1 후") for s in self.logs))


class _Stop(BaseException):
    pass


class RunForeverWiring(unittest.TestCase):
    """실제 run_forever 루프: 다운로드 결과 순서에 따라 새로고침이 언제 일어나는지."""

    def run_loop(self, outcomes, n_rounds, driver=None, recon=False, calls=None):
        logs, driver = [], driver or FakeDriver()
        results = iter(outcomes)

        def fake_download(*a):
            if calls is not None:
                calls.append(a[1:])  # (date_type, status, start, end)
            r = next(results)
            if isinstance(r, BaseException):
                raise r
            return r

        sleeps = {"n": 0}

        def fake_sleep(_s):
            sleeps["n"] += 1
            if sleeps["n"] >= n_rounds:
                raise _Stop

        with mock.patch.object(m, "log", side_effect=logs.append), \
             mock.patch.object(m, "_connect_driver", return_value=driver), \
             mock.patch.object(m, "run_download_macro", side_effect=fake_download), \
             mock.patch.object(m.os.path, "exists", return_value=True), \
             mock.patch.object(m, "RECON_INTERVAL_SEC", 0 if recon else 10 ** 9), \
             mock.patch.object(m.time, "time", return_value=10 ** 6), \
             mock.patch.object(m.time, "sleep", side_effect=fake_sleep), \
             mock.patch.object(m.PageRefresher, "_wait_wms_ready", return_value=True):
            with self.assertRaises(_Stop):
                m.run_forever()
        return driver, logs

    def test_success_rounds_never_refresh(self):
        driver, _ = self.run_loop([True] * 20, n_rounds=5)  # 회차당 조회 2개
        self.assertEqual(driver.refreshes, [])

    def test_failed_round_refreshes_before_next_round(self):
        # 1회차: 송장입력일 실패(False)·배송일 성공 → 회차 실패 / 2회차 시작 전 새로고침 → 성공
        driver, logs = self.run_loop([False, True, True, True, True, True], n_rounds=3)
        self.assertEqual(driver.refreshes, ["W"])
        self.assertTrue(any("직후 회차 결과: 성공" in s for s in logs))

    def test_exception_round_refreshes(self):
        # 팝업3 실패처럼 예외로 끝난 회차
        err = m.TimeoutException("popup3")
        driver, _ = self.run_loop([err, True, True, True, True], n_rounds=3)
        self.assertEqual(driver.refreshes, ["W"])

    def test_refresh_error_does_not_abort_round_or_skip_recon(self):
        # Codex 지적 2: 새로고침이 오류로 끝나도 그 회차 조회(재확인 포함)는 그대로 진행
        class BadRefreshDriver(FakeDriver):
            def refresh(self):
                raise m.TimeoutException("refresh timeout")

        calls, outcomes = [], [False, True] + [True] * 10
        # 1회차(재확인 4개 조회) 중 첫 조회 실패 → 2회차 시작 전 새로고침이 오류 → 2회차 조회는 계속
        driver, logs = self.run_loop(outcomes, n_rounds=2, driver=BadRefreshDriver(), recon=True, calls=calls)
        self.assertTrue(any("복구 새로고침 중 오류" in s for s in logs))
        self.assertEqual(len(calls), 8)  # 두 회차 모두 재확인 포함 4개씩 (RECON_INTERVAL_SEC=0)
        self.assertIn(m.RECON_START_OFFSET_DAYS, [c[2] for c in calls[4:]])

    def test_dead_session_round_does_not_refresh(self):
        err = m.WebDriverException("no such window: target window already closed")
        driver, _ = self.run_loop([err, True, True, True, True], n_rounds=3)
        self.assertEqual(driver.refreshes, [])


if __name__ == "__main__":
    unittest.main()
