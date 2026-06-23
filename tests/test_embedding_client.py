"""LM Studio embedding model resolution."""

from __future__ import annotations

import pytest

from src.llm.embedding_client import _pick_embedding_model


def test_pick_embedding_model_exact_match() -> None:
    ids = ["text-embedding-nomic-embed-text-v1.5@q8_0"]
    assert _pick_embedding_model("text-embedding-nomic-embed-text-v1.5@q8_0", ids) == ids[0]


def test_pick_embedding_model_substring_match() -> None:
    ids = [
        "text-embedding-nomic-embed-text-v1.5@q8_0",
        "text-embedding-nomic-embed-text-v1.5@q4_k_m",
    ]
    assert _pick_embedding_model("nomic-embed-text", ids) == ids[0]


def test_pick_embedding_model_prefers_embedding_models() -> None:
    ids = ["llama-3.2-1b", "text-embedding-bge-small@q8_0"]
    assert _pick_embedding_model("bge", ids) == ids[1]
