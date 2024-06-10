from abc import ABCMeta, abstractmethod
import shlex
from logging import getLogger

_log = getLogger(__name__)


class ShortCodeBase(metaclass=ABCMeta):
    """
    >>> import pprint
    >>> class Tag(ShortCodeBase):
    ...     def __init__(self):
    ...         super().__init__("tag")
    ...     def process_tag(self, attrs: dict, text: str) -> str:
    ...         return str(attrs) + text
    >>> sb = Tag()
    >>> text = 'hello [tag attr1="hello" /] world [tag attr1="hello" attr2="world"]this text[/tag]'
    >>> res = sb.split_tag(text)
    >>> sb.join_tag(res)
    'hello [tag attr1=hello /] world [tag attr1=hello attr2=world]this text[/tag]'
    >>> pprint.pprint(res) # doctest: +NORMALIZE_WHITESPACE
    [{'text': 'hello ', 'type': 'text'},
        {'attrs': {'attr1': 'hello'}, 'text': '', 'type': 'tag'},
        {'text': ' world ', 'type': 'text'},
        {'attrs': {'attr1': 'hello', 'attr2': 'world'},
        'text': 'this text',
        'type': 'tag'}]
    >>> "".join(sb.process(text))
    "hello {'attr1': 'hello'} world {'attr1': 'hello', 'attr2': 'world'}this text"
    """

    def __init__(self, tag):
        self.tag = tag
        self.tag_open_start = '[' + self.tag
        self.tag_open_end = ']'
        self.tag_openclose_end = '/'
        self.tag_close = '[/' + self.tag + ']'

    def parse_attr(self, text) -> dict:
        res = {}
        for i in shlex.split(text):
            kv = i.split("=", 1)
            if len(kv) == 2:
                res[kv[0]] = kv[1]
            elif len(kv) == 1:
                res[kv[0]] = True
        return res

    def join_tag(self, tags: list[dict]) -> str:
        res = ""
        for i in tags:
            if i["type"] == "text":
                res += i["text"]
            elif i["type"] == "tag":
                res += self.tag_open_start
                for k, v in i["attrs"].items():
                    if v is True:
                        res += " " + k
                    else:
                        res += " " + k + "=" + shlex.quote(v)
                if i["text"] == "":
                    res += " " + self.tag_openclose_end + self.tag_open_end
                else:
                    res += self.tag_open_end
                    res += i["text"]
                    res += self.tag_close
        return res

    def split_tag(self, text: str) -> list[dict]:
        res = []
        while len(text) != 0:
            index = text.find(self.tag_open_start)
            _log.debug("text=%s, find=%s, index=%s", text,
                       self.tag_open_start, index)
            if index == -1:
                res.append({"type": "text", "text": text})
                _log.debug("not found")
                break
            elif index > 0:
                res.append({"type": "text", "text": text[:index]})
                text = text[index:]
            i1 = text.find(self.tag_open_end)
            if i1 == -1:
                res.append({"type": "text", "text": text})
                _log.debug("not opened")
                break
            if text[:i1].endswith(self.tag_openclose_end):
                attrs = self.parse_attr(
                    text[len(self.tag_open_start):i1-len(self.tag_openclose_end)])
                res.append({"type": "tag", "attrs": attrs, "text": ""})
                text = text[i1+1:]
                _log.debug("simple tag found")
                continue
            else:
                attrs = self.parse_attr(text[len(self.tag_open_start):i1])
                rest = text[i1+1:]
                i2 = rest.find(self.tag_close)
                if i2 == -1:
                    # no close tag -> ignore
                    res.append({"type": "text", "text": text[:i1]})
                    text = text[i1:]
                    _log.debug("not closed")
                    continue
                _log.debug("tag found")
                res.append({"type": "tag", "attrs": attrs, "text": rest[:i2]})
                text = rest[i2+len(self.tag_close):]
        return res

    @abstractmethod
    def process_tag(self, attrs: dict, text: str) -> str:
        pass

    def process(self, text):
        for i in self.split_tag(text):
            if i["type"] == "text":
                yield i["text"]
            elif i["type"] == "tag":
                arg = i.copy()
                arg.pop("type")
                yield self.process_tag(**arg)
