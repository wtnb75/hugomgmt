import csv
import io
from .shortcode import ShortCodeBase


class Csv(ShortCodeBase):
    def __init__(self):
        super().__init__("csv")

    def process_tag(self, attrs: dict, text: str):
        res = io.StringIO()
        txt = "\n".join([
            x.strip() for x in text.splitlines() if x.strip() != ""])
        rd = csv.reader(io.StringIO(txt))
        hdr = next(rd)
        print("| " + " | ".join(hdr) + " |", file=res)
        print("|"+"|".join(["---"] * len(hdr))+"|", file=res)
        for i in rd:
            if len(i) == 0:
                continue
            print("| " + " | ".join(i) + " |", file=res)
        return res.getvalue()


def process(text: str):
    return "".join(Csv().process(text))
