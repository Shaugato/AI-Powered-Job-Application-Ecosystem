from __future__ import annotations

import re
from typing import Any

from backend.app.core.config import get_settings

try:
    from sentence_transformers import CrossEncoder
except Exception:  # pragma: no cover
    CrossEncoder = None


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9+#.-]{3,}", str(text or "").lower()))


def _jaccard(left: str, right: str) -> float:
    a = _tokenize(left)
    b = _tokenize(right)
    if not a or not b:
        return 0.0
    return len(a & b) / max(len(a | b), 1)


class RerankerService:
    _model = None
    _model_name = None

    def __init__(self) -> None:
        self.settings = get_settings()

    def rerank(self, query: str, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not candidates:
            return []
        scores = self._cross_encoder_scores(query, candidates)
        if scores is None:
            scores = [self._fallback_score(query, candidate) for candidate in candidates]
        reranked: list[dict[str, Any]] = []
        for candidate, score in zip(candidates, scores):
            item = dict(candidate)
            item["rerank_score"] = round(float(score), 6)
            reranked.append(item)
        reranked.sort(key=lambda item: item.get("rerank_score", 0.0), reverse=True)
        return reranked

    def _cross_encoder_scores(self, query: str, candidates: list[dict[str, Any]]) -> list[float] | None:
        if CrossEncoder is None:
            return None
        try:
            model = self._get_model()
        except Exception:
            return None
        if model is None:
            return None
        pairs = [(query, str(candidate.get("text") or "")) for candidate in candidates]
        try:
            values = model.predict(pairs, show_progress_bar=False)
        except TypeError:
            values = model.predict(pairs)
        return [float(value) for value in values]

    def _get_model(self):
        if CrossEncoder is None:
            return None
        model_name = self.settings.reranker_model_name
        if self.__class__._model is not None and self.__class__._model_name == model_name:
            return self.__class__._model
        self.__class__._model = CrossEncoder(model_name)
        self.__class__._model_name = model_name
        return self.__class__._model

    def _fallback_score(self, query: str, candidate: dict[str, Any]) -> float:
        dense = float(candidate.get("dense_score") or 0.0)
        lexical = _jaccard(query, str(candidate.get("text") or ""))
        keyword_overlap = _jaccard(" ".join(candidate.get("keywords") or []), query)
        return 0.55 * dense + 0.3 * lexical + 0.15 * keyword_overlap
