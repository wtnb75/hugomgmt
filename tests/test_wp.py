import unittest
from unittest.mock import patch
from click.testing import CliRunner
import sqlite3
import hugomgmt.main
import datetime
import tempfile
from pathlib import Path


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
        },
        "wp_posts": {
            "ID": pk,
            "post_author": "integer",
            "post_date": "datetime",
            "post_date_gmt": "datetime",
            "post_content": "longtext",
            "post_title": "text",
            "post_excerpt": "text",
            "post_status": "varchar(20)",
            "comment_status": "varchar(20)",
            "ping_status": "varchar(20)",
            "post_password": "varchar(255)",
            "post_name": "varchar(200)",
            "to_ping": "text",
            "pinged": "text",
            "post_modified": "datetime",
            "post_modified_gmt": "datetime",
            "guid": "varchar(255)",
            "post_type": "varchar(20)",
            "post_mime_type": "varchar(200)",
            "comment_count": "integer",
        },
        "wp_term_relationships": {
            "object_id": "integer",
            "term_taxonomy_id": "integer",
            "term_order": "integer",
        },
        "wp_users": {
            "ID": pk,
            "user_login": "varchar(60)",
            "user_pass": "varchar(255)",
            "user_nicename": "varchar(50)",
            "user_email": "varchar(100)",
            "user_url": "varchar(100)",
            "user_registered": "datetime",
            "user_activation_key": "varchar(255)",
            "user_status": "integer",
            "display_name": "varchar(250)",
        },
    }
    wp_initdata = {
        "wp_options": [{
            "option_name": "permalink_structure", "option_value": r"/archives/%post_id%"
        }, {
            "option_name": "posts_per_rss", "option_value": "20",
        }, {
            "option_name": "blogname", "option_value": "name123",
        }, {
            "option_name": "blogdescription", "option_value": "descr123",
        }, {
            "option_name": "siteurl", "option_value": "http://example.com/wordpress/",
        }],
        "wp_terms": [{"name": "cat1", "slug": "slug1"}, {"name": "cat2", "slug": "slug2"},
                     {"name": "tag1", "slug": "slug3"}],
        "wp_term_taxonomy": [{"term_id": 1, "taxonomy": "category"}, {"term_id": 2, "taxonomy": "category"},
                             {"term_id": 3, "taxonomy": "post_tag"},],
        "wp_comments": [{"comment_post_ID": 1, "comment_approved": "1"},
                        {"comment_post_ID": 2, "comment_approved": "0"},],
        "wp_posts": [{
            "post_type": "post",
            "post_date": datetime.datetime(2000, 1, 2, 3, 4, 5),
            "post_title": "hello world",
            "post_content": "<p>foo bar baz</p><p>xyz</p>",
            "post_status": "publish",
            "post_name": "hello",
            "post_author": 1,
        }, {
            "post_type": "post",
            "post_date": datetime.datetime(2001, 2, 3, 4, 5, 6),
            "post_title": "draft",
            "post_content": "<p>this is draft.</p>",
            "post_status": "draft",
            "post_name": "dont-read",
            "post_author": 1,
        }, {
            "post_type": "page",
            "post_date": datetime.datetime(2002, 3, 4, 5, 6, 7),
            "post_title": "hello page",
            "post_content": "<p>this is page</p><p>abcdefg</p>",
            "post_status": "publish",
            "post_name": "page-test",
            "post_author": 1,
        },],
        "wp_users": [{
            "display_name": "user123",
            "user_email": "mail123@example.com",
        }, {
            "display_name": "user234",
            "user_email": "mail234@example.com",
        }],
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

    def test_convpost1_notfound(self):
        res = CliRunner().invoke(self.cli, ["wp-convpost1", "99"])
        self.assertIsNotNone(res.exception)
        self.assertIn("post 99 not found", res.output)

    def test_convpost1(self):
        res = CliRunner().invoke(self.cli, ["wp-convpost1", "1"])
        if res.exception:
            raise res.exception
        self.assertEqual(0, res.exit_code)
        self.assertIn("title: hello world", res.output)
        self.assertIn("\nfoo bar baz\n", res.output)

    def test_list_post(self):
        res = CliRunner().invoke(self.cli, ["wp-list-post"])
        if res.exception:
            raise res.exception
        self.assertEqual(0, res.exit_code)
        self.assertIn("posts:\n", res.output)
        self.assertIn("2000-01-02T03:04:05", res.output)
        self.assertIn("\npages:\n", res.output)

    def test_redirect(self):
        res = CliRunner().invoke(self.cli, [
            "wp-get-redirect", "--baseurl", "http://example.com/wordpress/",
            "--hugopath", "/hugopath/"])
        if res.exception:
            raise res.exception
        self.assertEqual(0, res.exit_code)
        self.assertIn(r"rewrite ^/wordpress/feed/$ /hugopath/index.xml permanent;", res.output)
        self.assertIn(r"rewrite ^/wordpress/category/slug1(/.*)?$ /hugopath/categories/cat1/ permanent;", res.output)
        self.assertIn(r"rewrite ^/wordpress/category/slug2(/.*)?$ /hugopath/categories/cat2/ permanent;", res.output)

    def test_inithugo(self):
        with tempfile.TemporaryDirectory() as td:
            res = CliRunner().invoke(self.cli, ["wp-init-hugo", "--output", td])
            if res.exception:
                raise res.exception
            self.assertEqual(0, res.exit_code)
            conffile = Path(td) / "hugo.toml"
            self.assertTrue(conffile.exists())
            confstr = conffile.read_text()
            self.assertIn("example.com", confstr)
            self.assertIn("name123", confstr)
            self.assertIn("descr123", confstr)
