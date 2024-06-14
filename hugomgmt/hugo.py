import click
import base64
import difflib
import datetime
import subprocess
import io
import yaml
import toml
import mdformat
from pathlib import Path
from typing import Optional
from logging import getLogger
from .util import find_files

_log = getLogger(__name__)


def make_diff(name: Path, new_file: Path, old_file: Optional[Path] = None):
    newstat = new_file.stat()
    new_ts = datetime.datetime.fromtimestamp(newstat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    if old_file:
        oldstat = old_file.stat()
        old_ts = datetime.datetime.fromtimestamp(oldstat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    else:
        old_ts = datetime.datetime.fromtimestamp(0).strftime("%Y-%m-%d %H:%M:%S")
    try:
        # text file
        new_lines = new_file.read_text().splitlines(keepends=True)
        if old_file is None:
            old_lines = []
            old_name = "/dev/null"
        else:
            old_name = name.with_suffix(name.suffix + ".orig")
            old_lines = old_file.read_text().splitlines(keepends=True)
        yield from difflib.unified_diff(old_lines, new_lines, str(old_name), str(name), old_ts, new_ts)
    except UnicodeDecodeError:
        # binary file
        name2 = name.with_suffix(name.suffix + ".base64")
        new_bin = new_file.read_bytes()
        if old_file is None:
            old_bin = b''
            old_name = "/dev/null"
        else:
            old_name = name2 + ".orig"
            old_bin = old_file.read_bytes()
        new_lines = base64.encodebytes(new_bin).decode('utf-8').splitlines(keepends=True)
        old_lines = base64.encodebytes(old_bin).decode('utf-8').splitlines(keepends=True)
        yield from difflib.unified_diff(old_lines, new_lines, str(old_name), str(name2), old_ts, new_ts)


@click.option("--theme")
@click.argument("hugodir", type=click.Path(dir_okay=True, exists=True, file_okay=False),
                default=".")
def hugo_diff_from_theme(hugodir, theme):
    """hugo: diff from theme"""
    hugopath = Path(hugodir)
    ignore_dirs = [".git"]
    ignore_files = [".DS_Store"]
    dirnames = ["archetypes", "assets", "data", "layouts", "resources", "static"]
    paths = [hugopath / x for x in dirnames]
    themedir = hugopath / "themes" / theme
    if not themedir.is_dir():
        raise click.Abort(f"{themedir} is not directory")
    for filepath in find_files(paths, ignore_dirs, ignore_files, ["*"]):
        relpath = filepath.relative_to(hugopath)
        themepath = themedir / relpath
        if themepath.exists():
            # make diff
            _log.info("exists(make diff): filename=%s, relpath=%s, themepath=%s",
                      filepath, relpath, themepath)
            for line in make_diff(relpath, filepath, themepath):
                if not line.endswith("\n"):
                    click.echo(line)
                    click.echo("\\ No newline at end of file")
                else:
                    click.echo(line, nl=False)
        else:
            # make diff from /dev/null
            _log.info("not exists(make all): filename=%s, relpath=%s, themepath=%s",
                      filepath, relpath, themepath)
            for line in make_diff(relpath, filepath):
                if not line.endswith("\n"):
                    click.echo(line)
                    click.echo("\\ No newline at end of file")
                else:
                    click.echo(line, nl=False)


@click.option("--theme")
@click.argument("hugodir", type=click.Path(dir_okay=True, exists=True, file_okay=False),
                default=".")
@click.argument("patch", type=click.File("r"), default="-")
def hugo_patch_to_theme(hugodir, theme: str, patch):
    """hugo: patch to theme"""
    import shutil
    proc = subprocess.Popen(["patch", "-p0"], stdin=subprocess.PIPE, cwd=hugodir,
                            encoding='utf-8', text=True)
    out = proc.stdin
    hugopath = Path(hugodir)
    themepath = hugopath / "themes" / theme
    postprocs: list[tuple[str, str]] = []
    for line in patch:
        if line.startswith("+++ "):
            basename: str = line[4:].split()[0]
            if basename.endswith(".base64"):
                postprocs.append((basename, basename[:-7]))
            filepath = hugopath / basename
            themefpath = themepath / basename
            if themefpath.exists():
                _log.info("copy from theme: %s", basename)
                filepath.parent.mkdir(exist_ok=True)
                shutil.copy(themefpath, filepath)
            else:
                _log.info("create new(remove): %s", basename)
                filepath.parent.mkdir(exist_ok=True)
                filepath.unlink(missing_ok=True)
        print(line, file=out, end='')
    out.close()
    proc.wait()
    for b64name, binname in postprocs:
        _log.info("fix b64: %s %s", b64name, binname)
        b64path = hugopath / b64name
        binpath = hugopath / binname
        data = base64.decodebytes(b64path.read_bytes())
        binpath.write_bytes(data)
        b64path.unlink()


def parse_dict(lines: list[str]) -> tuple[dict, list[str]]:
    toml_idx = [x for x in range(len(lines)) if lines[x] == '+++\n']
    yaml_idx = [x for x in range(len(lines)) if lines[x] == '---\n']
    format = None
    preamble = None
    content = None
    if len(toml_idx) < 2 and len(yaml_idx) >= 2:
        # yaml preamble + content
        format = 'yaml'
        preamble = lines[yaml_idx[0]+1:yaml_idx[1]]
        content = lines[yaml_idx[1]+1:]
    elif len(yaml_idx) < 2 and len(toml_idx) >= 2:
        # toml preamble + content
        format = 'toml'
        preamble = lines[toml_idx[0]+1:toml_idx[1]]
        content = lines[toml_idx[1]+1:]
    elif len(yaml_idx) >= 2 and len(toml_idx) >= 2:
        # both preamble?
        if yaml_idx[0] < toml_idx[0]:
            # yaml preamble + content
            format = 'yaml'
            preamble = lines[yaml_idx[0]+1:yaml_idx[1]]
            content = lines[yaml_idx[1]+1:]
        else:
            # toml preamble + content
            format = 'toml'
            preamble = lines[toml_idx[0]+1:toml_idx[1]]
            content = lines[toml_idx[1]+1:]
    else:
        # no content
        try:
            data = toml.loads("".join(lines))
            return data, []
        except toml.decoder.TomlDecodeError:
            data = yaml.safe_load("".join(lines))
            return data, []
    if format == 'toml':
        data = toml.loads("".join(preamble))
        return data, content
    if format == 'yaml':
        data = yaml.safe_load("".join(preamble))
        return data, content
    raise Exception("cannot detect format")


@click.option("--format", type=click.Choice(["yaml", "toml"]), default="toml", show_default=True)
@click.argument("input", type=click.File('r'), default="-")
@click.argument("output", type=click.File('w'), default="-")
def hugo_yamltoml(format, input, output):
    """hugo: yaml <-> toml converter"""
    input_lines = input.readlines()
    data, content = parse_dict(input_lines)
    if format == 'yaml':
        if content:
            print("---", file=output)
        yaml.dump(data, stream=output, encoding='utf-8', allow_unicode=True, sort_keys=False)
        if content:
            print("---", file=output)
            print("".join(content), file=output)
    if format == 'toml':
        if content:
            print("+++", file=output)
        toml.dump(data, f=output)
        if content:
            print("+++", file=output)
            print("".join(content), file=output)


def reformat_post(basepath: Path, filepath: Path, dry: bool, diff: bool, format: str, format_md: bool):
    lines = filepath.read_text().splitlines(keepends=True)
    data, content = parse_dict(lines)
    if format_md:
        content_str = mdformat.text("".join(content))
    else:
        content_str = "".join(content)
    outfp = io.StringIO()
    if format == 'yaml':
        if content:
            print("---", file=outfp)
        yaml.dump(data, stream=outfp, encoding='utf-8', allow_unicode=True, sort_keys=False)
        if content:
            print("---", file=outfp)
            print(content_str, file=outfp, end='')
    if format == 'toml':
        if content:
            print("+++", file=outfp)
        toml.dump(data, f=outfp)
        if content:
            print("+++", file=outfp)
            print(content_str, file=outfp, end='')
    olines = outfp.getvalue().splitlines(keepends=True)
    if lines == olines:
        _log.info("no change: %s", filepath)
    else:
        if diff:
            ts = datetime.datetime.fromtimestamp(filepath.stat().st_mtime)
            bpath = filepath.relative_to(basepath)
            udiff = difflib.unified_diff(
                lines, olines,
                fromfile=str(bpath)+".orig", tofile=str(bpath),
                fromfiledate=ts.isoformat(),
                tofiledate=datetime.datetime.now().isoformat())
            click.echo("".join(udiff))
        if dry:
            _log.info("change(dry): %s", filepath)
        else:
            _log.info("overwrite: %s", filepath)
            filepath.write_text("".join(olines))


@click.option("--format", type=click.Choice(["yaml", "toml"]), default="toml", show_default=True)
@click.option("--dry/--wet", default=False, show_default=True)
@click.option("--diff/--no-diff", default=False, show_default=True)
@click.argument("input", type=click.Path(exists=True))
def hugo_reformat_posts(input, dry, diff, format):
    """hugo: reformat posts"""
    ignore_dirs = [".git"]
    ignore_files = ["*.png", "*.jpg"]
    pattern = ["*.md", "*.markdown"]

    root: Path = Path(input)
    if root.is_dir():
        for filepath in find_files([root], ignore_dirs, ignore_files, pattern):
            reformat_post(root, filepath, dry, diff, format, True)
    elif root.is_file():
        reformat_post(root.parent, root, dry, diff, format, True)
    else:
        raise click.BadParameter(f"input must file or dir: {input}")
