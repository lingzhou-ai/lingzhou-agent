from __future__ import annotations

import json
import logging as _log_sem
import sqlite3
from contextlib import contextmanager, suppress
from typing import Any

from . import _DDL, _DDL_FTS5, MemoryNode, _parse_table_cols

_log = _log_sem.getLogger("lingzhou.memory.semantic")


def _normalize_interlocutor_tags(tags: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in tags:
        tag = str(raw or "").strip()
        if not tag:
            continue
        if tag == "person_profile":
            tag = "interlocutor_profile"
        elif tag.startswith("person:"):
            tag = "interlocutor:" + tag.split(":", 1)[1]
        if tag not in seen:
            seen.add(tag)
            normalized.append(tag)
    return normalized


def _is_legacy_interlocutor_profile(cls, node: MemoryNode) -> bool:
    tags = {str(tag or "").strip() for tag in (node.tags or [])}
    return bool(
        node.kind == "person"
        and (
            getattr(node, "source", "") in {"user_profile", "person_profile"}
            or "person_profile" in tags
            or any(tag.startswith("person:") for tag in tags)
            or any(tag.startswith("handle:") for tag in tags)
        )
    )


def _migrate_interlocutor_profiles(self) -> None:
    migrated = 0
    for path in self._dir.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            node = MemoryNode.from_dict(payload)
        except Exception:
            continue
        if not self._is_legacy_interlocutor_profile(node):
            continue

        new_tags = self._normalize_interlocutor_tags(list(node.tags or []))
        new_source = "interlocutor_profile" if (node.source or "") in {"", "user_profile", "person_profile"} else node.source
        changed = bool(node.kind != "interlocutor" or new_tags != list(node.tags or []) or new_source != node.source)
        if not changed:
            continue

        migrated += 1
        node.kind = "interlocutor"
        node.tags = new_tags
        node.source = new_source
        path.write_text(json.dumps(node.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        self._db_upsert(node)

    if migrated:
        _log.info("[semantic] 已迁移 %d 个旧 person_profile 节点到 interlocutor_profile", migrated)


def _conn_getter(self) -> sqlite3.Connection:
    conn = getattr(self, "_conn_ref", None)
    if conn is None:
        raise RuntimeError("semantic db session is not open")
    return conn


def _conn_setter(self, value: sqlite3.Connection | None) -> None:
    self._conn_ref = value


@contextmanager
def _db_session(self):
    if self._conn_ref is not None:
        self._session_depth += 1
        try:
            yield self._conn_ref
        finally:
            self._session_depth -= 1
        return

    conn = self._open_db()
    self._conn = conn
    self._session_depth = 1
    try:
        yield conn
    finally:
        self._session_depth -= 1
        if self._session_depth == 0:
            self.close()


def close(self) -> None:
    conn = getattr(self, "_conn_ref", None)
    self._conn_ref = None
    self._session_depth = 0
    if conn is not None:
        with suppress(Exception):
            conn.close()


def _open_db(self) -> sqlite3.Connection:
    try:
        conn = self._connect()
        conn.executescript(_DDL)
        conn.commit()
        self._setup_fts5(conn)
        return conn
    except sqlite3.DatabaseError:
        self._db_path.unlink(missing_ok=True)
        conn = self._connect()
        conn.executescript(_DDL)
        conn.commit()
        self._setup_fts5(conn)
        return conn


def _migrate(self) -> None:
    try:
        desired = _parse_table_cols(_DDL)
        existing = {row[1] for row in self._conn.execute("PRAGMA table_info(nodes)")}
        changed = False
        for col, definition in desired.items():
            if col not in existing:
                self._conn.execute(f"ALTER TABLE nodes ADD COLUMN {col} {definition}")
                changed = True
        if changed:
            self._conn.commit()
    except Exception:
        pass
    try:
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_nodes_kind ON nodes(kind)"
        )
        self._conn.commit()
    except Exception:
        pass


def _setup_fts5(self, conn: sqlite3.Connection) -> None:
    try:
        try:
            conn.execute("SELECT id FROM nodes_fts LIMIT 0")
        except Exception:
            _log.warning("[semantic] nodes_fts 缺少 id 列，重建 FTS5 表")
            conn.execute("DROP TABLE IF EXISTS nodes_fts")
            conn.commit()
        conn.executescript(_DDL_FTS5)
        conn.execute(
            """
            INSERT INTO nodes_fts(id, title, body, tags)
            SELECT id, title, body, tags FROM nodes
            WHERE id NOT IN (SELECT id FROM nodes_fts)
            """
        )
        conn.commit()
        self._fts5_ok = True
    except Exception as exc:
        _log.warning("[semantic] FTS5 初始化失败，降级为全表扫描：%s", exc)
        self._fts5_ok = False


def _connect(self) -> sqlite3.Connection:
    conn = sqlite3.connect(str(self._db_path), check_same_thread=False, timeout=60)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.row_factory = sqlite3.Row
    return conn


def _sync_from_files(self) -> None:
    try:
        existing_ids: set[str] = {
            row[0] for row in self._conn.execute("SELECT id FROM nodes")
        }
        for p in self._dir.glob("*.json"):
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
                if d.get("id") not in existing_ids:
                    self._db_upsert(MemoryNode.from_dict(d))
            except Exception as exc:
                _log.warning("[semantic] 跳过损坏的节点文件 %s: %s", p.name, exc)
        self._conn.commit()
    except Exception as exc:
        _log.warning("[semantic] _sync_from_files 失败，回退到文件扫描: %s", exc)


def _validate_and_repair_index(self) -> None:
    try:
        json_count = sum(1 for _ in self._dir.glob("*.json"))
        db_count = self._conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        if json_count > 0 and (db_count == 0 or abs(db_count - json_count) > json_count * 0.2 or not self._fts5_ok):
            _log.warning("[semantic] 索引不一致或 FTS5 异常 (json=%d, db=%d, fts5=%s)，触发自动重建", json_count, db_count, self._fts5_ok)
            self.rebuild_index()
    except Exception as exc:
        _log.warning("[semantic] 索引校验失败，跳过自动重建: %s", exc)


def rebuild_index(self) -> None:
    with self._db_session():
        self._conn.execute("DELETE FROM nodes")
        if self._fts5_ok:
            with suppress(Exception):
                self._conn.execute("DELETE FROM nodes_fts")
        self._conn.commit()
        for p in self._dir.glob("*.json"):
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
                self._db_upsert(MemoryNode.from_dict(d))
                emb = d.get("embedding")
                if emb is not None:
                    emb_json = json.dumps(emb) if not isinstance(emb, str) else emb
                    self._conn.execute(
                        "UPDATE nodes SET embedding = ? WHERE id = ?",
                        (emb_json, d.get("id")),
                    )
            except Exception:
                pass
        self._conn.commit()


def _db_upsert(self, node: MemoryNode) -> None:
    tags_json = json.dumps(node.tags, ensure_ascii=False)
    self._conn.execute(
        """INSERT INTO nodes
                         (id, kind, title, body, activation, valence, importance, tags, source, created_at)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(id) DO UPDATE SET
             kind=excluded.kind,
             title=excluded.title,
             body=excluded.body,
             activation=excluded.activation,
             valence=excluded.valence,
                             importance=excluded.importance,
             tags=excluded.tags,
             source=excluded.source""",
        (
            node.id, node.kind, node.title, node.body,
            node.activation, node.valence,
                            node.importance,
            tags_json,
            getattr(node, "source", ""),
            node.created_at,
        ),
    )
    self._conn.commit()
    if self._fts5_ok:
        try:
            self._sync_node_fts(
                node_id=node.id,
                title=node.title,
                body=node.body,
                tags_json=tags_json,
            )
        except Exception as exc:
            with suppress(Exception):
                self._conn.rollback()
            self._fts5_ok = False
            _log.warning("[semantic] FTS5 同步失败，降级为全表扫描: %s", exc)


def _sync_node_fts(
    self,
    *,
    node_id: str,
    title: str,
    body: str,
    tags_json: str,
) -> None:
    self._conn.execute("DELETE FROM nodes_fts WHERE id = ?", (node_id,))
    self._conn.execute(
        "INSERT INTO nodes_fts(id, title, body, tags) VALUES (?, ?, ?, ?)",
        (node_id, title, body, tags_json),
    )
    self._conn.commit()


def fts5_ok(self) -> bool:
    return self._fts5_ok


def decay_lambda(self) -> float:
    return self._decay_lambda


def stats(self) -> dict[str, Any]:
    total_nodes = 0
    with self._db_session():
        try:
            row = self._conn.execute("SELECT COUNT(*) FROM nodes").fetchone()
            total_nodes = int(row[0] or 0) if row else 0
        except Exception:
            total_nodes = 0
    return {
        "nodes": total_nodes,
        "fts5_ok": bool(self._fts5_ok),
        "decay_lambda": float(self._decay_lambda),
        "embedding_enabled": bool(self._embed_fn is not None),
        "source_weight": float(self._source_weight),
        "temporal_weight": float(self._temporal_weight),
        "temporal_window_days": float(self._temporal_window_days),
        "db_path": str(self._db_path),
        "nodes_dir": str(self._dir),
    }


def upsert(self, node: MemoryNode) -> None:
    path = self._dir / f"{node.id}.json"
    path.write_text(json.dumps(node.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    with self._db_session():
        try:
            self._db_upsert(node)
        except Exception as exc:
            _log.warning("[semantic] 节点写入 DB 失败，保留 json 作为恢复源: %s", exc)
        if self._embed_fn is not None:
            try:
                vec = self._embed_fn(node.title + " " + node.body)
                self._conn.execute(
                    "UPDATE nodes SET embedding = ? WHERE id = ?",
                    (json.dumps(vec), node.id),
                )
                self._conn.commit()
            except Exception:
                pass


def get(self, node_id: str) -> MemoryNode | None:
    with self._db_session():
        try:
            row = self._conn.execute(
                "SELECT * FROM nodes WHERE id = ?", (node_id,)
            ).fetchone()
            if row:
                return self._row_to_node(row)
        except Exception:
            pass
    path = self._dir / f"{node_id}.json"
    if path.exists():
        return MemoryNode.from_dict(json.loads(path.read_text(encoding="utf-8")))
    return None


def find_by_title(self, title: str, limit: int = 10) -> list[MemoryNode]:
    normalized = (title or "").strip()
    if not normalized:
        return []
    with self._db_session():
        try:
            rows = self._conn.execute(
                "SELECT * FROM nodes WHERE title = ? ORDER BY created_at DESC LIMIT ?",
                (normalized, limit),
            ).fetchall()
            return [self._row_to_node(r) for r in rows]
        except Exception:
            pass
    hits: list[MemoryNode] = []
    for p in self._dir.glob("*.json"):
        try:
            node = MemoryNode.from_dict(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            continue
        if node.title == normalized:
            hits.append(node)
            if len(hits) >= limit:
                break
    hits.sort(key=lambda item: item.created_at, reverse=True)
    return hits[:limit]
