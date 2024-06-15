import unittest
from pathlib import Path
import tempfile
from click.testing import CliRunner
import subprocess
import hugomgmt.main


class TestHugo(unittest.TestCase):
    def setUp(self):
        hugomgmt.main.reg_cli()
        self.cli = hugomgmt.main.cli

    def tearDown(self):
        del self.cli

    toml_data = """
hello = "world"
abc = true
def = 1
"""

    yaml_data = """
hello: world
abc: true
def: 1
"""

    toml_post = f"""
+++
{toml_data.strip()}
+++
hello world
"""

    yaml_post = f"""
---
{yaml_data.strip()}
---
hello world
"""

    def _testyt(self, input, expected, format=None):
        cmd = ["hugo-yamltoml"]
        if format:
            cmd.extend(["--format", format])
        res = CliRunner().invoke(self.cli, cmd, input=input)
        if res.exception:
            raise res.exception
        self.assertEqual(0, res.exit_code)
        self.assertEqual(expected.strip(), res.output.strip())

    def test_toml2toml_post(self):
        self._testyt(self.toml_post, self.toml_post)

    def test_toml2yaml_post(self):
        self._testyt(self.toml_post, self.yaml_post, "yaml")

    def test_yaml2yaml_post(self):
        self._testyt(self.yaml_post, self.yaml_post, "yaml")

    def test_yaml2toml_post(self):
        self._testyt(self.yaml_post, self.toml_post, "toml")

    def test_toml2toml(self):
        self._testyt(self.toml_data, self.toml_data)

    def test_toml2yaml(self):
        self._testyt(self.toml_data, self.yaml_data, "yaml")

    def test_yaml2yaml(self):
        self._testyt(self.yaml_data, self.yaml_data, "yaml")

    def test_yaml2toml(self):
        self._testyt(self.yaml_data, self.toml_data, "toml")

    def test_yaml2toml_invalid(self):
        input = """a:=:{["""
        res = CliRunner().invoke(self.cli, ["hugo-yamltoml"], input=input)
        self.assertEqual(1, res.exit_code)
        self.assertIsNotNone(res.exception)

    def test_yaml2toml_mixed(self):
        input = """
---
hello: world
---
hello world

```toml
+++
toml = "toml"
+++
```

```yaml
---
yaml: yaml
---
```
"""
        expected = """
+++
hello = "world"
+++
hello world

```toml
+++
toml = "toml"
+++
```

```yaml
---
yaml: yaml
---
```
"""
        self._testyt(input, expected)
        self._testyt(expected, input, "yaml")

    png1x1 = b'\x89PNG\r\n\x1a\n\x00\x00\x00\r' \
        b'IHDR\x00\x00\x00\x01\x00\x00\x00\x01\x01\x03\x00\x00\x00%\xdbV\xca\x00\x00\x00\x03' \
        b'PLTE\x00\x00\x00\xa7z=\xda\x00\x00\x00\x01' \
        b'tRNS\x00@\xe6\xd8f\x00\x00\x00\n' \
        b'IDAT\x08\xd7c`\x00\x00\x00\x02\x00\x01\xe2!\xbc3\x00\x00\x00\x00' \
        b'IEND\xaeB`\x82'

    def _setuphugo(self, dir: Path, theme: str, have_custom: bool = True):
        subprocess.run(["hugo", "new", "site", str(dir)], check=True)
        subprocess.run(["hugo", "new", "theme", theme], cwd=dir, check=True)
        subprocess.run(["hugo", "new", "content", "hello.md"], cwd=dir, check=True)
        if have_custom:
            # make assets
            # 1x1.png
            (dir / "assets").mkdir(exist_ok=True)
            (dir / "layouts").mkdir(exist_ok=True)
            (dir / "layouts" / "partials").mkdir(exist_ok=True)
            (dir / "assets" / "hello.png").write_bytes(self.png1x1)
            # make layout
            (dir / "layouts" / "partials" / "head.html").write_text("""
<meta name="robots" content="index, nofollow" />
<meta charset="utf-8">
<meta name="viewport" content="width=device-width">
<title>{{ if .IsHome }}{{ site.Title }}{{ else }}{{ printf "%s | %s" .Title site.Title }}{{ end }}</title>
{{ partialCached "head/css.html" . }}
{{ partialCached "head/js.html" . }}
""".lstrip())

    def test_diff_patch(self):
        with tempfile.TemporaryDirectory() as td1:
            self._setuphugo(Path(td1), "tm1", True)
            res = CliRunner().invoke(self.cli, ["hugo-diff-from-theme", "--theme", "tm1", td1])
            if res.exception:
                raise res.exception
            self.assertEqual(0, res.exit_code)
            patch_str = res.output
            for line in patch_str.splitlines():
                self.assertIn(line[0], ' +-@')
        with tempfile.TemporaryDirectory() as td2:
            self._setuphugo(Path(td2), "tm1", False)
            res = CliRunner().invoke(self.cli, ["hugo-patch-to-theme", "--theme", "tm1", td2], input=patch_str)
            if res.exception:
                raise res.exception
            self.assertEqual(0, res.exit_code)
            self.assertTrue((Path(td2) / "assets" / "hello.png").exists())
            self.assertEqual(self.png1x1, (Path(td2) / "assets" / "hello.png").read_bytes())
            heads = (Path(td2) / "layouts" / "partials" / "head.html").read_text().splitlines()
            self.assertIn('<meta name="robots" content="index, nofollow" />',
                          heads)
            self.assertIn('<meta charset="utf-8">',
                          heads)
