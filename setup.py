from pathlib import Path
from setuptools import setup

extras_require = {
    x.stem.split("-", 1)[-1]: x.read_text().splitlines()
    for x in Path(__file__).parent.glob("requirements-*.txt")
}

setup(
    install_requires=Path("requirements.txt").read_text().splitlines(),
    extras_require=extras_require
)
