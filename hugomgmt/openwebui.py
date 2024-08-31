import click
import json
import yaml
from pathlib import Path
import emoji
import subprocess
import datetime
import re
from typing import Union
from logging import getLogger
from .hugo import parse_dict

_log = getLogger(__name__)


def install_theme_submodule(outpath: Path, theme_url: str) -> str:
    _log.info("install theme as submodule(%s): %s", outpath, theme_url)
    from urllib.parse import urlparse
    tmurl = urlparse(theme_url)
    tmpath = Path(tmurl.path).stem
    theme_cmd = [theme_url, Path("themes") / tmpath]
    subprocess.run(["git", "submodule", "add", "--depth", "1", *theme_cmd],
                   check=True, cwd=outpath, encoding="utf-8")
    return tmpath


def install_theme(outpath: Path, theme_url: str) -> str:
    _log.info("install theme with clone(%s): %s", outpath, theme_url)
    from urllib.parse import urlparse
    tmurl = urlparse(theme_url)
    tmpath = Path(tmurl.path).stem
    theme_cmd = [theme_url, Path("themes") / tmpath]
    subprocess.run(["git", "clone", *theme_cmd],
                   check=True, cwd=outpath, encoding="utf-8")
    return tmpath


def get_slug(title: str, default: str) -> str:
    for c in title:
        slug = emoji.demojize(c)
        if slug.startswith(":") and slug.endswith(":"):
            res = slug.strip(":").replace("_", "-")
            _log.info("slug: %s -> %s", title, res)
            return res
    _log.info("cannot get slug: default=%s", default)
    return default


@click.option("--output", type=click.Path(dir_okay=True, file_okay=False), required=True)
@click.option("--url")
@click.option("--title")
@click.option("--author")
@click.option("--subtitle")
@click.option("--hugo-config", type=click.Path(file_okay=True, dir_okay=False))
@click.option("--theme", default="https://github.com/adityatelange/hugo-PaperMod.git", show_default=True)
@click.option("--notice-theme", default="https://github.com/martignoni/hugo-notice.git", show_default=True)
def owui_init_hugo(output, url, title, author, theme, notice_theme, subtitle, hugo_config):
    """OWUI: 'hugo new site' and apply short update to hugo.toml"""
    import toml
    baseconf = {}
    if hugo_config:
        baseconf = toml.load(hugo_config)
    outpath = Path(output)
    subprocess.run(["hugo", "new", "site", output], check=True, encoding='utf-8')
    subprocess.run(["git", "init"], check=True, cwd=output, encoding="utf-8")
    theme_names = []
    for i in [notice_theme, theme]:
        if i:
            theme_names.append(install_theme(outpath, i))
    confpath = outpath / "hugo.toml"
    hugodata = toml.load(confpath.open())
    hugodata.update(baseconf)
    hugodata["theme"] = theme_names
    if "params" not in hugodata:
        hugodata["params"] = {}
    if title:
        hugodata["title"] = title
    if url:
        hugodata["baseURL"] = url
    if subtitle:
        hugodata["params"]["description"] = subtitle
    if author:
        hugodata["params"]["author"] = author
    toml.dump(hugodata, confpath.open('w'))


def strip_list(s: list[str]) -> list[str]:
    return ("\n".join(s)).strip().splitlines(keepends=False)


def create_insertmap(meta_content: list[str]) -> dict[Union[int, str], list[str]]:
    def add_to_res(blk: list[str]):
        _log.debug("add to res: idx=%s, %s lines", idx, len(blk))
        blk = strip_list(blk)
        if len(blk) == 0:
            return
        if idx not in res:
            res[idx] = []
        if len(blk) != 0 and not blk[0].startswith(r"{"):
            res[idx].extend([r"{{< notice info >}}"] + blk + [r"{{< /notice >}}", ""])
        else:
            res[idx].extend(blk)

    idx = 0
    block = []
    res = {}
    for line in meta_content:
        m = re.match(r'<\!-- *skip *(?P<skip_count>[0-9]+) *-->', line)
        if m:
            add_to_res(block)
            skip_count = int(m.group("skip_count"))
            _log.debug("skip %s", skip_count)
            idx += skip_count
            block = []
            continue
        m = re.match(r'<\!-- *seek *(?P<seek_id>[^ ]+) *-->', line)
        if m:
            add_to_res(block)
            seek_id = m.group("seek_id")
            _log.debug("seek %s", seek_id)
            try:
                seek_id_n: int = int(seek_id)
                idx = seek_id_n
            except ValueError:
                idx = seek_id
            block = []
            continue
        block.append(line)
    add_to_res(block)
    return res


@click.option("--output", type=click.Path(dir_okay=True, exists=True))
@click.option("--metadir", type=click.Path(dir_okay=True, exists=True), default=".")
@click.argument("input", type=click.File("r"), nargs=-1)
def owui_json2md(input, output, metadir):
    """OWUI: convert chat.json to markdown files"""
    metapath = Path(metadir)
    data = []
    for i in input:
        d1 = json.load(i)
        if isinstance(d1, list):
            data.extend(d1)
        else:
            data.append(d1)
    outdir = Path(output)
    done_ofn: set[Path] = set()
    for chat in data:
        body = []
        metadata = {
            "draft": False,
        }
        ch = chat.get("chat")
        if "id" not in chat or not chat["id"]:
            continue
        metadata["title"] = ch.get("title").strip()
        metadata["authors"] = [x.split(":", 1)[0] for x in ch.get("models")]
        metadata["id"] = chat["id"]
        metadata["slug"] = get_slug(metadata["title"], metadata["id"])
        if "updated_at" in chat:
            ts = chat["updated_at"]
        elif "created_at" in chat:
            ts = chat["created_at"]
        else:
            ts = datetime.datetime.now().timestamp()
        dt = datetime.datetime.fromtimestamp(ts).astimezone()
        metadata["date"] = dt.isoformat()
        basename = (dt.strftime("%Y-%m-%d-") + metadata["slug"] + ".md")
        midname = dt.strftime("%Y-%m")
        metafile: Path = metapath / basename
        skip_id: list[str] = []
        skip_n: list[int] = []
        insert_map: dict[Union[int, str], list[str]] = {}
        if metafile.exists():
            meta_headers, meta_content = parse_dict(metafile.read_text().splitlines(keepends=True))
            if meta_headers is None:
                meta_headers = {}
            if meta_content is None:
                meta_content = []
            if "skip_id" in meta_headers:
                skip_id = meta_headers.pop("skip_id")
            if "skip_n" in meta_headers:
                skip_n = meta_headers.pop("skip_n")
            if meta_headers:
                metadata.update(meta_headers)
            meta_content = [x.rstrip() for x in meta_content]
        else:
            metafile.write_text("---\ncategories: []\n---\n")
            meta_headers = {
                "categories": []
            }
            meta_content = []
        insert_map.update(create_insertmap(meta_content))
        ofn: Path = outdir / midname / basename
        assert ofn not in done_ofn   # uniq
        done_ofn.add(ofn)
        body.extend(insert_map.get("head", []))
        for idx, msg in enumerate(ch.get("messages", [])):
            msgid = msg.get("id")
            if msgid is None:
                _log.debug("no id: %s", msg)
                continue
            contents = msg.get("content").splitlines()
            if msgid in skip_id:
                _log.debug("skip by id: %s", msgid)
                continue
            if idx in skip_n:
                _log.debug("skip by n: %s", idx)
                continue
            body.extend(insert_map.get(idx, []))
            body.extend(insert_map.get(msgid, []))
            if msg.get("role") == "user":
                body.append(r"{{< notice tip >}}")
                body.extend(contents)
                body.append(r"{{< /notice >}}")
                body.append("")
            elif msg.get("role") == "assistant":
                body.extend(contents)
                body.append("")
        body.extend(insert_map.get(idx+1, []))
        body.extend(insert_map.get("tail", []))
        ofn.parent.mkdir(parents=True, exist_ok=True)
        with open(ofn, "w") as ofp:
            click.echo("---", file=ofp)
            click.echo(yaml.dump(metadata, default_flow_style=False, allow_unicode=True), nl=False, file=ofp)
            click.echo("---", file=ofp)
            click.echo("\n".join(body), file=ofp)