import unittest
from unittest.mock import patch
from click.testing import CliRunner
import sqlite3
import hugomgmt.main
import datetime
import tempfile
from pathlib import Path


class TestIsso(unittest.TestCase):
    pk = "integer PRIMARY KEY AUTOINCREMENT"
    isso_schema = {
        "preferences": {
            "key": "varchar primary key",
            "value": "varchar"
        },
        "threads": {
            "id": pk,
            "uri": "varchar(256) unique",
            "title": "varchar(256)",
        },
        "comments": {
            "tid": "references threads(id)",
            "id": pk,
            "parent": "integer",
            "created": "float",
            "modified": "float",
            "mode": "integer",
            "remote_addr": "varchar",
            "text": "varchar",
            "author": "varchar",
            "email": "varchar",
            "website": "varchar",
            "likes": "integer",
            "dislikes": "integer",
            "voters": "blob",
            "notification": "integer",
        },
    }
    isso_initdata = {}

    def setUp(self):
        hugomgmt.main.reg_cli()
        self.cli = hugomgmt.main.cli
        self.dbfile = tempfile.NamedTemporaryFile()
        conn = sqlite3.connect(self.dbfile.name)
        cur = conn.cursor()
        for tblname, schema in self.isso_schema.items():
            columns = []
            for k, t in schema.items():
                columns.append(f"{k} {t}")
            columns_str = ", ".join(columns)
            cur.execute(f"create table {tblname} ({columns_str});")
            cur.fetchall()
        for tblname, data in self.isso_initdata.items():
            for kv in data:
                keys = ",".join(kv.keys())
                args = tuple(kv.values())
                qs = ",".join(["?"] * len(args))
                q = f"INSERT INTO {tblname} ({keys}) VALUES ({qs})"
                cur.execute(q, args)
                cur.fetchall()

    def tearDown(self):
        self.dbfile.close()
        del self.cli
        del self.dbfile

    def test_initdb(self):
        with tempfile.NamedTemporaryFile() as tf:
            Path(tf.name).unlink()
            res = CliRunner().invoke(self.cli, ["isso-initdb", "--sqlite", tf.name])
            if res.exception:
                raise res.exception
            self.assertEqual(0, res.exit_code)
            self.assertTrue(Path(tf.name).exists())

    def test_initdb_overwrite(self):
        res = CliRunner().invoke(self.cli, ["isso-initdb", "--sqlite", self.dbfile.name])
        if res.exception:
            raise res.exception
        self.assertEqual(0, res.exit_code)

    def test_list_comment(self):
        res = CliRunner().invoke(self.cli, ["isso-list-comment", "--sqlite", self.dbfile.name])
        if res.exception:
            raise res.exception
        self.assertEqual(0, res.exit_code)

    def test_mail_comment(self):
        res = CliRunner().invoke(self.cli, ["isso-mail-comment", "--sqlite", self.dbfile.name, "--dry"])
        if res.exception:
            raise res.exception
        self.assertEqual(0, res.exit_code)
