"""cli/main.py — CLI 入口（纯注册层，不含业务逻辑）。"""
from __future__ import annotations

from typing import Annotated

import typer

from cli.common import DEFAULT_CONFIG_PATH, console
from cli.auth import auth_app
from cli.bootstrap import init, is_onboarded, onboard, setup
from cli.chat import chat
from cli.config import config_app
from cli.dev import dev_app
from cli.gateway import gateway_app, gateway_start, run, stop
from cli.task import task_app
from core.version import __codename__, __version__


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"lingzhou v{__version__} ({__codename__})")
        raise typer.Exit()


app = typer.Typer(
    name="lingzhou",
    help="自编程自进化认知 agent 种子",
    no_args_is_help=False,
    invoke_without_command=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)


@app.callback()
def app_callback(
    ctx: typer.Context,
    version: Annotated[
        bool | None,
        typer.Option("--version", "-V", callback=_version_callback, is_eager=True, help="显示版本号"),
    ] = None,
) -> None:
    """自编程自进化认知 agent 种子。未初始化时自动进入首次引导。"""
    if ctx.invoked_subcommand is None:
        if not is_onboarded(DEFAULT_CONFIG_PATH):
            onboard(config=DEFAULT_CONFIG_PATH, start=True)
            return
        gateway_start(channel="local", daemon=False)


app.add_typer(auth_app)
app.add_typer(config_app)
app.add_typer(gateway_app)
app.add_typer(task_app)
app.add_typer(dev_app)

app.command()(run)
app.command()(stop)
app.command()(chat)

app.command()(onboard)
app.command()(setup)
app.command()(init)


@app.command(name="help", hidden=True)
def _help(ctx: typer.Context) -> None:
    """显示帮助信息（等同于 --help）。"""
    import subprocess
    import sys

    subprocess.run([sys.argv[0], "--help"])


def _normalize_help_args() -> None:
    """将 -help / --h 等非标准 help 变体规范化为 --help。"""
    import sys

    help_aliases = {"-help", "--h", "-?", "/?"}
    sys.argv = ["--help" if arg in help_aliases else arg for arg in sys.argv]


def main() -> None:
    """CLI 入口（pyproject.toml 中的 scripts 指向此函数）。"""
    _normalize_help_args()
    app()


if __name__ == "__main__":
    main()
