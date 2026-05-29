from __future__ import annotations

import hashlib
import re

_TOPIC_PUNCT_PATTERN = re.compile(r"[，。！？；、,.!?]+")
_SENTENCE_SPLIT_PATTERN = re.compile(r"[。！？!?；;\n]+")
_SELF_NAME_PATTERNS = (
    re.compile(r"(?:我叫|我的名字是|你可以叫我|请叫我|以后叫我|下次叫我|就叫我)\s*[:：]?\s*([A-Za-z0-9_\-\u4e00-\u9fff]{1,24})"),
    re.compile(r"(?:我是)\s*([A-Za-z0-9_\-\u4e00-\u9fff]{1,24})"),
)
_INTERLOCUTOR_TYPE_HINTS: dict[str, tuple[str, ...]] = {
    "agent": ("agent", "subagent", "智能体"),
    "bot": ("bot", "robot", "机器人"),
    "assistant": ("assistant", "助手", "助理"),
    "ai": ("ai", "llm", "模型", "gpt", "claude", "qwen", "gemini", "copilot"),
    "webhook": ("webhook",),
    "internal": ("internal",),
    "external": ("external",),
}

_REASON_SYSTEM = """\
你是灵舟的记忆链接器，负责实体共指消解。

任务：分析用户消息，在候选记忆节点中找出与消息存在真实上下文关联的实体。

判断维度（任一满足即纳入）：
  direct    — 消息直接提及该实体名称或别名
  state     — 消息描述了该实体的状态变化（如"离职""完成""取消"）
  implicit  — 消息通过"上次的""你推荐的"等隐式引用该实体
  self_intro — 消息是自我介绍，与人物节点对应
    temporal  — 消息中的时间感知与候选节点 created_at / 最近叙事上下文吻合

可结合用户消息中的相对时间表达（如"昨天""刚才""上次"）自行判断 temporal 关联，
不要假定外部已经把这些时间词换算成固定小时窗口。

输出格式：JSON 数组，不加 markdown。每项字段：
  node_id          — 候选节点的 id（原样输出，不得修改）
  confidence       — 关联置信度 0.0~1.0（两位小数）
  relationship_note — 一句话说明关联性质（中文，≤20字）

无关候选不输出。无相关实体时输出 []。\
"""

_SPEAKER_REASON_SYSTEM = """\
你是灵舟的当前交互对象识别器。

任务：结合当前用户消息、最近交互记忆、当前 chat 连续性、当前对象的跨 chat 连续性和候选交互对象画像，判断“当前消息来自谁”。

判断原则：
    - chat_id / handle 只能当作线索，不能单独当成身份证明。
    - 必须优先综合：自我介绍、稳定偏好、记忆要求、过往互动连续性、交互对象画像摘要。
    - 如果候选里没有足够匹配的人，可以输出 NEW；如果证据太弱，就输出 UNKNOWN。

输出格式：JSON 对象，不加 markdown。字段：
    node_id            — 命中的交互对象节点 id；新对象填 NEW；无法判断填 UNKNOWN
    confidence         — 0.0~1.0，两位小数
    display_name       — 当前交互对象的称呼；命中旧节点时尽量沿用节点标题
    relationship_note  — 一句话说明为何认成此对象（中文，<=24字）
    evidence           — 最多 3 条证据短句数组
    provisional        — 是否只是临时画像 true/false
\
"""


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip()).strip()


def split_text_sentences(text: str) -> list[str]:
    return [
        part.strip(" ,，。；;!！?？")
        for part in _SENTENCE_SPLIT_PATTERN.split(normalize_text(text))
        if part and part.strip()
    ]


def short_text_digest(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def chat_handle_tag(chat_id: str) -> str:
    return f"handle:{chat_id.strip()}"


def default_interlocutor_title(chat_id: str) -> str:
    if not chat_id:
        return "当前交互对象"
    return f"当前交互对象@{chat_id[-12:]}"
