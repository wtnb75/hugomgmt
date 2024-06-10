from .shortcode import ShortCodeBase


class Tex(ShortCodeBase):
    def __init__(self):
        super().__init__('tex')

    def process_tag(self, attrs: dict, text: str):
        return '$' + text + '$'


def process(text: str):
    return "".join(Tex().process(text))
