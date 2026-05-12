"""cli/interact.py — interact 命令（对话驱动内环）。"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated, Any, Optional

import typer
from rich.panel import Panel

from cli._common import console, load_cfg


def interact(
    config: Annotated[Path, typer.Option("--config", "-c")] = Path("lingzhou.json"),
    debug: Annotated[Optional[bool], typer.Option("--debug/--no-debug")] = None,
    enqueue_only: Annotated[
        bool,
        typer.Option(
            "--enqueue-only/--inline-tick",
            help="默认将外部输入注入任务队列给运行中的 loop 处理；使用 --inline-tick 切回本地单进程对话",
        ),
    ] = True,
    priority: Annotated[
        str,
        typer.Option("--priority", "-p", help="enqueue-only 模式下注入任务优先级"),
    ] = "high",
) -> None:
    """对话驱动内环：每条用户消息触发一次完整认知 tick。

    交互设计依据：
    - Clark & Schaefer (1989) Grounding: 每次交换前展示 agent 当前基础状态，
      使双方拥有共同认知基础（common ground），而非盲目对话
    - Damasio (1994) Somatic Marker: 情绪状态作为可见的"躯体标记"显示，
      影响推理的情绪不应是隐藏的黑盒
    - Grice (1975) Cooperative Principle: 回复应与当前 ground 相关（relation），
      信息量适度（quantity），真实（quality），清晰（manner）
    - Ricoeur (1984) Narrative: chat 是门也是房间——对话即任务
    """
    cfg = load_cfg(config)
    if debug is not None:
        cfg.loop.debug = debug

    def _emotion_mood(valence: float, arousal: float) -> str:
        """Russell (1980) 环形情绪模型：将 valence/arousal 映射为情境标签。阈值来自 cfg.emotion。"""
        ec = cfg.emotion
        vh, vl = ec.mood_valence_high, ec.mood_valence_low
        ah, al = ec.mood_arousal_high, ec.mood_arousal_low
        if valence >= vh and arousal >= ah:
            return "活跃"
        if valence >= vh and arousal < al:
            return "平静"
        if valence >= (vh + vl) / 2:
            return "平稳"
        if valence < vl:
            return "低落"
        if arousal >= ah:
            return "紧张"
        return "中性"

    def _render_ground(state: dict[str, Any], cycle: int) -> None:
        """渲染当前基础状态（Clark & Schaefer 1989 common ground 可视化）。"""
        v, a = state["valence"], state["arousal"]
        mood = _emotion_mood(v, a)
        task_label = f"[cyan]{state['task_title']}[/cyan]" if state["task_title"] else "[dim]无活跃任务[/dim]"
        wm_label = f"{state['wm_size']} 条" if state["wm_size"] else "空"
        console.print(
            f"[dim]── cycle {cycle} │ 情绪: {mood} (V={v:.2f} A={a:.2f}) │ 任务: {task_label} │ WM: {wm_label} ──[/dim]"
        )

    async def _run() -> None:
        if enqueue_only:
            from memory.task_store import TaskStore

            store = TaskStore(cfg.db_path)
            await store.open()
            console.print(Panel(
                "[bold green]外部交互注入模式[/bold green]\n"
                "输入内容将直接写入任务队列，供正在运行的 loop 消费。\n"
                "[dim]Ctrl+C 退出[/dim]",
                title="💬 Interact → Task Queue",
                border_style="green",
            ))
            try:
                while True:
                    try:
                        user_input = input("[你] ").strip()
                    except (EOFError, KeyboardInterrupt):
                        console.print("\n[dim]再见。[/dim]")
                        break
                    if not user_input:
                        continue

                    # 将外部交互转成任务：标题短、目标保留完整输入
                    short = user_input.replace("\n", " ").strip()
                    if len(short) > 28:
                        short = short[:28] + "..."
                    task_id = await store.add_task(
                        title=f"外部交互: {short}",
                        goal=user_input,
                        priority=priority,
                        source="external",
                    )
                    console.print(f"[green]已注入任务[/green] id={task_id} priority={priority} — [dim]需要 loop 进程在后台运行才会被处理[/dim]")
            finally:
                await store.close()
            return

        from core.loop import CognitionLoop

        loop_instance = CognitionLoop(cfg)
        await loop_instance.open()

        # 读取 soul 名称
        name_val, _ = await loop_instance.task_store.get_fact("soul:name")
        agent_name = name_val or "灵舟"

        state = await loop_instance.state_snapshot()
        mood = _emotion_mood(state["valence"], state["arousal"])

        console.print(Panel(
            f"[bold green]{agent_name}[/bold green] 已就绪\n"
            f"情绪基线: {mood} (V={state['valence']:.2f}, A={state['arousal']:.2f})\n"
            f"[dim]输入消息 → 触发完整认知 tick → 收到 reply_to_user[/dim]\n"
            f"[dim]Ctrl+C 退出[/dim]",
            title="💬 对话模式",
            border_style="green",
        ))

        cycle = 0
        try:
            while True:
                # 每轮输入前渲染当前基础状态（grounding）
                state = await loop_instance.state_snapshot()
                _render_ground(state, cycle + 1)

                try:
                    user_input = input("[你] ").strip()
                except (EOFError, KeyboardInterrupt):
                    console.print("\n[dim]再见。[/dim]")
                    break
                if not user_input:
                    continue

                cycle += 1
                console.print(f"[dim]思考中…[/dim]")

                try:
                    reply = await loop_instance.tick_interact(cycle, user_input)

                    # 读取更新后的状态（Damasio：展示情绪变化）
                    new_state = await loop_instance.state_snapshot()
                    v_delta = new_state["valence"] - state["valence"]
                    a_delta = new_state["arousal"] - state["arousal"]
                    delta_str = ""
                    if abs(v_delta) > cfg.emotion.delta_display_min or abs(a_delta) > cfg.emotion.delta_display_min:
                        delta_str = (
                            f" [dim](情绪变化: V{v_delta:+.2f} A{a_delta:+.2f})[/dim]"
                        )

                    console.print(f"\n[bold cyan][{agent_name}][/bold cyan] {reply or '（处理中，暂无回复）'}{delta_str}\n")

                except Exception:
                    console.print_exception(max_frames=6)
        finally:
            await loop_instance.task_store.close()
            await loop_instance.provider.close()

    asyncio.run(_run())
