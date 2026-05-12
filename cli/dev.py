"""cli/dev.py — evolve / tools / model / update 命令（开发者工具）。"""
from __future__ import annotations

import asyncio
import json as _json
import shutil
import subprocess
from pathlib import Path
from typing import Annotated, Optional

import typer

from cli._common import console, load_cfg, PROJECT_ROOT
from core.version import __version__, __codename__


def evolve(
    description: Annotated[str, typer.Argument(help="新工具的自然语言描述")],
    config: Annotated[Path, typer.Option("--config", "-c")] = Path("lingzhou.json"),
) -> None:
    """合成并热加载一个新工具（自进化）。"""
    cfg = load_cfg(config)

    async def _run() -> None:
        from provider import create_provider
        from tools.registry import ToolRegistry
        from core.evolution import EvolutionEngine

        provider = create_provider(cfg)
        registry = ToolRegistry()
        engine = EvolutionEngine(cfg, provider, registry)
        result = await engine.synthesize_tool(description)
        await provider.close()
        if result.success:
            console.print(f"[green]工具 {result.target!r} 已合成[/green]")
        else:
            console.print(f"[red]合成失败: {result.reason}[/red]")

    asyncio.run(_run())


def tools(
    search: Annotated[Optional[str], typer.Argument(help="关键词过滤")] = None,
) -> None:
    """列出所有已注册的工具（支持关键词过滤）。"""
    from tools.registry import ToolRegistry

    reg = ToolRegistry()
    tools_dir = PROJECT_ROOT / "tools"
    reg.discover(tools_dir)
    manifests = reg.list_manifests()

    if search:
        kw = search.lower()
        manifests = [
            m for m in manifests
            if kw in m.name.lower() or kw in (m.description or "").lower()
        ]

    if not manifests:
        console.print("（没有匹配的工具）")
        return

    console.print(f"[bold]已注册工具[/bold]  ({len(manifests)} 个)\n")
    for m in sorted(manifests, key=lambda x: x.name):
        console.print(f"  [cyan]{m.name:<26}[/cyan] {m.description or ''}")


def model(
    set_model: Annotated[Optional[str], typer.Argument(help="要切换的模型 ID，如 bailian/qwen-plus")] = None,
    config: Annotated[Path, typer.Option("--config", "-c")] = Path("lingzhou.json"),
    list_all: Annotated[bool, typer.Option("--list", "-l", help="列出所有可用模型")] = False,
    interactive: Annotated[bool, typer.Option("--interactive", "-i", help="交互式选择 provider 和模型")] = False,
) -> None:
    """查看或切换当前使用的 LLM provider / 模型。"""
    from provider.catalog import list_providers, list_provider_models

    if list_all:
        for pname in list_providers():
            models_list = list_provider_models(pname)
            console.print(f"\n[bold]{pname}[/bold]")
            for m in models_list:
                ctx_k = (m.get("context_window") or 0) // 1000
                tags = []
                if m.get("thinking"):
                    tags.append("thinking")
                if m.get("reasoning"):
                    tags.append("reasoning")
                tag_str = f"  [dim][{', '.join(tags)}][/dim]" if tags else ""
                ctx_str = f"  [dim]{ctx_k}K[/dim]" if ctx_k else ""
                console.print(f"  {m['id']}{ctx_str}{tag_str}")
        return

    cfg_path = config if config.exists() else None
    # 尝试在搜索路径中找到配置
    if cfg_path is None:
        from cli._common import find_config
        try:
            cfg_path = find_config(config)
        except SystemExit:
            cfg_path = None

    if cfg_path is None or not cfg_path.exists():
        console.print(f"[red]配置文件不存在: {config}，请先运行 lingzhou setup[/red]")
        raise typer.Exit(1)

    cfg_data = _json.loads(cfg_path.read_text(encoding="utf-8"))
    current = cfg_data.get("model", "(未设置)")

    # ── 交互式选择 ─────────────────────────────────────────────────────────
    if interactive or (not set_model):
        console.print(f"当前模型: [bold cyan]{current}[/bold cyan]")
        if not interactive:
            console.print(f"[dim]切换模型: lingzhou model <provider/model-id>[/dim]")
            console.print(f"[dim]交互切换: lingzhou model -i[/dim]")
            console.print(f"[dim]查看全部: lingzhou model --list[/dim]")
            return

        # 交互式：先选 provider
        configured_providers = list(cfg_data.get("providers", {}).keys())
        all_catalog = list_providers()
        # 配置了的 provider 排在前面
        ordered = configured_providers + [p for p in all_catalog if p not in configured_providers]

        console.print("\n[bold]选择 provider[/bold]")
        for i, p in enumerate(ordered, 1):
            mark = "[green]✓[/green]" if p in configured_providers else "[dim]  [/dim]"
            console.print(f"  {i}. {mark} {p}")

        raw_p = typer.prompt("Provider 编号", default="1")
        try:
            pidx = int(raw_p.strip()) - 1
        except ValueError:
            pidx = 0
        if not (0 <= pidx < len(ordered)):
            console.print("[red]无效编号[/red]")
            raise typer.Exit(1)
        chosen_provider = ordered[pidx]

        # 如果选了未配置的 provider，提示先 setup
        if chosen_provider not in configured_providers:
            console.print(f"[yellow]{chosen_provider} 未在配置文件的 providers 中定义。[/yellow]")
            console.print(f"[dim]请先在 lingzhou.json 的 providers 中添加 {chosen_provider} 的配置，或运行 lingzhou setup。[/dim]")
            raise typer.Exit(1)

        # 选模型
        catalog_models = list_provider_models(chosen_provider)
        console.print(f"\n[bold]选择模型[/bold]  [dim](provider={chosen_provider})[/dim]")
        if catalog_models:
            for i, m in enumerate(catalog_models, 1):
                ctx_k = (m.get("context_window") or 0) // 1000
                tags = []
                if m.get("thinking"):
                    tags.append("thinking")
                if m.get("reasoning"):
                    tags.append("reasoning")
                ctx_str = f"  [dim]{ctx_k}K[/dim]" if ctx_k else ""
                tag_str = f"  [dim][{', '.join(tags)}][/dim]" if tags else ""
                console.print(f"  {i}. {m['id']}{ctx_str}{tag_str}")
            console.print(f"  {len(catalog_models)+1}. 手动输入")
            raw_m = typer.prompt("  模型编号", default="1")
            try:
                midx = int(raw_m.strip()) - 1
            except ValueError:
                midx = -1
            if 0 <= midx < len(catalog_models):
                chosen_model_id = catalog_models[midx]["id"]
            else:
                chosen_model_id = typer.prompt("  手动输入模型 ID")
        else:
            chosen_model_id = typer.prompt(f"  {chosen_provider} 模型 ID")

        set_model = f"{chosen_provider}/{chosen_model_id}"

    # ── 写入配置 ───────────────────────────────────────────────────────────
    cfg_data["model"] = set_model
    cfg_path.write_text(_json.dumps(cfg_data, ensure_ascii=False, indent=2), encoding="utf-8")
    console.print(f"[green]✓ 模型已切换:[/green] {current} → [bold cyan]{set_model}[/bold cyan]")
    console.print("[dim]lingzhou 运行中时将在下一轮自动生效（配置热重载）[/dim]")


def update() -> None:
    """更新 lingzhou 到最新版本（git pull + 重新安装依赖）。"""
    console.print(f"当前版本: [bold]v{__version__}[/bold]  代号: {__codename__}")

    repo_dir = PROJECT_ROOT
    if not (repo_dir / ".git").exists():
        console.print("[yellow]当前目录不是 git 工作区，请手动拉取最新代码后重新安装：[/yellow]")
        console.print("  git pull && uv pip install -e .")
        raise typer.Exit(1)

    console.print("[dim]执行 git pull...[/dim]")
    result = subprocess.run(["git", "pull"], cwd=repo_dir, capture_output=True, text=True)
    if result.returncode != 0:
        console.print(f"[red]git pull 失败:[/red]\n{result.stderr.strip()}")
        raise typer.Exit(1)
    console.print(f"[green]{result.stdout.strip() or 'Already up to date.'}[/green]")

    uv = shutil.which("uv")
    pip_cmd = [uv, "pip", "install", "-e", "."] if uv else [
        shutil.which("pip") or "pip", "install", "-e", "."
    ]
    console.print(f"[dim]重装依赖: {' '.join(pip_cmd)}[/dim]")
    result = subprocess.run(pip_cmd, cwd=repo_dir, capture_output=True, text=True)
    if result.returncode == 0:
        console.print("[green]✓ 更新完成，重启 lingzhou 生效[/green]")
    else:
        console.print(f"[red]依赖安装失败:[/red]\n{result.stderr.strip()}")
        raise typer.Exit(1)
