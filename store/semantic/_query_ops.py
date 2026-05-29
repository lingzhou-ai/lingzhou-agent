from __future__ import annotations

import json
import logging as _log_sem
import re
import sqlite3
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any

from memory.quality_checker import evaluate_retrieval_quality

from . import (
    _EPHEMERAL_MEMORY_KINDS,
    _STABLE_MEMORY_KINDS,
    _STABLE_MEMORY_SOURCES,
    MemoryNode,
    _cosine,
    effective_activation,
)

_log = _log_sem.getLogger("lingzhou.memory.semantic")


def retrieve(
    self,
    query: str,
    top_k: int = 5,
    *,
    kind: str | None = None,
    tag: str | None = None,
    source: str | None = None,
    task_id: str | int | None = None,
    path_prefix: str | None = None,
    id_prefix: str | None = None,
) -> list[dict[str, Any]]:
    with self._db_session():
        query_vec: list[float] | None = None
        if self._embed_fn is not None:
            with suppress(Exception):
                query_vec = self._embed_fn(query)
        candidate_ids = self._fts_candidates(query, limit=100 if any((kind, tag, task_id, path_prefix, id_prefix)) else 50)
        nodes = self._load_by_ids(candidate_ids) if candidate_ids else self._load_all()
        if any((kind, tag, source, task_id, path_prefix, id_prefix)):
            nodes = [
                node for node in nodes
                if self._matches_filters(
                    node,
                    kind=kind,
                    tag=tag,
                    source=source,
                    task_id=task_id,
                    path_prefix=path_prefix,
                    id_prefix=id_prefix,
                )
            ]
            if candidate_ids and not nodes:
                nodes = [
                    node for node in self._load_all()
                    if self._matches_filters(
                        node,
                        kind=kind,
                        tag=tag,
                        source=source,
                        task_id=task_id,
                        path_prefix=path_prefix,
                        id_prefix=id_prefix,
                    )
                ]
        if not nodes:
            return []
        scored = [(self._score(query, n, query_vec=query_vec), n) for n in nodes]
        scored.sort(key=lambda x: x[0], reverse=True)
        retrieved = []
        for score, node in scored[:top_k]:
            item = node.to_dict()
            item["score"] = round(float(score), 4)
            retrieved.append(item)

        if _log.isEnabledFor(_log_sem.DEBUG):
            qm = evaluate_retrieval_quality(query, retrieved, self._decay_lambda)
            _log.debug("[semantic.retrieve] quality=%s", qm.get("overall_score", 0))
        return retrieved


def _matches_filters(
    node: MemoryNode,
    *,
    kind: str | None = None,
    tag: str | None = None,
    source: str | None = None,
    task_id: str | int | None = None,
    path_prefix: str | None = None,
    id_prefix: str | None = None,
) -> bool:
    if kind and node.kind != str(kind).strip():
        return False
    if tag:
        normalized_tag = str(tag).strip()
        if normalized_tag and normalized_tag not in node.tags:
            return False
    if source:
        normalized_source = str(source).strip()
        node_source = str(getattr(node, "source", "")).strip()
        if normalized_source and normalized_source != node_source:
            return False
    if task_id is not None:
        expected_task_tag = f"task:{str(task_id).strip()}"
        if expected_task_tag not in node.tags:
            return False
    if id_prefix:
        normalized_id_prefix = str(id_prefix).strip()
        if normalized_id_prefix and not node.id.startswith(normalized_id_prefix):
            return False
    if path_prefix:
        normalized_path = str(path_prefix).strip().replace("\\", "/")
        if normalized_path:
            haystack = [
                node.title.replace("\\", "/"),
                node.body.replace("\\", "/"),
                *(tag_item.replace("\\", "/") for tag_item in node.tags),
            ]
            if not any(normalized_path in item for item in haystack):
                return False
    return True


def retrieve_multi_anchor(
    self, anchors: list[str], top_k: int = 5, convergence_bonus: float = 0.15, source: str | None = None
) -> list[dict[str, Any]]:
    with self._db_session():
        valid_anchors = [a for a in anchors if a and a.strip()]
        if not valid_anchors:
            return []
        all_ids: list[str] = []
        seen: set[str] = set()
        for anchor in valid_anchors:
            for nid in self._fts_candidates(anchor, limit=30):
                if nid not in seen:
                    seen.add(nid)
                    all_ids.append(nid)
        nodes = self._load_by_ids(all_ids) if all_ids else self._load_all()
        if source:
            nodes = [n for n in nodes if getattr(n, "source", "") == source]
        if not nodes:
            return []

        best_score: dict[str, float] = {}
        hit_count: dict[str, int] = {}
        for anchor in valid_anchors:
            query_vec: list[float] | None = None
            if self._embed_fn is not None:
                with suppress(Exception):
                    query_vec = self._embed_fn(anchor)
            for node in nodes:
                s = self._score(anchor, node, query_vec=query_vec)
                if s > 0:
                    if node.id not in best_score or s > best_score[node.id]:
                        best_score[node.id] = s
                    hit_count[node.id] = hit_count.get(node.id, 0) + 1

        if not best_score:
            return []

        node_map = {n.id: n for n in nodes}
        final: list[tuple[float, MemoryNode]] = []
        for nid, base in best_score.items():
            hits = hit_count.get(nid, 1)
            score = base * (1.0 + convergence_bonus * (hits - 1))
            final.append((score, node_map[nid]))

        final.sort(key=lambda x: x[0], reverse=True)
        retrieved = []
        for score, node in final[:top_k]:
            item = node.to_dict()
            item["score"] = round(float(score), 4)
            retrieved.append(item)

        if _log.isEnabledFor(_log_sem.DEBUG):
            combined_query = " ".join(valid_anchors)
            qm = evaluate_retrieval_quality(combined_query, retrieved, self._decay_lambda)
            _log.debug("[semantic.multi_anchor] quality=%s", qm.get("overall_score", 0))
        return retrieved


def store_reflection(self, kind: str, insight: str, valence: float = 0.5) -> str:
    node_id = f"reflection-{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}"
    self.upsert(MemoryNode(
        id=node_id,
        kind="learned_insight",
        title=f"[{kind}] [{node_id[-6:]}]",
        body=insight.strip(),
        activation=0.8,
        valence=valence,
        tags=[kind],
    ))
    return node_id


def list_reflections(self, limit: int = 10) -> list[MemoryNode]:
    with self._db_session():
        nodes = [n for n in self._load_all() if n.kind == "learned_insight"]
        nodes.sort(key=lambda n: n.created_at, reverse=True)
        return nodes[:limit]


def _fts_candidates(self, query: str, limit: int = 50) -> list[str]:
    if not self._fts5_ok:
        return []
    safe = re.sub(r"[^\w\s]", " ", query, flags=re.UNICODE)
    _strict = [t for t in safe.split() if len(t) >= 2 and not (t.isascii() and len(t) < 5)]
    terms = _strict if _strict else [t for t in safe.split() if len(t) > 1]
    if not terms:
        return []
    fts_query = " OR ".join(terms)
    try:
        rows = self._conn.execute(
            "SELECT id FROM nodes_fts WHERE nodes_fts MATCH ? LIMIT ?",
            (fts_query, limit),
        ).fetchall()
        return [r[0] for r in rows]
    except Exception as exc:
        self._fts5_ok = False
        _log.warning("[semantic] FTS5 查询失败，降级为全表扫描: %s", exc)
        return []


def _load_by_ids(self, ids: list[str]) -> list[MemoryNode]:
    if not ids:
        return []
    try:
        placeholders = ",".join("?" * len(ids))
        rows = self._conn.execute(
            f"SELECT * FROM nodes WHERE id IN ({placeholders})", ids
        ).fetchall()
        return [self._row_to_node(r) for r in rows]
    except Exception:
        return []


def _load_all(self) -> list[MemoryNode]:
    try:
        rows = self._conn.execute("SELECT * FROM nodes").fetchall()
        return [self._row_to_node(r) for r in rows]
    except Exception:
        pass
    nodes: list[MemoryNode] = []
    for p in self._dir.glob("*.json"):
        with suppress(Exception):
            nodes.append(MemoryNode.from_dict(json.loads(p.read_text(encoding="utf-8"))))
    return nodes


def _row_to_node(row: sqlite3.Row) -> MemoryNode:
    d: dict[str, Any] = dict(row)
    d["tags"] = json.loads(d.get("tags") or "[]")
    node = MemoryNode.from_dict(d)
    emb = d.get("embedding")
    if emb is not None:
        node.__dict__["embedding"] = emb
    return node


def _score(
    self,
    query: str,
    node: MemoryNode,
    query_vec: list[float] | None = None,
) -> float:
    eff_act = effective_activation(node, self._decay_lambda)
    q_tokens = set(re.findall(r"\w+", query.lower()))
    n_tokens = set(re.findall(r"\w+", (node.title + " " + node.body).lower()))
    if not q_tokens or not n_tokens:
        kw_score = 0.1
    else:
        kw_score = len(q_tokens & n_tokens) / len(q_tokens | n_tokens)
    source_score = self._source_score(node)
    temporal_score = self._temporal_score(node)
    text_score = max(0.0, kw_score * 0.55 + eff_act * 0.25 + source_score + temporal_score)

    node_emb_raw = getattr(node, "embedding", None)
    if query_vec is not None and node_emb_raw is not None:
        try:
            node_vec: list[float] = (
                json.loads(node_emb_raw)
                if isinstance(node_emb_raw, str)
                else node_emb_raw
            )
            cos_sim = _cosine(query_vec, node_vec)
            w = self._embedding_weight
            return (1 - w) * text_score + w * cos_sim
        except Exception:
            pass

    return text_score


def _source_score(self, node: MemoryNode) -> float:
    score = 0.0
    stable_kind = node.kind in _STABLE_MEMORY_KINDS
    if node.kind in _STABLE_MEMORY_KINDS:
        score += self._source_weight
    elif node.kind in _EPHEMERAL_MEMORY_KINDS:
        score -= self._source_weight * 0.4

    node_source = str(getattr(node, "source", "") or "").strip()
    if node_source in _STABLE_MEMORY_SOURCES:
        score += self._source_weight * 0.5
        if stable_kind:
            score += self._source_weight * 0.25

    tags = set(getattr(node, "tags", []) or [])
    if "wm_promoted" in tags and node.kind not in _EPHEMERAL_MEMORY_KINDS:
        score += self._source_weight * 0.25
    return score


def _temporal_score(self, node: MemoryNode) -> float:
    if self._temporal_weight <= 0:
        return 0.0
    age_days = self._node_age_days(node)
    if age_days is None:
        return 0.0

    normalized = min(age_days / self._temporal_window_days, 1.0)
    freshness = max(0.0, 1.0 - normalized)
    if node.kind in _STABLE_MEMORY_KINDS:
        return self._temporal_weight * normalized
    if node.kind in _EPHEMERAL_MEMORY_KINDS:
        return self._temporal_weight * 0.35 * freshness
    return self._temporal_weight * 0.15 * freshness


def _node_age_days(node: MemoryNode) -> float | None:
    try:
        created = datetime.fromisoformat(node.created_at)
        if created.tzinfo is None:
            created = created.replace(tzinfo=UTC)
        return max(0.0, (datetime.now(UTC) - created).total_seconds() / 86400)
    except Exception:
        return None


def get_unembedded(self, limit: int = 20) -> list[tuple[str, str]]:
    with self._db_session():
        try:
            rows = self._conn.execute(
                "SELECT id, title, body FROM nodes WHERE embedding IS NULL LIMIT ?",
                (limit,),
            ).fetchall()
            return [(r[0], (r[1] or "") + " " + (r[2] or "")) for r in rows]
        except Exception:
            return []


def set_embedding(self, node_id: str, vec: list[float]) -> None:
    with self._db_session():
        try:
            vec_json = json.dumps(vec)
            self._conn.execute(
                "UPDATE nodes SET embedding = ? WHERE id = ?",
                (vec_json, node_id),
            )
            self._conn.commit()
            json_path = self._dir / f"{node_id}.json"
            if json_path.exists():
                try:
                    d = json.loads(json_path.read_text(encoding="utf-8"))
                    d["embedding"] = vec
                    json_path.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
                except Exception:
                    pass
        except Exception:
            pass
