"""Write the evaluation set into dataset/ for the Hugging Face Hub: the questions and the norm text they cite.

    uv run python scripts/export_dataset.py
    uv run hf upload <user>/<dataset> dataset/ --repo-type dataset

The corpus is the norms only: the consolidated notes.md files are left out, as they were in the evaluation runs.
"""

import json
import shutil
from pathlib import Path

from tiered_memory_agent.consolidate import NOTES
from tiered_memory_agent.search import chunk_tree

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "dataset"


def main() -> None:
    shutil.copy(ROOT / "eval" / "questions.jsonl", OUT / "questions.jsonl")
    corpus = [c for c in chunk_tree(ROOT / "semantic") if not c["path"].endswith(NOTES)]
    lines = "".join(json.dumps(c, ensure_ascii=False) + "\n" for c in corpus)
    (OUT / "corpus.jsonl").write_text(lines, encoding="utf-8")
    print(f"{len(corpus)} chunks -> dataset/corpus.jsonl")


if __name__ == "__main__":
    main()
