"""cli/config.py — config get / config set 命令组。"""
from __future__ import annotations

import json as _json
from pathlib import Path
from typing import Annotated, Any

import typer

from cli._common import DEFAULT_CONFIG_PATH, console, resolve_config_path

config_app = typer.Typer(name="config", help="配置文件管理", no_args_is_help=True, context_settings={"help_option_names": ["-h", "--help"]})


@config_app.command("get")
def config_get(
    key: Annotated[str, typer.Argument(help="配置键（支持点号路径，如 loop.debug）")],
    config: Annotated[Path, typer.Option("--config", "-c")] = DEFAULT_CONFIG_PATH,
) -> None:
    """读取配置文件中某个键的值。"""
    config = resolve_config_path(config)
    if not config.exists():
        console.print(f"[red]配置文件不存在: {config}[/red]")
        raise typer.Exit(1)

    cfg_data = _json.loads(config.read_text(encoding="utf-8"))
    parts = key.split(".")
    val = cfg_data
    try:
        for p in parts:
            val = val[p]
        console.print(f"{key} = [cyan]{_json.dumps(val, ensure_ascii=False)}[/cyan]")
    except (KeyError, TypeError):
        console.print(f"[yellow]键不存在: {key}[/yellow]")
        raise typer.Exit(1) from None


@config_app.command("set")
def config_set(
    key: Annotated[str, typer.Argument(help="配置键（支持点号路径，如 loop.debug）")],
    value: Annotated[str, typer.Argument(help="新值（true/false/数字/字符串自动推断类型）")],
    config: Annotated[Path, typer.Option("--config", "-c")] = DEFAULT_CONFIG_PATH,
) -> None:
    """修改配置文件中某个键的值（支持点号嵌套路径）。"""
    config = resolve_config_path(config)
    if not config.exists():
        console.print(f"[red]配置文件不存在: {config}[/red]")
        raise typer.Exit(1)

    cfg_data = _json.loads(config.read_text(encoding="utf-8"))

    # 类型推断
    parsed: Any
    if value.lower() == "true":
        parsed = True
    elif value.lower() == "false":
        parsed = False
    else:
        try:
            parsed = int(value)
        except ValueError:
            try:
                parsed = float(value)
            except ValueError:
                parsed = value

    parts = key.split(".")
    node = cfg_data
    for p in parts[:-1]:
        if p not in node or not isinstance(node[p], dict):
            node[p] = {}
        node = node[p]
    old = node.get(parts[-1], "(未设置)")
    node[parts[-1]] = parsed

    config.write_text(_json.dumps(cfg_data, ensure_ascii=False, indent=2), encoding="utf-8")
    console.print(
        f"[green]✓ {key}[/green]: "
        f"{_json.dumps(old, ensure_ascii=False)} → "
        f"[cyan]{_json.dumps(parsed, ensure_ascii=False)}[/cyan]"
    )


# ── 各 section 与其顶层字段名的对应关系 ──────────────────────────────────────
# 键：显示给用户的 group 名；值：Config 顶层字段（可以是嵌套 section 的 key）
_CONFIG_GROUPS: dict[str, list[str]] = {
    "model":      ["model", "routing", "model_fallbacks", "temperature", "timeout", "thinking"],
    "providers":  ["providers"],
    "loop":       ["loop"],
    "memory":     ["memory"],
    "emotion":    ["emotion"],
    "evolution":  ["evolution"],
    "soul":       ["soul"],
    "thresholds": ["thresholds"],
    "prompts":    ["prompts"],
}


@config_app.command("keys")
def config_keys(
    group: Annotated[str | None, typer.Argument(help=(
        "可选 group 名：model / providers / loop / memory / emotion / evolution / soul / thresholds / prompts。"
        "省略则列出所有分组的可调键。"
    ))] = None,
    with_defaults: Annotated[bool, typer.Option("--defaults", "-d", help="同时显示默认值")] = False,
) -> None:
    """列出所有可调配置键（按分组），附带描述和默认值。

    用于发现 config.set 可以写入哪些字段，以及它们的含义。
    示例::

        lingzhou config keys
        lingzhou config keys loop
        lingzhou config keys memory --defaults
    """
    from core.config import Config as _Config
    schema = _Config.model_json_schema()
    defs = schema.get("$defs", {})
    top_props = schema.get("properties", {})

    def _get_section_props(section_key: str) -> dict[str, Any]:
        """返回某 section 的属性字典（展开 $ref）。"""
        field_schema = top_props.get(section_key, {})
        ref = field_schema.get("$ref", "") or (
            field_schema.get("anyOf", [{}])[0].get("$ref", "")
        )
        if ref:
            model_name = ref.rsplit("/", 1)[-1]
            return defs.get(model_name, {}).get("properties", {})
        return field_schema.get("properties", {})

    def _print_group(group_name: str, top_keys: list[str]) -> None:
        from rich.table import Table
        table = Table(
            title=f"[bold]{group_name}[/bold]",
            show_header=True,
            header_style="bold cyan",
            show_lines=False,
            expand=False,
        )
        table.add_column("键路径", style="green", no_wrap=True)
        if with_defaults:
            table.add_column("默认值", style="yellow", no_wrap=True)
        table.add_column("说明", style="white")

        for top_key in top_keys:
            section_props = _get_section_props(top_key)
            if not section_props:
                # 顶层简单字段（如 model、temperature）
                field = top_props.get(top_key, {})
                desc = field.get("description", "")
                default = field.get("default", "")
                row = [top_key, _json.dumps(default, ensure_ascii=False) if with_defaults else None, desc]
                table.add_row(*[r for r in row if r is not None])
                continue
            for field_name, field_schema in section_props.items():
                if field_name.startswith("_"):
                    continue
                path = f"{top_key}.{field_name}"
                desc = field_schema.get("description", "")
                if with_defaults:
                    default = field_schema.get("default", "")
                    table.add_row(path, _json.dumps(default, ensure_ascii=False), desc)
                else:
                    table.add_row(path, desc)

        console.print(table)

    groups_to_show = (
        {group: _CONFIG_GROUPS[group]}
        if group and group in _CONFIG_GROUPS
        else _CONFIG_GROUPS
    )
    if group and group not in _CONFIG_GROUPS:
        console.print(
            f"[red]未知 group '{group}'，可选：{', '.join(_CONFIG_GROUPS)}[/red]"
        )
        raise typer.Exit(1)

    for gname, gkeys in groups_to_show.items():
        _print_group(gname, gkeys)


@config_app.command("schema")
def config_schema(
    output: Annotated[Path | None, typer.Option("--output", "-o", help="输出文件路径（默认打印到 stdout）")] = None,
) -> None:
    """导出完整 JSON Schema（供 IDE 自动补全 lingzhou.json）。

    示例::

        lingzhou config schema > lingzhou-schema.json
        lingzhou config schema -o ~/.lingzhou/lingzhou-schema.json
    """
    from core.config import Config as _Config
    schema = _Config.model_json_schema()
    # 加 $schema meta 字段让 IDE 识别
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["title"] = "lingzhou configuration"
    text = _json.dumps(schema, ensure_ascii=False, indent=2)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
        console.print(f"[green]✓ schema 已写入 {output}[/green]")
    else:
        console.print(text)
