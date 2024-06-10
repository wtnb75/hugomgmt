import click
import sys
import yaml
import functools
import sqlite3
import datetime
from .util import make_template, sqlite_option, file_or_resource
from logging import getLogger

_log = getLogger(__name__)


def comment_option(func):
    @click.option("--baseurl", type=str, envvar="HUGO_BASE_URL", show_envvar=True)
    @click.option("--days", type=int, default=None)
    @click.option("--last", type=int, default=10, show_default=True)
    @click.option("--offset", type=int, default=0, show_default=True)
    @functools.wraps(func)
    def _(*args, **kwargs):
        return func(*args, **kwargs)
    return _


def _isso_getdata(cur: sqlite3.Cursor, base, q, qargs) -> list[dict]:
    ret = []
    res = cur.execute(q, qargs)
    keys = [x[0] for x in res.description]
    tskeys = ['created', 'modified']
    for i in res.fetchall():
        v = dict(zip(keys, i))
        for k in tskeys:
            if k in v and v[k] is not None:
                v[k] = datetime.datetime.fromtimestamp(v[k]).astimezone()
        tid = v['tid']
        r2 = cur.execute('SELECT * FROM threads WHERE id = ?', (tid, ))
        k2 = [x[0] for x in r2.description]
        th = r2.fetchone()
        thread = dict(zip(k2, th))
        _log.debug("result: %s / %s", thread, v)
        ent = base.copy()
        ent.update({
            "thread": thread,
            "comment": v,
        })
        ret.append(ent)
    return ret


@click.option("--sqlite", type=click.Path(dir_okay=False), envvar="ISSO_DB", show_envvar=True)
def isso_initdb(sqlite):
    """ISSO: create tables"""
    initdb_sql = """
CREATE TABLE IF NOT EXISTS preferences (
    key VARCHAR PRIMARY KEY,
    value VARCHAR
);
CREATE TABLE IF NOT EXISTS threads (
    id INTEGER PRIMARY KEY,
    uri VARCHAR(256) UNIQUE,
    title VARCHAR(256)
);
CREATE TABLE IF NOT EXISTS comments (
    tid REFERENCES threads(id),
    id INTEGER PRIMARY KEY,
    parent INTEGER,
    created FLOAT NOT NULL,
    modified FLOAT,
    mode INTEGER,
    remote_addr VARCHAR,
    text VARCHAR,
    author VARCHAR,
    email VARCHAR,
    website VARCHAR,
    likes INTEGER DEFAULT 0,
    dislikes INTEGER DEFAULT 0,
    voters BLOB NOT NULL,
    notification INTEGER DEFAULT 0
);
CREATE TRIGGER IF NOT EXISTS remove_stale_threads AFTER DELETE ON comments BEGIN
    DELETE FROM threads WHERE id NOT IN (SELECT tid FROM comments);
END;
"""
    sqlite3_conn = sqlite3.connect(sqlite)
    cur = sqlite3_conn.cursor()
    res = cur.executescript(initdb_sql)
    click.echo(res.fetchall())


def _isso_make_query(days: int, last: int, offset: int) -> tuple[str, tuple]:
    if days is not None:
        start_ts = (datetime.datetime.now() - datetime.timedelta(days=days)).timestamp()
        q = 'SELECT * FROM comments WHERE created > ? ORDER BY created'
        qargs = (start_ts,)
    else:
        q = 'SELECT * FROM comments ORDER BY created DESC LIMIT ? OFFSET ?'
        qargs = (last, offset)
    return q, qargs


@sqlite_option
@comment_option
def isso_list_comment(sqlite3_conn: sqlite3.Connection, days: int, last: int, offset: int, baseurl: str):
    """ISSO: show recent comments"""
    cur = sqlite3_conn.cursor()
    q, qargs = _isso_make_query(days, last, offset)
    for ent in _isso_getdata(cur, {"blog": {"baseurl": baseurl}}, q, qargs):
        yaml.dump(ent, stream=sys.stdout, allow_unicode=True, sort_keys=False)


@sqlite_option
@comment_option
@click.option("--smtp-host", default="localhost", show_default=True)
@click.option("--smtp-port", type=int, default=25, show_default=True)
@click.option("--dry/--wet", default=True, show_default=True)
@click.option("--single-template", default="template/single-comment.mail.j2", show_default=True)
@click.option("--multi-template", default="template/multi-comment.mail.j2", show_default=True)
@click.option("--mail-from", envvar="ISSO_MAIL_FROM", show_envvar=True)
@click.option("--mail-to", envvar="ISSO_MAIL_TO", show_envvar=True)
def isso_mail_comment(sqlite3_conn: sqlite3.Connection, days: int, last: int, offset: int, baseurl: str,
                      dry: bool, smtp_host: str, smtp_port: int, mail_from, mail_to,
                      single_template, multi_template):
    """ISSO: show recent comments"""
    import smtplib
    from email.parser import Parser
    import email.policy
    cur = sqlite3_conn.cursor()
    q, qargs = _isso_make_query(days, last, offset)
    base = {"blog": {"baseurl": baseurl}}
    comments = _isso_getdata(cur, base, q, qargs)
    if len(comments) == 0:
        # empty
        _log.info("no comments exists")
        return
    if len(comments) == 1:
        # single mail
        tmpl = make_template(file_or_resource(single_template).read())
        mail_str = tmpl.render(**comments[0])
        msg = Parser(policy=email.policy.default).parsestr(mail_str)
        if mail_from:
            msg['From'] = mail_from
        if mail_to:
            msg['To'] = mail_to
        if dry:
            click.echo(msg.as_string())
        else:
            with smtplib.SMTP(host=smtp_host, port=smtp_port) as s:
                s.send_message(msg)
    else:
        tmpl = make_template(file_or_resource(multi_template).read())
        mail_str = tmpl.render(comments=comments, **base)
        msg = Parser(policy=email.policy.default).parsestr(mail_str)
        if mail_from:
            msg['From'] = mail_from
        if mail_to:
            msg['To'] = mail_to
        if dry:
            click.echo(msg.as_string())
        else:
            with smtplib.SMTP(host=smtp_host, port=smtp_port) as s:
                s.send_message(msg)
