from .shortcode import ShortCodeBase


class Ignore(ShortCodeBase):
    def process_tag(self, attrs: dict, text: str):
        return text


def process(text: str):
    for i in ["gradient", "tegaki"]:
        text = "".join(Ignore(i).process(text))
    return text
