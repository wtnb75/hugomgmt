from pathlib import Path
import functools
import tempfile
from typing import Optional
import subprocess
import gzip
import click
import shutil
from logging import getLogger
from .util import find_files

_log = getLogger(__name__)


@click.option("--pretty/--compact", default=False, show_default=True)
@click.option("--format", type=click.Choice(["rss", "atom", "rdf"]),
              default="atom", show_default=True, help="output format")
@click.argument("input", type=click.File('r'), default="-")
@click.argument("output", type=click.File('w'), default="-")
def static_rss_atom(input, output, format, pretty):
    """static site: convert rss, rdf and atom"""
    import xml.dom.minidom
    import feedendum
    data = input.read()
    feed = None
    if feed is None:
        try:
            feed = feedendum.from_rss_text(data)
            _log.info("feed is rss")
        except feedendum.exceptions.FeedParseError:
            pass
    if feed is None:
        try:
            feed = feedendum.from_rdf_text(data)
            _log.info("feed is rdf")
        except feedendum.exceptions.FeedParseError:
            pass
    if feed is None:
        try:
            feed = feedendum.from_atom_text(data)
            _log.info("feed is atom")
        except feedendum.exceptions.FeedParseError:
            pass
    if feed is None:
        raise click.Abort("cannot parse input xml")
    if format == "atom":
        outstr = feedendum.to_atom_string(feed)
    elif format == "rss":
        outstr = feedendum.to_rss_string(feed)
    elif format == "rdf":
        outstr = feedendum.to_rdf_string(feed)
    else:
        raise click.Abort(f"unknown format: {format}")
    if pretty:
        dom = xml.dom.minidom.parseString(outstr)
        output.write(dom.toprettyxml())
    else:
        output.write(outstr)


def may_comp(filepath: Path, minsize: int,
             compressfn: callable, decompressfn: callable, ext: str, dry: bool):
    filepath_comp = filepath.with_suffix(filepath.suffix + ext)
    st_orig = filepath.stat()
    prefix = "(WET)"
    if dry:
        prefix = "(DRY)"
    try:
        st_comp = filepath_comp.stat()
        if not st_orig.st_size > minsize:
            _log.info(prefix + "small but %s exists(remove): %s", ext, filepath_comp)
            if not dry:
                filepath_comp.unlink()
            return
        if st_comp.st_mtime > st_orig.st_mtime:
            _log.debug(prefix + "newer %s(keep): %s", ext, filepath_comp)
            return
        _log.debug(prefix + "older ext(compare): %s", ext, filepath_comp)
        with gzip.open(filepath_comp, 'rb') as comp_ifp:
            orig_data = filepath.read_bytes()
            try:
                comp_data = decompressfn(comp_ifp.read())
            except Exception:
                comp_data = None
        if orig_data == comp_data:
            _log.debug(prefix + "equal(keep): %s", filepath_comp)
            return
        _log.info(prefix + "mismatch(update): %s", filepath_comp)
        if not dry:
            filepath_comp.unlink()
        comp_content = compressfn(orig_data)
        if len(comp_content) < st_orig.st_size:
            _log.info(prefix + "compressed: %s %s -> %s", filepath_comp, st_orig.st_size, len(comp_content))
            if not dry:
                filepath_comp.write_bytes(comp_content)
                shutil.copystat(filepath, filepath_comp)
        else:
            _log.info(prefix + "compress less(not write): %s %s < %s",
                      filepath_comp, st_orig.st_size, len(comp_content))
    except FileNotFoundError:
        if st_orig.st_size > minsize:
            _log.debug(prefix + "compress(new): %s", filepath)
            orig_data = filepath.read_bytes()
            comp_content = compressfn(orig_data)
            if len(comp_content) < st_orig.st_size:
                _log.info(prefix + "compressed: %s %s -> %s", filepath_comp, st_orig.st_size, len(comp_content))
                if not dry:
                    filepath_comp.write_bytes(comp_content)
                    shutil.copystat(filepath, filepath_comp)
            else:
                _log.info(prefix + "compress less(not write): %s %s < %s",
                          filepath_comp, st_orig.st_size, len(comp_content))


def may_remove(filepath: Path, ext: str, dry: bool):
    if filepath.suffix != ext:
        _log.debug("suffix mismatch. continue %s != %s", filepath.suffix, ext)
        return
    base = filepath.stem
    origpath = filepath.parent / base
    if not origpath.exists():
        if not dry:
            _log.info("%s: %s does not exists. remove", filepath, origpath)
            filepath.unlink()
        else:
            _log.warning("%s: %s does not exists (continue)", filepath, origpath)


@click.option("--minsize", type=int, default=1024*8, show_default=True)
@click.argument("publicdir", type=click.Path(dir_okay=True, exists=True, file_okay=False),
                default="./public")
@click.option("--try-zopfli/--gzip", default=False, show_default=True)
@click.option("--dry/--wet", default=False, show_default=True)
@click.option("--remove/--no-remove", default=False, show_default=True, help="remove xxx.gz if xxx does not exists")
def static_gzip(publicdir, minsize, try_zopfli, dry, remove):
    """static site: gzip_static on;"""
    compressfn = None
    if try_zopfli:
        try:
            from zopfli.gzip import compress as compressfn
            _log.info("using zopfli module")
        except ImportError:
            _log.warning("cannot import zopfli. use standard gzip module")
    if compressfn is None:
        from gzip import compress as compress
        compressfn = functools.partial(compress, compresslevel=9)
        _log.info("using standard gzip module.")
    ignore_dirs = [".git"]
    ignore_files = ["*.gz", "*.br"]
    file_patterns = ["*.txt", "*.css", "*.html", "*.js", "*.xml", "*.svg"]
    for filepath in find_files([Path(publicdir)], ignore_dirs, ignore_files, file_patterns):
        may_comp(filepath, minsize, compressfn, gzip.decompress, ".gz", dry)
    for filepath in find_files([Path(publicdir)], ignore_dirs, file_patterns, ignore_files):
        may_remove(filepath, ".gz", not remove)


@click.option("--minsize", type=int, default=1024*8, show_default=True)
@click.argument("publicdir", type=click.Path(dir_okay=True, exists=True, file_okay=False),
                default="./public")
@click.option("--dry/--wet", default=False, show_default=True)
@click.option("--remove/--no-remove", default=False, show_default=True, help="remove xxx.br if xxx does not exists")
def static_brotli(publicdir, minsize, dry, remove):
    """static site: brotli_static on;"""
    try:
        import brotli
    except ImportError:
        _log.error("cannot import brotli: try 'pip install brotli'")
        raise
    ignore_dirs = [".git"]
    ignore_files = ["*.gz", "*.br"]
    file_patterns = ["*.txt", "*.css", "*.html", "*.js", "*.xml", "*.svg"]
    for filepath in find_files([Path(publicdir)], ignore_dirs, ignore_files, file_patterns):
        may_comp(filepath, minsize, brotli.compress, brotli.decompress, ".br", dry)
    for filepath in find_files([Path(publicdir)], ignore_dirs, file_patterns, ignore_files):
        may_remove(filepath, ".br", not remove)


imageopt_map = {
    "zopflipng": (["*.png"], ["zopflipng", "-m", "-y", "__INPUT__", "__OUTPUT__"]),
    "optipng": (["*.png"], ["optipng", "-o7", "__INPUT__", "-out", "__OUTPUT__"]),
    "convert": (["*.png", "*.jpg", "*.jpeg"], ["convert", "__INPUT__", "-strip", "__OUTPUT__"]),
    "pngcrush": (["*.png"], ["pngcrush", "-rem", "alla", "-brute", "-reduce", "__INPUT__", "__OUTPUT__"]),
    "pngquant": (["*.png"], ["pngquant", "--speed", "1", "--output", "__OUTPUT__", "__INPUT__"]),
    "pngnq": (["*.png"], ["pngnq", "-d", "__TMPDIR__", "__INPUT__"]),
    "advpng": (["*.png"], ["advpng", "-z", "__TMPFILE__"]),
    "lossypng": (["*.png"], ["lossypng", "-r", "__TMPFILE__"]),
    "jpegtran": (
        ["*.jpg", "*.jpeg"],
        ["jpegtran", "-outfile", "__OUTPUT__", "-optimize", "-copy", "none", "__INPUT__"]),
    "jpegoptim": (["*.jpg", "*.jpeg"], ["jpegoptim", "--strip-all", "__TMPFILE__"]),
    "gifsicle": (["*.gif"], ["gifsicle", "-i", "__INPUT__", "-O3", "-o", "__OUTPUT__"]),
}

# choose installed
imageopt_map = {k: v for k, v in imageopt_map.items() if shutil.which(v[1][0])}


def may_imagecomp(filepath: Path, command: list[str], dry: bool):
    defer = []
    cmd = []
    infname: Optional[Path] = None
    outfname: Optional[Path] = None
    ext = filepath.suffix
    ist = filepath.stat()
    for i in command:
        if i == "__INPUT__":
            infname = filepath
            cmd.append(str(infname))
        elif i == "__OUTPUT__":
            tf = tempfile.NamedTemporaryFile("wb+", suffix=ext, )
            outfname = Path(tf.name)
            cmd.append(str(outfname))
            defer.append(tf.close)
            outfname.unlink()
        elif i == "__TMPDIR__":
            td = tempfile.TemporaryDirectory()
            outfname = Path(td.name)
            cmd.append(str(td.name))
            defer.append(td.cleanup)
        elif i == "__TMPFILE__":
            tf = tempfile.NamedTemporaryFile("wb+", suffix=ext)
            tf.write(filepath.read_bytes())
            tf.flush()
            infname = Path(tf.name)
            outfname = Path(tf.name)
            cmd.append(infname)
            defer.append(tf.close)
        else:
            cmd.append(i)
    _log.debug("%s: %s -> %s, cmd=%s, defer=%s", filepath, infname, outfname, cmd, defer)
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL, text=True)
    if res.stdout:
        _log.debug("stdout: %s", repr(res.stdout))
    if res.stderr:
        _log.debug("stderr: %s", repr(res.stderr))
    res.check_returncode()
    if outfname.is_dir():
        files = list(outfname.iterdir())
        if len(files) != 1:
            _log.warning("multiple files: %s", files)
            files = [x for x in files if x.endswith(ext)]
            _log.info("choose[0] %s", files)
            outfname = files[0]
    ost = outfname.stat()
    _log.info("compress(dry=%s): %s %s -> %s", dry, filepath, ist.st_size, ost.st_size)
    if ist.st_size <= ost.st_size or ost.st_size == 0:
        _log.info("already optimized. continue")
    elif not dry:
        _log.info("update file: %s %s -> %s", filepath, ist.st_size, ost.st_size)
        filepath.write_bytes(outfname.read_bytes())
    for fn in defer:
        fn()


if len(imageopt_map) != 0:
    @click.argument("publicdir", type=click.Path(dir_okay=True, exists=True, file_okay=False),
                    default="./public")
    @click.option("--dry/--wet", default=False, show_default=True)
    @click.option("--mode", type=click.Choice(list(imageopt_map.keys())),
                  default=list(imageopt_map.keys())[0], show_default=True)
    def static_image_optimize(publicdir, mode, dry):
        """static site: optimize image"""
        ignore_dirs = [".git"]
        ignore_files = ["*.gz", "*.br", "*.html", "*.xml", "*.css", "*.js"]
        file_patterns, command = imageopt_map.get(mode)
        for filepath in find_files([Path(publicdir)], ignore_dirs, ignore_files, file_patterns):
            may_imagecomp(filepath, command, dry)
