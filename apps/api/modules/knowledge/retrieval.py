from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import re
from typing import Any, Callable

from sqlmodel import select

from apps.api.models import KnowledgeEmbedding, KnowledgeItem, utc_now


EMBEDDING_MODEL = "workbuddy-local-hash-v1"
EMBEDDING_DIMENSIONS = 192
CONCEPT_GROUPS = (
    ("登录", "登陆", "账号", "账户", "密码", "认证", "进不去", "登不上"),
    ("失败", "报错", "异常", "错误", "不可用", "无法使用", "不能用"),
    ("退款", "退费", "返款", "撤销付款"),
    ("发票", "开票", "票据", "抬头"),
    ("网络", "连接", "断线", "超时", "访问"),
    ("权限", "授权", "角色", "无权", "禁止访问"),
    ("订单", "购买", "下单", "支付", "付款"),
    ("客服", "支持", "工单", "售后", "人工"),
)


@dataclass
class RetrievalMatch:
    item: KnowledgeItem
    score: int
    keyword_score: int
    semantic_score: float
    quality_score: int
    reasons: list[str]
    snippet: str
    citation: str


def retrieve_knowledge(
    session: Any,
    tenant_id: int,
    query: str,
    *,
    category: str | None = None,
    include_drafts: bool = False,
    limit: int = 8,
    keyword_score_fn: Callable[[str, KnowledgeItem], tuple[int, list[str]]],
) -> tuple[int, list[RetrievalMatch]]:
    statement = select(KnowledgeItem).where(KnowledgeItem.tenant_id == tenant_id)
    if not include_drafts:
        statement = statement.where(KnowledgeItem.status == "published")
    if category:
        statement = statement.where(KnowledgeItem.category == category)
    candidates = list(
        session.exec(statement.order_by(KnowledgeItem.updated_at.desc(), KnowledgeItem.id.desc()).limit(500)).all()
    )
    query_vector = embed_text(query)
    ranked: list[RetrievalMatch] = []
    for item in candidates:
        embedding = ensure_item_embedding(session, item)
        keyword_score, keyword_reasons = keyword_score_fn(query, item)
        semantic_score = cosine_similarity(query_vector, embedding.vector_json)
        if keyword_score <= 0 and semantic_score < 0.12:
            continue
        quality = max(0, min(int(item.quality_score or 0), 100))
        combined = round(
            min(keyword_score, 100) * 0.46
            + max(semantic_score, 0.0) * 100 * 0.44
            + quality * 0.10
        )
        reasons = list(keyword_reasons)
        if semantic_score >= 0.12:
            reasons.append(f"semantic:{semantic_score:.2f}")
        reasons.append(f"quality:{quality}")
        ranked.append(
            RetrievalMatch(
                item=item,
                score=max(0, min(combined, 100)),
                keyword_score=min(keyword_score, 100),
                semantic_score=round(semantic_score, 4),
                quality_score=quality,
                reasons=dedupe(reasons),
                snippet=build_evidence_snippet(query, item),
                citation=f"[KB-{item.id}]",
            )
        )
    ranked.sort(
        key=lambda match: (match.score, match.semantic_score, match.item.updated_at),
        reverse=True,
    )
    return len(candidates), ranked[:limit]


def ensure_item_embedding(session: Any, item: KnowledgeItem) -> KnowledgeEmbedding:
    content_hash = item_content_hash(item)
    embedding = session.exec(
        select(KnowledgeEmbedding).where(
            KnowledgeEmbedding.tenant_id == item.tenant_id,
            KnowledgeEmbedding.item_id == item.id,
        )
    ).first()
    if embedding is not None and embedding.content_hash == content_hash and embedding.model == EMBEDDING_MODEL:
        return embedding
    vector = embed_text(item_embedding_text(item))
    if embedding is None:
        embedding = KnowledgeEmbedding(
            tenant_id=item.tenant_id,
            item_id=item.id or 0,
            model=EMBEDDING_MODEL,
            dimensions=EMBEDDING_DIMENSIONS,
            vector_json=vector,
            content_hash=content_hash,
        )
    else:
        embedding.model = EMBEDDING_MODEL
        embedding.dimensions = EMBEDDING_DIMENSIONS
        embedding.vector_json = vector
        embedding.content_hash = content_hash
        embedding.updated_at = utc_now()
    session.add(embedding)
    session.flush()
    return embedding


def rebuild_embeddings(session: Any, tenant_id: int) -> dict[str, Any]:
    items = list(session.exec(select(KnowledgeItem).where(KnowledgeItem.tenant_id == tenant_id)).all())
    for item in items:
        ensure_item_embedding(session, item)
    return {
        "model": EMBEDDING_MODEL,
        "dimensions": EMBEDDING_DIMENSIONS,
        "indexed_items": len(items),
    }


def embed_text(text: str) -> list[float]:
    vector = [0.0] * EMBEDDING_DIMENSIONS
    for feature, weight in text_features(text):
        digest = hashlib.sha256(feature.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % EMBEDDING_DIMENSIONS
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[index] += sign * weight
    norm = math.sqrt(sum(value * value for value in vector))
    if norm:
        return [round(value / norm, 8) for value in vector]
    return vector


def text_features(text: str) -> list[tuple[str, float]]:
    normalized = normalize_text(text)
    features: list[tuple[str, float]] = []
    words = re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]+", normalized)
    for word in words:
        if re.fullmatch(r"[\u4e00-\u9fff]+", word):
            features.extend((f"c2:{word[index:index + 2]}", 1.0) for index in range(max(len(word) - 1, 0)))
            features.extend((f"c3:{word[index:index + 3]}", 1.2) for index in range(max(len(word) - 2, 0)))
        elif len(word) > 1:
            features.append((f"word:{word}", 1.4))
    for group_index, group in enumerate(CONCEPT_GROUPS):
        matched = sum(1 for term in group if term in normalized)
        if matched:
            features.append((f"concept:{group_index}", 2.0 + min(matched, 3) * 0.5))
    return features


def build_evidence_snippet(query: str, item: KnowledgeItem, limit: int = 240) -> str:
    answer = (item.answer or "").strip()
    if not answer:
        return ""
    segments = [segment.strip() for segment in re.split(r"(?<=[。！？!?；;\n])", answer) if segment.strip()]
    query_features = {feature for feature, _ in text_features(query)}
    best_segment = answer
    best_score = -1
    for segment in segments:
        segment_features = {feature for feature, _ in text_features(segment)}
        score = len(query_features & segment_features)
        if score > best_score:
            best_score = score
            best_segment = segment
    if len(best_segment) <= limit:
        return best_segment
    return best_segment[: limit - 1].rstrip() + "…"


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    return sum(a * b for a, b in zip(left, right))


def item_content_hash(item: KnowledgeItem) -> str:
    return hashlib.sha256(item_embedding_text(item).encode("utf-8")).hexdigest()


def item_embedding_text(item: KnowledgeItem) -> str:
    return "\n".join((item.title or "", item.answer or "", item.category or ""))


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))
