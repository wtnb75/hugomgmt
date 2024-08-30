import click
import json
import yaml
from pathlib import Path
import emoji
import subprocess
import datetime
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
        ofn: Path = outdir / midname / basename
        for msg in ch.get("messages", []):
            contents = msg.get("content").splitlines()
            if msg.get("role") == "user":
                body.append(r"{{< notice tip >}}")
                body.extend(contents)
                body.append(r"{{< /notice >}}")
                body.append("")
            elif msg.get("role") == "assistant":
                body.extend(contents)
                body.append("")
        if metafile.exists():
            headers, content = parse_dict(metafile.read_text().splitlines(keepends=True))
            if headers:
                metadata.update(headers)
            content = [x.rstrip() for x in content]
            if len(content) != 0 and not content[0].startswith(r"{"):
                content.insert(0, r'{{< notice info >}}')
                content.append(r'{{< /notice >}}')
                content.append("")
            body = content + body
        else:
            metafile.write_text("---\ncategories: []\n---\n")
        ofn.parent.mkdir(parents=True, exist_ok=True)
        with open(ofn, "w") as ofp:
            click.echo("---", file=ofp)
            click.echo(yaml.dump(metadata, default_flow_style=False, allow_unicode=True), nl=False, file=ofp)
            click.echo("---", file=ofp)
            click.echo("\n".join(body), file=ofp)
