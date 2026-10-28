import re
import zlib

import numpy as np

from tiered_memory_agent import server
from tiered_memory_agent.search import SemanticIndex, chunk_tree

NORM = """---
norm: "Portaria X"
---

# Preparação — Portaria X

### Seção III Preparo

4.8.16 O resfriamento deve ser feito de 60ºC a 10ºC em até duas horas.

Art. 53. O descongelamento de alimentos deve ser efetuado:

I - Sob refrigeração, em temperatura inferior a 5ºC, ou em forno de micro-ondas;

continuação do inciso.

Parágrafo único. É vedado recongelar o produto.

## ANEXO II

Lista dos alimentos que causam alergias.

1. Trigo.
"""


def fake_encode(texts):
    """Bag of words hashed into 256 dimensions: similar wording, similar vector."""
    vectors = np.zeros((len(texts), 256), dtype=np.float32)
    for row, text in enumerate(texts):
        for word in re.findall(r"\w+", text.lower()):
            vectors[row, zlib.crc32(word.encode()) % 256] += 1
    return vectors / np.linalg.norm(vectors, axis=1, keepdims=True)


def write_tree(root):
    (root / "semantic" / "prep").mkdir(parents=True)
    (root / "semantic" / "prep" / "index.md").write_text("# Preparação")
    (root / "semantic" / "prep" / "norm.md").write_text(NORM)
    return root / "semantic"


def test_chunks_are_items_with_their_incisos_cited_apart(tmp_path):
    chunks = chunk_tree(write_tree(tmp_path))

    assert [c["item"] for c in chunks] == ["4.8.16", "Art. 53", "Art. 53, I", "Art. 53, Parágrafo único", "ANEXO II"]
    assert {c["path"] for c in chunks} == {"semantic/prep/norm.md"}
    inciso = chunks[2]
    assert inciso["context"].startswith("Art. 53.") and inciso["text"].endswith("continuação do inciso.")
    assert chunks[4]["text"] == "Lista dos alimentos que causam alergias.\n1. Trigo."


def test_search_ranks_by_similarity_and_reuses_the_cache(tmp_path):
    calls = []

    def counting_encode(texts):
        calls.append(len(texts))
        return fake_encode(texts)

    semantic = write_tree(tmp_path)
    index = SemanticIndex(semantic, encode=counting_encode, cache_dir=tmp_path / ".cache")
    top = index.search("posso recongelar o produto?", k=2)
    SemanticIndex(semantic, encode=counting_encode, cache_dir=tmp_path / ".cache")

    assert top[0]["item"] == "Art. 53, Parágrafo único" and len(top) == 2
    assert calls == [5, 1]  # passages encoded once, then only the query


def test_search_tool_formats_path_and_item(tmp_path, monkeypatch):
    index = SemanticIndex(write_tree(tmp_path), encode=fake_encode)
    monkeypatch.setattr(server, "_index", lambda root: index)

    result = server.search("resfriamento em duas horas", k=1)

    assert result.startswith("[1] semantic/prep/norm.md | 4.8.16 | score ")
