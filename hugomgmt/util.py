from logging import getLogger
import click
from pathlib import Path
import functools
import fnmatch
import importlib
import json
import yaml
import toml
import markdownify
import mdformat
import datetime
import jinja2
import sqlite3
import importlib.resources
from typing import TextIO

_log = getLogger(__name__)


def sqlite_option(func):
    @click.option("--sqlite", type=click.Path(exists=True, file_okay=True, dir_okay=False), envvar="ISSO_DB",
                  show_envvar=True)
    @functools.wraps(func)
    def _(sqlite, *args, **kwargs):
        conn = sqlite3.connect(database=sqlite)
        return func(sqlite3_conn=conn, *args, **kwargs)
    return _


def find_files(rootdirs: list[Path], ignore_dirs: list[str], ignore_files: list[str], pattern: list[str]):
    for r in rootdirs:
        for root, dirs, files in r.walk():
            for i in ignore_dirs:
                if i in dirs:
                    _log.debug("skip %s %s", root, i)
                    dirs.remove(i)
            for i in files:
                for p in ignore_files:
                    if fnmatch.fnmatch(i, p):
                        _log.debug("ignore %s %s", root, i)
                        break
                else:
                    for p in pattern:
                        if fnmatch.fnmatch(i, p):
                            yield root / i
                            break
                    else:
                        _log.debug("pass %s %s", root, i)


def json_serial(obj):
    if isinstance(obj, (datetime.datetime, datetime.date)):
        return obj.isoformat()
    raise TypeError("Type %s not serializable" % type(obj))


def to_json(s) -> str:
    return json.dumps(s, default=json_serial, ensure_ascii=False)


def to_yaml(s) -> str:
    return yaml.safe_dump(s, allow_unicode=True, sort_keys=False)


def to_toml(s) -> str:
    return toml.dumps(s)


def to_markdown(s: str) -> str:
    return markdownify.markdownify(s)


def to_markdown_format(s: str) -> str:
    return mdformat.text(s, extensions={"gfm"})


def to_isotime(s: datetime.datetime) -> str:
    return s.astimezone().isoformat()


def to_strftime(s: datetime.datetime, format: str) -> str:
    return s.astimezone().strftime(format)


def to_shortcode(s: str, module: str) -> str:
    for i in module.split(","):
        mod = importlib.import_module(f"{__package__}.shortcode_{i}")
        s = mod.process(s)
    return s


def make_template(s: str) -> jinja2.Template:
    env = jinja2.Environment()
    env.filters["json"] = to_json
    env.filters["shortcode"] = to_shortcode
    env.filters["markdown"] = to_markdown
    env.filters["markdown_format"] = to_markdown_format
    env.filters["isotime"] = to_isotime
    env.filters["strftime"] = to_strftime
    env.filters["yaml"] = to_yaml
    env.filters["toml"] = to_toml
    return env.from_string(s)


def file_or_resource(name) -> TextIO:
    if Path(name).exists():
        return Path(name).open("r")
    else:
        return importlib.resources.files().joinpath(name).open("r")
