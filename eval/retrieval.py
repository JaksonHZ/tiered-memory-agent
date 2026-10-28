"""Retrieval-only evaluation of strategy (b): does search put the expected item in its top k? No LLM involved.

uv run python eval/retrieval.py
"""

import json
import statistics
import time
from pathlib import Path

from tiered_memory_agent.search import MODEL, SemanticIndex

ROOT = Path(__file__).resolve().parents[1]
KS = (1, 3, 5, 10)


def load_questions() -> list[dict]:
    lines = (ROOT / "eval" / "questions.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def matches(result: dict, source: dict) -> bool:
    """A chunk cites the source when it is the same item or one of its incisos ("Art. 53, III" cites "Art. 53")."""
    return result["path"] == source["path"] and (result["item"] + ",").startswith(source["item"] + ",")


def main() -> None:
    questions = [q for q in load_questions() if q["answerable"]]
    index = SemanticIndex(ROOT / "semantic", cache_dir=ROOT / ".cache")
    index.search("aquecimento")  # load the model before timing

    any_rank, all_rank, latencies = [], [], []
    for q in questions:
        start = time.perf_counter()
        results = index.search(q["question"], k=max(KS))
        latencies.append(time.perf_counter() - start)
        # rank at which the first source shows up, and at which all of them have
        ranks = [next((n for n, r in enumerate(results, 1) if matches(r, s)), None) for s in q["sources"]]
        found = [r for r in ranks if r]
        any_rank.append(min(found) if found else None)
        all_rank.append(max(ranks) if all(ranks) else None)

    print(f"{len(questions)} answerable questions, model {MODEL}\n")
    print("| k | any source in top k | all sources in top k |\n|---|---|---|")
    for k in KS:
        hit_any = sum(1 for r in any_rank if r and r <= k) / len(questions)
        hit_all = sum(1 for r in all_rank if r and r <= k) / len(questions)
        print(f"| {k} | {hit_any:.0%} | {hit_all:.0%} |")
    mrr = statistics.mean(1 / r if r else 0 for r in any_rank)
    print(f"\nMRR@{max(KS)}: {mrr:.3f} | median latency: {statistics.median(latencies) * 1000:.0f} ms")

    print("\nMissed at k=5:")
    for q, r in zip(questions, any_rank, strict=True):
        if not r or r > 5:
            print(f"- {q['id']} (rank {r}): {q['question']}")


if __name__ == "__main__":
    main()
