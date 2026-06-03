"""感知层测试。"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.config import Config
from core.perception import PerceptionLayer
from memory.working import WorkingMemory


@pytest.mark.asyncio
async def test_perception_layer_extracts_multimodal_observations(tmp_path) -> None:
    cfg = Config.model_validate({
        "providers": {
            "local": {
                "type": "openai_compat",
                "base_url": "https://example.invalid/v1",
                "api_key_env": "OPENAI_API_KEY",
            },
        },
        "model": "local/qwen3.6-plus",
        "loop": {
            "workspace_dir": str(tmp_path / "workspace"),
        },
    })
    (tmp_path / "workspace").mkdir(parents=True, exist_ok=True)
    layer = PerceptionLayer(cfg)
    wm = WorkingMemory(capacity=5)

    msg = (
        "我先发一段文字\n"
        "[图片消息，已保存] path=/tmp/shot1.png\n"
        "[图片消息] {\"aeskey\": \"abc\"}\n"
        "以及一些说明"
    )
    percept = await layer.sense(
        wm,
        SimpleNamespace(goal="处理测试任务"),
        user_message=msg,
        last_next_step="",
        last_decision="act",
    )

    assert len(percept.multimodal_inputs) == 2
    assert percept.multimodal_inputs[0].startswith("[图片消息，已保存]")
    assert percept.summary == "处理测试任务（多模态输入: 2 条）"
    assert percept.to_dict()["multimodal_inputs"] == 2


@pytest.mark.asyncio
async def test_perception_layer_no_multimodal_keeps_empty_inputs(tmp_path) -> None:
    cfg = Config.model_validate({
        "providers": {
            "local": {
                "type": "openai_compat",
                "base_url": "https://example.invalid/v1",
                "api_key_env": "OPENAI_API_KEY",
            },
        },
        "model": "local/qwen3.6-plus",
        "loop": {
            "workspace_dir": str(tmp_path / "workspace"),
        },
    })
    (tmp_path / "workspace").mkdir(parents=True, exist_ok=True)
    layer = PerceptionLayer(cfg)
    wm = WorkingMemory(capacity=5)

    percept = await layer.sense(
        wm,
        SimpleNamespace(goal="处理文本任务"),
        user_message="纯文本消息，不含图片",
    )

    assert percept.multimodal_inputs == []
    assert "多模态输入" not in percept.summary


@pytest.mark.asyncio
async def test_perception_layer_extracts_voice_markers(tmp_path) -> None:
    cfg = Config.model_validate({
        "providers": {
            "local": {
                "type": "openai_compat",
                "base_url": "https://example.invalid/v1",
                "api_key_env": "OPENAI_API_KEY",
            },
        },
        "model": "local/qwen3.6-plus",
        "loop": {
            "workspace_dir": str(tmp_path / "workspace"),
        },
    })
    (tmp_path / "workspace").mkdir(parents=True, exist_ok=True)
    layer = PerceptionLayer(cfg)
    wm = WorkingMemory(capacity=5)

    msg = "语音到达：\n[语音消息] voice://u1.amr\n[语音消息，已保存] {\"path\": \"/tmp/u2.mp3\"}"
    percept = await layer.sense(
        wm,
        SimpleNamespace(goal="处理语音测试"),
        user_message=msg,
        last_next_step="",
        last_decision="act",
    )

    assert len(percept.multimodal_inputs) == 2
    assert percept.multimodal_inputs[0].startswith("[语音消息]")
    assert percept.multimodal_inputs[1].startswith("[语音消息，已保存]")
    assert percept.summary == "处理语音测试（多模态输入: 2 条）"


@pytest.mark.asyncio
async def test_perception_layer_extracts_colon_voice_marker(tmp_path) -> None:
    cfg = Config.model_validate({
        "providers": {
            "local": {
                "type": "openai_compat",
                "base_url": "https://example.invalid/v1",
                "api_key_env": "OPENAI_API_KEY",
            },
        },
        "model": "local/qwen3.6-plus",
        "loop": {
            "workspace_dir": str(tmp_path / "workspace"),
        },
    })
    (tmp_path / "workspace").mkdir(parents=True, exist_ok=True)
    layer = PerceptionLayer(cfg)
    wm = WorkingMemory(capacity=5)

    msg = "[语音消息: \"hello from wechat\"] 识别文本"
    percept = await layer.sense(
        wm,
        SimpleNamespace(goal="处理转写测试"),
        user_message=msg,
        last_next_step="",
        last_decision="act",
    )

    assert percept.multimodal_inputs == ['[语音消息: "hello from wechat"]']
    assert percept.summary == "处理转写测试（多模态输入: 1 条）"
