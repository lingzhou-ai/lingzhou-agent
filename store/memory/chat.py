from __future__ import annotations

import re
from typing import Any, Callable, Optional

import aiosqlite

_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_CHAT_ZERO_WIDTH_CHARS = {"\ufeff", "\u200b", "\u200c", "\u200d", "\u2060"}
_CJK_NEIGHBOR_RE = re.compile(
    r"(?<=[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\u3000-\u303f\uff00-\uffef])"
    r"[ \t\u00a0\u3000]+"
    r"(?=[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\u3000-\u303f\uff00-\uffef])"
)


def sanitize_chat_content(content: str) -> str:
    text = str(content or "")
    text = _ANSI_ESCAPE_RE.sub("", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    cleaned_chars: list[str] = []
    for ch in text:
        if ch in _CHAT_ZERO_WIDTH_CHARS or ch == "\ufffd":
            continue
        if ord(ch) < 32 and ch not in {"\n", "\t"}:
            continue
        cleaned_chars.append(ch)
    text = "".join(cleaned_chars)
    text = _CJK_NEIGHBOR_RE.sub("", text)
    return text.strip()


class ChatMessageStore:
    def __init__(self, db_getter: Callable[[], aiosqlite.Connection]) -> None:
        self._db_getter = db_getter

    @property
    def _db(self) -> aiosqlite.Connection:
        return self._db_getter()

    async def add_message(
        self,
        role: str,
        content: str,
        chat_id: str = "",
        session_id: str | None = None,
    ) -> int:
        cleaned = sanitize_chat_content(content)
        resolved_chat_id = str(chat_id or session_id or "")
        async with self._db.execute(
            "INSERT INTO chat_messages(role, content, session_id) VALUES (?,?,?)",
            (role, cleaned, resolved_chat_id),
        ) as cur:
            row_id: int = cur.lastrowid or 0
        await self._db.commit()
        return row_id

    async def has_pending_message(self) -> bool:
        async with self._db.execute(
            "SELECT 1 FROM chat_messages WHERE role='user' AND status='pending' LIMIT 1"
        ) as cur:
            return await cur.fetchone() is not None

    async def pop_pending_message(self) -> Optional[dict[str, Any]]:
        async with self._db.execute(
            "SELECT id, content, session_id FROM chat_messages "
            "WHERE role='user' AND status='pending' ORDER BY id LIMIT 1"
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return None
        mid, content, chat_id = row
        await self._db.execute(
            "UPDATE chat_messages SET status='processed' WHERE id=?", (mid,)
        )
        await self._db.commit()
        return {"id": mid, "content": content, "chat_id": chat_id}

    async def get_messages_since(
        self,
        since_id: int = 0,
        chat_id: str = "",
        session_id: str | None = None,
    ) -> list[dict[str, Any]]:
        resolved_chat_id = str(chat_id or session_id or "")
        if resolved_chat_id:
            sql = (
                "SELECT id, role, content, created_at FROM chat_messages "
                "WHERE id > ? AND session_id = ? ORDER BY id"
            )
            params: tuple[Any, ...] = (since_id, resolved_chat_id)
        else:
            sql = (
                "SELECT id, role, content, created_at FROM chat_messages "
                "WHERE id > ? ORDER BY id"
            )
            params = (since_id,)
        async with self._db.execute(sql, params) as cur:
            rows = await cur.fetchall()
        return [{"id": r[0], "role": r[1], "content": r[2], "created_at": r[3]} for r in rows]
