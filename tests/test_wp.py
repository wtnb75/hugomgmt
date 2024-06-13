import unittest
from unittest.mock import patch
from pathlib import Path
import tempfile
from click.testing import CliRunner
import subprocess
import sqlite3
import hugomgmt.main


class sqlite2mysql_cur:
    def __init__(self, cur: sqlite3.Cursor):
        self.cur = cur

    def execute(self, q: str, qargs=()):
        # (py)format to qmark
        nq = q.replace("%s", "?")
        return self.cur.execute(nq, qargs)

    def __getattr__(self, name):
        # other members
        return getattr(self.cur, name)


class sqlite3mysql_conn:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def cursor(self):
        return sqlite2mysql_cur(self.conn.cursor())

    def ping(self, **kwargs):
        # dummy ping
        pass

    def __getattr__(self, name):
        # other members
        return getattr(self.conn, name)


class TestWordpress(unittest.TestCase):
    pk = "integer PRIMARY KEY AUTOINCREMENT"
    wp_schema = {
        "wp_options": {
            "option_id": pk,
            "option_name": "varchar(191)",
            "option_value": "longtext",
        },
        "wp_terms": {
            "term_id": pk,
            "name": "varchar(200)",
            "slug": "varchar(200)",
            "term_group": "integer",
        },
        "wp_term_taxonomy": {
            "term_taxonomy_id": pk,
            "term_id": "integer",
            "taxonomy": "varchar(30)",
            "description": "longtext",
            "parent": "integer",
            "count": "integer",
        },
        "wp_comments": {
            "comment_ID": pk,
            "comment_post_ID": "integer",
            "comment_author": "text",
            "comment_author_email": "varchar(100)",
            "comment_author_url": "varchar(200)",
            "comment_author_IP": "varchar(100)",
            "comment_date": "datetime",
            "comment_date_gmt": "datetime",
            "comment_content": "text",
            "comment_karma": "integer",
            "comment_approved": "varchar(20)",
            "comment_agent": "varchar(255)",
            "comment_type": "varchar(20)",
            "comment_parent": "integer",
            "user_id": "integer",
        }
    }
    wp_initdata = {
        "wp_options": [{"option_name": "permalink_structure", "option_value": r"/archives/%post_id%"}],
        "wp_terms": [{"name": "cat1", "slug": "slug1"}, {"name": "cat2", "slug": "slug2"},
                     {"name": "tag1", "slug": "slug3"}],
        "wp_term_taxonomy": [{"term_id": 1, "taxonomy": "category"}, {"term_id": 2, "taxonomy": "category"},
                             {"term_id": 3, "taxonomy": "post_tag"},],
        "wp_comments": [{"comment_post_ID": 1, "comment_approved": "1"},
                        {"comment_post_ID": 2, "comment_approved": "0"},],
    }

    def setUp(self):
        hugomgmt.main.reg_cli()
        self.cli = hugomgmt.main.cli
        self.p = patch("mysql.connector.connect")
        self.pconn = self.p.__enter__()
        self.conn = sqlite3mysql_conn(sqlite3.connect(":memory:"))
        self.pconn.return_value = self.conn
        cur = self.conn.cursor()
        for tblname, schema in self.wp_schema.items():
            columns = []
            for k, t in schema.items():
                columns.append(f"{k} {t}")
            columns_str = ", ".join(columns)
            cur.execute(f"create table {tblname} ({columns_str});")
            cur.fetchall()
        for tblname, data in self.wp_initdata.items():
            for kv in data:
                keys = ",".join(kv.keys())
                args = tuple(kv.values())
                qs = ",".join(["?"] * len(args))
                q = f"INSERT INTO {tblname} ({keys}) VALUES ({qs})"
                cur.execute(q, args)

    def tearDown(self):
        self.p.__exit__(None, None, None)
        self.conn.close()
        del self.pconn
        del self.conn
        del self.cli
        del self.p

    def test_help(self):
        res = CliRunner().invoke(self.cli, [])
        if res.exception:
            raise res.exception
        self.assertEqual(0, res.exit_code)
        self.assertIn("wp-check-db", res.output)
        self.assertIn("wp-comment-ids", res.output)
        self.assertIn("wp-convpost1", res.output)
        self.assertIn("wp-convcomment1", res.output)
        self.assertIn("wp-convpost-all", res.output)
        self.assertIn("wp-convcomment-all", res.output)

    def test_check_db(self):
        res = CliRunner().invoke(self.cli, ["wp-check-db"])
        if res.exception:
            raise res.exception
        self.assertEqual(0, res.exit_code)
        self.assertIn(r"/archives/%post_id%", res.output)
        self.assertIn("cat1", res.output)
        self.assertNotIn("tag1", res.output)

    def test_comment_ids(self):
        res = CliRunner().invoke(self.cli, ["wp-comment-ids"])
        if res.exception:
            raise res.exception
        self.assertEqual(0, res.exit_code)
        self.assertIn("1", res.output)
        self.assertNotIn("2", res.output)   # not approved
