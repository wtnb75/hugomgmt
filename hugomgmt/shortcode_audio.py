from .shortcode import ShortCodeBase


class Audio(ShortCodeBase):
    def __init__(self):
        super().__init__('audio')

    def process_tag(self, attrs: dict, text: str):
        url = attrs.get("mp3", None)
        if url:
            return f'<audio controls><source src="{url}" type="audio/mpeg"/>' + text + '</audio>'
        return ''


def process(text: str):
    return "".join(Audio().process(text))
