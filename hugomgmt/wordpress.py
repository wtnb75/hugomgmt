import pprint
import click
import functools
import re
import urllib.parse
import mysql.connector as mydb
import datetime
import uuid
import requests
from typing import Optional
from pathlib import Path
from .util import make_template, sqlite_option, file_or_resource
from logging import getLogger
import lxml.html
import lxml.etree

_log = getLogger(__name__)


def mysql_option(func):
    @click.option("--socket", type=click.Path(exists=True),
                  envvar="DB_SOCKET", show_default=True, show_envvar=True)
    @click.option("--host", default="localhost", envvar="DB_HOST", show_default=True, show_envvar=True)
    @click.option("--port", type=int, default=3306, envvar="DB_PORT", show_default=True, show_envvar=True)
    @click.option("--user", envvar="DB_USER", show_default=True, show_envvar=True)
    @click.option("--password", envvar="DB_PASS", show_default=True, show_envvar=True)
    @click.option("--database", default="wordpress", envvar="DB_NAME", show_default=True, show_envvar=True)
    @functools.wraps(func)
    def _(socket, host, port, user, password, database, *args, **kwargs):
        if socket:
            conn = mydb.connect(
                unix_socket=socket, user=user, password=password,
                database=database)
        else:
            conn = mydb.connect(
                host=host, port=port, user=user,
                password=password, database=database)
        conn.ping(reconnect=True)
        return func(mysql_conn=conn, *args, **kwargs)
    return _


def template_option(func):
    @click.option("--template", envvar="WP_POST_TEMPLATE", default="template/post.md.j2", show_default=True)
    @functools.wraps(func)
    def _(template, *args, **kwargs):
        fp = file_or_resource(template)
        tmpl = make_template(fp.read())
        return func(template=tmpl, *args, **kwargs)
    return _


class WP:
    replacer = {}

    def __init__(self, conn, baseurl=None, path=None, uploads_dir=None, copy_resource=False):
        self.conn = conn
        self.cur = conn.cursor()
        self.wp_baseurl = baseurl
        self.hugo_path = path
        self.copy_resource = copy_resource
        self.wp_path = urllib.parse.urlparse(baseurl).path
        if uploads_dir:
            self.wp_uploads_path = Path(uploads_dir)
        else:
            self.wp_uploads_path = None
        if baseurl and path:
            root = urllib.parse.urljoin(baseurl, "/")
            archive = urllib.parse.urljoin(baseurl, r"archives/([0-9]+)")
            self.replacer = {
                archive: f"{path}/archives/\\1/",
                root: "/",
            }

    def select(self, table, **kwargs):
        _log.debug("SELECT(ALL): %s, args=%s", table, kwargs)
        args = tuple(kwargs.values())
        q = f'SELECT * FROM {table}'
        if len(kwargs) != 0:
            qargs = [f'{k} = %s' for k in kwargs.keys()]
            q += ' WHERE ' + ' AND '.join(qargs)
        self.cur.execute(q, args)
        keys = [x[0] for x in self.cur.description]
        return [dict(zip(keys, one)) for one in self.cur.fetchall()]

    def select_one(self, table, **kwargs):
        _log.debug("SELECT(1): %s, args=%s", table, kwargs)
        args = tuple(kwargs.values())
        q = f'SELECT * FROM {table}'
        if len(kwargs) != 0:
            qargs = [f'{k} = %s' for k in kwargs.keys()]
            q += ' WHERE ' + ' AND '.join(qargs)
        q += ' LIMIT 1'
        self.cur.execute(q, args)
        keys = [x[0] for x in self.cur.description]
        one = self.cur.fetchone()
        if one is None:
            return None
        return dict(zip(keys, one))

    def select_raw(self, q: str, args: tuple):
        self.cur.execute(q, args)
        keys = [x[0] for x in self.cur.description]
        return [dict(zip(keys, one)) for one in self.cur.fetchall()]

    def get_option(self, name: str) -> str:
        res = self.select_one('wp_options', option_name=name)
        if res:
            return res["option_value"]

    def posts(self):
        return self.select('wp_posts', post_status="publish", post_type="post")

    def get_post(self, id: int):
        return self.select_one('wp_posts', id=id)

    def comments(self):
        return self.select('wp_comments', comment_approved="1")

    def get_comment(self, post_id: int):
        return self.select('wp_comments', comment_post_ID=post_id)

    def pages(self):
        return self.select('wp_posts', post_status="publish", post_type="page")

    def get_page(self, id: int):
        return self.select_one('wp_posts', id=id)

    @functools.cached_property
    def permalink(self):
        return self.get_option("permalink_structure")

    @functools.cached_property
    def category(self):
        cats = self.select_raw(
            'SELECT * FROM wp_terms INNER JOIN wp_term_taxonomy ON wp_term_taxonomy.term_id = wp_terms.term_id'
            ' WHERE wp_term_taxonomy.taxonomy = %s', ("category", ))
        return {x["term_taxonomy_id"]: x["name"] for x in cats}

    @functools.cached_property
    def categorymap(self):
        rel = self.select('wp_term_relationships')
        res = {}
        for i in rel:
            key = int(i["object_id"])
            if i["term_taxonomy_id"] not in self.category:
                continue
            if key not in res:
                res[key] = []
            res[key].append(self.category[i["term_taxonomy_id"]])
        return res

    def download_replace(self, htmlstr: str, baseurl: str, replace_to: str = "./",
                         filepath: Optional[Path] = None) -> tuple[str, dict[str, bytes]]:
        # returns replaced-html, assets(filename:content)
        root = lxml.html.fromstring(htmlstr)
        urlmap = {}   # url: (filename, content)

        def update_urlmap(url: str) -> str:
            _log.debug("img/a to url: %s", url)
            if url in urlmap:
                # duplicate
                _log.debug("alread downloaded: %s", url)
                new_url = urlmap[url][0]
            else:
                new_url = replace_to + url.rsplit("/", 1)[-1]
                if new_url in dict(urlmap.values()):
                    new_url = replace_to + str(uuid.uuid4()) + Path(new_url).suffix
                content = None
                if filepath:
                    relative_url = Path(urllib.parse.unquote(url)).relative_to(baseurl)
                    target_file = filepath / relative_url
                    if target_file.exists():
                        _log.debug("file exists. read it: %s -> %s", target_file, new_url)
                        content = target_file.read_bytes()
                    else:
                        _log.debug("file does not exists: %s -> %s", target_file, new_url)
                if content is None:
                    _log.debug("fetch %s -> %s", url, new_url)
                    res = requests.get(url)
                    if res.status_code == 200:
                        content = res.content
                    else:
                        _log.warning("cannot get asset: %s -> %s", url, new_url)
                if content:
                    urlmap[url] = (new_url, content)
            return new_url

        for tag in root.xpath(f"//img[starts-with(@src, '{baseurl}')]"):
            burl = tag.attrib["src"]
            tag.attrib["src"] = update_urlmap(burl)
        for tag in root.xpath(f"//a[starts-with(@href, '{baseurl}')]"):
            burl = tag.attrib["href"]
            tag.attrib["href"] = update_urlmap(burl)
        return lxml.etree.tostring(root, encoding="utf-8").decode("utf-8"), dict(urlmap.values())

    def convert_post(self, post: dict) -> dict:
        if post is None:
            return post
        if isinstance(post["post_date"], str):
            post["post_date"] = datetime.datetime.fromisoformat(post["post_date"])
        post["categories"] = self.categorymap.get(post["ID"], [])
        post["post_id"] = post["ID"]
        post["post_path"] = self.post2url(post).lstrip("/")
        post["header"] = {
            "title": post["post_title"],
            "date": post["post_date"].astimezone().isoformat(),
            "url": post["post_path"],
            "post_id": post["post_id"],
            "draft": (post["post_status"] != "publish"),
            "categories": post["categories"]
        }
        ct: str = post["post_content"]
        if self.copy_resource:
            ct, assets = self.download_replace(
                ct, urllib.parse.urljoin(self.wp_baseurl, "wp-content/uploads/"),
                filepath=self.wp_uploads_path)
            post["assets"] = assets
        else:
            post["assets"] = {}
        for f, t in self.replacer.items():
            ct = re.sub(f, t, ct)
        post["post_content"] = ct
        return post

    def convert_comment(self, comment: dict) -> dict:
        return comment

    def convert_page(self, page: dict) -> dict:
        page = self.convert_post(page)
        page["header"]["url"] = "/" + page["post_name"] + "/"
        return page

    def post2url(self, post):
        return re.sub('%([a-z_]+)%', lambda m: str(post.get(m.group(1))), self.permalink)

    def category_redirect(self):
        pfx1 = self.wp_path
        pfx2 = self.hugo_path
        cats = self.select_raw(
            'SELECT * FROM wp_terms INNER JOIN wp_term_taxonomy ON wp_term_taxonomy.term_id = wp_terms.term_id'
            ' WHERE wp_term_taxonomy.taxonomy = %s', ("category", ))
        res = [
            "absolute_redirect off;",
            "if ($arg_wl_mode != '') {",
            "  set $args '';",
            "}",
            "if ($arg_wl_search != '') {",
            "  set $args '';",
            "}",
            f"rewrite ^{pfx1}feed/$ {pfx2}index.xml permanent;",
            f"rewrite ^{pfx1}page/([0-9]+)/$ {pfx2}page/$1/ permanent;",
            f"rewrite ^{pfx1}archives/([0-9]+)$ {pfx2}archives/$1/ permanent;",
            f"location = {pfx1} " + "{",
            "  if ($arg_p ~ [0-9]+) {",
            f"    return 301 {pfx2}archives/$arg_p/;",
            "  }",
            f"  return 301 {pfx2};",
            "}",
        ]
        skp = False
        for c in cats:
            slug = c["slug"]
            name = urllib.parse.quote(c["name"].lower())
            if slug == name:
                _log.debug("skip %s", slug)
                skp = True
                continue
            res.append(
                f"rewrite ^{pfx1}category/{slug}(/.*)?$ {pfx2}categories/{name}/ permanent;")
        if skp:
            res.append(
                f"rewrite ^{pfx1}category/(.*)/?$ {pfx2}categories/$1/ permanent;")
        return res

    def authors(self):
        q = """
SELECT `wp_users`.*, COUNT(*) AS `posts_total` FROM `wp_users`
    INNER JOIN `wp_posts` ON `wp_posts`.`post_author`=`wp_users`.`ID`
    GROUP BY `wp_users`.`ID`
"""
        return self.select_raw(q, ())


class IssoComment:
    def __init__(self, conn, url_prefix, url_suffix="/"):
        self.conn = conn
        self.cur = conn.cursor()
        self.url_prefix = url_prefix
        self.url_suffix = url_suffix

    def select(self, table, **kwargs):
        _log.debug("SELECT(ALL): %s, args=%s", table, kwargs)
        args = tuple(kwargs.values())
        q = f'SELECT * FROM {table}'
        if len(kwargs) != 0:
            qargs = [f'{k} = ?' for k in kwargs.keys()]
            q += ' WHERE ' + ' AND '.join(qargs)
        self.cur.execute(q, args)
        keys = [x[0] for x in self.cur.description]
        return [dict(zip(keys, one)) for one in self.cur.fetchall()]

    def select_one(self, table, **kwargs):
        _log.debug("SELECT(1): %s, args=%s", table, kwargs)
        args = tuple(kwargs.values())
        q = f'SELECT * FROM {table}'
        if len(kwargs) != 0:
            qargs = [f'{k} = ?' for k in kwargs.keys()]
            q += ' WHERE ' + ' AND '.join(qargs)
        q += ' LIMIT 1'
        self.cur.execute(q, args)
        keys = [x[0] for x in self.cur.description]
        one = self.cur.fetchone()
        if one is None:
            return None
        return dict(zip(keys, one))

    def select_raw(self, q: str, args: tuple):
        self.cur.execute(q, args)
        keys = [x[0] for x in self.cur.description]
        return [dict(zip(keys, one)) for one in self.cur.fetchall()]

    def insert_to(self, table, **kwargs):
        keys = kwargs.keys()
        values = tuple(kwargs.values())
        q = f'INSERT INTO {table} ('
        q += ", ".join(keys)
        q += ') VALUES ('
        q += ", ".join(["?"] * len(keys))
        q += ')'
        _log.debug("INSERT: q=%s, vals=%s", q, values)
        self.cur.execute(q, values)
        self.conn.commit()

    def get_thread(self, post_id):
        return self.select_one('threads', id=post_id)

    def create_thread(self, post_id, url, title):
        new_url = self.url_prefix+url+self.url_suffix
        self.insert_to(
            'threads', id=post_id, uri=new_url, title=title)

    def get_comment(self, post_id, comment_id):
        return self.select_one('comments', tid=post_id, id=comment_id)

    def create_comment(self, post_id, comment_id, **kwargs):
        self.insert_to('comments', id=comment_id, tid=post_id, **kwargs)

    def convert_comment(self, post, comment):
        key_conv = {
            "comment_id": "comment_ID",
            "parent": "comment_parent",
            "created": "comment_date",
            "remote_addr": "comment_author_IP",
            "text": "comment_content",
            "author": "comment_author",
            "email": "comment_author_email",
            "website": "comment_author_url",
        }
        url = post.get("post_path")
        title = post.get("post_title")
        post_id = post.get("post_id")
        # have thread?
        if self.get_thread(post_id) is None:
            _log.debug("thread does not exists: post=%s", post_id)
            # create thread
            self.create_thread(post_id, url, title)
        if self.get_comment(post_id, comment["comment_ID"]) is not None:
            # exists
            _log.info("comment exists: post=%s, comment=%s",
                      post_id, comment["comment_ID"])
            return
        # create comment
        kwargs = {k: comment[v] for k, v in key_conv.items()}
        kwargs["created"] = kwargs["created"].timestamp()
        if kwargs["parent"] == 0:
            kwargs.pop("parent")
        self.create_comment(
            post_id=post_id, mode=1, voters=b'',
            **kwargs)


def wordpress_option(func):
    @click.option("--baseurl", envvar="WP_URL", show_envvar=True)
    @click.option("--hugopath", envvar="HUGO_PATH", show_envvar=True)
    @click.option("--copy-resource/--no-copy-resource", default=False, show_default=True)
    @click.option("--uploads-dir", envvar="WP_UPLOADS_DIR", show_envvar=True)
    @mysql_option
    @functools.wraps(func)
    def _(baseurl, hugopath, mysql_conn, uploads_dir, copy_resource, *args, **kwargs):
        return func(wp=WP(mysql_conn, baseurl, hugopath, uploads_dir, copy_resource), *args, **kwargs)
    return _


@wordpress_option
def wp_check_db(wp: WP):
    """WP: (for debug) check database connection"""
    print("plink", wp.get_option("permalink_structure"))
    print("category")
    pprint.pprint(wp.category)


@wordpress_option
@click.argument("id", type=int)
def wp_post_info(wp: WP, id):
    """WP: show post info"""
    post = wp.convert_post(wp.get_post(id))
    pprint.pprint(post)


@wordpress_option
@click.argument("post_id", type=int)
def wp_comment_info(wp: WP, post_id):
    """WP: show comment info"""
    for c in wp.get_comment(post_id):
        cmt = wp.convert_comment(c)
        pprint.pprint(cmt)


@wordpress_option
def wp_comment_ids(wp: WP):
    """WP: show post/comment mapping"""
    res = {}
    for c in wp.comments():
        post_id = c["comment_post_ID"]
        comment_id = c["comment_ID"]
        if post_id not in res:
            res[post_id] = []
        res[post_id].append(comment_id)
    pprint.pprint(res)


@wordpress_option
def wp_list_post(wp: WP):
    """WP: list post/page ids"""
    click.echo("posts:")
    for p in wp.posts():
        post = wp.convert_post(p)
        # id size date urlpath
        click.echo(" %6d %6d %s %s" % (post['post_id'], len(post['post_content']),
                   post['post_date'].isoformat(), post['post_path']))
    click.echo("pages:")
    for p in wp.pages():
        page = wp.convert_page(p)
        click.echo(" %6d %6d %s %s" % (page['post_id'], len(page['post_content']),
                   page['post_date'].isoformat(), page['post_path']))


@wordpress_option
@template_option
@click.argument("id", type=int)
def wp_convpost1(wp: WP, id, template):
    """WP: convert single post to hugo markdown"""
    permalink = wp.get_option("permalink_structure")
    _log.debug("permalink: %s", permalink)
    post = wp.convert_post(wp.get_post(id))
    if post is None:
        raise click.BadParameter(f"post {id} not found")
    click.echo(template.render(post))
    for k, v in post["assets"].items():
        _log.debug("assets: %s: %s bytes", k, len(v))


@wordpress_option
@sqlite_option
@click.option("--url-prefix", envvar="HUGO_PATH", show_envvar=True)
@click.argument("id", type=int)
def wp_convcomment1(sqlite3_conn, wp: WP, url_prefix: str, id):
    """WP: convert single comment to isso"""
    isso = IssoComment(sqlite3_conn, url_prefix)
    permalink = wp.get_option("permalink_structure")
    _log.debug("permalink: %s", permalink)
    post = wp.convert_post(wp.get_post(id))
    title = post.get("post_title")
    post_id = post.get("post_id")
    # comments
    comments = wp.get_comment(post_id)
    if len(comments) == 0:
        _log.error("no comment found[%s] %s", post_id, title)
        return
    for c in comments:
        isso.convert_comment(post, c)


@wordpress_option
@template_option
@click.argument("outdir", type=click.Path(dir_okay=True, exists=True))
def wp_convpost_all(wp: WP, outdir, template):
    """WP: convert all post to hugo markdown"""
    outpath = Path(outdir)
    for p in wp.posts():
        post = wp.convert_post(p)
        # dt = post["post_date"]
        # outf: Path = outpath / dt.strftime("%Y-%m") / (dt.strftime("%Y-%m-%d-")+str(post["ID"])+".markdown")
        outf: Path = outpath / post["header"]["url"] / "post.md"
        outf.parent.mkdir(exist_ok=True, parents=True)
        outf.write_text(template.render(post))
        for k, v in post["assets"].items():
            _log.info("assets: %s: %s bytes", k, len(v))
            (outf.parent / k).write_bytes(v)
    for p in wp.pages():
        page = wp.convert_page(p)
        # dt = page["post_date"]
        # outf: Path = outpath / "pages" / (page["post_name"]+".markdown")
        outf: Path = outpath / "pages" / (page["post_name"].strip("/") + ".markdown")
        outf.parent.mkdir(exist_ok=True, parents=True)
        outf.write_text(template.render(page))
        for k, v in page["assets"].items():
            _log.info("assets: %s: %s bytes", k, len(v))
            (outf.parent / k).write_bytes(v)


@wordpress_option
@sqlite_option
@click.option("--url-prefix", envvar="HUGO_PATH", show_envvar=True)
def wp_convcomment_all(sqlite3_conn, wp: WP, url_prefix):
    """WP: convert all comment to isso"""
    isso = IssoComment(sqlite3_conn, url_prefix)
    permalink = wp.get_option("permalink_structure")
    _log.debug("permalink: %s", permalink)
    done_posts = set()
    for comment in wp.comments():
        post_id = comment["comment_post_ID"]
        if post_id not in done_posts:
            done_posts.add(post_id)
        post = wp.convert_post(wp.get_post(post_id))
        _log.debug("convert %s/%d", post_id, comment["comment_ID"])
        isso.convert_comment(post, comment)


@wordpress_option
def wp_get_redirect(wp: WP):
    """WP: create redirect configuration for nginx"""
    click.echo("\n".join(wp.category_redirect()))


@wordpress_option
@click.option("--output", type=click.Path(dir_okay=True, file_okay=False))
def wp_init_hugo(wp: WP, output):
    """WP: 'hugo new site' and apply short update to hugo.toml"""
    import subprocess
    import toml
    outpath = Path(output)
    subprocess.run(["hugo", "new", "site", output], check=True, encoding='utf-8')
    author = sorted(wp.authors(), key=lambda f: f.get('posts_total'), reverse=True)[0]
    _log.debug("author: %s", author)
    confpath = outpath / "hugo.toml"
    if wp.wp_baseurl and wp.hugo_path:
        hugo_url = urllib.parse.urljoin(wp.wp_baseurl, wp.hugo_path)
    else:
        hugo_url = wp.get_option('siteurl')
    hugodata = toml.load(confpath.open())
    hugodata.update({
        'title': wp.get_option('blogname'),
        'baseURL': hugo_url,
        'rssLimit': int(wp.get_option('posts_per_rss')),
        'summaryLength': 200,   # <- customize
        'hasCJKLanguage': True,
        'theme': "your-theme",  # <- FIXME
        'author': {
            'name': author['display_name'],
            'email': author['user_email'],
        },
        'params': {
            'subtitle': wp.get_option('blogdescription'),
            'author': {
                'name': author['display_name'],
                'email': author['user_email'],
            },
            'readMore': True,
            'isso': {   # depend on theme
                'enabled': True,
                'data': '/comments/',
                'jsLocation': '/comments/js/embed.min.js',
            },
        },
        'outputs': {
            'home': ["HTML", "RSS", ],
        },
        'menu': {
            'main': [{
                'identifier': 'archive',
                'name': 'Archive',
                'title': 'Archive',
                'url': '/archives/',
                'weight': 1,
            }, {
                'identifier': 'categories',
                'name': 'Categories',
                'title': 'Categories',
                'url': '/categories/',
                'weight': 1,
            }, {
                'identifier': 'pages',
                'name': 'Pages',
                'title': 'Pages',
                'url': '/pages/',
                'weight': 1,
            }]
        },
    })
    toml.dump(hugodata, confpath.open('w'))
