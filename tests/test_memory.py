from pathlib import Path

from memory import SYNTHETIC, conversations, load_memory_questions, summarize

from tiered_memory_agent import server
from tiered_memory_agent.search import chunk_tree

REPO = Path(__file__).resolve().parents[1]


def test_conversations_hide_the_synthetic_mark(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "ROOT", tmp_path)
    path = server.remember("Pode recongelar", SYNTHETIC + "O gerente disse que pode.", "conversa sintética")

    assert conversations(tmp_path) == [
        {
            "path": path,
            "item": "Pode recongelar",
            "title": "Pode recongelar",
            "context": "",
            "text": "O gerente disse que pode.",
        }
    ]


def test_memory_questions_are_well_formed_and_cite_existing_items():
    items = {(c["path"], c["item"]) for c in chunk_tree(REPO / "semantic")}
    questions = load_memory_questions()

    assert len({q["id"] for q in questions}) == len(questions)
    for q in questions:
        assert q["kind"] in {"fact", "contradiction", "unsupported"}, q["id"]
        assert q["question"] and q["answer"], q["id"]
        assert q["answerable"] == (q["kind"] != "unsupported"), q["id"]
        for source in q["sources"]:
            assert (source["path"], source["item"]) in items, (q["id"], source)


def test_summarize_counts_right_facts_repeated_errors_and_cited_conversations():
    questions = {"f": {"kind": "fact"}, "e": {"kind": "contradiction"}}
    talk = [{"path": "episodic/x.md", "item": "x"}]

    def r(id, arm, verdict, citations=()):
        return {"id": id, "arm": arm, "verdict": verdict, "citations": list(citations)}

    records = [r("f", "episodic", "correct", talk), r("e", "episodic", "incorrect", talk), r("e", "mixed", None)]

    table = summarize(records, questions)

    assert table["episodic"] == {
        "facts right": (1, 1),
        "planted errors repeated": (1, 1),
        "cites a conversation": (2, 2),
    }
    assert table["mixed"]["planted errors repeated"] == (0, 0)  # not graded yet
