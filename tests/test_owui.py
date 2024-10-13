import unittest
from pathlib import Path
import tempfile
import datetime
import subprocess
import tomllib
import json
from click.testing import CliRunner
import hugomgmt.main


class TestOWUI(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.tdpath = Path(self.td.name)
        hugomgmt.main.reg_cli()
        self.cli = hugomgmt.main.cli

    def tearDown(self):
        self.td.cleanup()
        del self.td
        del self.cli

    def _setup_dirs(self):
        (self.tdpath / "out").mkdir()
        (self.tdpath / "t1").mkdir()
        (self.tdpath / "t2").mkdir()
        subprocess.call(["git", "config", "--global", "user.name", "user 123"])
        subprocess.call(["git", "config", "--global", "user.email", "wtnb75@gmail.com"])
        subprocess.call(["git", "config", "--global", "init.defaultBranch", "main"])
        subprocess.call(["git", "init", self.tdpath / "t1"])
        subprocess.call(["git", "init", self.tdpath / "t2"])

    def test_help(self):
        res = CliRunner().invoke(self.cli)
        if res.exception:
            raise res.exception
        self.assertEqual(0, res.exit_code)
        self.assertIn("owui-json2md", res.output)
        self.assertIn("owui-init-hugo", res.output)
        self.assertIn("owui-json2md-history", res.output)

    def test_init_hugo(self):
        self._setup_dirs()
        res = CliRunner().invoke(self.cli, [
            "owui-init-hugo", "--output", self.tdpath / "out", "--url", "http://example.com/owui/",
            "--title", "example", "--theme", self.tdpath / "t1", "--notice-theme", self.tdpath / "t2"])
        if res.exception:
            raise res.exception
        self.assertEqual(0, res.exit_code)
        self.assertTrue((self.tdpath / "out" / "hugo.toml").exists())
        self.assertTrue((self.tdpath / "out" / "themes" / "t1").exists())
        self.assertTrue((self.tdpath / "out" / "themes" / "t2").exists())
        conf = tomllib.load((self.tdpath / "out" / "hugo.toml").open("rb"))
        self.assertEqual("http://example.com/owui/", conf.get("baseURL"))
        self.assertEqual("example", conf.get("title"))
        self.assertEqual({"t1", "t2"}, set(conf.get("theme")))

    def test_json2md_1(self):
        data = [{
            "id": "id1",
            "user_id": "user1",
            "title": "hello🍺🍖  \n",
            "updated_at": int(datetime.datetime(2024, 1, 1, 0).timestamp()),
            "created_at": int(datetime.datetime(2024, 1, 1, 0).timestamp()),
            "chat": {
                "id": "cid1",
                "title": "hello🍺🍖  \n",
                "models": ["model1:latest"],
                "params": {},
                "messages": [{
                    "id": "msg1",
                    "role": "user",
                    "content": "content 1",
                }, {
                    "id": "res1",
                    "role": "assistant",
                    "content": "response 1",
                }],
            },
        }]
        (self.tdpath / "out").mkdir()
        (self.tdpath / "md").mkdir()
        (self.tdpath / "md" / "2024-01").mkdir()
        (self.tdpath / "md" / "2024-01" / "2024-01-01-beer-mug.md").write_text("""
---
categories: [hello]
authors_add: [author2]
---
first memo
<!-- skip 2 -->
second memo
<!-- seek last -->
last memo
""")
        (self.tdpath / "input.json").write_text(json.dumps(data))
        res = CliRunner().invoke(self.cli, [
            "owui-json2md", "--output", self.tdpath / "out", "--metadir", self.tdpath / "md",
            str(self.tdpath / "input.json")])
        if res.exception:
            raise res.exception
        self.assertEqual(0, res.exit_code)
        self.assertTrue((self.tdpath / "out" / "2024-01" / "2024-01-01-beer-mug.md").exists())
        content_out = (self.tdpath / "out" / "2024-01" / "2024-01-01-beer-mug.md").read_text()
        self.assertIn("model1", content_out)
        self.assertIn("author2", content_out)
        self.assertIn("first memo", content_out)
        self.assertIn("content 1", content_out)
        self.assertIn("response 1", content_out)
        self.assertIn("last memo", content_out)
        self.assertIn("notice info", content_out)
        self.assertIn("notice tip", content_out)

    def test_json2md_2(self):
        data = [{
            "id": "id1",
            "user_id": "user1",
            "title": "hello🍺🍖  \n",
            "updated_at": int(datetime.datetime(2024, 1, 1, 0).timestamp()),
            "created_at": int(datetime.datetime(2024, 1, 1, 0).timestamp()),
            "chat": {
                "id": "cid1",
                "title": "hello🍺🍖  \n",
                "models": ["model1:latest", "prefix/model2:latest"],
                "params": {},
                "history": {
                    "messages": {
                        "uuid1": {
                            "id": "uuid1",
                            "childrenIds": ["uuid2"],
                            "role": "user",
                            "content": "content 1",
                        },
                        "uuid2": {
                            "id": "uuid2",
                            "parentId": "uuid1",
                            "role": "assistant",
                            "content": "response 1",
                        }
                    }
                },
            },
        }]
        (self.tdpath / "out").mkdir()
        (self.tdpath / "md").mkdir()
        (self.tdpath / "md" / "2024-01").mkdir()
        (self.tdpath / "md" / "2024-01" / "2024-01-01-beer-mug.md").write_text("""
---
categories: [hello]
authors_add: [author2]
---
first memo
<!-- skip 2 -->
second memo
<!-- seek last -->
last memo
""")
        (self.tdpath / "input.json").write_text(json.dumps(data))
        res = CliRunner().invoke(self.cli, [
            "owui-json2md", "--output", self.tdpath / "out", "--metadir", self.tdpath / "md",
            str(self.tdpath / "input.json")])
        if res.exception:
            raise res.exception
        self.assertEqual(0, res.exit_code)
        self.assertTrue((self.tdpath / "out" / "2024-01" / "2024-01-01-beer-mug.md").exists())
        content_out = (self.tdpath / "out" / "2024-01" / "2024-01-01-beer-mug.md").read_text()
        self.assertIn("model1", content_out)
        self.assertIn("model2", content_out)
        self.assertNotIn("prefix", content_out)
        self.assertIn("author2", content_out)
        self.assertIn("first memo", content_out)
        self.assertIn("content 1", content_out)
        self.assertIn("response 1", content_out)
        self.assertIn("last memo", content_out)
        self.assertIn("notice info", content_out)
        self.assertIn("notice tip", content_out)
