import unittest
from pathlib import Path
import tempfile
import gzip
try:
    import brotli
except ImportError:
    brotli = None
from click.testing import CliRunner
import hugomgmt.main


class TestStatic(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.tdpath = Path(self.td.name)
        hugomgmt.main.reg_cli()
        self.cli = hugomgmt.main.cli

    def tearDown(self):
        self.td.cleanup()
        del self.td
        del self.cli

    def test_help(self):
        res = CliRunner().invoke(self.cli)
        if res.exception:
            raise res.exception
        self.assertEqual(0, res.exit_code)
        self.assertIn("static-gzip", res.output)
        self.assertIn("static-brotli", res.output)
        # self.assertIn("static-image-optimize", res.output)
        self.assertIn("static-rss-atom", res.output)

    def prep(self):
        ofp1 = self.tdpath / "test.html"
        ofp1.write_text("hello\n"*10240)
        ofp2 = self.tdpath / "test-short.js"
        ofp2.write_text("hello\n")
        ofp3 = self.tdpath / "test.png"
        ofp3.write_text("hello\n"*10240)
        ofp4 = self.tdpath / "test-to-del.html.gz"
        ofp4.write_text("hello\n")
        ofp5 = self.tdpath / "test-to-del.html.br"
        ofp5.write_text("hello\n")
        return ofp1, ofp2, ofp3, ofp4, ofp5

    def test_gzip(self):
        ofp1, _, _, ofp4, ofp5 = self.prep()
        res = CliRunner().invoke(self.cli, ["static-gzip", self.td.name, "--remove"])
        if res.exception:
            raise res.exception
        self.assertEqual(0, res.exit_code)
        self.assertTrue(ofp1.exists())
        self.assertFalse(ofp4.exists())  # --remove
        self.assertTrue(ofp5.exists())  # other ext
        self.assertTrue((self.tdpath / "test.html.gz").exists())
        self.assertFalse((self.tdpath / "test-short.js.gz").exists())
        self.assertFalse((self.tdpath / "test.png.gz").exists())
        # check content
        with gzip.open(self.tdpath / "test.html.gz") as ifp:
            self.assertEqual(b"hello\n"*10240, ifp.read())

    def test_gzip_zopfli(self):
        ofp1, _, _, ofp4, ofp5 = self.prep()
        res = CliRunner().invoke(self.cli, ["static-gzip", self.td.name, "--try-zopfli"])
        if res.exception:
            raise res.exception
        self.assertEqual(0, res.exit_code)
        self.assertTrue(ofp1.exists())
        self.assertTrue(ofp4.exists())  # --no-remove
        self.assertTrue(ofp5.exists())  # other ext
        self.assertTrue((self.tdpath / "test.html.gz").exists())
        self.assertFalse((self.tdpath / "test-short.js.gz").exists())
        self.assertFalse((self.tdpath / "test.png.gz").exists())
        # check content
        with gzip.open(self.tdpath / "test.html.gz") as ifp:
            self.assertEqual(b"hello\n"*10240, ifp.read())

    @unittest.skipIf(brotli is None, "brotli not installed")
    def test_brotli(self):
        ofp1, _, _, ofp4, ofp5 = self.prep()
        res = CliRunner().invoke(self.cli, ["static-brotli", self.td.name, "--remove"])
        if res.exception:
            raise res.exception
        self.assertEqual(0, res.exit_code)
        self.assertTrue(ofp1.exists())
        self.assertTrue(ofp4.exists())  # other ext
        self.assertFalse(ofp5.exists())  # --remove
        self.assertTrue((self.tdpath / "test.html.br").exists())
        self.assertFalse((self.tdpath / "test-short.js.br").exists())
        self.assertFalse((self.tdpath / "test.png.br").exists())
        # check content
        with open(self.tdpath / "test.html.br", "rb") as ifp:
            self.assertEqual(b"hello\n"*10240, brotli.decompress(ifp.read()))

    @unittest.skipUnless(brotli is None, "brotli installed")
    def test_no_brotli(self):
        ofp1, _, _, ofp4, _ = self.prep()
        res = CliRunner().invoke(self.cli, ["static-brotli", self.td.name, "--remove"])
        self.assertIsNotNone(res.exception)
        self.assertEqual(1, res.exit_code)
        self.assertTrue(ofp1.exists())
        self.assertTrue(ofp4.exists())  # do not remove
        self.assertFalse((self.tdpath / "test.html.br").exists())
        self.assertFalse((self.tdpath / "test-short.js.br").exists())
        self.assertFalse((self.tdpath / "test.png.br").exists())

    def test_rssatom_invalid_xml(self):
        inputxml = 'xyzxyz'
        res = CliRunner().invoke(self.cli, ["static-rss-atom", "--format", "atom"], input=inputxml)
        self.assertIsNotNone(res.exception)
        self.assertEqual(1, res.exit_code)
        self.assertEqual("", res.output)

    def test_rssatom_invalid_feed(self):
        inputxml = """<?xml version='1.0' encoding='UTF-8'?><hello/>"""
        res = CliRunner().invoke(self.cli, ["static-rss-atom", "--format", "atom"], input=inputxml)
        self.assertIsNotNone(res.exception)
        self.assertEqual(1, res.exit_code)
        self.assertIn("Aborted", res.output)

    def test_rssatom_rdf2atom(self):
        inputxml = """<?xml version='1.0' encoding='UTF-8'?>
<rdf:RDF
    xmlns="http://purl.org/rss/1.0/"
    xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
    xmlns:dc="http://purl.org/dc/elements/1.1/">
<channel>
<title>this is title</title>
</channel>
<item>
<title>entry title</title>
</item>
</rdf:RDF>
"""
        res = CliRunner().invoke(self.cli, ["static-rss-atom", "--format", "atom"], input=inputxml)
        if res.exception:
            raise res.exception
        self.assertEqual(0, res.exit_code)
        self.assertIn("<feed ", res.output)
        self.assertIn("<title>", res.output)

    def test_rssatom_rss2rdf(self):
        inputxml = """<?xml version='1.0' encoding='UTF-8'?>
<rss xmlns:atom="http://www.w3.org/2005/Atom" version="2.0">
<channel>
<title>this is title</title>
<pubDate>Thu, 06 Jun 2024 22:25:10 +0900</pubDate>
<item>
<title>entry title</title>
<pubDate>Thu, 06 Jun 2024 22:25:10 +0900</pubDate>
</item>
</channel>
</rss>
"""
        res = CliRunner().invoke(self.cli, ["static-rss-atom", "--format", "rdf", "--pretty"], input=inputxml)
        if res.exception:
            raise res.exception
        self.assertEqual(0, res.exit_code)
        self.assertIn("<rdf:RDF ", res.output)
        self.assertIn("<title>", res.output)

    def test_rssatom_atom2rss(self):
        inputxml = """<?xml version='1.0' encoding='UTF-8'?>
<feed xmlns="http://www.w3.org/2005/Atom">
<channel>
<title>this is title</title>
<updated>2024-06-06T22:25:10+09:00</updated>
<entry>
<title>entry title</title>
<updated>2024-06-06T22:25:10+09:00</updated>
</entry>
</channel>
</feed>
"""
        res = CliRunner().invoke(self.cli, ["static-rss-atom", "--format", "atom"], input=inputxml)
        if res.exception:
            raise res.exception
        self.assertEqual(0, res.exit_code)
        self.assertIn("<feed ", res.output)
        self.assertIn("<title>", res.output)
