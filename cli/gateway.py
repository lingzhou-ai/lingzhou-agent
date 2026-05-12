"""cli/gateway.py — run / gateway 命令组（消息网关与认知循环启动）。"""
from __future__ import annotations

import asyncio
import json as _json
import logging
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Annotated, Any, Optional

import typer

from cli._common import console, load_cfg

# channel名称 → (描述, 是否需要 setup 配置)
_GATEWAY_CHANNELS: dict[str, tuple[str, bool]] = {
    "local":    ("本地终端 — 直接在当前终端运行，无需额外配置", False),
    "webhook":  ("HTTP Webhook — 对外暴露 /message 端点（适合集成其他系统）", True),
    "telegram": ("Telegram Bot — 需要 BOT_TOKEN", True),
    "wechat":   ("微信公众号 / 企业微信 — 开发中", True),
    "qq":       ("QQ Bot — 开发中", True),
}

# 已实现的渠道
_GATEWAY_READY = {"local", "webhook"}

gateway_app = typer.Typer(name="gateway", help="消息网关（Telegram、Webhook 等）", no_args_is_help=True)


@gateway_app.command("channels")
def gateway_channels() -> None:
    """列出支持的消息渠道。"""
    console.print("[bold]支持的消息渠道[/bold]\n")
    for ch, (desc, needs_setup) in _GATEWAY_CHANNELS.items():
        if ch in _GATEWAY_READY:
            status = "[green]可用[/green]"
            setup_hint = f"  [dim]lingzhou gateway setup --channel {ch}[/dim]" if needs_setup else ""
        else:
            status = "[dim]开发中[/dim]"
            setup_hint = ""
        console.print(f"  [cyan]{ch:<10}[/cyan] {status}  {desc}{setup_hint}")
    console.print(
        "\n[dim]启动: lingzhou gateway start --channel <name>[/dim]\n"
        "[dim]配置: lingzhou gateway setup --channel <name>[/dim]"
    )


@gateway_app.command("setup")
def gateway_setup(
    channel: Annotated[str, typer.Option("--channel", "-ch", help="渠道名称")] = "webhook",
    config: Annotated[Path, typer.Option("--config", "-c")] = Path("lingzhou.json"),
) -> None:
    """配置消息渠道（向导模式）。local 渠道无需配置。"""
    from rich.panel import Panel

    if channel not in _GATEWAY_CHANNELS:
        console.print(f"[red]未知渠道: {channel}。支持: {', '.join(_GATEWAY_CHANNELS)}[/red]")
        raise typer.Exit(1)

    if channel == "local":
        console.print("[green]local 渠道无需配置，直接运行: lingzhou gateway start[/green]")
        return

    if channel not in _GATEWAY_READY:
        console.print(f"[yellow]{channel} 渠道尚在开发中，暂不支持配置。[/yellow]")
        raise typer.Exit(1)

    gw_dir = Path("~/.lingzhou/gateway").expanduser()
    gw_dir.mkdir(parents=True, exist_ok=True)
    gw_cfg_path = gw_dir / f"{channel}.json"

    console.print(Panel(
        f"[bold]网关配置向导[/bold]  渠道: [cyan]{channel}[/cyan]",
        border_style="blue",
    ))

    if channel == "telegram":
        console.print("\n  获取 Bot Token: 与 @BotFather 对话 → /newbot → 复制 token")
        token = typer.prompt("  BOT_TOKEN").strip()
        allowed_raw = typer.prompt("  允许的用户 ID（逗号分隔，留空则允许所有人）", default="").strip()
        allowed = [int(x.strip()) for x in allowed_raw.split(",") if x.strip().isdigit()]
        gw_conf: dict[str, Any] = {"channel": "telegram", "bot_token": token, "allowed_user_ids": allowed}
        gw_cfg_path.write_text(_json.dumps(gw_conf, ensure_ascii=False, indent=2), encoding="utf-8")
        gw_cfg_path.chmod(0o600)
        console.print(f"\n[green]✓ Telegram 网关配置已保存: {gw_cfg_path}[/green]")

    elif channel == "webhook":
        host = typer.prompt("  监听地址", default="0.0.0.0")
        port = int(typer.prompt("  监听端口", default="8765"))
        secret = typer.prompt("  共享 secret（留空则无鉴权）", default="").strip() or None
        gw_conf: dict[str, Any] = {"channel": "webhook", "host": host, "port": port, "secret": secret}
        gw_cfg_path.write_text(_json.dumps(gw_conf, ensure_ascii=False, indent=2), encoding="utf-8")
        console.print(f"\n[green]✓ Webhook 网关配置已保存: {gw_cfg_path}[/green]")

    console.print(f"\n  启动: [bold]lingzhou gateway start --channel {channel}[/bold]")


@gateway_app.command("start")
def gateway_start(
    channel: Annotated[str, typer.Option("--channel", "-ch", help="消息渠道（默认 local）")] = "local",
    config: Annotated[Path, typer.Option("--config", "-c")] = Path("lingzhou.json"),
    debug: Annotated[Optional[bool], typer.Option("--debug/--no-debug")] = None,
    dry_run: Annotated[Optional[bool], typer.Option("--dry-run/--act")] = None,
) -> None:
    """启动认知循环 + 消息渠道（loop 是内核，channel 是 I/O 层）。

    local    — 本地终端，无需配置，直接运行
    webhook  — HTTP 接入，loop 与 webhook server 并行
    telegram — Telegram Bot（开发中）
    """
    if channel not in _GATEWAY_CHANNELS:
        console.print(f"[red]未知渠道: {channel}。支持: {', '.join(_GATEWAY_CHANNELS)}[/red]")
        raise typer.Exit(1)

    if channel not in _GATEWAY_READY:
        console.print(f"[yellow]{channel} 渠道尚在开发中。当前可用: {', '.join(_GATEWAY_READY)}[/yellow]")
        raise typer.Exit(1)

    # 非 local 渠道需要提前 setup
    gw_conf: dict[str, Any] = {}
    if channel != "local":
        gw_cfg_path = Path("~/.lingzhou/gateway").expanduser() / f"{channel}.json"
        if not gw_cfg_path.exists():
            console.print(
                f"[red]渠道 {channel!r} 尚未配置，请先运行: "
                f"lingzhou gateway setup --channel {channel}[/red]"
            )
            raise typer.Exit(1)
        gw_conf = _json.loads(gw_cfg_path.read_text(encoding="utf-8"))

    cfg = load_cfg(config)
    if debug is not None:
        cfg.loop.debug = debug
    if dry_run is not None:
        cfg.loop.act = not dry_run

    # 日志
    log_dir = Path("~/.lingzhou/logs").expanduser()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"lingzhou-{datetime.now().strftime('%Y-%m-%d')}.log"
    log_level = logging.DEBUG if (debug or cfg.loop.debug) else logging.INFO
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-5s %(message)s", datefmt="%H:%M:%S"))
    file_handler.setLevel(log_level)
    lz_logger = logging.getLogger("lingzhou")
    lz_logger.setLevel(log_level)
    lz_logger.addHandler(file_handler)
    lz_logger.propagate = False
    console.print(f"[dim]渠道: [cyan]{channel}[/cyan]  日志: {log_file}[/dim]")

    # 启动 channel sidecar（loop 主线程仍是 asyncio）
    if channel == "webhook":
        _start_webhook_sidecar(gw_conf, cfg)

    from core.loop import CognitionLoop
    loop_instance = CognitionLoop(cfg)
    try:
        asyncio.run(loop_instance.run())
    except KeyboardInterrupt:
        console.print("\n[dim]认知循环已停止。[/dim]")


def run(
    config: Annotated[Path, typer.Option("--config", "-c")] = Path("lingzhou.json"),
    debug: Annotated[Optional[bool], typer.Option("--debug/--no-debug")] = None,
    dry_run: Annotated[Optional[bool], typer.Option("--dry-run/--act")] = None,
) -> None:
    """启动认知循环（等同于 gateway start --channel local）。"""
    gateway_start(channel="local", config=config, debug=debug, dry_run=dry_run)


def _start_webhook_sidecar(gw_conf: dict[str, Any], cfg: Any) -> None:
    """在 daemon 线程中启动 webhook HTTP 服务，与主 loop asyncio 并行。

    POST /message  {"message": "...", "priority": "high"}
    → 同步写入 SQLite tasks 表 → loop 下一个 tick 消费
    """
    import sqlite3
    import datetime as _dt

    host = gw_conf.get("host", "0.0.0.0")
    port = int(gw_conf.get("port", 8765))
    secret = gw_conf.get("secret")
    db_path = str(cfg.db_path)

    console.print(
        f"[dim]Webhook 监听: http://{host}:{port}/message"
        f"{'  (Bearer token)' if secret else '  (无鉴权)'}[/dim]"
    )

    class _Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            pass  # 静默访问日志

        def do_POST(self) -> None:
            if self.path != "/message":
                self.send_response(404); self.end_headers(); return
            if secret:
                if self.headers.get("Authorization", "") != f"Bearer {secret}":
                    self.send_response(401); self.end_headers(); return
            length = min(int(self.headers.get("Content-Length", 0)), 65536)
            body = self.rfile.read(length)
            try:
                payload = _json.loads(body)
                msg = payload.get("message", "").strip()
                priority = payload.get("priority", "high")
            except Exception:
                self.send_response(400); self.end_headers(); return
            if not msg:
                self.send_response(400); self.end_headers()
                self.wfile.write(b'{"error":"empty message"}'); return

            short = msg.replace("\n", " ")[:28] + ("..." if len(msg) > 28 else "")
            now = _dt.datetime.now(_dt.UTC).isoformat()
            try:
                conn = sqlite3.connect(db_path)
                try:
                    data_json = _json.dumps(
                        {"goal": msg, "source": "gateway:webhook", "next_step": ""},
                        ensure_ascii=False,
                    )
                    conn.execute(
                        "INSERT INTO tasks (title, status, priority, created_at, data) VALUES (?,?,?,?,?)",
                        (f"webhook: {short}", "pending", priority, now, data_json),
                    )
                    conn.commit()
                    task_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                finally:
                    conn.close()
                resp = _json.dumps({"ok": True, "task_id": task_id}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(resp)
                console.print(f"[green][webhook] 注入任务 id={task_id}: {short}[/green]")
            except Exception as e:
                self.send_response(500); self.end_headers()
                self.wfile.write(_json.dumps({"error": str(e)}).encode())

    server = HTTPServer((host, port), _Handler)
    t = threading.Thread(target=server.serve_forever, daemon=True, name="webhook-gateway")
    t.start()
