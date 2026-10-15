# -*- coding: utf-8 -*-
"""verify_migration.py 검증 (AX-20261014-05, 감사 F1: 불일치인데 종료코드 0).

실제 DB 없이 SQLite 파일로 원본/대상을 흉내 낸다. 원본 쪽에는 pg_tables(schemaname, tablename)
테이블을 만들어 PostgreSQL 카탈로그 조회를 대신한다.

실행 (저장소 루트에서): py -m unittest discover -s _local_db/tests -v
"""
import contextlib
import io
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from sqlalchemy import create_engine

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import verify_migration as vm  # noqa: E402


def make_db(path, tables, catalog=False):
    """tables: {이름: 행수}. catalog=True면 pg_tables 카탈로그도 만든다."""
    con = sqlite3.connect(path)
    for name, n in tables.items():
        con.execute(f'CREATE TABLE "{name}" (id INTEGER)')
        con.executemany(f'INSERT INTO "{name}" VALUES (?)', [(i,) for i in range(n)])
    if catalog:
        con.execute("CREATE TABLE pg_tables (schemaname TEXT, tablename TEXT)")
        con.executemany("INSERT INTO pg_tables VALUES ('public', ?)", [(t,) for t in tables])
    con.commit()
    con.close()


class _Dbs:
    """임시 폴더에 원본(supabase_src.db)·대상(local_dst.db) SQLite 파일을 만든다."""

    def __init__(self, src_tables, dst_tables):
        self._tmp = tempfile.TemporaryDirectory()
        d = Path(self._tmp.name)
        self.src_path, self.dst_path = d / "supabase_src.db", d / "local_dst.db"
        make_db(self.src_path, src_tables, catalog=True)
        make_db(self.dst_path, dst_tables)
        self.src_url = f"sqlite:///{self.src_path.as_posix()}"
        self.dst_url = f"sqlite:///{self.dst_path.as_posix()}"
        self.engines = []

    def engine(self, url, **_ignored):  # create_engine 대체: PG 전용 connect_args 무시
        e = create_engine(url)
        self.engines.append(e)
        return e

    def close(self):
        for e in self.engines:
            e.dispose()  # Windows: 파일 잠금 해제 후 임시 폴더 삭제
        self._tmp.cleanup()


class Compare(unittest.TestCase):
    def check(self, src_tables, dst_tables):
        dbs = _Dbs(src_tables, dst_tables)
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                return vm.compare(dbs.engine(dbs.src_url), dbs.engine(dbs.dst_url))
        finally:
            dbs.close()

    def test_all_match(self):
        self.assertTrue(self.check({"a": 2, "b": 3}, {"a": 2, "b": 3}))

    def test_row_count_mismatch(self):
        self.assertFalse(self.check({"a": 2, "b": 3}, {"a": 1, "b": 3}))

    def test_missing_target_table(self):
        self.assertFalse(self.check({"a": 2, "b": 3}, {"a": 2}))


class MainExitCode(unittest.TestCase):
    def run_main(self, src_tables, dst_tables):
        dbs = _Dbs(src_tables, dst_tables)
        env = {"SUPABASE_URL": dbs.src_url, "LOCAL_DB_URL": dbs.dst_url}
        try:
            with mock.patch.dict(os.environ, env), \
                 mock.patch.object(vm, "create_engine", dbs.engine), \
                 mock.patch.object(vm, "load_dotenv"), \
                 mock.patch.object(vm.io, "TextIOWrapper", lambda *a, **k: io.StringIO()), \
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


if __name__ == "__main__":
    unittest.main()
