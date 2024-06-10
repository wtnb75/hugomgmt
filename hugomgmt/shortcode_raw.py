from .shortcode import ShortCodeBase


class Raw(ShortCodeBase):
    def __init__(self):
        super().__init__('raw')

    def process_tag(self, attrs: dict, text: str):
        return text.replace('[', '&#91;')


def process(text: str):
    return "".join(Raw().process(text))
