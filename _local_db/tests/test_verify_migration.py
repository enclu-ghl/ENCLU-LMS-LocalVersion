# -*- coding: utf-8 -*-
"""verify_migration.py 검증 (AX-20261014-05 F1 종료코드, AX-20261015-05 F2 테이블·컬럼·증가 규칙).

실제 DB 없이 SQLite 파일로 원본/대상을 흉내 낸다.
- 각 DB에 pg_tables(schemaname, tablename) 테이블을 만들어 PostgreSQL 카탈로그 조회를 대신한다.
- information_schema.columns는 별도 SQLite 파일을 연결 시마다 ATTACH해 흉내 낸다.

실행 (저장소 루트에서): py -m unittest discover -s _local_db/tests -v
"""
import contextlib
import io
import os
import re
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from sqlalchemy import create_engine, event

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import verify_migration as vm  # noqa: E402


def make_db(path, tables):
    """tables: {이름: (행, 컬럼)} — 행은 개수(int, id 0..n-1) 또는 id 리스트, 컬럼은 {이름: data_type}.
    값이 int나 list만이면 컬럼은 {"id": "integer"}."""
    con = sqlite3.connect(path)
    is_con = sqlite3.connect(str(path) + ".is")
    con.execute("CREATE TABLE pg_tables (schemaname TEXT, tablename TEXT)")
    is_con.execute("CREATE TABLE columns (table_schema TEXT, table_name TEXT, column_name TEXT,"
                   " data_type TEXT, ordinal_position INTEGER)")
    for name, spec in tables.items():
        rows, cols = spec if isinstance(spec, tuple) else (spec, {"id": "integer"})
        ids = list(range(rows)) if isinstance(rows, int) else list(rows)
        con.execute(f'CREATE TABLE "{name}" ({", ".join(f"{c} {t}" for c, t in cols.items())})')
        first = next(iter(cols))
        con.executemany(f'INSERT INTO "{name}" ({first}) VALUES (?)', [(i,) for i in ids])
        con.execute("INSERT INTO pg_tables VALUES ('public', ?)", (name,))
        is_con.executemany("INSERT INTO columns VALUES ('public', ?, ?, ?, ?)",
                           [(name, c, t, i) for i, (c, t) in enumerate(cols.items(), 1)])
    for c in (con, is_con):
        c.commit()
        c.close()


class _Dbs:
    """임시 폴더에 원본(supabase_src.db)·대상(local_dst.db)을 만든다."""

    def __init__(self, src_tables, dst_tables):
        self._tmp = tempfile.TemporaryDirectory()
        d = Path(self._tmp.name)
        self.src_path, self.dst_path = d / "supabase_src.db", d / "local_dst.db"
        make_db(self.src_path, src_tables)
        make_db(self.dst_path, dst_tables)
        self.src_url = f"sqlite:///{self.src_path.as_posix()}"
        self.dst_url = f"sqlite:///{self.dst_path.as_posix()}"
        self.engines = []

    def engine(self, url, **_ignored):  # create_engine 대체: PG 전용 connect_args 무시 + information_schema ATTACH
        e = create_engine(url)
        is_file = url[len("sqlite:///"):] + ".is"

        @event.listens_for(e, "connect")
        def _attach(dbapi_con, _rec):
            dbapi_con.execute(f"ATTACH DATABASE '{is_file}' AS information_schema")

        self.engines.append(e)
        return e

    def close(self):
        for e in self.engines:
            e.dispose()  # Windows: 파일 잠금 해제 후 임시 폴더 삭제
        self._tmp.cleanup()


class Compare(unittest.TestCase):
    def check(self, src_tables, dst_tables, strict=False):
        dbs = _Dbs(src_tables, dst_tables)
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                ok = vm.compare(dbs.engine(dbs.src_url), dbs.engine(dbs.dst_url), strict=strict)
            self.output = buf.getvalue()
            return ok
        finally:
            dbs.close()

    # ── F1 기존 ──
    def test_all_match(self):
        self.assertTrue(self.check({"a": 2, "b": 3}, {"a": 2, "b": 3}))

    def test_row_count_mismatch(self):
        self.assertFalse(self.check({"a": 2, "b": 3}, {"a": 1, "b": 3}))
        self.assertIn("부족", self.output)

    def test_missing_target_table(self):
        self.assertFalse(self.check({"a": 2, "b": 3}, {"a": 2}))
        self.assertIn("로컬에 테이블 없음", self.output)

    # ── F2 ──
    def test_target_only_table_is_info(self):
        self.assertTrue(self.check({"a": 2}, {"a": 2, "new_tbl": 5}))
        self.assertIn("로컬에만 있는 테이블", self.output)

    def test_column_mismatch_fails(self):
        src = {"a": (2, {"id": "integer", "name": "text"})}
        dst = {"a": (2, {"id": "integer", "name": "integer"})}
        self.assertFalse(self.check(src, dst))
        self.assertIn("컬럼 구성 다름", self.output)

    def test_growth_with_id_range_covered_is_info(self):
        # 전환 후 로컬에서 쌓인 행(id 3~5): 원본 범위 0~2는 모두 있음 → 정보
        self.assertTrue(self.check({"log": 3}, {"log": [0, 1, 2, 3, 4, 5]}))
        self.assertIn("증가", self.output)

    def test_growth_but_rows_missing_in_source_range_fails(self):
        # 로컬 행수는 많지만 원본 id 1이 빠짐 (0,2 + 새 행 10,11,12)
        self.assertFalse(self.check({"log": [0, 1, 2]}, {"log": [0, 2, 10, 11, 12]}))
        self.assertIn("원본 id 범위 안의 로컬 행이 1건 부족", self.output)

    def test_growth_without_id_info_by_default_fails_when_strict(self):
        spec_src = {"t": (2, {"code": "text"})}
        spec_dst = {"t": (4, {"code": "text"})}
        self.assertTrue(self.check(spec_src, spec_dst))
        self.assertIn("확인 못 함", self.output)
        self.assertFalse(self.check(spec_src, spec_dst, strict=True))

    def test_empty_source_with_growth_is_info(self):
        self.assertTrue(self.check({"log": 0}, {"log": 3}))

    # ── 대체 검토(devops-review) 지적 반영 ──
    def test_equal_count_but_missing_in_range_fails(self):
        # 지적 1: 원본 1건 누락 + 로컬 신규 1건 → 행수는 같지만 실패해야 함
        self.assertFalse(self.check({"log": [0, 1, 2]}, {"log": [0, 2, 10]}))
        self.assertIn("원본 id 범위 안의 로컬 행이 1건 부족", self.output)

    def test_growth_wording_is_approximate(self):
        # 지적 2: 범위 확인은 근사 — 단정적 문구 대신 "근사 확인"과 비교 범위 밖 안내
        self.check({"log": 3}, {"log": [0, 1, 2, 3]})
        self.assertIn("근사 확인", self.output)
        self.assertIn("비교하지 않는 것", self.output)

    def _check_with_failure(self, which):
        real = vm.count_rows

        def flaky(conn, table):
            if which in str(conn.engine.url):
                raise RuntimeError("boom")
            return real(conn, table)

        with mock.patch.object(vm, "count_rows", side_effect=flaky):
            return self.check({"a": 2}, {"a": 2})

    def test_source_query_failure_counts_as_failure(self):
        # 지적 3·6: 조회 실패 경로와 원본/로컬 구분
        self.assertFalse(self._check_with_failure("supabase_src"))
        self.assertIn("Supabase 조회 실패", self.output)

    def test_target_query_failure_counts_as_failure(self):
        self.assertFalse(self._check_with_failure("local_dst"))
        self.assertIn("로컬 조회 실패", self.output)

    def test_source_receives_only_light_queries(self):
        # 지적 3: 원본에는 카탈로그·COUNT(*)·MIN/MAX(id)만 — 범위 COUNT 등은 로컬에서만
        allowed = re.compile(
            r"^\s*SELECT (tablename FROM pg_tables|column_name, data_type FROM information_schema\.columns"
            r"|COUNT\(\*\) FROM \"[^\"]+\"\s*$|MIN\(id\), MAX\(id\) FROM \"[^\"]+\"\s*$)", re.S)
        seen = []
        cases = [({"log": 3, "t": (2, {"code": "text"})}, {"log": [0, 1, 2, 3, 4], "t": (3, {"code": "text"})}),
                 ({"log": [0, 1, 2]}, {"log": [0, 2, 10]})]
        for src_tables, dst_tables in cases:
            dbs = _Dbs(src_tables, dst_tables)
            try:
                src = dbs.engine(dbs.src_url)
                event.listen(src, "before_cursor_execute",
                             lambda conn, cur, stmt, params, ctx, many: seen.append(stmt))
                with contextlib.redirect_stdout(io.StringIO()):
                    vm.compare(src, dbs.engine(dbs.dst_url))
            finally:
                dbs.close()
        self.assertTrue(any("MIN(id), MAX(id)" in s for s in seen))  # 증가 경로가 실제로 실행됐는지
        bad = [s for s in seen if not allowed.match(s)]
        self.assertEqual(bad, [])


class MainExitCode(unittest.TestCase):
    def run_main(self, src_tables, dst_tables, argv=()):
        dbs = _Dbs(src_tables, dst_tables)
        env = {"SUPABASE_URL": dbs.src_url, "LOCAL_DB_URL": dbs.dst_url}
        try:
            with mock.patch.dict(os.environ, env), \
                 mock.patch.object(vm, "create_engine", dbs.engine), \
                 mock.patch.object(vm, "load_dotenv"), \
                 mock.patch.object(vm.io, "TextIOWrapper", lambda *a, **k: io.StringIO()), \
                 mock.patch.object(sys, "argv", ["verify_migration.py", *argv]), \
                 mock.patch.object(sys, "stdout", sys.stdout):
                with self.assertRaises(SystemExit) as cm:
                    vm.main()
            return cm.exception.code
        finally:
            dbs.close()

    def test_match_exits_0(self):
        self.assertEqual(self.run_main({"a": 2}, {"a": 2}), 0)

    def test_mismatch_exits_1(self):
        self.assertEqual(self.run_main({"a": 2}, {"a": 1}), 1)

    def test_strict_flag(self):
        src, dst = {"t": (1, {"code": "text"})}, {"t": (2, {"code": "text"})}
        self.assertEqual(self.run_main(src, dst), 0)
        self.assertEqual(self.run_main(src, dst, argv=["--strict"]), 1)


if __name__ == "__main__":
    unittest.main()
