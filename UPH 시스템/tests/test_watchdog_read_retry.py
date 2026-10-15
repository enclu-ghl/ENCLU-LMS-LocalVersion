# -*- coding: utf-8 -*-
"""watchdog 읽기 실패 재시도 검증 (AX-20261015-04, 감사 F6).

실제 main() 폴링 루프와 실제 process_file()을 돌린다. DB 연결·매핑·SKU 집계·대기만 가짜로 바꾸고,
감시 폴더·캐시·로그는 임시 폴더를 쓴다(운영 폴더·DB 미사용). 파일 내용 읽기(read_wms_file)는
실패/성공을 주입하고, 병합 결과는 비워서 "변경 없음" 경로로 끝낸다.

실행 (저장소 루트에서): py -m unittest discover -s "UPH 시스템/tests" -v
"""
import logging
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

_TMP = tempfile.mkdtemp(prefix="uph_f6_")
WATCH = os.path.join(_TMP, "watch")
os.makedirs(WATCH)
os.environ.update({
    "UPH_WATCH_FOLDER": WATCH,
    "UPH_CACHE_DB": os.path.join(_TMP, "cache.sqlite3"),
    "UPH_LOG_FILE": os.path.join(_TMP, "agent.log"),
    "UPH_READ_RETRY_MAX": "3",
})
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import watchdog_agent as wa  # noqa: E402

assert wa.WATCH_FOLDER == WATCH, "테스트가 운영 감시 폴더를 쓰면 안 된다"


class _StopLoop(Exception):
    pass


def make_files(names, start_age=1000):
    """오래된 순서대로 mtime을 매겨 파일을 만든다 (names[0]이 가장 오래됨)."""
    now = time.time()
    paths = []
    for i, n in enumerate(names):
        p = os.path.join(WATCH, n)
        with open(p, "w") as f:
            f.write("x")
        t = now - start_age + i
        os.utime(p, (t, t))
        paths.append(p)
    return paths


class WatchdogReadRetry(unittest.TestCase):
    def setUp(self):
        for f in os.listdir(WATCH):
            os.remove(os.path.join(WATCH, f))
        self.reads = []    # 읽기 시도한 파일 이름 순서
        self.applied = []  # 읽기에 성공해 반영 단계(병합)까지 간 파일 순서

    def run_polls(self, n_polls, read_plan, settled=lambda p: True, merge=None):
        """read_plan: {파일이름: [예외 또는 None, ...]} — 시도 순서대로 꺼내 쓰고, 다 쓰면 마지막 값을 반복."""
        polls = {"n": 0}

        def fake_read(path):
            name = os.path.basename(path)
            self.reads.append(name)
            plan = read_plan.get(name, [None])
            outcome = plan[min(self.reads.count(name) - 1, len(plan) - 1)]
            if outcome is not None:
                raise outcome
            return [name]  # 병합(반영) 순서 기록용 — process_file은 len()만 쓴다

        def fake_sleep(_sec):
            polls["n"] += 1
            if polls["n"] >= n_polls:
                raise KeyboardInterrupt  # main()이 정상 종료 경로로 빠져나감

        with mock.patch.object(wa, "get_engine"), \
             mock.patch.object(wa, "DongMappingCache"), \
             mock.patch.object(wa, "build_sku_daily_shipment", return_value=0), \
             mock.patch.object(wa, "read_wms_file", side_effect=fake_read), \
             mock.patch.object(wa, "merge_duplicate_rows", side_effect=merge or self._record_merge), \
             mock.patch.object(wa, "is_file_settled", side_effect=settled), \
             mock.patch.object(wa.time, "sleep", side_effect=fake_sleep), \
             self.assertLogs("uph_agent", level="INFO") as logs:
            wa.main()
        return logs.output

    def _record_merge(self, df, dong_cache):
        self.applied.append(df[0])
        return {}

    def test_transient_failure_retried_next_poll(self):
        make_files(["a.xls"])
        out = self.run_polls(4, {"a.xls": [PermissionError("locked"), None]})
        self.assertEqual(self.reads, ["a.xls", "a.xls"])  # 2번째 폴링에 성공, 이후 다시 안 읽음
        self.assertTrue(any("1/3회" in m for m in out))
        self.assertFalse(any("재시도 중단" in m for m in out))

    def test_permanent_failure_stops_after_max(self):
        make_files(["bad.xls"])
        out = self.run_polls(6, {"bad.xls": [ValueError("corrupt")]})
        self.assertEqual(self.reads, ["bad.xls"] * 3)  # 3회에서 멈추고 4~6번째 폴링엔 안 읽음
        stops = [m for m in out if "재시도 중단" in m]
        self.assertEqual(len(stops), 1)
        self.assertTrue(stops[0].startswith("ERROR"))

    def test_newer_file_waits_for_older_retry(self):
        # Codex 검토 지적(높음): 새 파일을 먼저 반영한 뒤 옛 파일을 재시도하면 같은 주문이 과거 값으로 되돌아간다.
        # → 옛 파일 읽기가 실패하면 그 폴링에서는 새 파일을 처리하지 않고, 반영은 항상 오래된 순서.
        make_files(["old.xls", "new.xls"])
        self.run_polls(3, {"old.xls": [OSError("partial"), None]})
        self.assertEqual(self.reads, ["old.xls", "old.xls", "new.xls"])  # 1폴링: old 실패 후 멈춤 / 2폴링: old→new
        self.assertEqual(self.applied, ["old.xls", "new.xls"])

    def test_retrying_file_turning_unsettled_still_blocks_newer(self):
        # Codex 2차 검토 지적(높음): 재시도 대기 파일이 다음 폴링에 '미안정'이면 건너뛰고 새 파일을 먼저 반영했다.
        settle_calls = {"old.xls": 0}

        def settled(path):
            name = os.path.basename(path)
            if name == "old.xls":
                settle_calls[name] += 1
                return settle_calls[name] != 2  # 2번째 폴링에서만 old가 미안정
            return True

        make_files(["old.xls", "new.xls"])
        self.run_polls(4, {"old.xls": [OSError("partial"), None]}, settled=settled)
        self.assertEqual(self.applied, ["old.xls", "new.xls"])  # 반영 순서가 뒤집히지 않음

    def test_newer_file_processed_after_give_up(self):
        make_files(["old.xls", "new.xls"])
        self.run_polls(4, {"old.xls": [OSError("corrupt")]})
        self.assertEqual(self.reads, ["old.xls"] * 3 + ["new.xls"])  # 3회 포기 후 같은 폴링에서 new 진행
        self.assertEqual(self.applied, ["new.xls"])

    def test_cleanup_keeps_retrying_file(self):
        # f0은 처리되고 f1에서 읽기 실패 → 정리 대상(보존 5개 밖)은 f0·f1이지만 f1은 재시도 대기라 남는다
        names = [f"f{i}.xls" for i in range(7)]
        make_files(names)
        self.run_polls(1, {"f1.xls": [OSError("locked")]})
        left = set(os.listdir(WATCH))
        self.assertNotIn("f0.xls", left)   # 처리 끝난 오래된 파일은 정리
        self.assertIn("f1.xls", left)      # 오래됐지만 재시도 대기라 보존
        self.assertEqual(left, set(names[1:]))

    def test_cleanup_releases_after_success(self):
        names = [f"g{i}.xls" for i in range(7)]
        make_files(names)
        self.run_polls(3, {"g1.xls": [OSError("locked"), None]})
        left = set(os.listdir(WATCH))
        self.assertNotIn("g1.xls", left)   # 성공 후엔 일반 규칙대로 정리
        self.assertEqual(left, set(names[2:]))

    def test_unsettled_file_not_read_nor_deleted(self):
        names = [f"u{i}.xls" for i in range(7)]
        make_files(names)
        self.run_polls(2, {}, settled=lambda p: os.path.basename(p) != "u0.xls")
        self.assertNotIn("u0.xls", self.reads)
        self.assertIn("u0.xls", os.listdir(WATCH))

    def test_error_after_read_keeps_existing_behavior(self):
        make_files(["m.xls"])

        def boom(df, dc):
            raise RuntimeError("merge failed")

        out = self.run_polls(5, {}, merge=boom)
        self.assertEqual(self.reads, ["m.xls"] * 5)  # 기존처럼 매 폴링 재시도 — 읽기 실패 한도에 안 들어감
        self.assertFalse(any("재시도 중단" in m or "/3회" in m for m in out))


class ProcessFileReturn(unittest.TestCase):
    def setUp(self):
        self.cache = wa.init_cache_db()
        tables = [r[0] for r in self.cache.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        for name in tables:  # 테스트끼리 같은 임시 캐시 파일을 쓰므로 매번 비운다
            self.cache.execute(f'DELETE FROM "{name}"')
        self.cache.commit()

    def tearDown(self):
        self.cache.close()

    def test_read_failure_returns_false(self):
        with mock.patch.object(wa, "read_wms_file", side_effect=OSError("x")), \
             self.assertLogs("uph_agent", level="ERROR"):
            self.assertIs(wa.process_file("x.xls", None, self.cache, None), False)

    def test_no_change_returns_true(self):
        with mock.patch.object(wa, "read_wms_file", return_value=[]), \
             mock.patch.object(wa, "merge_duplicate_rows", return_value={}):
            self.assertIs(wa.process_file("x.xls", None, self.cache, None), True)

    def _push(self, n_ok):
        entry = {"cs_status": "정상", "is_hold": False, "quantity": 1, "channel_name": "c", "dong": "A동"}
        merged = {(k, "배송"): dict(entry, order_key=k, status="배송") for k in ("k1", "k2")}
        with mock.patch.object(wa, "read_wms_file", return_value=[]), \
             mock.patch.object(wa, "merge_duplicate_rows", return_value=merged), \
             mock.patch.object(wa, "push_to_db", side_effect=lambda e, rows: rows[:n_ok]), \
             self.assertLogs("uph_agent", level="INFO") as logs:
            result = wa.process_file("x.xls", None, self.cache, None)
        return result, logs.output, set(wa.load_cache_dict(self.cache))

    def test_db_partial_failure_returns_true_and_caches_only_success(self):
        result, out, cached = self._push(1)
        self.assertIs(result, True)  # 읽기 재시도 대상 아님
        self.assertTrue(any("DB 반영 일부 실패" in m for m in out))  # 기존 경고 그대로
        self.assertEqual(cached, {("k1", "배송")})                    # 실패한 k2는 캐시에 안 들어감 → 다음에 재시도

    def test_db_total_failure_returns_true_and_caches_nothing(self):
        result, out, cached = self._push(0)
        self.assertIs(result, True)
        self.assertEqual(cached, set())

if __name__ == "__main__":
    unittest.main()
