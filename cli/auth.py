"""cli/auth.py — auth 命令组（GitHub Copilot 凭证授权）。"""
from __future__ import annotations

import os
import subprocess
import time
import json as _json
from pathlib import Path
from typing import Annotated

import typer
from rich.panel import Panel

from cli._common import console, load_cfg

auth_app = typer.Typer(name="auth", help="凭证授权管理")


@auth_app.command("copilot")
def auth_copilot(
    config: Annotated[Path, typer.Option("--config", "-c")] = Path("lingzhou.json"),
    force: Annotated[bool, typer.Option("--force/--no-force", help="已有 token 时强制重新授权")] = False,
) -> None:
    """交互式授权 GitHub Copilot（Device Flow / gh CLI / 手动 PAT）。

    获取的 token 持久化到 ~/.lingzhou/credentials.json，
    下次启动时 provider 自动读取，无需手动 export GITHUB_TOKEN。

    认证顺序：
    1. gh CLI（已安装时最简单）
    2. GitHub OAuth Device Flow（需在 lingzhou.json 配置 oauth_client_id）
    3. 手动粘贴 Personal Access Token（PAT）
    """
    import httpx

    cred_file = Path("~/.lingzhou/credentials.json").expanduser()
    cred_file.parent.mkdir(parents=True, exist_ok=True)

    # 读取已有凭证
    existing: dict = {}
    if cred_file.exists():
        try:
            existing = _json.loads(cred_file.read_text(encoding="utf-8"))
        except Exception:
            existing = {}

    if existing.get("GITHUB_TOKEN") and not force:
        console.print("[yellow]已存在 GitHub token（使用 --force 重新授权）[/yellow]")
        masked = existing["GITHUB_TOKEN"][:8] + "..." + existing["GITHUB_TOKEN"][-4:]
        console.print(f"  当前 token: [dim]{masked}[/dim]")
        raise typer.Exit(0)

    token: str = ""

    # ── 路径 1：gh CLI ──────────────────────────────────────────────────
    console.print("\n[bold]尝试路径 1/3：gh CLI[/bold]")
    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            token = result.stdout.strip()
            if token:
                console.print(f"[green]✓ 通过 gh CLI 获取 token[/green]")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        console.print("  gh CLI 未找到，跳过")

    # ── 路径 2：GitHub OAuth Device Flow ───────────────────────────────
    if not token:
        console.print("\n[bold]尝试路径 2/3：GitHub OAuth Device Flow[/bold]")

        # 读取 client_id：lingzhou.json → 环境变量
        client_id = ""
        try:
            cfg = load_cfg(config)
            pdef = cfg.active_provider
            client_id = getattr(pdef, "oauth_client_id", "") or ""
        except Exception:
            pass
        if not client_id:
            client_id = os.environ.get("LINGZHOU_GITHUB_CLIENT_ID", "").strip()

        if not client_id:
            console.print(
                "  [dim]未配置 oauth_client_id，跳过 Device Flow。\n"
                "  如需使用 Device Flow，请在 lingzhou.json 的 providers.copilot 节\n"
                "  添加: \"oauth_client_id\": \"<your_github_oauth_app_client_id>\"\n"
                "  或设置环境变量: export LINGZHOU_GITHUB_CLIENT_ID=Iv1.xxxx[/dim]"
            )
        else:
            try:
                # 1. 请求 device code
                resp = httpx.post(
                    "https://github.com/login/device/code",
                    headers={"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"},
                    content=f"client_id={client_id}&scope=read%3Auser",
                    timeout=15.0,
                )
                resp.raise_for_status()
                dc = resp.json()
                if "error" in dc:
                    raise RuntimeError(dc.get("error_description", dc["error"]))

                user_code: str = dc["user_code"]
                device_code: str = dc["device_code"]
                verification_uri: str = dc["verification_uri"]
                expires_in: int = int(dc["expires_in"])
                interval_s: int = max(5, int(dc.get("interval", 5)))

                # 2. 显示验证码
                console.print(Panel(
                    f"[bold]访问以下网址并输入验证码：[/bold]\n\n"
                    f"  网址: [link]{verification_uri}[/link]\n"
                    f"  验证码: [bold yellow]{user_code}[/bold yellow]\n\n"
                    f"  [dim]（{expires_in}s 内有效）[/dim]",
                    border_style="cyan",
                    title="GitHub 授权",
                ))

                # 尝试自动打开浏览器（best-effort）
                try:
                    import webbrowser
                    webbrowser.open(verification_uri)
                except Exception:
                    pass

                # 3. 轮询 token
                expires_at = time.time() + expires_in
                console.print("[dim]等待 GitHub 授权...[/dim]")
                while time.time() < expires_at:
                    time.sleep(interval_s)
                    poll = httpx.post(
                        "https://github.com/login/oauth/access_token",
                        headers={"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"},
                        content=(
                            f"client_id={client_id}"
                            f"&device_code={device_code}"
                            f"&grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Adevice_code"
                        ),
                        timeout=15.0,
                    )
                    poll.raise_for_status()
                    pdata = poll.json()
                    if "access_token" in pdata:
                        token = pdata["access_token"]
                        console.print("[green]✓ GitHub Device Flow 授权成功[/green]")
                        break
                    err = pdata.get("error", "")
                    if err == "authorization_pending":
                        console.print("  [dim]等待确认...[/dim]", end="\r")
                        continue
                    if err == "slow_down":
                        interval_s += 5
                        continue
                    if err in ("access_denied", "expired_token"):
                        console.print(f"[red]授权失败: {err}[/red]")
                        break
                    console.print(f"[red]未知错误: {pdata}[/red]")
                    break
                else:
                    console.print("[yellow]授权超时，请重试[/yellow]")
            except Exception as exc:
                console.print(f"  Device Flow 失败: {exc}")

    # ── 路径 3：手动粘贴 PAT ───────────────────────────────────────────
    if not token:
        console.print("\n[bold]路径 3/3：手动输入 Personal Access Token[/bold]")
        console.print(
            "  [dim]在 https://github.com/settings/tokens 创建 PAT，\n"
            "  建议勾选 read:user 权限（Copilot API 最低要求）[/dim]"
        )
        token = typer.prompt("  粘贴 GitHub PAT", hide_input=True).strip()

    if not token:
        console.print("[red]未获取到 token，授权失败[/red]")
        raise typer.Exit(1)

    # ── 持久化 ─────────────────────────────────────────────────────────
    existing["GITHUB_TOKEN"] = token
    cred_file.write_text(
        _json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    cred_file.chmod(0o600)  # 仅 owner 可读
    masked = token[:8] + "..." + token[-4:]
    console.print(f"\n[green]✓ token 已保存: {cred_file}[/green]  [dim]{masked}[/dim]")
    console.print("  下次运行 lingzhou 时自动使用，无需 export GITHUB_TOKEN")
