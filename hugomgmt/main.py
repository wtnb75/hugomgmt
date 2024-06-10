import click
import functools
from typing import Callable
from logging import getLogger
from .version import VERSION

_log = getLogger(__name__)


@click.group(invoke_without_command=True)
@click.pass_context
@click.version_option(version=VERSION, prog_name="hugomgmt")
def cli(ctx):
    if ctx.invoked_subcommand is None:
        print(ctx.get_help())


def verbose_option(func):
    @click.option("--verbose/--quiet", default=None)
    @functools.wraps(func)
    def _(verbose, *args, **kwargs):
        from logging import basicConfig
        level = "INFO"
        if verbose:
            level = "DEBUG"
        elif verbose is False:
            level = "WARNING"
        basicConfig(level=level, format="%(asctime)s %(levelname)s %(message)s")
        return func(*args, **kwargs)
    return _


def reg_cli():
    from . import wordpress
    from . import isso
    from . import staticsite
    from . import hugo

    def register_cli(mod, prefix):
        for i in dir(mod):
            if not i.startswith(prefix):
                continue
            if isinstance(getattr(mod, i), Callable):
                cli.command()(verbose_option(getattr(mod, i)))

    register_cli(wordpress, "wp_")
    register_cli(isso, "isso_")
    register_cli(hugo, "hugo_")
    register_cli(staticsite, "static_")


def main():
    reg_cli()
    cli()


if __name__ == "__main__":
    main()
