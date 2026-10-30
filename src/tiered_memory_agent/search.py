"""Strategy (b): embedding search over the semantic tree, one chunk per item of a norm.

uv run python -m tiered_memory_agent.search "como descongelar carne?"
"""

import hashlib
import re
import sys
from collections.abc import Callable
from functools import cache
from pathlib import Path

import numpy as np

MODEL = "intfloat/multilingual-e5-small"
# An article or numbered item opens a chunk; its incisos, alíneas and parágrafos become chunks of their own,
# cited as "Art. 53, III", and carry the caput along for context.
ITEM = re.compile(r"(Art\. \d+º?|\d+(?:\.\d+)+)\.?\s")
SUB = re.compile(r"([IVXL]+) - |([a-z])\) |(§ ?\d+º?)|(Parágrafo único)")

Encoder = Callable[[list[str]], np.ndarray]


def chunk_tree(semantic: Path) -> list[dict]:
    """Split every norm file under semantic/ into items: {"path", "item", "title", "context", "text"}."""
    chunks: list[dict] = []
    for path in sorted(semantic.rglob("*.md")):
        if path.name == "index.md":
            continue
        rel = path.relative_to(semantic.parent).as_posix()
        title, caput, current = "", None, None
        for para in path.read_text(encoding="utf-8").split("\n---\n", 1)[1].split("\n\n"):
            para = para.strip()
            if para.startswith("# "):
                title = para[2:]
            elif para.startswith("#"):  # section heading: what follows belongs to it until the next item
                caput = current = None
                heading = para.lstrip("# ")
            elif m := ITEM.match(para):
                caput = current = {"path": rel, "item": m.group(1), "title": title, "context": "", "text": para}
                chunks.append(current)
            elif (m := SUB.match(para)) and caput:
                label = next(g for g in m.groups() if g)
                current = {**caput, "item": f"{caput['item']}, {label}", "context": caput["text"], "text": para}
                chunks.append(current)
            elif current:
                current["text"] += "\n" + para
            elif para:  # text right under a heading, e.g. an annex
                current = {"path": rel, "item": heading, "title": title, "context": "", "text": para}
                chunks.append(current)
    return chunks


def normalize(item: str) -> str:
    return re.sub(r"[º°.\s]", "", item.lower())


def cites(citation: dict, source: dict) -> bool:
    """Same file, and one item contains the other: "Art. 53" and "Art. 53, III" cite each other."""
    a, b = normalize(citation["item"]) + ",", normalize(source["item"]) + ","
    return citation["path"].removeprefix("./") == source["path"] and (a.startswith(b) or b.startswith(a))


def e5_encode(texts: list[str]) -> np.ndarray:
    return _model().encode(texts, normalize_embeddings=True, batch_size=32, show_progress_bar=False)


@cache
def _model():
    from sentence_transformers import SentenceTransformer  # slow import, paid only when searching

    return SentenceTransformer(MODEL)


class SemanticIndex:
    def __init__(self, corpus: Path | list[dict], encode: Encoder = e5_encode, cache_dir: Path | None = None):
        """corpus: the semantic/ folder, or chunks already made."""
        self.encode = encode
        self.chunks = chunk_tree(corpus) if isinstance(corpus, Path) else corpus
        # e5 expects "passage: " and "query: " prefixes
        passages = [f"passage: {c['title']}\n{c['context']}\n{c['text']}" for c in self.chunks]
        key = hashlib.sha256("\0".join([MODEL, *passages]).encode()).hexdigest()[:16]
        cached = cache_dir / f"embeddings-{key}.npy" if cache_dir else None
        if cached and cached.exists():
            self.vectors = np.load(cached)
        else:
            self.vectors = np.asarray(encode(passages), dtype=np.float32)
            if cached:
                cached.parent.mkdir(parents=True, exist_ok=True)
                np.save(cached, self.vectors)

    def search(self, query: str, k: int = 5) -> list[dict]:
        scores = self.vectors @ np.asarray(self.encode([f"query: {query}"]), dtype=np.float32)[0]
        top = np.argsort(-scores)[:k]
        return [{**self.chunks[i], "score": float(scores[i])} for i in top]


def format_results(results: list[dict]) -> str:
    return "\n\n".join(
        f"[{n}] {r['path']} | {r['item']} | score {r['score']:.3f}\n"
        + (f"{r['context']}\n" if r["context"] else "")
        + r["text"]
        for n, r in enumerate(results, 1)
    )


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[2]
    index = SemanticIndex(root / "semantic", cache_dir=root / ".cache")
    print(format_results(index.search(" ".join(sys.argv[1:]))))
