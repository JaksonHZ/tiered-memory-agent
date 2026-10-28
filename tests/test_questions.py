import json
from pathlib import Path

from tiered_memory_agent.search import chunk_tree

REPO = Path(__file__).resolve().parents[1]
KEYS = {"id", "question", "answer", "sources", "answerable", "origin", "reviewed"}


def test_every_question_is_well_formed_and_cites_existing_items():
    items = {(c["path"], c["item"]) for c in chunk_tree(REPO / "semantic")}
    lines = (REPO / "eval" / "questions.jsonl").read_text(encoding="utf-8").splitlines()
    questions = [json.loads(line) for line in lines if line.strip()]

    assert len({q["id"] for q in questions}) == len(questions)
    for q in questions:
        assert set(q) == KEYS, q["id"]
        assert q["origin"] in {"llm", "manual"}, q["id"]
        assert bool(q["sources"]) == q["answerable"], q["id"]
        for source in q["sources"]:
            assert (source["path"], source["item"]) in items, (q["id"], source)
