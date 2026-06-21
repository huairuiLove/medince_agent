"""Paragraph-level RAG index for doctor Q&A on clinical reports."""
from __future__ import annotations

import math
import re
from collections import Counter

from src.schemas import ClinicalReport, ReportParagraph


def _tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[\u4e00-\u9fff]+|[a-zA-Z0-9_]+", text.lower())
    return [t for t in tokens if len(t) > 1]


def _tfidf_vector(tokens: list[str], df: Counter, n_docs: int) -> dict[str, float]:
    tf = Counter(tokens)
    vec: dict[str, float] = {}
    for term, count in tf.items():
        idf = math.log((n_docs + 1) / (df[term] + 1)) + 1.0
        vec[term] = (count / max(len(tokens), 1)) * idf
    return vec


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    keys = set(a) | set(b)
    dot = sum(a.get(k, 0) * b.get(k, 0) for k in keys)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


class ParagraphRAGIndex:
    def __init__(self, report: ClinicalReport) -> None:
        self.report = report
        self._paragraphs = report.paragraphs
        self._docs = [_tokenize(f"{p.title} {p.content}") for p in self._paragraphs]
        self._df: Counter = Counter()
        for doc in self._docs:
            self._df.update(set(doc))
        self._vectors = [_tfidf_vector(doc, self._df, max(len(self._docs), 1)) for doc in self._docs]

    def search(self, query: str, top_k: int = 3) -> list[tuple[ReportParagraph, float]]:
        q_vec = _tfidf_vector(_tokenize(query), self._df, max(len(self._docs), 1))
        scored: list[tuple[ReportParagraph, float]] = []
        for para, vec in zip(self._paragraphs, self._vectors):
            scored.append((para, _cosine(q_vec, vec)))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    def build_context(self, query: str, top_k: int = 3) -> str:
        hits = self.search(query, top_k=top_k)
        blocks: list[str] = []
        for para, score in hits:
            blocks.append(f"[{para.section}] {para.title} (相关度 {score:.2f})\n{para.content}")
        if self.report.supplements:
            blocks.append("--- 历史补充问答 ---")
            for sup in self.report.supplements[-5:]:
                blocks.append(f"Q: {sup.question}\nA: {sup.answer}")
        return "\n\n".join(blocks)
