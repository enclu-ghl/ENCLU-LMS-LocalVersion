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
        self.title = "확장주문검색2 이지어드민 V3.5+"  # 실제 WMS 탭 제목 형식
        self.refreshes = []  # 새로고침 때 선택돼 있던 창
        self.switch_to = mock.Mock()
        self.switch_to.window.side_effect = self._switch

    def _switch(self, h):
        self.current_window_handle = h

    def refresh(self):
        self.refreshes.append(self.current_window_handle)

    def close(self):
        if self.current_window_handle == "W":
            raise AssertionError("WMS 탭(W)을 닫으면 안 된다")
        self.window_handles.remove(self.current_window_handle)
        self.closed = getattr(self, "closed", []) + [self.current_window_handle]


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

    def test_closes_other_windows_keeps_only_wms_then_refreshes(self):
        # AX-20261017-01 (사용자 요청): 오류 후 첫 페이지(WMS 탭)만 남기고 나머지 창을 닫은 뒤 새로고침
        d = FakeDriver(handles=("W", "MGR1", "MGR2"), current="MGR2")
        self.r.record_round(False)
        self.assertTrue(self.r.maybe_refresh(d, "W"))
        self.assertEqual(d.window_handles, ["W"])
        self.assertEqual(sorted(d.closed), ["MGR1", "MGR2"])
        self.assertEqual(d.refreshes, ["W"])
        self.assertTrue(any("다른 창 2개 닫음" in s for s in self.logs))

    def test_close_error_on_one_window_does_not_stop_refresh(self):
        d = FakeDriver(handles=("W", "GONE", "MGR"), current="W")
        real_close = d.close

        def close():
            if d.current_window_handle == "GONE":
                raise m.WebDriverException("no such window")
            real_close()

        d.close = close
        self.r.record_round(False)
        self.assertTrue(self.r.maybe_refresh(d, "W"))
        self.assertEqual(d.refreshes, ["W"])
        self.assertIn("W", d.window_handles)

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


class PollDownloadManager(unittest.TestCase):
    """다운로드관리자 폴링: 상세 문구가 붙은 '오류' 판정과 전체 대기 상한 (AX-20261017-01)."""

    class _Cell:
        def __init__(self, text):
            self.text = text

    class _Row:
        def __init__(self, status):
            self.status = status

        def find_element(self, _by, css):
            return PollDownloadManager._Cell({m.DLMGR_STATUS_CELL: self.status,
                                              m.DLMGR_PERCENT_CELL: "0%",
                                              m.DLMGR_REQTIME_CELL: "T"}.get(css, ""))

    def poll(self, statuses, time_step=6):
        logs, clock = [], {"t": 0.0}
        seq = iter(statuses)
        rows = {"r": None}
        drv = mock.Mock()

        def find_elements(_by, _css):
            rows["r"] = self._Row(next(seq))
            return [rows["r"]]

        drv.find_elements.side_effect = find_elements

        def fake_time():
            clock["t"] += time_step
            return clock["t"]

        with mock.patch.object(m, "log", side_effect=logs.append), \
             mock.patch.object(m, "safe_click"), \
             mock.patch.object(m, "find_my_request_row", side_effect=lambda rs: (rs[0], "T")), \
             mock.patch.object(m.time, "monotonic", side_effect=fake_time), \
             mock.patch.object(m.time, "sleep"):
            from datetime import datetime
            try:
                result = m.poll_download_manager(drv, "MGR", datetime(2026, 10, 16, 13, 30, 53))
            except StopIteration:  # 준비한 상태를 다 쓸 때까지 끝나지 않음 = 상한·오류로 끊기지 않았음
                result = None
        return result, logs

    def test_parse_status(self):
        self.assertEqual(m._parse_download_status("오류\nreCAPTCHA 오류입니다. 다시 시도해주세요."),
                         ("오류", "reCAPTCHA 오류입니다. 다시 시도해주세요."))
        self.assertEqual(m._parse_download_status("완료"), ("완료", ""))
        self.assertEqual(m._parse_download_status(""), ("", ""))
        self.assertNotEqual(m._parse_download_status("오류 없음")[0], "오류")

    def test_error_with_recaptcha_detail_gives_up_after_two(self):
        # 2026-10-16 13:30 실측 문구 — 예전엔 정확히 "오류"가 아니라서 3시간 무한 대기
        msg = "오류\nreCAPTCHA 오류입니다. 다시 시도해주세요."
        result, logs = self.poll([msg] * 50)
        self.assertIs(result, False)
        self.assertTrue(any("reCAPTCHA" in s and "포기" in s for s in logs))
        self.assertLessEqual(sum("회차," in s for s in logs), 2)

    def test_error_streak_resets_on_other_status(self):
        msg = "오류\nreCAPTCHA"
        result, logs = self.poll([msg, "작업중", msg, "작업중", msg, msg] + ["작업중"] * 10)
        self.assertIs(result, False)
        self.assertEqual(sum("회차," in s for s in logs), 6)  # 2회 연속이 된 6번째에서 포기

    def test_poll_timeout_stops_infinite_wait(self):
        # 영원히 '작업중' → 상한(기본 30분)에서 실패로 반환
        result, logs = self.poll(["작업중"] * 10000, time_step=60)
        self.assertIs(result, False)
        self.assertTrue(any("대기 상한" in s for s in logs))

    def test_error_detected_even_without_percent_cell(self):
        # Codex 지적 1: 진척도 셀이 없어도 상태가 '오류'면 판정
        class R(self._Row):
            def find_element(self, _by, css):
                if css == m.DLMGR_PERCENT_CELL:
                    raise m.NoSuchElementException("no percent")
                return super().find_element(_by, css)

        logs = []
        drv = mock.Mock()
        drv.find_elements.return_value = [R("오류\nreCAPTCHA 오류입니다.")]
        with mock.patch.object(m, "log", side_effect=logs.append), \
             mock.patch.object(m, "safe_click"), \
             mock.patch.object(m, "find_my_request_row", side_effect=lambda rs: (rs[0], "T")), \
             mock.patch.object(m.time, "sleep"):
            from datetime import datetime
            self.assertIs(m.poll_download_manager(drv, "MGR", datetime(2026, 10, 16)), False)
        self.assertTrue(any("reCAPTCHA" in s and "포기" in s for s in logs))

    def test_wall_clock_jump_does_not_affect_timeout(self):
        # Codex 지적 3: 시스템 시각(time.time)이 크게 뛰어도 상한은 monotonic 기준
        jumps = iter([0, 10 ** 7, -(10 ** 7)] * 1000)
        with mock.patch.object(m.time, "time", side_effect=lambda: next(jumps)):
            result, logs = self.poll(["작업중"] * 20, time_step=6)  # 20회 × 6초 = 2분 → 상한 전
        self.assertIsNone(result)  # 끝까지 기다림 (time.time 점프에 끊기지 않음)
        self.assertFalse(any("대기 상한" in s for s in logs))

    def test_completed_still_downloads(self):
        class R(self._Row):
            def find_element(self, _by, css):
                if css == m.DLMGR_PERCENT_CELL:
                    return PollDownloadManager._Cell("100%")
                return super().find_element(_by, css)

        logs = []
        drv = mock.Mock()
        drv.find_elements.return_value = [R("완료")]
        with mock.patch.object(m, "log", side_effect=logs.append), \
             mock.patch.object(m, "safe_click"), \
             mock.patch.object(m, "find_my_request_row", side_effect=lambda rs: (rs[0], "T")), \
             mock.patch.object(m.time, "sleep"):
            from datetime import datetime
            self.assertIs(m.poll_download_manager(drv, "MGR", datetime(2026, 10, 16)), True)


class _Stop(BaseException):
    pass


class RunForeverWiring(unittest.TestCase):
    """실제 run_forever 루프: 다운로드 결과 순서에 따라 새로고침이 언제 일어나는지."""

    def run_loop(self, outcomes, n_rounds, driver=None, recon=False, calls=None, recon_first_only=False):
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
             mock.patch.object(m, "RECON_INTERVAL_SEC", 0 if recon else (100 if recon_first_only else 10 ** 9)), \
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
        # 1회차 첫 조회 실패 → 회차 즉시 종료(AX-20261017-01) → 2회차 시작 전 새로고침이 오류 → 2회차 조회는 계속
        driver, logs = self.run_loop(outcomes, n_rounds=2, driver=BadRefreshDriver(), recon=True, calls=calls)
        self.assertTrue(any("복구 새로고침 중 오류" in s for s in logs))
        self.assertEqual(len(calls), 5)  # 1회차 1개(실패로 중단) + 2회차 재확인 포함 4개
        self.assertIn(m.RECON_START_OFFSET_DAYS, [c[2] for c in calls[1:]])

    def test_round_starts_on_wms_tab_even_if_focus_left_on_manager(self):
        # 이전 회차가 다운로드관리자 창에 초점을 남겼어도 다음 회차는 WMS 탭에서 시작
        driver = FakeDriver(handles=("W", "MGR"), current="W")
        seen = []
        results = iter([True] * 20)

        def fake_download(*_a):
            seen.append(driver.current_window_handle)
            driver.current_window_handle = "MGR"  # 회차가 관리자 창에 초점을 남긴 채 끝났다고 가정
            return next(results)

        sleeps = {"n": 0}

        def fake_sleep(_s):
            sleeps["n"] += 1
            if sleeps["n"] >= 3:
                raise _Stop

        with mock.patch.object(m, "log"), \
             mock.patch.object(m, "_connect_driver", return_value=driver), \
             mock.patch.object(m, "run_download_macro", side_effect=fake_download), \
             mock.patch.object(m.os.path, "exists", return_value=True), \
             mock.patch.object(m, "RECON_INTERVAL_SEC", 10 ** 9), \
             mock.patch.object(m.time, "time", return_value=10 ** 6), \
             mock.patch.object(m.time, "sleep", side_effect=fake_sleep):
            with self.assertRaises(_Stop):
                m.run_forever()
        self.assertEqual(seen[0], "W")
        self.assertTrue(all(h == "W" for h in seen[::2]))  # 각 회차의 첫 조회는 WMS 탭에서

    def test_backoff_interval_after_refresh_exhausted(self):
        # 새로고침 3번으로도 안 되면 회차 간격을 늘린다 (reCAPTCHA 반복 시 계속 두드리지 않게)
        driver = FakeDriver()
        sleeps = []

        def fake_sleep(s):
            sleeps.append(s)
            if len(sleeps) >= 6:
                raise _Stop

        with mock.patch.object(m, "log"), \
             mock.patch.object(m, "_connect_driver", return_value=driver), \
             mock.patch.object(m, "run_download_macro", return_value=False), \
             mock.patch.object(m.os.path, "exists", return_value=True), \
             mock.patch.object(m, "RECON_INTERVAL_SEC", 10 ** 9), \
             mock.patch.object(m.time, "time", return_value=10 ** 6), \
             mock.patch.object(m.time, "sleep", side_effect=fake_sleep), \
             mock.patch.object(m.PageRefresher, "_wait_wms_ready", return_value=True):
            with self.assertRaises(_Stop):
                m.run_forever()
        self.assertEqual(len(driver.refreshes), m.REFRESH_MAX_CONSECUTIVE)
        self.assertEqual(sleeps[:3], [m.LOOP_INTERVAL_SEC] * 3)
        self.assertEqual(sleeps[3:], [m.EXHAUSTED_LOOP_INTERVAL_SEC] * 3)

    def test_failed_pass_ends_round_before_remaining_passes(self):
        # Codex 지적 2 / 사용자 방침: 조회 하나가 실패하면 남은 조회 없이 회차 종료 → 다음 회차 전 새로고침
        calls = []
        driver, logs = self.run_loop([False, True, True, True, True], n_rounds=2, calls=calls)
        self.assertEqual(len(calls), 3)  # 1회차: 첫 조회 실패로 1개만 / 2회차: 새로고침 후 2개
        self.assertEqual(driver.refreshes, ["W"])

    def test_recon_not_deferred_if_recon_passes_never_started(self):
        # 정상 조회에서 실패해 재확인 조회를 시작도 못 했으면, 다음 회차에 재확인을 다시 넣는다
        calls = []
        self.run_loop([False] + [True] * 10, n_rounds=2, recon=False, calls=calls, recon_first_only=True)
        recon_offsets = [c for c in calls if c[2] == m.RECON_START_OFFSET_DAYS]
        self.assertEqual(len(recon_offsets), 2)  # 2회차에 재확인(송장입력일·배송일) 실행됨

    def test_recon_not_deferred_if_last_recon_pass_never_started(self):
        # AX-20261017-01 Codex 지적: 3번째(송장입력일 재확인)가 실패해 4번째(배송일 재확인)를 못 돌았으면
        # 재확인 일정을 미루지 않고 다음 회차에 재확인 두 조회를 다시 넣는다
        calls = []
        # 1회차: 평소 2개 성공 → 재확인 1번째 실패(회차 종료) / 2회차: 4개 모두
        self.run_loop([True, True, False] + [True] * 10, n_rounds=2, calls=calls, recon_first_only=True)
        recon_calls = [c for c in calls if c[2] == m.RECON_START_OFFSET_DAYS]
        self.assertEqual(len(recon_calls), 3)  # 1회차 1개(실패) + 2회차 2개

    def test_exhausted_interval_env_validation(self):
        # 모듈 reload는 표준출력 래핑을 다시 해서 테스트 러너를 망가뜨리므로 계산 함수만 검증한다
        for raw, expected in (("abc", 600), ("-5", 600), ("0", 600), ("30", m.LOOP_INTERVAL_SEC), ("1200", 1200)):
            with mock.patch.dict(m.os.environ, {"UPH_EXHAUSTED_LOOP_INTERVAL_SEC": raw}):
                self.assertEqual(m._exhausted_loop_interval(), expected, raw)

    def test_dead_session_round_does_not_refresh(self):
        err = m.WebDriverException("no such window: target window already closed")
        driver, _ = self.run_loop([err, True, True, True, True], n_rounds=3)
        self.assertEqual(driver.refreshes, [])


class TitledDriver(FakeDriver):
    """창마다 제목이 다른 가짜 driver — W는 WMS, MGR*는 다운로드관리자."""

    TITLES = {"W": "확장주문검색2 이지어드민 V3.5+"}

    @property
    def title(self):
        return self.TITLES.get(self.current_window_handle, "다운로드관리자 이지어드민 V4.0+")

    @title.setter
    def title(self, _v):  # FakeDriver.__init__의 고정 제목 대입은 무시
        pass

    def close(self):
        # 닫기 시도 자체를 기록한다 — 호출자가 예외를 삼켜도 'W를 닫으려 했다'는 게 남도록
        self.close_attempts = getattr(self, "close_attempts", []) + [self.current_window_handle]
        super().close()


class WmsWindowSelection(unittest.TestCase):
    """2026-10-21: 시작 때 다운로드관리자 창에 붙어 로그인된 WMS 탭을 닫아버린 사고 재현."""

    def setUp(self):
        self.logs = []
        self.enterContext(mock.patch.object(m, "log", side_effect=self.logs.append))

    def test_select_skips_download_manager(self):
        d = TitledDriver(handles=("MGR", "W"), current="MGR")
        self.assertEqual(m._select_wms_window(d), "W")
        self.assertEqual(d.current_window_handle, "W")

    def test_select_returns_none_when_only_manager(self):
        d = TitledDriver(handles=("MGR",), current="MGR")
        self.assertIsNone(m._select_wms_window(d))
        self.assertEqual(d.current_window_handle, "MGR")
        self.assertTrue(any("WMS(이지어드민) 탭을 찾지 못했습니다" in s for s in self.logs))

    def test_select_ignores_unrelated_tab_and_refresh_keeps_wms(self):
        # Codex 검토 재현: 새 탭(OTHER)이 WMS보다 먼저 나열돼도 WMS를 고르고, 복구 새로고침이 WMS를 닫지 않는다
        class D(TitledDriver):
            TITLES = {"W": "확장주문검색2 이지어드민 V3.5+", "OTHER": "New Tab"}

        d = D(handles=("OTHER", "W", "MGR"), current="W")
        self.assertEqual(m._select_wms_window(d), "W")
        d2 = D(handles=("OTHER", "MGR", "W"), current="MGR")
        self.assertEqual(m._select_wms_window(d2), "W")
        r = m.PageRefresher(clock=Clock())
        r.record_round(False)
        with mock.patch.object(m.PageRefresher, "_wait_wms_ready", return_value=True):
            self.assertTrue(r.maybe_refresh(d2, "W"))
        self.assertEqual(d2.window_handles, ["W"])
        self.assertNotIn("W", getattr(d2, "close_attempts", []))
        self.assertEqual(d2.refreshes, ["W"])

    def test_select_accepts_post_login_home_title(self):
        # 로그인 직후 첫 화면 제목은 "이지WMS" (2026-10-21 실측)
        class D(TitledDriver):
            TITLES = {"H": "이지WMS", "OTHER": "New Tab"}

        d = D(handles=("OTHER", "MGR", "H"), current="MGR")
        self.assertEqual(m._select_wms_window(d), "H")

    def test_select_none_when_only_unrelated_tabs(self):
        class D(TitledDriver):
            TITLES = {"OTHER": "New Tab"}

        d = D(handles=("OTHER", "MGR"), current="OTHER")
        self.assertIsNone(m._select_wms_window(d))

    def test_stray_cleanup_never_closes_wms_even_if_focused_on_manager(self):
        d = TitledDriver(handles=("W", "MGR"), current="MGR")
        with mock.patch.object(m, "WebDriverWait") as wait:
            wait.return_value.until.side_effect = m.TimeoutException("none")
            with mock.patch.object(m.time, "sleep"):
                m.clear_stray_popups(d)
        self.assertIn("W", d.window_handles)
        self.assertNotIn("W", getattr(d, "close_attempts", []))  # WMS 탭은 닫으려 시도조차 하지 않는다

    def test_stray_cleanup_still_closes_leftover_manager(self):
        d = TitledDriver(handles=("W", "MGR"), current="W")
        with mock.patch.object(m, "WebDriverWait") as wait:
            wait.return_value.until.side_effect = m.TimeoutException("none")
            with mock.patch.object(m.time, "sleep"):
                m.clear_stray_popups(d)
        self.assertEqual(d.window_handles, ["W"])

    def test_run_forever_starts_on_wms_when_connected_to_manager(self):
        driver = TitledDriver(handles=("MGR", "W"), current="MGR")
        seen = []

        def fake_download(*_a):
            seen.append(driver.current_window_handle)
            return True

        with mock.patch.object(m, "_connect_driver", return_value=driver), \
             mock.patch.object(m, "run_download_macro", side_effect=fake_download), \
             mock.patch.object(m.os.path, "exists", return_value=True), \
             mock.patch.object(m, "RECON_INTERVAL_SEC", 10 ** 9), \
             mock.patch.object(m.time, "time", return_value=10 ** 6), \
             mock.patch.object(m.time, "sleep", side_effect=_Stop):
            with self.assertRaises(_Stop):
                m.run_forever()
        self.assertEqual(seen, ["W", "W"])

    def test_run_forever_picks_up_wms_tab_opened_later(self):
        # 시작 땐 WMS 탭이 없음 → 사람이 다시 열고 로그인 → 다음 회차가 그 탭을 찾아 쓴다
        driver = TitledDriver(handles=("MGR",), current="MGR")
        seen, sleeps = [], {"n": 0}

        def fake_download(*_a):
            seen.append(driver.current_window_handle)
            return driver.current_window_handle == "W"

        def fake_sleep(_s):
            sleeps["n"] += 1
            if sleeps["n"] == 1:
                driver.window_handles.append("W")  # 사람이 탭을 다시 엶
            else:
                raise _Stop

        with mock.patch.object(m, "_connect_driver", return_value=driver), \
             mock.patch.object(m, "run_download_macro", side_effect=fake_download), \
             mock.patch.object(m.os.path, "exists", return_value=True), \
             mock.patch.object(m, "RECON_INTERVAL_SEC", 10 ** 9), \
             mock.patch.object(m.time, "time", return_value=10 ** 6), \
             mock.patch.object(m.time, "sleep", side_effect=fake_sleep), \
             mock.patch.object(m.PageRefresher, "_wait_wms_ready", return_value=True):
            with self.assertRaises(_Stop):
                m.run_forever()
        self.assertEqual(seen[-2:], ["W", "W"])



class ForcePaintWait(unittest.TestCase):
    """가려진 창에서 팝업이 투명으로 굳는 경우: 대기 중 화면 캡처로 프레임을 그리게 한다."""

    def _run(self, visible_after_nudges, timeout):
        driver = mock.Mock()
        state = {"nudges": 0}
        driver.execute_cdp_cmd.side_effect = lambda *a, **k: state.__setitem__("nudges", state["nudges"] + 1)

        class FakeWait:
            def __init__(self, drv, t):
                self.t = t
            def until(self, cond):
                if state["nudges"] >= visible_after_nudges:
                    return "INPUT"
                clock[0] += self.t
                raise m.TimeoutException("hidden")

        clock = [0.0]
        with mock.patch.object(m, "WebDriverWait", FakeWait),              mock.patch.object(m.time, "time", side_effect=lambda: clock[0]):
            return driver, m.wait_visible_forcing_paint(driver, "#swal2-input", timeout=timeout, nudge_every=3)

    def test_nudge_makes_popup_visible(self):
        driver, el = self._run(visible_after_nudges=1, timeout=45)
        self.assertEqual(el, "INPUT")
        driver.execute_cdp_cmd.assert_called_with("Page.captureScreenshot", {"format": "jpeg", "quality": 10})

    def test_times_out_when_never_visible(self):
        with self.assertRaises(m.TimeoutException):
            self._run(visible_after_nudges=10**6, timeout=9)

if __name__ == "__main__":
    unittest.main()
