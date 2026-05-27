"""cli/plugin.py — 插件管理命令。"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.table import Table

from cli._common import console

plugin_app = typer.Typer(name="plugin", help="插件管理", no_args_is_help=True)
PLUGINS_DIR = Path(__file__).parent.parent / "plugins"


@plugin_app.command("list")
def plugin_list() -> None:
    """列出所有已安装插件。"""
    from core.plugin import PluginManager
    pm = PluginManager(PLUGINS_DIR)
    manifests = pm.discover()
    if not manifests:
        console.print("[dim]无插件[/dim]")
        console.print(f"[dim]将插件放入 {PLUGINS_DIR}/<name>/ 即可[/dim]")
        return

    table = Table(title="已安装插件")
    table.add_column("ID", style="cyan")
    table.add_column("名称")
    table.add_column("版本")
    table.add_column("描述")

    for m in manifests:
        table.add_row(m.id, m.name, m.version, m.description[:40])

    console.print(table)


@plugin_app.command("install")
def plugin_install(
    name: Annotated[str, typer.Argument(help="插件标识（用于目录名）")],
    source: Annotated[str | None, typer.Option("--source", "-s", help="插件源码路径")] = None,
) -> None:
    """安装插件。创建插件目录骨架或从 source 复制。"""
    plugin_dir = PLUGINS_DIR / name
    if plugin_dir.exists():
        console.print(f"[yellow]插件 {name} 已存在: {plugin_dir}[/yellow]")
        return

    if source:
        import shutil
        src_path = Path(source).expanduser().resolve()
        if not src_path.exists():
            console.print(f"[red]源路径不存在: {src_path}[/red]")
            raise typer.Exit(1)
        shutil.copytree(src_path, plugin_dir)
        console.print(f"[green]✓ 已安装: {name} ← {src_path}[/green]")
    else:
        plugin_dir.mkdir(parents=True)
        import json
        manifest = {
            "id": name,
            "name": name,
            "version": "0.1.0",
            "description": f"{name} plugin",
        }
        (plugin_dir / "plugin.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
        (plugin_dir / "__init__.py").write_text('"""插件初始化。"""\n\ndef register(ctx):\n    """注册工具/通道。"""\n    pass\n')
        console.print(f"[green]✓ 已创建插件骨架: {plugin_dir}[/green]")


@plugin_app.command("remove")
def plugin_remove(
    name: Annotated[str, typer.Argument(help="插件 ID")],
) -> None:
    """移除插件。"""
    plugin_dir = PLUGINS_DIR / name
    if not plugin_dir.exists():
        console.print(f"[yellow]插件 {name} 不存在[/yellow]")
        return
    import shutil
    shutil.rmtree(plugin_dir)
    console.print(f"[green]✓ 已移除: {name}[/green]")
